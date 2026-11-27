# scrapy#10

Commit message of the reviewed change: refactoring redirect logic

Oracle (fix location at buggy_commit): [{'file': 'scrapy/downloadermiddlewares/redirect.py', 'line_start': 6, 'line_end': 6}, {'file': 'scrapy/downloadermiddlewares/redirect.py', 'line_start': 68, 'line_end': 69}]

## Reviewed diff (introducing commit)
```diff
diff --git a/scrapy/downloadermiddlewares/redirect.py b/scrapy/downloadermiddlewares/redirect.py
index 3a6da85e..4ed7e4c2 100644
--- a/scrapy/downloadermiddlewares/redirect.py
+++ b/scrapy/downloadermiddlewares/redirect.py
@@ -61,23 +61,21 @@ class RedirectMiddleware(BaseRedirectMiddleware):
                 request.meta.get('handle_httpstatus_all', False)):
             return response
 
-        location = None
-        if 'Location' in response.headers:
-            # HTTP header is ascii or latin1, redirected url will be percent-encoded utf-8
-            location = to_native_str(response.headers['location'].decode('latin1'))
+        allowed_status = (301, 302, 303, 307)
+        if 'Location' not in response.headers or response.status not in allowed_status:
+            return response
 
-        if location is not None and response.status in [301, 302, 303, 307]:
-            redirected_url = urljoin(request.url, location)
+        # HTTP header is ascii or latin1, redirected url will be percent-encoded utf-8
+        location = to_native_str(response.headers['location'].decode('latin1'))
 
-            if response.status in [301, 307] or request.method == 'HEAD':
-                redirected = request.replace(url=redirected_url)
-                return self._redirect(redirected, request, spider, response.status)
+        redirected_url = urljoin(request.url, location)
 
-            if response.status in [302, 303]:
-                redirected = self._redirect_request_using_get(request, redirected_url)
-                return self._redirect(redirected, request, spider, response.status)
+        if response.status in (301, 307) or request.method == 'HEAD':
+            redirected = request.replace(url=redirected_url)
+            return self._redirect(redirected, request, spider, response.status)
 
-        return response
+        redirected = self._redirect_request_using_get(request, redirected_url)
+        return self._redirect(redirected, request, spider, response.status)
 
 
 class MetaRefreshMiddleware(BaseRedirectMiddleware):

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/scrapy/downloadermiddlewares/redirect.py b/scrapy/downloadermiddlewares/redirect.py
index 4ed7e4c2..db276eef 100644
--- a/scrapy/downloadermiddlewares/redirect.py
+++ b/scrapy/downloadermiddlewares/redirect.py
@@ -1,11 +1,12 @@
 import logging
 from six.moves.urllib.parse import urljoin
 
+from w3lib.url import safe_url_string
+
 from scrapy.http import HtmlResponse
 from scrapy.utils.response import get_meta_refresh
-from scrapy.utils.python import to_native_str
 from scrapy.exceptions import IgnoreRequest, NotConfigured
 
 logger = logging.getLogger(__name__)
 
 
@@ -63,12 +64,11 @@ class RedirectMiddleware(BaseRedirectMiddleware):
 
         allowed_status = (301, 302, 303, 307)
         if 'Location' not in response.headers or response.status not in allowed_status:
             return response
 
-        # HTTP header is ascii or latin1, redirected url will be percent-encoded utf-8
-        location = to_native_str(response.headers['location'].decode('latin1'))
+        location = safe_url_string(response.headers['location'])
 
         redirected_url = urljoin(request.url, location)
 
         if response.status in (301, 307) or request.method == 'HEAD':
             redirected = request.replace(url=redirected_url)

```

## ODIS candidates: 3 total, path=small, tiers={'full': 3, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee scrapy/http/response/__init__.py:79 urljoin | def urljoin(self, url):
```python
  69  
  70      def replace(self, *args, **kwargs):
  71          """Create a new Response with the same attributes except for those
  72          given new values.
  73          """
  74          for x in ['url', 'status', 'headers', 'body', 'request', 'flags']:
  75              kwargs.setdefault(x, getattr(self, x))
  76          cls = kwargs.pop('cls', self.__class__)
  77          return cls(*args, **kwargs)
  78  
  79      def urljoin(self, url):
  80          """Join this Response's url with a possible relative url to form an
  81          absolute interpretation of the latter."""
  82          return urljoin(self.url, url)
```
- [full] callee scrapy/http/response/text.py:70 urljoin | def urljoin(self, url):
```python
  60      def body_as_unicode(self):
  61          """Return body as unicode"""
  62          # check for self.encoding before _cached_ubody just in
  63          # _body_inferred_encoding is called
  64          benc = self.encoding
  65          if self._cached_ubody is None:
  66              charset = 'charset=%s' % benc
  67              self._cached_ubody = html_to_unicode(charset, self.body)[1]
  68          return self._cached_ubody
  69  
  70      def urljoin(self, url):
  71          """Join this Response's url with a possible relative url to form an
  72          absolute interpretation of the latter."""
  73          return urljoin(get_base_url(self), url)
  74  
  75      @memoizemethod_noargs
  76      def _headers_encoding(self):
  77          content_type = self.headers.get(b'Content-Type', b'')
  78          return http_content_type_encoding(to_native_str(content_type))
  79  
  80      def _body_inferred_encoding(self):
```
- [full] callee scrapy/utils/python.py:123 to_native_str | def to_native_str(text, encoding=None, errors='strict'):
```python
 113      if isinstance(text, bytes):
 114          return text
 115      if not isinstance(text, six.string_types):
 116          raise TypeError('to_bytes must receive a unicode, str or bytes '
 117                          'object, got %s' % type(text).__name__)
 118      if encoding is None:
 119          encoding = 'utf-8'
 120      return text.encode(encoding, errors)
 121  
 122  
 123  def to_native_str(text, encoding=None, errors='strict'):
 124      """ Return str representation of `text`
 125      (bytes in Python 2.x and unicode in Python 3.x). """
 126      if six.PY2:
 127          return to_bytes(text, encoding, errors)
 128      else:
 129          return to_unicode(text, encoding, errors)
 130  
 131  
 132  def re_rsearch(pattern, text, chunk_size=1024):
 133      """
```
