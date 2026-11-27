# Code Review Context

## 1. Git Diff (What Changed)

<diff>
diff --git a/src/sentry/integrations/github/integration.py b/src/sentry/integrations/github/integration.py
index 2e157a0..fa535e4 100644
--- a/src/sentry/integrations/github/integration.py
+++ b/src/sentry/integrations/github/integration.py
@@ -4,8 +4,10 @@ import logging
 import re
 from collections.abc import Collection, Mapping, Sequence
 from typing import Any
+from urllib.parse import parse_qsl
 
 from django.http import HttpResponse
+from django.urls import reverse
 from django.utils.text import slugify
 from django.utils.translation import gettext_lazy as _
 from rest_framework.request import Request
@@ -13,6 +15,8 @@ from rest_framework.request import Request
 from sentry import features, options
 from sentry.api.utils import generate_organization_url
 from sentry.constants import ObjectStatus
+from sentry.http import safe_urlopen, safe_urlread
+from sentry.identity.github import GitHubIdentityProvider, get_user_info
 from sentry.integrations import (
     FeatureDescription,
     IntegrationFeatures,
@@ -35,6 +39,7 @@ from sentry.tasks.integrations import migrate_repo
 from sentry.tasks.integrations.github.constants import RATE_LIMITED_MESSAGE
 from sentry.tasks.integrations.link_all_repos import link_all_repos
 from sentry.utils import metrics
+from sentry.utils.http import absolute_uri
 from sentry.web.helpers import render_to_response
 
 from .client import GitHubAppsClient, GitHubClientMixin
@@ -108,6 +113,9 @@ API_ERRORS = {
 ERR_INTEGRATION_EXISTS_ON_ANOTHER_ORG = _(
     "It seems that your GitHub account has been installed on another Sentry organization. Please uninstall and try again."
 )
+ERR_INTEGRATION_INVALID_INSTALLATION_REQUEST = _(
+    "We could not verify the authenticity of the installation request. We recommend restarting the installation process."
+)
 ERR_INTEGRATION_PENDING_DELETION = _(
     "It seems that your Sentry organization has an installation pending deletion. Please wait ~15min for the uninstall to complete and try again."
 )
@@ -118,6 +126,32 @@ def build_repository_query(metadata: Mapping[str, Any], name: str, query: str) -
     return f"{account_type}:{name} {query}".encode()
 
 
+def error(
+    request,
+    org,
+    error_short="Invalid installation request.",
+    error_long=ERR_INTEGRATION_INVALID_INSTALLATION_REQUEST,
+):
+    return render_to_response(
+        "sentry/integrations/github-integration-failed.html",
+        context={
+            "error": error_long,
+            "payload": {
+                "success": False,
+                "data": {"error": _(error_short)},
+            },
+            "document_origin": get_document_origin(org),
+        },
+        request=request,
+    )
+
+
+def get_document_origin(org) -> str:
+    if org and features.has("organizations:customer-domains", org.organization):
+        return f'"{generate_organization_url(org.organization.slug)}"'
+    return "document.origin"
+
+
 # Github App docs and list of available endpoints
 # https://docs.github.com/en/rest/apps/installations
 # https://docs.github.com/en/rest/overview/endpoints-available-for-github-apps
@@ -307,7 +341,7 @@ class GitHubIntegrationProvider(IntegrationProvider):
         )
 
     def get_pipeline_views(self) -> Sequence[PipelineView]:
-        return [GitHubInstallation()]
+        return [OAuthLoginView(), GitHubInstallation()]
 
     def get_installation_info(self, installation_id: str) -> Mapping[str, Any]:
         client = self.get_client()
@@ -352,15 +386,72 @@ class GitHubIntegrationProvider(IntegrationProvider):
         )
 
 
+class OAuthLoginView(PipelineView):
+    def dispatch(self, request: Request, pipeline) -> HttpResponse:
+        self.determine_active_organization(request)
+
+        ghip = GitHubIdentityProvider()
+        github_client_id = ghip.get_oauth_client_id()
+        github_client_secret = ghip.get_oauth_client_secret()
+
+        installation_id = request.GET.get("installation_id")
+        if installation_id:
+            pipeline.bind_state("installation_id", installation_id)
+
+        if not request.GET.get("state"):
+            state = pipeline.signature
+
+            redirect_uri = absolute_uri(
+                reverse("sentry-extension-setup", kwargs={"provider_id": "github"})
+            )
+            return self.redirect(
+                f"{ghip.get_oauth_authorize_url()}?client_id={github_client_id}&state={state}&redirect_uri={redirect_uri}"
+            )
+
+        # At this point, we are past the GitHub "authorize" step
+        if request.GET.get("state") != pipeline.signature:
+            return error(request, self.active_organization)
+
+        # similar to OAuth2CallbackView.get_token_params
+        data = {
+            "code": request.GET.get("code"),
+            "client_id": github_client_id,
+            "client_secret": github_client_secret,
+        }
+
+        # similar to OAuth2CallbackView.exchange_token
+        req = safe_urlopen(url=ghip.get_oauth_access_token_url(), data=data)
+
+        try:
+            body = safe_urlread(req).decode("utf-8")
+            payload = dict(parse_qsl(body))
+        except Exception:
+            payload = {}
+
+        if "access_token" not in payload:
+            return error(request, self.active_organization)
+
+        authenticated_user_info = get_user_info(payload["access_token"])
+        if "login" not in authenticated_user_info:
+            return error(request, self.active_organization)
+
+        pipeline.bind_state("github_authenticated_user", authenticated_user_info["login"])
+        return pipeline.next_step()
+
+
 class GitHubInstallation(PipelineView):
     def get_app_url(self) -> str:
         name = options.get("github-app.name")
         return f"https://github.com/apps/{slugify(name)}"
 
     def dispatch(self, request: Request, pipeline: Pipeline) -> HttpResponse:
-        if "installation_id" not in request.GET:
+        installation_id = request.GET.get(
+            "installation_id", pipeline.fetch_state("installation_id")
+        )
+        if installation_id is None:
             return self.redirect(self.get_app_url())
 
+        pipeline.bind_state("installation_id", installation_id)
         self.determine_active_organization(request)
 
         integration_pending_deletion_exists = False
@@ -374,57 +465,43 @@ class GitHubInstallation(PipelineView):
             ).exists()
 
         if integration_pending_deletion_exists:
-            document_origin = "document.origin"
-            if self.active_organization and features.has(
-                "organizations:customer-domains", self.active_organization.organization
-            ):
-                document_origin = (
-                    f'"{generate_organization_url(self.active_organization.organization.slug)}"'
-                )
-            return render_to_response(
-                "sentry/integrations/github-integration-failed.html",
-                context={
-                    "error": ERR_INTEGRATION_PENDING_DELETION,
-                    "payload": {
-                        "success": False,
-                        "data": {"error": _("GitHub installation pending deletion.")},
-                    },
-                    "document_origin": document_origin,
-                },
-                request=request,
+            return error(
+                request,
+                self.active_organization,
+                error_short="GitHub installation pending deletion.",
+                error_long=ERR_INTEGRATION_PENDING_DELETION,
             )
 
         try:
             # We want to limit GitHub integrations to 1 organization
             installations_exist = OrganizationIntegration.objects.filter(
-                integration=Integration.objects.get(external_id=request.GET["installation_id"])
+                integration=Integration.objects.get(external_id=installation_id)
             ).exists()
 
         except Integration.DoesNotExist:
-            pipeline.bind_state("installation_id", request.GET["installation_id"])
             return pipeline.next_step()
 
         if installations_exist:
-            document_origin = "document.origin"
-            if self.active_organization and features.has(
-                "organizations:customer-domains", self.active_organization.organization
-            ):
-                document_origin = (
-                    f'"{generate_organization_url(self.active_organization.organization.slug)}"'
-                )
-            return render_to_response(
-                "sentry/integrations/github-integration-failed.html",
-                context={
-                    "error": ERR_INTEGRATION_EXISTS_ON_ANOTHER_ORG,
-                    "payload": {
-                        "success": False,
-                        "data": {"error": _("Github installed on another Sentry organization.")},
-                    },
-                    "document_origin": document_origin,
-                },
-                request=request,
+            return error(
+                request,
+                self.active_organization,
+                error_short="Github installed on another Sentry organization.",
+                error_long=ERR_INTEGRATION_EXISTS_ON_ANOTHER_ORG,
             )
 
         # OrganizationIntegration does not exist, but Integration does exist.
-        pipeline.bind_state("installation_id", request.GET["installation_id"])
+        try:
+            integration = Integration.objects.get(
+                external_id=installation_id, status=ObjectStatus.ACTIVE
+            )
+        except Integration.DoesNotExist:
+            return error(request, self.active_organization)
+
+        # Check that the authenticated GitHub user is the same as who installed the app.
+        if (
+            pipeline.fetch_state("github_authenticated_user")
+            != integration.metadata["sender"]["login"]
+        ):
+            return error(request, self.active_organization)
+
         return pipeline.next_step()
diff --git a/src/sentry/web/frontend/pipeline_advancer.py b/src/sentry/web/frontend/pipeline_advancer.py
index 63183a4..cfe9792 100644
--- a/src/sentry/web/frontend/pipeline_advancer.py
+++ b/src/sentry/web/frontend/pipeline_advancer.py
@@ -16,12 +16,6 @@ from sentry.web.frontend.base import BaseView
 PIPELINE_CLASSES = [IntegrationPipeline, IdentityProviderPipeline]
 
 
-# GitHub apps may be installed directly from GitHub, in which case
-# they will redirect here *without* being in the pipeline. If that happens
-# redirect to the integration install org picker.
-FORWARD_INSTALL_FOR = ["github"]
-
-
 from rest_framework.request import Request
 
 
@@ -40,8 +34,11 @@ class PipelineAdvancerView(BaseView):
             if pipeline:
                 break
 
+        # GitHub apps may be installed directly from GitHub, in which case
+        # they will redirect here *without* being in the pipeline. If that happens
+        # redirect to the integration install org picker.
         if (
-            provider_id in FORWARD_INSTALL_FOR
+            provider_id == "github"
             and request.GET.get("setup_action") == "install"
             and pipeline is None
         ):
diff --git a/tests/sentry/integrations/github/test_integration.py b/tests/sentry/integrations/github/test_integration.py
index c6417da..895219d 100644
--- a/tests/sentry/integrations/github/test_integration.py
+++ b/tests/sentry/integrations/github/test_integration.py
@@ -12,6 +12,7 @@ import responses
 from django.urls import reverse
 
 import sentry
+from fixtures.github import INSTALLATION_EVENT_EXAMPLE
 from sentry.api.utils import generate_organization_url
 from sentry.constants import ObjectStatus
 from sentry.integrations.github import (
@@ -32,6 +33,7 @@ from sentry.shared_integrations.exceptions import ApiError
 from sentry.silo.base import SiloMode
 from sentry.testutils.cases import IntegrationTestCase
 from sentry.testutils.silo import assume_test_silo_mode, control_silo_test
+from sentry.utils import json
 from sentry.utils.cache import cache
 
 TREE_RESPONSES = {
@@ -111,6 +113,15 @@ class GitHubIntegrationTest(IntegrationTestCase):
         self.gh_org = "Test-Organization"
         pp = 1
 
+        access_token = "xxxxx-xxxxxxxxx-xxxxxxxxxx-xxxxxxxxxxxx"
+        responses.add(
+            responses.POST,
+            "https://github.com/login/oauth/access_token",
+            body=f"access_token={access_token}",
+        )
+
+        responses.add(responses.GET, self.base_url + "/user", json={"login": "octocat"})
+
         responses.add(
             responses.POST,
             self.base_url + f"/app/installations/{self.installation_id}/access_tokens",
@@ -218,6 +229,24 @@ class GitHubIntegrationTest(IntegrationTestCase):
         redirect = urlparse(resp["Location"])
         assert redirect.scheme == "https"
         assert redirect.netloc == "github.com"
+        assert redirect.path == "/login/oauth/authorize"
+        assert (
+            redirect.query
+            == "client_id=github-client-id&state=9cae5e88803f35ed7970fc131e6e65d3&redirect_uri=http://testserver/extensions/github/setup/"
+        )
+
+        resp = self.client.get(
+            "{}?{}".format(
+                self.setup_path,
+                urlencode(
+                    {"code": "12345678901234567890", "state": "9cae5e88803f35ed7970fc131e6e65d3"}
+                ),
+            )
+        )
+        assert resp.status_code == 302
+        redirect = urlparse(resp["Location"])
+        assert redirect.scheme == "https"
+        assert redirect.netloc == "github.com"
         assert redirect.path == "/apps/sentry-test-app"
 
         # App installation ID is provided
@@ -225,7 +254,7 @@ class GitHubIntegrationTest(IntegrationTestCase):
             "{}?{}".format(self.setup_path, urlencode({"installation_id": self.installation_id}))
         )
 
-        auth_header = responses.calls[0].request.headers["Authorization"]
+        auth_header = responses.calls[2].request.headers["Authorization"]
         assert auth_header == "Bearer jwt_token_1"
 
         self.assertDialogSuccess(resp)
@@ -303,8 +332,15 @@ class GitHubIntegrationTest(IntegrationTestCase):
             ),
             urlencode({"installation_id": self.installation_id}),
         )
+        self.setup_path_2 = "{}?{}".format(
+            self.setup_path,
+            urlencode(
+                {"code": "12345678901234567890", "state": "9cae5e88803f35ed7970fc131e6e65d3"}
+            ),
+        )
         with self.feature({"organizations:customer-domains": [self.organization_2.slug]}):
             resp = self.client.get(self.init_path_2)
+            resp = self.client.get(self.setup_path_2)
             self.assertTemplateUsed(resp, "sentry/integrations/github-integration-failed.html")
             assert (
                 b'{"success":false,"data":{"error":"Github installed on another Sentry organization."}}'
@@ -330,6 +366,8 @@ class GitHubIntegrationTest(IntegrationTestCase):
 
         # Try again and should be successful
         resp = self.client.get(self.init_path_2)
+        resp = self.client.get(self.setup_path_2)
+
         self.assertDialogSuccess(resp)
         integration = Integration.objects.get(external_id=self.installation_id)
         assert integration.provider == "github"
@@ -347,7 +385,73 @@ class GitHubIntegrationTest(IntegrationTestCase):
         resp = self.client.get(
             "{}?{}".format(self.setup_path, urlencode({"installation_id": self.installation_id}))
         )
-        assert b"The GitHub installation could not be found." in resp.content
+        resp = self.client.get(
+            "{}?{}".format(
+                self.setup_path,
+                urlencode(
+                    {"code": "12345678901234567890", "state": "ddd023d87a913d5226e2a882c4c4cc05"}
+                ),
+            )
+        )
+        assert b"Invalid installation request." in resp.content
+
+    @responses.activate
+    def test_github_user_mismatch(self):
+        self._stub_github()
+
+        # Emulate GitHub installation
+        init_path_1 = "{}?{}".format(
+            reverse(
+                "sentry-organization-integrations-setup",
+                kwargs={
+                    "organization_slug": self.organization.slug,
+                    "provider_id": self.provider.key,
+                },
+            ),
+            urlencode({"installation_id": self.installation_id}),
+        )
+        self.client.get(init_path_1)
+
+        webhook_event = json.loads(INSTALLATION_EVENT_EXAMPLE)
+        webhook_event["installation"]["id"] = self.installation_id
+        webhook_event["sender"]["login"] = "attacker"
+        resp = self.client.post(
+            path="/extensions/github/webhook/",
+            data=json.dumps(webhook_event),
+            content_type="application/json",
+            HTTP_X_GITHUB_EVENT="installation",
+            HTTP_X_HUB_SIGNATURE="sha1=d184e6717f8bfbcc291ebc8c0756ee446c6c9486",
+            HTTP_X_GITHUB_DELIVERY="00000000-0000-4000-8000-1234567890ab",
+        )
+        assert resp.status_code == 204
+
+        # Validate the installation user
+        user_2 = self.create_user("foo@example.com")
+        org_2 = self.create_organization(name="Rowdy Tiger", owner=user_2)
+        self.login_as(user_2)
+        init_path_2 = "{}?{}".format(
+            reverse(
+                "sentry-organization-integrations-setup",
+                kwargs={
+                    "organization_slug": org_2.slug,
+                    "provider_id": self.provider.key,
+                },
+            ),
+            urlencode({"installation_id": self.installation_id}),
+        )
+        setup_path_2 = "{}?{}".format(
+            self.setup_path,
+            urlencode(
+                {"code": "12345678901234567890", "state": "9cae5e88803f35ed7970fc131e6e65d3"}
+            ),
+        )
+        with self.feature({"organizations:customer-domains": [org_2.slug]}):
+            resp = self.client.get(init_path_2)
+            resp = self.client.get(setup_path_2)
+            self.assertTemplateUsed(resp, "sentry/integrations/github-integration-failed.html")
+            assert resp.status_code == 200
+            assert b'window.opener.postMessage({"success":false' in resp.content
+            assert b"Invalid installation request." in resp.content
 
     @responses.activate
     def test_disable_plugin_when_fully_migrated(self):
@@ -594,6 +698,17 @@ class GitHubIntegrationTest(IntegrationTestCase):
             resp = self.client.get(
                 "{}?{}".format(self.init_path, urlencode({"installation_id": self.installation_id}))
             )
+            resp = self.client.get(
+                "{}?{}".format(
+                    self.setup_path,
+                    urlencode(
+                        {
+                            "code": "12345678901234567890",
+                            "state": "9cae5e88803f35ed7970fc131e6e65d3",
+                        }
+                    ),
+                )
+            )
 
         assert resp.status_code == 200
         self.assertTemplateUsed(resp, "sentry/integrations/github-integration-failed.html")
@@ -615,6 +730,14 @@ class GitHubIntegrationTest(IntegrationTestCase):
         resp = self.client.get(
             "{}?{}".format(self.init_path, urlencode({"installation_id": self.installation_id}))
         )
+        resp = self.client.get(
+            "{}?{}".format(
+                self.setup_path,
+                urlencode(
+                    {"code": "12345678901234567890", "state": "9cae5e88803f35ed7970fc131e6e65d3"}
+                ),
+            )
+        )
         self.assertDialogSuccess(resp)
         integration = Integration.objects.get(external_id=self.installation_id)
         assert integration.provider == "github"

</diff>

## 2. Changed Code (Modified Files with Context)

<file name="src/sentry/integrations/github/integration.py" lines="7-10" type="changed">
```python
   2  
   3  import logging
   4  import re
   5  from collections.abc import Collection, Mapping, Sequence
   6  from typing import Any
   7  from urllib.parse import parse_qsl
   8  
   9  from django.http import HttpResponse
  10  from django.urls import reverse
  11  from django.utils.text import slugify
  12  from django.utils.translation import gettext_lazy as _
  13  from rest_framework.request import Request
  14  
  15  from sentry import features, options
  16  from sentry.api.utils import generate_organization_url
  17  from sentry.constants import ObjectStatus
  18  from sentry.http import safe_urlopen, safe_urlread
```
</file>

<file name="src/sentry/integrations/github/integration.py" lines="18-19" type="changed">
```python
  11  from django.utils.text import slugify
  12  from django.utils.translation import gettext_lazy as _
  13  from rest_framework.request import Request
  14  
  15  from sentry import features, options
  16  from sentry.api.utils import generate_organization_url
  17  from sentry.constants import ObjectStatus
  18  from sentry.http import safe_urlopen, safe_urlread
  19  from sentry.identity.github import GitHubIdentityProvider, get_user_info
  20  from sentry.integrations import (
  21      FeatureDescription,
  22      IntegrationFeatures,
  23      IntegrationInstallation,
  24      IntegrationMetadata,
  25      IntegrationProvider,
  26  )
  27  from sentry.integrations.mixins import RepositoryMixin
```
</file>

<file name="src/sentry/integrations/github/integration.py" lines="42-42" type="changed">
```python
  34  from sentry.services.hybrid_cloud.organization import RpcOrganizationSummary, organization_service
  35  from sentry.services.hybrid_cloud.repository import RpcRepository, repository_service
  36  from sentry.shared_integrations.constants import ERR_INTERNAL, ERR_UNAUTHORIZED
  37  from sentry.shared_integrations.exceptions import ApiError, IntegrationError
  38  from sentry.tasks.integrations import migrate_repo
  39  from sentry.tasks.integrations.github.constants import RATE_LIMITED_MESSAGE
  40  from sentry.tasks.integrations.link_all_repos import link_all_repos
  41  from sentry.utils import metrics
  42  from sentry.utils.http import absolute_uri
  43  from sentry.web.helpers import render_to_response
  44  
  45  from .client import GitHubAppsClient, GitHubClientMixin
  46  from .issues import GitHubIssueBasic
  47  from .repository import GitHubRepositoryProvider
  48  
  49  logger = logging.getLogger("sentry.integrations.github")
  50  
```
</file>

<file name="src/sentry/integrations/github/integration.py" lines="116-118" type="changed">
```python
 109      " (https://github.com/settings/installations).",
 110      401: ERR_UNAUTHORIZED,
 111  }
 112  
 113  ERR_INTEGRATION_EXISTS_ON_ANOTHER_ORG = _(
 114      "It seems that your GitHub account has been installed on another Sentry organization. Please uninstall and try again."
 115  )
 116  ERR_INTEGRATION_INVALID_INSTALLATION_REQUEST = _(
 117      "We could not verify the authenticity of the installation request. We recommend restarting the installation process."
 118  )
 119  ERR_INTEGRATION_PENDING_DELETION = _(
 120      "It seems that your Sentry organization has an installation pending deletion. Please wait ~15min for the uninstall to complete and try again."
 121  )
 122  
 123  
 124  def build_repository_query(metadata: Mapping[str, Any], name: str, query: str) -> bytes:
 125      account_type = "user" if metadata["account_type"] == "User" else "org"
```
</file>

<file name="src/sentry/integrations/github/integration.py" lines="129-154" type="changed">
```python
 134  ):
 135      return render_to_response(
 136          "sentry/integrations/github-integration-failed.html",
 137          context={
 138              "error": error_long,
 139              "payload": {
 140                  "success": False,
 141                  "data": {"error": _(error_short)},
 142              },
 143              "document_origin": get_document_origin(org),
 144          },
 145          request=request,
 146      )
 147  
 148  
 149  def get_document_origin(org) -> str:
 150      if org and features.has("organizations:customer-domains", org.organization):
```
</file>

<file name="src/sentry/integrations/github/integration.py" lines="344-344" type="changed">
```python
 336              kwargs={
 337                  "integration_key": self.key,
 338                  "integration_id": integration.id,
 339                  "organization_id": organization.id,
 340              }
 341          )
 342  
 343      def get_pipeline_views(self) -> Sequence[PipelineView]:
 344          return [OAuthLoginView(), GitHubInstallation()]
 345  
 346      def get_installation_info(self, installation_id: str) -> Mapping[str, Any]:
 347          client = self.get_client()
 348          resp: Mapping[str, Any] = client.get(f"/app/installations/{installation_id}")
 349          return resp
 350  
 351      def build_integration(self, state: Mapping[str, str]) -> Mapping[str, Any]:
 352          try:
```
</file>

<file name="src/sentry/integrations/github/integration.py" lines="389-441" type="changed">
```python
 407              return self.redirect(
 408                  f"{ghip.get_oauth_authorize_url()}?client_id={github_client_id}&state={state}&redirect_uri={redirect_uri}"
 409              )
 410  
 411          # At this point, we are past the GitHub "authorize" step
 412          if request.GET.get("state") != pipeline.signature:
 413              return error(request, self.active_organization)
 414  
 415          # similar to OAuth2CallbackView.get_token_params
 416          data = {
 417              "code": request.GET.get("code"),
 418              "client_id": github_client_id,
 419              "client_secret": github_client_secret,
 420          }
 421  
 422          # similar to OAuth2CallbackView.exchange_token
 423          req = safe_urlopen(url=ghip.get_oauth_access_token_url(), data=data)
```
</file>

<file name="src/sentry/integrations/github/integration.py" lines="448-454" type="changed">
```python
 442  class GitHubInstallation(PipelineView):
 443      def get_app_url(self) -> str:
 444          name = options.get("github-app.name")
 445          return f"https://github.com/apps/{slugify(name)}"
 446  
 447      def dispatch(self, request: Request, pipeline: Pipeline) -> HttpResponse:
 448          installation_id = request.GET.get(
 449              "installation_id", pipeline.fetch_state("installation_id")
 450          )
 451          if installation_id is None:
 452              return self.redirect(self.get_app_url())
 453  
 454          pipeline.bind_state("installation_id", installation_id)
 455          self.determine_active_organization(request)
 456  
 457          integration_pending_deletion_exists = False
 458          if self.active_organization:
```
</file>

<file name="src/sentry/integrations/github/integration.py" lines="468-472" type="changed">
```python
 462                  integration__provider=GitHubIntegrationProvider.key,
 463                  organization_id=self.active_organization.organization.id,
 464                  status=ObjectStatus.PENDING_DELETION,
 465              ).exists()
 466  
 467          if integration_pending_deletion_exists:
 468              return error(
 469                  request,
 470                  self.active_organization,
 471                  error_short="GitHub installation pending deletion.",
 472                  error_long=ERR_INTEGRATION_PENDING_DELETION,
 473              )
 474  
 475          try:
 476              # We want to limit GitHub integrations to 1 organization
 477              installations_exist = OrganizationIntegration.objects.filter(
 478                  integration=Integration.objects.get(external_id=installation_id)
```
</file>

<file name="src/sentry/integrations/github/integration.py" lines="478-506" type="changed">
```python
 488                  error_short="Github installed on another Sentry organization.",
 489                  error_long=ERR_INTEGRATION_EXISTS_ON_ANOTHER_ORG,
 490              )
 491  
 492          # OrganizationIntegration does not exist, but Integration does exist.
 493          try:
 494              integration = Integration.objects.get(
 495                  external_id=installation_id, status=ObjectStatus.ACTIVE
 496              )
 497          except Integration.DoesNotExist:
 498              return error(request, self.active_organization)
 499  
 500          # Check that the authenticated GitHub user is the same as who installed the app.
 501          if (
 502              pipeline.fetch_state("github_authenticated_user")
 503              != integration.metadata["sender"]["login"]
 504          ):
```
</file>

<file name="src/sentry/web/frontend/pipeline_advancer.py" lines="18-18" type="changed">
```python
  10  from sentry.utils.http import absolute_uri, create_redirect_url
  11  from sentry.web.frontend.base import BaseView
  12  
  13  # The request doesn't contain the pipeline type (pipeline information is stored
  14  # in redis keyed by the pipeline name), so we try to construct multiple pipelines
  15  # and use whichever one works.
  16  PIPELINE_CLASSES = [IntegrationPipeline, IdentityProviderPipeline]
  17  
  18  
  19  from rest_framework.request import Request
  20  
  21  
  22  class PipelineAdvancerView(BaseView):
  23      """Gets the current pipeline from the request and executes the current step."""
  24  
  25      auth_required = False
  26  
```
</file>

<file name="src/sentry/web/frontend/pipeline_advancer.py" lines="37-41" type="changed">
```python
  31  
  32          for pipeline_cls in PIPELINE_CLASSES:
  33              pipeline = pipeline_cls.get_for_request(request=request)
  34              if pipeline:
  35                  break
  36  
  37          # GitHub apps may be installed directly from GitHub, in which case
  38          # they will redirect here *without* being in the pipeline. If that happens
  39          # redirect to the integration install org picker.
  40          if (
  41              provider_id == "github"
  42              and request.GET.get("setup_action") == "install"
  43              and pipeline is None
  44          ):
  45              installation_id = request.GET.get("installation_id")
  46              return self.redirect(
  47                  reverse("integration-installation", args=[provider_id, installation_id])
```
</file>

<file name="tests/sentry/integrations/github/test_integration.py" lines="15-15" type="changed">
```python
   7  from unittest.mock import patch
   8  from urllib.parse import urlencode, urlparse
   9  
  10  import pytest
  11  import responses
  12  from django.urls import reverse
  13  
  14  import sentry
  15  from fixtures.github import INSTALLATION_EVENT_EXAMPLE
  16  from sentry.api.utils import generate_organization_url
  17  from sentry.constants import ObjectStatus
  18  from sentry.integrations.github import (
  19      API_ERRORS,
  20      MINIMUM_REQUESTS,
  21      GitHubIntegrationProvider,
  22      client,
  23  )
```
</file>

<file name="tests/sentry/integrations/github/test_integration.py" lines="36-36" type="changed">
```python
  28  from sentry.models.project import Project
  29  from sentry.models.repository import Repository
  30  from sentry.plugins.base import plugins
  31  from sentry.plugins.bases.issue2 import IssueTrackingPlugin2
  32  from sentry.shared_integrations.exceptions import ApiError
  33  from sentry.silo.base import SiloMode
  34  from sentry.testutils.cases import IntegrationTestCase
  35  from sentry.testutils.silo import assume_test_silo_mode, control_silo_test
  36  from sentry.utils import json
  37  from sentry.utils.cache import cache
  38  
  39  TREE_RESPONSES = {
  40      "xyz": {"status_code": 200, "body": {"tree": [{"path": "src/xyz.py", "type": "blob"}]}},
  41      "foo": {
  42          "status_code": 200,
  43          "body": {
  44              # The latest sha for a specific branch
```
</file>

<file name="tests/sentry/integrations/github/test_integration.py" lines="116-124" type="changed">
```python
 112          """This stubs the calls related to a Github App"""
 113          self.gh_org = "Test-Organization"
 114          pp = 1
 115  
 116          access_token = "xxxxx-xxxxxxxxx-xxxxxxxxxx-xxxxxxxxxxxx"
 117          responses.add(
 118              responses.POST,
 119              "https://github.com/login/oauth/access_token",
 120              body=f"access_token={access_token}",
 121          )
 122  
 123          responses.add(responses.GET, self.base_url + "/user", json={"login": "octocat"})
 124  
 125          responses.add(
 126              responses.POST,
 127              self.base_url + f"/app/installations/{self.installation_id}/access_tokens",
 128              json={"token": self.access_token, "expires_at": self.expires_at},
```
</file>

<file name="tests/sentry/integrations/github/test_integration.py" lines="232-249" type="changed">
```python
 233          assert (
 234              redirect.query
 235              == "client_id=github-client-id&state=9cae5e88803f35ed7970fc131e6e65d3&redirect_uri=http://testserver/extensions/github/setup/"
 236          )
 237  
 238          resp = self.client.get(
 239              "{}?{}".format(
 240                  self.setup_path,
 241                  urlencode(
 242                      {"code": "12345678901234567890", "state": "9cae5e88803f35ed7970fc131e6e65d3"}
 243                  ),
 244              )
 245          )
 246          assert resp.status_code == 302
 247          redirect = urlparse(resp["Location"])
 248          assert redirect.scheme == "https"
 249          assert redirect.netloc == "github.com"
```
</file>

<file name="tests/sentry/integrations/github/test_integration.py" lines="257-257" type="changed">
```python
 249          assert redirect.netloc == "github.com"
 250          assert redirect.path == "/apps/sentry-test-app"
 251  
 252          # App installation ID is provided
 253          resp = self.client.get(
 254              "{}?{}".format(self.setup_path, urlencode({"installation_id": self.installation_id}))
 255          )
 256  
 257          auth_header = responses.calls[2].request.headers["Authorization"]
 258          assert auth_header == "Bearer jwt_token_1"
 259  
 260          self.assertDialogSuccess(resp)
 261          return resp
 262  
 263      @responses.activate
 264      def test_plugin_migration(self):
 265          with assume_test_silo_mode(SiloMode.REGION):
```
</file>

<file name="tests/sentry/integrations/github/test_integration.py" lines="335-343" type="changed">
```python
 330                      "provider_id": self.provider.key,
 331                  },
 332              ),
 333              urlencode({"installation_id": self.installation_id}),
 334          )
 335          self.setup_path_2 = "{}?{}".format(
 336              self.setup_path,
 337              urlencode(
 338                  {"code": "12345678901234567890", "state": "9cae5e88803f35ed7970fc131e6e65d3"}
 339              ),
 340          )
 341          with self.feature({"organizations:customer-domains": [self.organization_2.slug]}):
 342              resp = self.client.get(self.init_path_2)
 343              resp = self.client.get(self.setup_path_2)
 344              self.assertTemplateUsed(resp, "sentry/integrations/github-integration-failed.html")
 345              assert (
 346                  b'{"success":false,"data":{"error":"Github installed on another Sentry organization."}}'
```
</file>

<file name="tests/sentry/integrations/github/test_integration.py" lines="369-370" type="changed">
```python
 362              organization_id=self.organization.id, integration=integration
 363          ):
 364              oi.delete()
 365          integration.delete()
 366  
 367          # Try again and should be successful
 368          resp = self.client.get(self.init_path_2)
 369          resp = self.client.get(self.setup_path_2)
 370  
 371          self.assertDialogSuccess(resp)
 372          integration = Integration.objects.get(external_id=self.installation_id)
 373          assert integration.provider == "github"
 374          assert OrganizationIntegration.objects.filter(
 375              organization_id=self.organization_2.id, integration=integration
 376          ).exists()
 377  
 378      @responses.activate
```
</file>

<file name="tests/sentry/integrations/github/test_integration.py" lines="388-454" type="changed">
```python
 413          self.client.get(init_path_1)
 414  
 415          webhook_event = json.loads(INSTALLATION_EVENT_EXAMPLE)
 416          webhook_event["installation"]["id"] = self.installation_id
 417          webhook_event["sender"]["login"] = "attacker"
 418          resp = self.client.post(
 419              path="/extensions/github/webhook/",
 420              data=json.dumps(webhook_event),
 421              content_type="application/json",
 422              HTTP_X_GITHUB_EVENT="installation",
 423              HTTP_X_HUB_SIGNATURE="sha1=d184e6717f8bfbcc291ebc8c0756ee446c6c9486",
 424              HTTP_X_GITHUB_DELIVERY="00000000-0000-4000-8000-1234567890ab",
 425          )
 426          assert resp.status_code == 204
 427  
 428          # Validate the installation user
 429          user_2 = self.create_user("foo@example.com")
```
</file>

<file name="tests/sentry/integrations/github/test_integration.py" lines="701-711" type="changed">
```python
 698              resp = self.client.get(
 699                  "{}?{}".format(self.init_path, urlencode({"installation_id": self.installation_id}))
 700              )
 701              resp = self.client.get(
 702                  "{}?{}".format(
 703                      self.setup_path,
 704                      urlencode(
 705                          {
 706                              "code": "12345678901234567890",
 707                              "state": "9cae5e88803f35ed7970fc131e6e65d3",
 708                          }
 709                      ),
 710                  )
 711              )
 712  
 713          assert resp.status_code == 200
 714          self.assertTemplateUsed(resp, "sentry/integrations/github-integration-failed.html")
```
</file>

<file name="tests/sentry/integrations/github/test_integration.py" lines="733-740" type="changed">
```python
 729          # Try again and should be successful
 730          resp = self.client.get(
 731              "{}?{}".format(self.init_path, urlencode({"installation_id": self.installation_id}))
 732          )
 733          resp = self.client.get(
 734              "{}?{}".format(
 735                  self.setup_path,
 736                  urlencode(
 737                      {"code": "12345678901234567890", "state": "9cae5e88803f35ed7970fc131e6e65d3"}
 738                  ),
 739              )
 740          )
 741          self.assertDialogSuccess(resp)
 742          integration = Integration.objects.get(external_id=self.installation_id)
 743          assert integration.provider == "github"
 744          assert OrganizationIntegration.objects.filter(
 745              organization_id=self.organization.id, integration=integration
```
</file>

## 3. Impact Code (Contracts & Call Sites)

### CALLEES: Definitions that the changed code CALLS (check if changed code respects these contracts)
<callees>
None
</callees>

### CALLERS: Call sites that invoke the changed functions/classes (check if callers pass correct arguments)
<callers>
None
</callers>
