# Code Review Context

## 1. Git Diff (What Changed)

<diff>
diff --git a/src/sentry/integrations/mixins/issues.py b/src/sentry/integrations/mixins/issues.py
index 9a77dd4..044fabf 100644
--- a/src/sentry/integrations/mixins/issues.py
+++ b/src/sentry/integrations/mixins/issues.py
@@ -12,6 +12,7 @@ from typing import Any, ClassVar
 from sentry.eventstore.models import GroupEvent
 from sentry.integrations.base import IntegrationInstallation
 from sentry.integrations.models.external_issue import ExternalIssue
+from sentry.integrations.services.assignment_source import AssignmentSource
 from sentry.integrations.services.integration import integration_service
 from sentry.integrations.tasks.sync_status_inbound import (
     sync_status_inbound as sync_status_inbound_task,
@@ -62,7 +63,7 @@ class ResolveSyncAction(enum.Enum):
 
 
 class IssueBasicIntegration(IntegrationInstallation, ABC):
-    def should_sync(self, attribute):
+    def should_sync(self, attribute, sync_source: AssignmentSource | None = None):
         return False
 
     def get_group_title(self, group, event, **kwargs):
@@ -378,10 +379,17 @@ class IssueSyncIntegration(IssueBasicIntegration, ABC):
     outbound_assignee_key: ClassVar[str | None] = None
     inbound_assignee_key: ClassVar[str | None] = None
 
-    def should_sync(self, attribute: str) -> bool:
+    def should_sync(self, attribute: str, sync_source: AssignmentSource | None = None) -> bool:
         key = getattr(self, f"{attribute}_key", None)
         if key is None or self.org_integration is None:
             return False
+
+        # Check that the assignment source isn't this same integration in order to
+        # prevent sync-cycles from occurring. This should still allow other
+        # integrations to propagate changes outward.
+        if sync_source and sync_source.integration_id == self.org_integration.integration_id:
+            return False
+
         value: bool = self.org_integration.config.get(key, False)
         return value
 
@@ -400,7 +408,14 @@ class IssueSyncIntegration(IssueBasicIntegration, ABC):
         raise NotImplementedError
 
     @abstractmethod
-    def sync_status_outbound(self, external_issue, is_resolved, project_id, **kwargs):
+    def sync_status_outbound(
+        self,
+        external_issue,
+        is_resolved,
+        project_id,
+        assignment_source: AssignmentSource | None = None,
+        **kwargs,
+    ):
         """
         Propagate a sentry issue's status to a linked issue's status.
         """
diff --git a/src/sentry/integrations/services/assignment_source.py b/src/sentry/integrations/services/assignment_source.py
new file mode 100644
index 0000000..fbf4c85
--- /dev/null
+++ b/src/sentry/integrations/services/assignment_source.py
@@ -0,0 +1,35 @@
+from __future__ import annotations
+
+from dataclasses import asdict, dataclass
+from datetime import datetime
+from typing import TYPE_CHECKING, Any
+
+from django.utils import timezone
+
+if TYPE_CHECKING:
+    from sentry.integrations.models import Integration
+    from sentry.integrations.services.integration import RpcIntegration
+
+
+@dataclass(frozen=True)
+class AssignmentSource:
+    source_name: str
+    integration_id: int
+    queued: datetime = timezone.now()
+
+    @classmethod
+    def from_integration(cls, integration: Integration | RpcIntegration) -> AssignmentSource:
+        return AssignmentSource(
+            source_name=integration.name,
+            integration_id=integration.id,
+        )
+
+    def to_dict(self) -> dict[str, Any]:
+        return asdict(self)
+
+    @classmethod
+    def from_dict(cls, input_dict: dict[str, Any]) -> AssignmentSource | None:
+        try:
+            return cls(**input_dict)
+        except (ValueError, TypeError):
+            return None
diff --git a/src/sentry/integrations/tasks/sync_assignee_outbound.py b/src/sentry/integrations/tasks/sync_assignee_outbound.py
index 9b68da6..301e3c5 100644
--- a/src/sentry/integrations/tasks/sync_assignee_outbound.py
+++ b/src/sentry/integrations/tasks/sync_assignee_outbound.py
@@ -1,6 +1,9 @@
+from typing import Any
+
 from sentry import analytics, features
 from sentry.integrations.models.external_issue import ExternalIssue
 from sentry.integrations.models.integration import Integration
+from sentry.integrations.services.assignment_source import AssignmentSource
 from sentry.integrations.services.integration import integration_service
 from sentry.models.organization import Organization
 from sentry.silo.base import SiloMode
@@ -24,7 +27,12 @@ from sentry.users.services.user.service import user_service
         Organization.DoesNotExist,
     )
 )
-def sync_assignee_outbound(external_issue_id: int, user_id: int | None, assign: bool) -> None:
+def sync_assignee_outbound(
+    external_issue_id: int,
+    user_id: int | None,
+    assign: bool,
+    assignment_source_dict: dict[str, Any] | None = None,
+) -> None:
     # Sync Sentry assignee to an external issue.
     external_issue = ExternalIssue.objects.get(id=external_issue_id)
 
@@ -42,10 +50,15 @@ def sync_assignee_outbound(external_issue_id: int, user_id: int | None, assign:
     ):
         return
 
-    if installation.should_sync("outbound_assignee"):
+    parsed_assignment_source = (
+        AssignmentSource.from_dict(assignment_source_dict) if assignment_source_dict else None
+    )
+    if installation.should_sync("outbound_assignee", parsed_assignment_source):
         # Assume unassign if None.
         user = user_service.get_user(user_id) if user_id else None
-        installation.sync_assignee_outbound(external_issue, user, assign=assign)
+        installation.sync_assignee_outbound(
+            external_issue, user, assign=assign, assignment_source=parsed_assignment_source
+        )
         analytics.record(
             "integration.issue.assignee.synced",
             provider=integration.provider,
diff --git a/src/sentry/integrations/utils/sync.py b/src/sentry/integrations/utils/sync.py
index a97c6dd..e6a3a97 100644
--- a/src/sentry/integrations/utils/sync.py
+++ b/src/sentry/integrations/utils/sync.py
@@ -5,6 +5,7 @@ from collections.abc import Mapping, Sequence
 from typing import TYPE_CHECKING
 
 from sentry import features
+from sentry.integrations.services.assignment_source import AssignmentSource
 from sentry.integrations.services.integration import integration_service
 from sentry.integrations.tasks.sync_assignee_outbound import sync_assignee_outbound
 from sentry.models.group import Group
@@ -92,7 +93,11 @@ def sync_group_assignee_inbound(
 
     if not assign:
         for group in affected_groups:
-            GroupAssignee.objects.deassign(group)
+            GroupAssignee.objects.deassign(
+                group,
+                assignment_source=AssignmentSource.from_integration(integration),
+            )
+
         return affected_groups
 
     users = user_service.get_many_by_email(emails=[email], is_verified=True)
@@ -104,14 +109,23 @@ def sync_group_assignee_inbound(
         user_id = get_user_id(projects_by_user, group)
         user = users_by_id.get(user_id)
         if user:
-            GroupAssignee.objects.assign(group, user)
+            GroupAssignee.objects.assign(
+                group,
+                user,
+                assignment_source=AssignmentSource.from_integration(integration),
+            )
             groups_assigned.append(group)
         else:
             logger.info("assignee-not-found-inbound", extra=log_context)
     return groups_assigned
 
 
-def sync_group_assignee_outbound(group: Group, user_id: int | None, assign: bool = True) -> None:
+def sync_group_assignee_outbound(
+    group: Group,
+    user_id: int | None,
+    assign: bool = True,
+    assignment_source: AssignmentSource | None = None,
+) -> None:
     from sentry.models.grouplink import GroupLink
 
     external_issue_ids = GroupLink.objects.filter(
@@ -120,5 +134,12 @@ def sync_group_assignee_outbound(group: Group, user_id: int | None, assign: bool
 
     for external_issue_id in external_issue_ids:
         sync_assignee_outbound.apply_async(
-            kwargs={"external_issue_id": external_issue_id, "user_id": user_id, "assign": assign}
+            kwargs={
+                "external_issue_id": external_issue_id,
+                "user_id": user_id,
+                "assign": assign,
+                "assignment_source_dict": assignment_source.to_dict()
+                if assignment_source
+                else None,
+            }
         )
diff --git a/src/sentry/models/groupassignee.py b/src/sentry/models/groupassignee.py
index e3c979e..bdba29b 100644
--- a/src/sentry/models/groupassignee.py
+++ b/src/sentry/models/groupassignee.py
@@ -12,6 +12,7 @@ from sentry.backup.scopes import RelocationScope
 from sentry.db.models import FlexibleForeignKey, Model, region_silo_model, sane_repr
 from sentry.db.models.fields.hybrid_cloud_foreign_key import HybridCloudForeignKey
 from sentry.db.models.manager.base import BaseManager
+from sentry.integrations.services.assignment_source import AssignmentSource
 from sentry.models.grouphistory import GroupHistoryStatus, record_group_history
 from sentry.models.groupowner import GroupOwner
 from sentry.models.groupsubscription import GroupSubscription
@@ -134,6 +135,7 @@ class GroupAssigneeManager(BaseManager["GroupAssignee"]):
         create_only: bool = False,
         extra: dict[str, str] | None = None,
         force_autoassign: bool = False,
+        assignment_source: AssignmentSource | None = None,
     ):
         from sentry.integrations.utils import sync_group_assignee_outbound
         from sentry.models.activity import Activity
@@ -187,7 +189,9 @@ class GroupAssigneeManager(BaseManager["GroupAssignee"]):
             if assignee_type == "user" and features.has(
                 "organizations:integrations-issue-sync", group.organization, actor=acting_user
             ):
-                sync_group_assignee_outbound(group, assigned_to.id, assign=True)
+                sync_group_assignee_outbound(
+                    group, assigned_to.id, assign=True, assignment_source=assignment_source
+                )
 
             if not created:  # aka re-assignment
                 self.remove_old_assignees(group, assignee, assigned_to_id, assignee_type)
@@ -200,6 +204,7 @@ class GroupAssigneeManager(BaseManager["GroupAssignee"]):
         acting_user: User | RpcUser | None = None,
         assigned_to: Team | RpcUser | None = None,
         extra: dict[str, str] | None = None,
+        assignment_source: AssignmentSource | None = None,
     ) -> None:
         from sentry.integrations.utils import sync_group_assignee_outbound
         from sentry.models.activity import Activity
@@ -230,7 +235,9 @@ class GroupAssigneeManager(BaseManager["GroupAssignee"]):
             if features.has(
                 "organizations:integrations-issue-sync", group.organization, actor=acting_user
             ):
-                sync_group_assignee_outbound(group, None, assign=False)
+                sync_group_assignee_outbound(
+                    group, None, assign=False, assignment_source=assignment_source
+                )
 
             issue_unassigned.send_robust(
                 project=group.project, group=group, user=acting_user, sender=self.__class__
diff --git a/tests/sentry/integrations/services/test_assignment_source.py b/tests/sentry/integrations/services/test_assignment_source.py
new file mode 100644
index 0000000..d09364d
--- /dev/null
+++ b/tests/sentry/integrations/services/test_assignment_source.py
@@ -0,0 +1,38 @@
+from typing import Any
+
+from sentry.integrations.services.assignment_source import AssignmentSource
+from sentry.testutils.cases import TestCase
+
+
+class TestAssignmentSource(TestCase):
+    def test_from_dict_empty_array(self):
+        data: dict[str, Any] = {}
+        result = AssignmentSource.from_dict(data)
+        assert result is None
+
+    def test_from_dict_inalid_data(self):
+        data = {
+            "foo": "bar",
+        }
+
+        result = AssignmentSource.from_dict(data)
+        assert result is None
+
+    def test_from_dict_valid_data(self):
+        data = {"source_name": "foo-source", "integration_id": 123}
+
+        result = AssignmentSource.from_dict(data)
+        assert result is not None
+        assert result.source_name == "foo-source"
+        assert result.integration_id == 123
+
+    def test_to_dict(self):
+        source = AssignmentSource(
+            source_name="foo-source",
+            integration_id=123,
+        )
+
+        result = source.to_dict()
+        assert result.get("queued") is not None
+        assert result.get("source_name") == "foo-source"
+        assert result.get("integration_id") == 123
diff --git a/tests/sentry/models/test_groupassignee.py b/tests/sentry/models/test_groupassignee.py
index 640b2b4..6596e87 100644
--- a/tests/sentry/models/test_groupassignee.py
+++ b/tests/sentry/models/test_groupassignee.py
@@ -4,6 +4,7 @@ import pytest
 
 from sentry.integrations.example.integration import ExampleIntegration
 from sentry.integrations.models.external_issue import ExternalIssue
+from sentry.integrations.services.assignment_source import AssignmentSource
 from sentry.integrations.utils import sync_group_assignee_inbound
 from sentry.models.activity import Activity
 from sentry.models.groupassignee import GroupAssignee
@@ -148,12 +149,77 @@ class GroupAssigneeTestCase(TestCase):
 
         with self.feature({"organizations:integrations-issue-sync": True}):
             with self.tasks():
-                GroupAssignee.objects.assign(self.group, self.user)
+                GroupAssignee.objects.assign(
+                    self.group,
+                    self.user,
+                )
 
                 mock_sync_assignee_outbound.assert_called_with(
-                    external_issue, user_service.get_user(self.user.id), assign=True
+                    external_issue,
+                    user_service.get_user(self.user.id),
+                    assign=True,
+                    assignment_source=None,
+                )
+
+                assert GroupAssignee.objects.filter(
+                    project=self.group.project,
+                    group=self.group,
+                    user_id=self.user.id,
+                    team__isnull=True,
+                ).exists()
+
+                activity = Activity.objects.get(
+                    project=self.group.project, group=self.group, type=ActivityType.ASSIGNED.value
+                )
+
+                assert activity.data["assignee"] == str(self.user.id)
+                assert activity.data["assigneeEmail"] == self.user.email
+                assert activity.data["assigneeType"] == "user"
+
+    @mock.patch.object(ExampleIntegration, "sync_assignee_outbound")
+    def test_assignee_sync_outbound_assign_with_matching_source_integration(
+        self, mock_sync_assignee_outbound
+    ):
+        group = self.group
+        integration = self.create_integration(
+            organization=group.organization,
+            external_id="123456",
+            provider="example",
+            oi_params={
+                "config": {
+                    "sync_comments": True,
+                    "sync_status_outbound": True,
+                    "sync_status_inbound": True,
+                    "sync_assignee_outbound": True,
+                    "sync_assignee_inbound": True,
+                }
+            },
+        )
+
+        external_issue = ExternalIssue.objects.create(
+            organization_id=group.organization.id, integration_id=integration.id, key="APP-123"
+        )
+
+        GroupLink.objects.create(
+            group_id=group.id,
+            project_id=group.project_id,
+            linked_type=GroupLink.LinkedType.issue,
+            linked_id=external_issue.id,
+            relationship=GroupLink.Relationship.references,
+        )
+
+        with self.feature({"organizations:integrations-issue-sync": True}):
+            with self.tasks():
+                # Assert that we don't perform an outbound assignment if
+                # the source of the assignment is the same target integration
+                GroupAssignee.objects.assign(
+                    self.group,
+                    self.user,
+                    assignment_source=AssignmentSource.from_integration(integration),
                 )
 
+                mock_sync_assignee_outbound.assert_not_called()
+
                 assert GroupAssignee.objects.filter(
                     project=self.group.project,
                     group=self.group,
@@ -205,7 +271,9 @@ class GroupAssigneeTestCase(TestCase):
         with self.feature({"organizations:integrations-issue-sync": True}):
             with self.tasks():
                 GroupAssignee.objects.deassign(self.group)
-                mock_sync_assignee_outbound.assert_called_with(external_issue, None, assign=False)
+                mock_sync_assignee_outbound.assert_called_with(
+                    external_issue, None, assign=False, assignment_source=None
+                )
 
                 assert not GroupAssignee.objects.filter(
                     project=self.group.project,

</diff>

## 2. Changed Code (Modified Files with Context)

<file name="src/sentry/integrations/mixins/issues.py" lines="15-15" type="changed">
```python
   7  from collections.abc import Mapping, Sequence
   8  from copy import deepcopy
   9  from operator import attrgetter
  10  from typing import Any, ClassVar
  11  
  12  from sentry.eventstore.models import GroupEvent
  13  from sentry.integrations.base import IntegrationInstallation
  14  from sentry.integrations.models.external_issue import ExternalIssue
  15  from sentry.integrations.services.assignment_source import AssignmentSource
  16  from sentry.integrations.services.integration import integration_service
  17  from sentry.integrations.tasks.sync_status_inbound import (
  18      sync_status_inbound as sync_status_inbound_task,
  19  )
  20  from sentry.integrations.utils import where_should_sync
  21  from sentry.issues.grouptype import GroupCategory
  22  from sentry.models.group import Group
  23  from sentry.models.grouplink import GroupLink
```
</file>

<file name="src/sentry/integrations/mixins/issues.py" lines="66-66" type="changed">
```python
  58  
  59          if should_unresolve:
  60              return ResolveSyncAction.UNRESOLVE
  61  
  62          return ResolveSyncAction.NOOP
  63  
  64  
  65  class IssueBasicIntegration(IntegrationInstallation, ABC):
  66      def should_sync(self, attribute, sync_source: AssignmentSource | None = None):
  67          return False
  68  
  69      def get_group_title(self, group, event, **kwargs):
  70          return get_notification_group_title(group, event, **kwargs)
  71  
  72      @abstractmethod
  73      def get_issue_url(self, key: str) -> str:
  74          """
```
</file>

<file name="src/sentry/integrations/mixins/issues.py" lines="382-392" type="changed">
```python
 381  
 382      def should_sync(self, attribute: str, sync_source: AssignmentSource | None = None) -> bool:
 383          key = getattr(self, f"{attribute}_key", None)
 384          if key is None or self.org_integration is None:
 385              return False
 386  
 387          # Check that the assignment source isn't this same integration in order to
 388          # prevent sync-cycles from occurring. This should still allow other
 389          # integrations to propagate changes outward.
 390          if sync_source and sync_source.integration_id == self.org_integration.integration_id:
 391              return False
 392  
 393          value: bool = self.org_integration.config.get(key, False)
 394          return value
 395  
 396      @abstractmethod
 397      def sync_assignee_outbound(
```
</file>

<file name="src/sentry/integrations/mixins/issues.py" lines="411-418" type="changed">
```python
 407          """
 408          raise NotImplementedError
 409  
 410      @abstractmethod
 411      def sync_status_outbound(
 412          self,
 413          external_issue,
 414          is_resolved,
 415          project_id,
 416          assignment_source: AssignmentSource | None = None,
 417          **kwargs,
 418      ):
 419          """
 420          Propagate a sentry issue's status to a linked issue's status.
 421          """
 422          raise NotImplementedError
 423  
```
</file>

<file name="src/sentry/integrations/services/assignment_source.py" lines="1-35" type="changed">
```python
  10      from sentry.integrations.models import Integration
  11      from sentry.integrations.services.integration import RpcIntegration
  12  
  13  
  14  @dataclass(frozen=True)
  15  class AssignmentSource:
  16      source_name: str
  17      integration_id: int
  18      queued: datetime = timezone.now()
  19  
  20      @classmethod
  21      def from_integration(cls, integration: Integration | RpcIntegration) -> AssignmentSource:
  22          return AssignmentSource(
  23              source_name=integration.name,
  24              integration_id=integration.id,
  25          )
  26  
```
</file>

<file name="src/sentry/integrations/tasks/sync_assignee_outbound.py" lines="1-6" type="changed">
```python
   1  from typing import Any
   2  
   3  from sentry import analytics, features
   4  from sentry.integrations.models.external_issue import ExternalIssue
   5  from sentry.integrations.models.integration import Integration
   6  from sentry.integrations.services.assignment_source import AssignmentSource
   7  from sentry.integrations.services.integration import integration_service
   8  from sentry.models.organization import Organization
   9  from sentry.silo.base import SiloMode
  10  from sentry.tasks.base import instrumented_task, retry
```
</file>

<file name="src/sentry/integrations/tasks/sync_assignee_outbound.py" lines="30-35" type="changed">
```python
  25          Integration.DoesNotExist,
  26          User.DoesNotExist,
  27          Organization.DoesNotExist,
  28      )
  29  )
  30  def sync_assignee_outbound(
  31      external_issue_id: int,
  32      user_id: int | None,
  33      assign: bool,
  34      assignment_source_dict: dict[str, Any] | None = None,
  35  ) -> None:
  36      # Sync Sentry assignee to an external issue.
  37      external_issue = ExternalIssue.objects.get(id=external_issue_id)
  38  
  39      organization = Organization.objects.get(id=external_issue.organization_id)
  40      has_issue_sync = features.has("organizations:integrations-issue-sync", organization)
  41      if not has_issue_sync:
```
</file>

<file name="src/sentry/integrations/tasks/sync_assignee_outbound.py" lines="53-61" type="changed">
```python
  48      if not (
  49          hasattr(installation, "should_sync") and hasattr(installation, "sync_assignee_outbound")
  50      ):
  51          return
  52  
  53      parsed_assignment_source = (
  54          AssignmentSource.from_dict(assignment_source_dict) if assignment_source_dict else None
  55      )
  56      if installation.should_sync("outbound_assignee", parsed_assignment_source):
  57          # Assume unassign if None.
  58          user = user_service.get_user(user_id) if user_id else None
  59          installation.sync_assignee_outbound(
  60              external_issue, user, assign=assign, assignment_source=parsed_assignment_source
  61          )
  62          analytics.record(
  63              "integration.issue.assignee.synced",
  64              provider=integration.provider,
```
</file>

<file name="src/sentry/integrations/utils/sync.py" lines="8-8" type="changed">
```python
   1  from __future__ import annotations
   2  
   3  import logging
   4  from collections.abc import Mapping, Sequence
   5  from typing import TYPE_CHECKING
   6  
   7  from sentry import features
   8  from sentry.integrations.services.assignment_source import AssignmentSource
   9  from sentry.integrations.services.integration import integration_service
  10  from sentry.integrations.tasks.sync_assignee_outbound import sync_assignee_outbound
  11  from sentry.models.group import Group
  12  from sentry.models.groupassignee import GroupAssignee
  13  from sentry.models.organization import Organization
  14  from sentry.models.project import Project
  15  from sentry.silo.base import region_silo_function
  16  from sentry.users.services.user.service import user_service
```
</file>

<file name="src/sentry/integrations/utils/sync.py" lines="96-100" type="changed">
```python
  90      if not affected_groups:
  91          logger.info("no-affected-groups", extra=log_context)
  92          return []
  93  
  94      if not assign:
  95          for group in affected_groups:
  96              GroupAssignee.objects.deassign(
  97                  group,
  98                  assignment_source=AssignmentSource.from_integration(integration),
  99              )
 100  
 101          return affected_groups
 102  
 103      users = user_service.get_many_by_email(emails=[email], is_verified=True)
 104      users_by_id = {user.id: user for user in users}
 105      projects_by_user = Project.objects.get_by_users(users)
 106  
```
</file>

<file name="src/sentry/integrations/utils/sync.py" lines="112-116" type="changed">
```python
 106  
 107      groups_assigned = []
 108      for group in affected_groups:
 109          user_id = get_user_id(projects_by_user, group)
 110          user = users_by_id.get(user_id)
 111          if user:
 112              GroupAssignee.objects.assign(
 113                  group,
 114                  user,
 115                  assignment_source=AssignmentSource.from_integration(integration),
 116              )
 117              groups_assigned.append(group)
 118          else:
 119              logger.info("assignee-not-found-inbound", extra=log_context)
 120      return groups_assigned
 121  
 122  
```
</file>

<file name="src/sentry/integrations/utils/sync.py" lines="123-128" type="changed">
```python
 118          else:
 119              logger.info("assignee-not-found-inbound", extra=log_context)
 120      return groups_assigned
 121  
 122  
 123  def sync_group_assignee_outbound(
 124      group: Group,
 125      user_id: int | None,
 126      assign: bool = True,
 127      assignment_source: AssignmentSource | None = None,
 128  ) -> None:
 129      from sentry.models.grouplink import GroupLink
 130  
 131      external_issue_ids = GroupLink.objects.filter(
 132          project_id=group.project_id, group_id=group.id, linked_type=GroupLink.LinkedType.issue
 133      ).values_list("linked_id", flat=True)
 134  
```
</file>

<file name="src/sentry/integrations/utils/sync.py" lines="137-144" type="changed">
```python
 133      ).values_list("linked_id", flat=True)
 134  
 135      for external_issue_id in external_issue_ids:
 136          sync_assignee_outbound.apply_async(
 137              kwargs={
 138                  "external_issue_id": external_issue_id,
 139                  "user_id": user_id,
 140                  "assign": assign,
 141                  "assignment_source_dict": assignment_source.to_dict()
 142                  if assignment_source
 143                  else None,
 144              }
 145          )
```
</file>

<file name="src/sentry/models/groupassignee.py" lines="15-15" type="changed">
```python
   7  from django.db import models, router, transaction
   8  from django.utils import timezone
   9  
  10  from sentry import features
  11  from sentry.backup.scopes import RelocationScope
  12  from sentry.db.models import FlexibleForeignKey, Model, region_silo_model, sane_repr
  13  from sentry.db.models.fields.hybrid_cloud_foreign_key import HybridCloudForeignKey
  14  from sentry.db.models.manager.base import BaseManager
  15  from sentry.integrations.services.assignment_source import AssignmentSource
  16  from sentry.models.grouphistory import GroupHistoryStatus, record_group_history
  17  from sentry.models.groupowner import GroupOwner
  18  from sentry.models.groupsubscription import GroupSubscription
  19  from sentry.notifications.types import GroupSubscriptionReason
  20  from sentry.signals import issue_assigned, issue_unassigned
  21  from sentry.types.activity import ActivityType
  22  from sentry.types.actor import Actor, ActorType
  23  from sentry.utils import metrics
```
</file>

<file name="src/sentry/models/groupassignee.py" lines="138-138" type="changed">
```python
 130      def assign(
 131          self,
 132          group: Group,
 133          assigned_to: Team | RpcUser,
 134          acting_user: User | None = None,
 135          create_only: bool = False,
 136          extra: dict[str, str] | None = None,
 137          force_autoassign: bool = False,
 138          assignment_source: AssignmentSource | None = None,
 139      ):
 140          from sentry.integrations.utils import sync_group_assignee_outbound
 141          from sentry.models.activity import Activity
 142          from sentry.models.groupsubscription import GroupSubscription
 143  
 144          GroupSubscription.objects.subscribe_actor(
 145              group=group, actor=assigned_to, reason=GroupSubscriptionReason.assigned
 146          )
```
</file>

<file name="src/sentry/models/groupassignee.py" lines="192-194" type="changed">
```python
 185              record_group_history(group, GroupHistoryStatus.ASSIGNED, actor=acting_user)
 186  
 187              metrics.incr("group.assignee.change", instance="assigned", skip_internal=True)
 188              # sync Sentry assignee to external issues
 189              if assignee_type == "user" and features.has(
 190                  "organizations:integrations-issue-sync", group.organization, actor=acting_user
 191              ):
 192                  sync_group_assignee_outbound(
 193                      group, assigned_to.id, assign=True, assignment_source=assignment_source
 194                  )
 195  
 196              if not created:  # aka re-assignment
 197                  self.remove_old_assignees(group, assignee, assigned_to_id, assignee_type)
 198  
 199          return {"new_assignment": created, "updated_assignment": bool(not created and affected)}
 200  
 201      def deassign(
```
</file>

<file name="src/sentry/models/groupassignee.py" lines="207-207" type="changed">
```python
 199          return {"new_assignment": created, "updated_assignment": bool(not created and affected)}
 200  
 201      def deassign(
 202          self,
 203          group: Group,
 204          acting_user: User | RpcUser | None = None,
 205          assigned_to: Team | RpcUser | None = None,
 206          extra: dict[str, str] | None = None,
 207          assignment_source: AssignmentSource | None = None,
 208      ) -> None:
 209          from sentry.integrations.utils import sync_group_assignee_outbound
 210          from sentry.models.activity import Activity
 211          from sentry.models.projectownership import ProjectOwnership
 212  
 213          try:
 214              previous_groupassignee = self.get(group=group)
 215          except GroupAssignee.DoesNotExist:
```
</file>

<file name="src/sentry/models/groupassignee.py" lines="238-240" type="changed">
```python
 231              GroupOwner.invalidate_debounce_issue_owners_evaluation_cache(group.project.id, group.id)
 232  
 233              metrics.incr("group.assignee.change", instance="deassigned", skip_internal=True)
 234              # sync Sentry assignee to external issues
 235              if features.has(
 236                  "organizations:integrations-issue-sync", group.organization, actor=acting_user
 237              ):
 238                  sync_group_assignee_outbound(
 239                      group, None, assign=False, assignment_source=assignment_source
 240                  )
 241  
 242              issue_unassigned.send_robust(
 243                  project=group.project, group=group, user=acting_user, sender=self.__class__
 244              )
 245              self.remove_old_assignees(group, previous_groupassignee)
 246  
 247  
```
</file>

<file name="tests/sentry/integrations/services/test_assignment_source.py" lines="1-38" type="changed">
```python
  12  
  13      def test_from_dict_inalid_data(self):
  14          data = {
  15              "foo": "bar",
  16          }
  17  
  18          result = AssignmentSource.from_dict(data)
  19          assert result is None
  20  
  21      def test_from_dict_valid_data(self):
  22          data = {"source_name": "foo-source", "integration_id": 123}
  23  
  24          result = AssignmentSource.from_dict(data)
  25          assert result is not None
  26          assert result.source_name == "foo-source"
  27          assert result.integration_id == 123
  28  
```
</file>

<file name="tests/sentry/models/test_groupassignee.py" lines="7-7" type="changed">
```python
   1  from unittest import mock
   2  
   3  import pytest
   4  
   5  from sentry.integrations.example.integration import ExampleIntegration
   6  from sentry.integrations.models.external_issue import ExternalIssue
   7  from sentry.integrations.services.assignment_source import AssignmentSource
   8  from sentry.integrations.utils import sync_group_assignee_inbound
   9  from sentry.models.activity import Activity
  10  from sentry.models.groupassignee import GroupAssignee
  11  from sentry.models.grouplink import GroupLink
  12  from sentry.testutils.cases import TestCase
  13  from sentry.testutils.skips import requires_snuba
  14  from sentry.types.activity import ActivityType
  15  from sentry.users.services.user.service import user_service
```
</file>

<file name="tests/sentry/models/test_groupassignee.py" lines="152-222" type="changed">
```python
 179      @mock.patch.object(ExampleIntegration, "sync_assignee_outbound")
 180      def test_assignee_sync_outbound_assign_with_matching_source_integration(
 181          self, mock_sync_assignee_outbound
 182      ):
 183          group = self.group
 184          integration = self.create_integration(
 185              organization=group.organization,
 186              external_id="123456",
 187              provider="example",
 188              oi_params={
 189                  "config": {
 190                      "sync_comments": True,
 191                      "sync_status_outbound": True,
 192                      "sync_status_inbound": True,
 193                      "sync_assignee_outbound": True,
 194                      "sync_assignee_inbound": True,
 195                  }
```
</file>

<file name="tests/sentry/models/test_groupassignee.py" lines="274-276" type="changed">
```python
 267          )
 268  
 269          GroupAssignee.objects.assign(self.group, self.user)
 270  
 271          with self.feature({"organizations:integrations-issue-sync": True}):
 272              with self.tasks():
 273                  GroupAssignee.objects.deassign(self.group)
 274                  mock_sync_assignee_outbound.assert_called_with(
 275                      external_issue, None, assign=False, assignment_source=None
 276                  )
 277  
 278                  assert not GroupAssignee.objects.filter(
 279                      project=self.group.project,
 280                      group=self.group,
 281                      user_id=self.user.id,
 282                      team__isnull=True,
 283                  ).exists()
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
