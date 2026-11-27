# scrapy#25

Commit message of the reviewed change: support overriding url in FormRequest.from_response

Oracle (fix location at buggy_commit): [{'file': 'scrapy/http/request/form.py', 'line_start': 47, 'line_end': 47}, {'file': 'scrapy/http/request/form.py', 'line_start': 61, 'line_end': 61}]

## Reviewed diff (introducing commit)
```diff
diff --git a/scrapy/http/request/form.py b/scrapy/http/request/form.py
index 5c639a60..69088c48 100644
--- a/scrapy/http/request/form.py
+++ b/scrapy/http/request/form.py
@@ -5,7 +5,7 @@ This module implements the FormRequest class which is a more covenient class
 See documentation in docs/topics/request-response.rst
 """
 
-import urllib
+import urllib, urlparse
 import lxml.html
 from scrapy.http.request import Request
 from scrapy.utils.python import unicode_to_str
@@ -35,10 +35,14 @@ class FormRequest(Request):
         kwargs.setdefault('encoding', response.encoding)
         form = _get_form(response, formname, formnumber, formxpath)
         formdata = _get_inputs(form, formdata, dont_click, clickdata, response)
-        url = form.action or form.base_url
+        url = _get_form_url(form, kwargs.pop('url', None))
         method = kwargs.pop('method', form.method)
-        return cls(url, method=method, formdata=formdata, **kwargs)
+        return cls(url=url, method=method, formdata=formdata, **kwargs)
 
+def _get_form_url(form, url):
+    if url is None:
+        return form.action or form.base_url
+    return urlparse.urljoin(form.base_url, url)
 
 def _urlencode(seq, enc):
     values = [(unicode_to_str(k, enc), unicode_to_str(v, enc))
diff --git a/scrapy/tests/test_http_request.py b/scrapy/tests/test_http_request.py
index a1cc162f..069b1cd0 100644
--- a/scrapy/tests/test_http_request.py
+++ b/scrapy/tests/test_http_request.py
@@ -282,6 +282,18 @@ class FormRequestTest(RequestTest):
         request = FormRequest.from_response(response, method='POST')
         self.assertEqual(request.method, 'POST')
 
+    def test_from_response_override_url(self):
+        response = _buildresponse(
+                '''<html><body>
+                <form action="/app"></form>
+                </body></html>''')
+        request = FormRequest.from_response(response)
+        self.assertEqual(request.url, 'http://example.com/app')
+        request = FormRequest.from_response(response, url='http://foo.bar/absolute')
+        self.assertEqual(request.url, 'http://foo.bar/absolute')
+        request = FormRequest.from_response(response, url='/relative')
+        self.assertEqual(request.url, 'http://example.com/relative')
+
     def test_from_response_submit_first_clickable(self):
         response = _buildresponse(
             """<form action="get.php" method="GET">

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/scrapy/http/request/form.py b/scrapy/http/request/form.py
index a12a2fd0..4a9bd732 100644
--- a/scrapy/http/request/form.py
+++ b/scrapy/http/request/form.py
@@ -9,10 +9,11 @@ from six.moves.urllib.parse import urljoin, urlencode
 import lxml.html
 from parsel.selector import create_root_node
 import six
 from scrapy.http.request import Request
 from scrapy.utils.python import to_bytes, is_listlike
+from scrapy.utils.response import get_base_url
 
 
 class FormRequest(Request):
 
     def __init__(self, *args, **kwargs):
@@ -42,11 +43,11 @@ class FormRequest(Request):
         return cls(url=url, method=method, formdata=formdata, **kwargs)
 
 
 def _get_form_url(form, url):
     if url is None:
-        return form.action or form.base_url
+        return urljoin(form.base_url, form.action)
     return urljoin(form.base_url, url)
 
 
 def _urlencode(seq, enc):
     values = [(to_bytes(k, enc), to_bytes(v, enc))
@@ -56,11 +57,11 @@ def _urlencode(seq, enc):
 
 
 def _get_form(response, formname, formid, formnumber, formxpath):
     """Find the form element """
     text = response.body_as_unicode()
-    root = create_root_node(text, lxml.html.HTMLParser, base_url=response.url)
+    root = create_root_node(text, lxml.html.HTMLParser, base_url=get_base_url(response))
     forms = root.xpath('//form')
     if not forms:
         raise ValueError("No <form> element found in %s" % response)
 
     if formname is not None:

```

## ODIS candidates: 1 total, path=small, tiers={'full': 1, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee scrapy/tests/test_http_request.py:650 _buildresponse | def _buildresponse(body, **kwargs):
```python
 640          fs = _qs(r1)
 641          self.assertEqual(fs['one'], ['1'])
 642  
 643          r1 = self.request_class.from_response(response, formxpath="//form/input[@name='four']")
 644          fs = _qs(r1)
 645          self.assertEqual(fs['three'], ['3'])
 646  
 647          self.assertRaises(ValueError, self.request_class.from_response,
 648                            response, formxpath="//form/input[@name='abc']")
 649  
 650  def _buildresponse(body, **kwargs):
 651      kwargs.setdefault('body', body)
 652      kwargs.setdefault('url', 'http://example.com')
 653      kwargs.setdefault('encoding', 'utf-8')
 654      return HtmlResponse(**kwargs)
 655  
 656  def _qs(req):
 657      if req.method == 'POST':
 658          qs = req.body
 659      else:
 660          qs = req.url.partition('?')[2]
```
