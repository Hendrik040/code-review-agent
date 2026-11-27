# fastapi#12

Commit message of the reviewed change: :sparkles: Add security checks for HTTP utils

Oracle (fix location at buggy_commit): [{'file': 'fastapi/security/http.py', 'line_start': 115, 'line_end': 118}]

## Reviewed diff (introducing commit)
```diff
diff --git a/fastapi/security/__init__.py b/fastapi/security/__init__.py
index 738cb8e5..5f2b38c2 100644
--- a/fastapi/security/__init__.py
+++ b/fastapi/security/__init__.py
@@ -1,4 +1,10 @@
 from .api_key import APIKeyQuery, APIKeyHeader, APIKeyCookie
-from .http import HTTPBasic, HTTPBearer, HTTPDigest
+from .http import (
+    HTTPBasic,
+    HTTPBearer,
+    HTTPDigest,
+    HTTPBasicCredentials,
+    HTTPAuthorizationCredentials,
+)
 from .oauth2 import OAuth2PasswordRequestForm, OAuth2, OAuth2PasswordBearer
 from .open_id_connect_url import OpenIdConnect
diff --git a/fastapi/security/http.py b/fastapi/security/http.py
index 287beee5..3e4aeb67 100644
--- a/fastapi/security/http.py
+++ b/fastapi/security/http.py
@@ -78,6 +78,11 @@ class HTTPBearer(HTTPBase):
             raise HTTPException(
                 status_code=HTTP_403_FORBIDDEN, detail="Not authenticated"
             )
+        if scheme.lower() != "bearer":
+            raise HTTPException(
+                status_code=HTTP_403_FORBIDDEN,
+                detail="Invalid authentication credentials",
+            )
         return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)
 
 
@@ -93,4 +98,9 @@ class HTTPDigest(HTTPBase):
             raise HTTPException(
                 status_code=HTTP_403_FORBIDDEN, detail="Not authenticated"
             )
+        if scheme.lower() != "digest":
+            raise HTTPException(
+                status_code=HTTP_403_FORBIDDEN,
+                detail="Invalid authentication credentials",
+            )
         return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)
diff --git a/tests/test_security_http_base.py b/tests/test_security_http_base.py
new file mode 100644
index 00000000..d37248e0
--- /dev/null
+++ b/tests/test_security_http_base.py
@@ -0,0 +1,56 @@
+from fastapi import FastAPI, Security
+from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBase
+from starlette.testclient import TestClient
+
+app = FastAPI()
+
+security = HTTPBase(scheme="Other")
+
+
+@app.get("/users/me")
+def read_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
+    return {"scheme": credentials.scheme, "credentials": credentials.credentials}
+
+
+client = TestClient(app)
+
+openapi_schema = {
+    "openapi": "3.0.2",
+    "info": {"title": "Fast API", "version": "0.1.0"},
+    "paths": {
+        "/users/me": {
+            "get": {
+                "responses": {
+                    "200": {
+                        "description": "Successful Response",
+                        "content": {"application/json": {"schema": {}}},
+                    }
+                },
+                "summary": "Read Current User Get",
+                "operationId": "read_current_user_users_me_get",
+                "security": [{"HTTPBase": []}],
+            }
+        }
+    },
+    "components": {
+        "securitySchemes": {"HTTPBase": {"type": "http", "scheme": "Other"}}
+    },
+}
+
+
+def test_openapi_schema():
+    response = client.get("/openapi.json")
+    assert response.status_code == 200
+    assert response.json() == openapi_schema
+
+
+def test_security_http_base():
+    response = client.get("/users/me", headers={"Authorization": "Other foobar"})
+    assert response.status_code == 200
+    assert response.json() == {"scheme": "Other", "credentials": "foobar"}
+
+
+def test_security_http_base_no_credentials():
+    response = client.get("/users/me")
+    assert response.status_code == 403
+    assert response.json() == {"detail": "Not authenticated"}
diff --git a/tests/test_security_http_basic.py b/tests/test_security_http_basic.py
new file mode 100644
index 00000000..c0c94dad
--- /dev/null
+++ b/tests/test_security_http_basic.py
@@ -0,0 +1,76 @@
+from base64 import b64encode
+
+from fastapi import FastAPI, Security
+from fastapi.security import HTTPBasic, HTTPBasicCredentials
+from requests.auth import HTTPBasicAuth
+from starlette.testclient import TestClient
+
+app = FastAPI()
+
+security = HTTPBasic()
+
+
+@app.get("/users/me")
+def read_current_user(credentials: HTTPBasicCredentials = Security(security)):
+    return {"username": credentials.username, "password": credentials.password}
+
+
+client = TestClient(app)
+
+openapi_schema = {
+    "openapi": "3.0.2",
+    "info": {"title": "Fast API", "version": "0.1.0"},
+    "paths": {
+        "/users/me": {
+            "get": {
+                "responses": {
+                    "200": {
+                        "description": "Successful Response",
+                        "content": {"application/json": {"schema": {}}},
+                    }
+                },
+                "summary": "Read Current User Get",
+                "operationId": "read_current_user_users_me_get",
+                "security": [{"HTTPBasic": []}],
+            }
+        }
+    },
+    "components": {
+        "securitySchemes": {"HTTPBasic": {"type": "http", "scheme": "basic"}}
+    },
+}
+
+
+def test_openapi_schema():
+    response = client.get("/openapi.json")
+    assert response.status_code == 200
+    assert response.json() == openapi_schema
+
+
+def test_security_http_basic():
+    auth = HTTPBasicAuth(username="john", password="secret")
+    response = client.get("/users/me", auth=auth)
+    assert response.status_code == 200
+    assert response.json() == {"username": "john", "password": "secret"}
+
+
+def test_security_http_basic_no_credentials():
+    response = client.get("/users/me")
+    assert response.status_code == 403
+    assert response.json() == {"detail": "Not authenticated"}
+
+
+def test_security_http_basic_invalid_credentials():
+    response = client.get(
+        "/users/me", headers={"Authorization": "Basic notabase64token"}
+    )
+    assert response.status_code == 403
+    assert response.json() == {"detail": "Invalid authentication credentials"}
+
+
+def test_security_http_basic_non_basic_credentials():
+    payload = b64encode(b"johnsecret").decode("ascii")
+    auth_header = f"Basic {payload}"
+    response = client.get("/users/me", headers={"Authorization": auth_header})
+    assert response.status_code == 403
+    assert response.json() == {"detail": "Invalid authentication credentials"}
diff --git a/tests/test_security_http_bearer.py b/tests/test_security_http_bearer.py
new file mode 100644
index 00000000..ad1bef38
--- /dev/null
+++ b/tests/test_security_http_bearer.py
@@ -0,0 +1,62 @@
+from fastapi import FastAPI, Security
+from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
+from starlette.testclient import TestClient
+
+app = FastAPI()
+
+security = HTTPBearer()
+
+
+@app.get("/users/me")
+def read_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
+    return {"scheme": credentials.scheme, "credentials": credentials.credentials}
+
+
+client = TestClient(app)
+
+openapi_schema = {
+    "openapi": "3.0.2",
+    "info": {"title": "Fast API", "version": "0.1.0"},
+    "paths": {
+        "/users/me": {
+            "get": {
+                "responses": {
+                    "200": {
+                        "description": "Successful Response",
+                        "content": {"application/json": {"schema": {}}},
+                    }
+                },
+                "summary": "Read Current User Get",
+                "operationId": "read_current_user_users_me_get",
+                "security": [{"HTTPBearer": []}],
+            }
+        }
+    },
+    "components": {
+        "securitySchemes": {"HTTPBearer": {"type": "http", "scheme": "bearer"}}
+    },
+}
+
+
+def test_openapi_schema():
+    response = client.get("/openapi.json")
+    assert response.status_code == 200
+    assert response.json() == openapi_schema
+
+
+def test_security_http_bearer():
+    response = client.get("/users/me", headers={"Authorization": "Bearer foobar"})
+    assert response.status_code == 200
+    assert response.json() == {"scheme": "Bearer", "credentials": "foobar"}
+
+
+def test_security_http_bearer_no_credentials():
+    response = client.get("/users/me")
+    assert response.status_code == 403
+    assert response.json() == {"detail": "Not authenticated"}
+
+
+def test_security_http_bearer_incorrect_scheme_credentials():
+    response = client.get("/users/me", headers={"Authorization": "Basic notreally"})
+    assert response.status_code == 403
+    assert response.json() == {"detail": "Invalid authentication credentials"}
diff --git a/tests/test_security_http_digest.py b/tests/test_security_http_digest.py
new file mode 100644
index 00000000..d9be2d45
--- /dev/null
+++ b/tests/test_security_http_digest.py
@@ -0,0 +1,64 @@
+from fastapi import FastAPI, Security
+from fastapi.security import HTTPAuthorizationCredentials, HTTPDigest
+from starlette.testclient import TestClient
+
+app = FastAPI()
+
+security = HTTPDigest()
+
+
+@app.get("/users/me")
+def read_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
+    return {"scheme": credentials.scheme, "credentials": credentials.credentials}
+
+
+client = TestClient(app)
+
+openapi_schema = {
+    "openapi": "3.0.2",
+    "info": {"title": "Fast API", "version": "0.1.0"},
+    "paths": {
+        "/users/me": {
+            "get": {
+                "responses": {
+                    "200": {
+                        "description": "Successful Response",
+                        "content": {"application/json": {"schema": {}}},
+                    }
+                },
+                "summary": "Read Current User Get",
+                "operationId": "read_current_user_users_me_get",
+                "security": [{"HTTPDigest": []}],
+            }
+        }
+    },
+    "components": {
+        "securitySchemes": {"HTTPDigest": {"type": "http", "scheme": "digest"}}
+    },
+}
+
+
+def test_openapi_schema():
+    response = client.get("/openapi.json")
+    assert response.status_code == 200
+    assert response.json() == openapi_schema
+
+
+def test_security_http_digest():
+    response = client.get("/users/me", headers={"Authorization": "Digest foobar"})
+    assert response.status_code == 200
+    assert response.json() == {"scheme": "Digest", "credentials": "foobar"}
+
+
+def test_security_http_digest_no_credentials():
+    response = client.get("/users/me")
+    assert response.status_code == 403
+    assert response.json() == {"detail": "Not authenticated"}
+
+
+def test_security_http_digest_incorrect_scheme_credentials():
+    response = client.get(
+        "/users/me", headers={"Authorization": "Other invalidauthorization"}
+    )
+    assert response.status_code == 403
+    assert response.json() == {"detail": "Invalid authentication credentials"}

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/fastapi/security/http.py b/fastapi/security/http.py
index f41d8d94..362390b7 100644
--- a/fastapi/security/http.py
+++ b/fastapi/security/http.py
@@ -110,14 +110,17 @@ class HTTPBearer(HTTPBase):
                     status_code=HTTP_403_FORBIDDEN, detail="Not authenticated"
                 )
             else:
                 return None
         if scheme.lower() != "bearer":
-            raise HTTPException(
-                status_code=HTTP_403_FORBIDDEN,
-                detail="Invalid authentication credentials",
-            )
+            if self.auto_error:
+                raise HTTPException(
+                    status_code=HTTP_403_FORBIDDEN,
+                    detail="Invalid authentication credentials",
+                )
+            else:
+                return None
         return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)
 
 
 class HTTPDigest(HTTPBase):
     def __init__(self, *, scheme_name: str = None, auto_error: bool = True):

```

## ODIS candidates: 6 total, path=small, tiers={'full': 6, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee fastapi/applications.py:19 FastAPI | class FastAPI(Starlette):
```python
   8  from starlette.exceptions import ExceptionMiddleware, HTTPException
   9  from starlette.middleware.errors import ServerErrorMiddleware
  10  from starlette.middleware.lifespan import LifespanMiddleware
  11  from starlette.requests import Request
  12  from starlette.responses import JSONResponse, Response
  13  
  14  
  15  async def http_exception(request: Request, exc: HTTPException) -> JSONResponse:
  16      return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
  17  
  18  
  19  class FastAPI(Starlette):
  20      def __init__(
  21          self,
  22          debug: bool = False,
  23          template_directory: str = None,
  24          title: str = "Fast API",
  25          description: str = "",
  26          version: str = "0.1.0",
  27          openapi_url: Optional[str] = "/openapi.json",
  28          docs_url: Optional[str] = "/docs",
  29          redoc_url: Optional[str] = "/redoc",
  30          **extra: Dict[str, Any],
  31      ) -> None:
  32          self._debug = debug
```
- [full] callee fastapi/openapi/models.py:276 HTTPBase | class HTTPBase(SecurityBase):
```python
 264  class APIKeyIn(Enum):
 265      query = "query"
 266      header = "header"
 267      cookie = "cookie"
 268  
 269  
 270  class APIKey(SecurityBase):
 271      type_ = PSchema(SecuritySchemeType.apiKey, alias="type")  # type: ignore
 272      in_: APIKeyIn = PSchema(..., alias="in")  # type: ignore
 273      name: str
 274  
 275  
 276  class HTTPBase(SecurityBase):
 277      type_ = PSchema(SecuritySchemeType.http, alias="type")  # type: ignore
 278      scheme: str
 279  
 280  
 281  class HTTPBearer(HTTPBase):
 282      scheme = "bearer"
 283      bearerFormat: Optional[str] = None
 284  
 285  
 286  class OAuthFlow(BaseModel):
 287      refreshUrl: Optional[str] = None
 288      scopes: Dict[str, str] = {}
```
- [full] callee fastapi/openapi/models.py:281 HTTPBearer | class HTTPBearer(HTTPBase):
```python
 269  
 270  class APIKey(SecurityBase):
 271      type_ = PSchema(SecuritySchemeType.apiKey, alias="type")  # type: ignore
 272      in_: APIKeyIn = PSchema(..., alias="in")  # type: ignore
 273      name: str
 274  
 275  
 276  class HTTPBase(SecurityBase):
 277      type_ = PSchema(SecuritySchemeType.http, alias="type")  # type: ignore
 278      scheme: str
 279  
 280  
 281  class HTTPBearer(HTTPBase):
 282      scheme = "bearer"
 283      bearerFormat: Optional[str] = None
 284  
 285  
 286  class OAuthFlow(BaseModel):
 287      refreshUrl: Optional[str] = None
 288      scopes: Dict[str, str] = {}
 289  
 290  
 291  class OAuthFlowImplicit(OAuthFlow):
 292      authorizationUrl: str
 293  
```
- [full] callee fastapi/params.py:315 Security | class Security(Depends):
```python
 304              max_length=max_length,
 305              regex=regex,
 306              **extra,
 307          )
 308  
 309  
 310  class Depends:
 311      def __init__(self, dependency: Callable = None):
 312          self.dependency = dependency
 313  
 314  
 315  class Security(Depends):
 316      def __init__(self, dependency: Callable = None, scopes: Sequence[str] = None):
 317          self.scopes = scopes or []
 318          super().__init__(dependency=dependency)
```
- [full] callee fastapi/security/http.py:26 HTTPBase | class HTTPBase(SecurityBase):
```python
  15  
  16  class HTTPBasicCredentials(BaseModel):
  17      username: str
  18      password: str
  19  
  20  
  21  class HTTPAuthorizationCredentials(BaseModel):
  22      scheme: str
  23      credentials: str
  24  
  25  
  26  class HTTPBase(SecurityBase):
  27      def __init__(self, *, scheme: str, scheme_name: str = None):
  28          self.model = HTTPBaseModel(scheme=scheme)
  29          self.scheme_name = scheme_name or self.__class__.__name__
  30  
  31      async def __call__(self, request: Request) -> str:
  32          authorization: str = request.headers.get("Authorization")
  33          scheme, credentials = get_authorization_scheme_param(authorization)
  34          if not (authorization and scheme and credentials):
  35              raise HTTPException(
  36                  status_code=HTTP_403_FORBIDDEN, detail="Not authenticated"
  37              )
  38          return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)
  39  
```
- [full] callee fastapi/security/http.py:41 HTTPBasic | class HTTPBasic(HTTPBase):
```python
  30  
  31      async def __call__(self, request: Request) -> str:
  32          authorization: str = request.headers.get("Authorization")
  33          scheme, credentials = get_authorization_scheme_param(authorization)
  34          if not (authorization and scheme and credentials):
  35              raise HTTPException(
  36                  status_code=HTTP_403_FORBIDDEN, detail="Not authenticated"
  37              )
  38          return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)
  39  
  40  
  41  class HTTPBasic(HTTPBase):
  42      def __init__(self, *, scheme_name: str = None, realm: str = None):
  43          self.model = HTTPBaseModel(scheme="basic")
  44          self.scheme_name = scheme_name or self.__class__.__name__
  45          self.realm = realm
  46  
  47      async def __call__(self, request: Request) -> str:
  48          authorization: str = request.headers.get("Authorization")
  49          scheme, param = get_authorization_scheme_param(authorization)
  50          # before implementing headers with 401 errors, wait for: https://github.com/encode/starlette/issues/295
  51          # unauthorized_headers = {"WWW-Authenticate": "Basic"}
  52          invalid_user_credentials_exc = HTTPException(
  53              status_code=HTTP_403_FORBIDDEN, detail="Invalid authentication credentials"
  54          )
```
