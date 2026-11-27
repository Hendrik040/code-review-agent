# scrapy#14

Commit message of the reviewed change: Use if Py2/Py3 function instead of custom GzipFile class method

Oracle (fix location at buggy_commit): [{'file': 'scrapy/utils/gz.py', 'line_start': 10, 'line_end': 10}, {'file': 'scrapy/utils/gz.py', 'line_start': 57, 'line_end': 57}]

## Reviewed diff (introducing commit)
```diff
diff --git a/scrapy/utils/gz.py b/scrapy/utils/gz.py
index df1d2969..3e6596b0 100644
--- a/scrapy/utils/gz.py
+++ b/scrapy/utils/gz.py
@@ -7,24 +7,35 @@ except ImportError:
 from io import UnsupportedOperation
 from gzip import GzipFile
 
-class ReadOneGzipFile(GzipFile):
-    def readone(self, size=-1):
-        try:
-            return self.read1(size)
-        except UnsupportedOperation:
-            return self.read(size)
+import six
+
+
+# - Python>=3.5 GzipFile's read() has issues returning leftover
+#   uncompressed data when input is corrupted
+#   (regression or bug-fix compared to Python 3.4)
+# - read1(), which fetches data before raising EOFError on next call
+#   works here but is only available from Python>=3.3
+# - scrapy does not support Python 3.2
+# - Python 2.7 GzipFile works fine with standard read() + extrabuf
+if six.PY3:
+    def read1(gzf, size=-1):
+        return gzf.read1(size)
+else:
+    def read1(gzf, size=-1):
+        return gzf.read(size)
+
 
 def gunzip(data):
     """Gunzip the given data and return as much data as possible.
 
     This is resilient to CRC checksum errors.
     """
-    f = ReadOneGzipFile(fileobj=BytesIO(data))
+    f = GzipFile(fileobj=BytesIO(data))
     output = b''
     chunk = b'.'
     while chunk:
         try:
-            chunk = f.readone(8196)
+            chunk = read1(f, 8196)
             output += chunk
         except (IOError, EOFError, struct.error):
             # complete only if there is some data, otherwise re-raise

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/scrapy/utils/gz.py b/scrapy/utils/gz.py
index d035f9fd..cfb65214 100644
--- a/scrapy/utils/gz.py
+++ b/scrapy/utils/gz.py
@@ -5,11 +5,11 @@ try:
 except ImportError:
     from io import BytesIO
 from gzip import GzipFile
 
 import six
-
+import re
 
 # - Python>=3.5 GzipFile's read() has issues returning leftover
 #   uncompressed data when input is corrupted
 #   (regression or bug-fix compared to Python 3.4)
 # - read1(), which fetches data before raising EOFError on next call
@@ -48,10 +48,11 @@ def gunzip(data):
                     break
             else:
                 raise
     return output
 
+_is_gzipped_re = re.compile(br'^application/(x-)?gzip\b', re.I)
 
 def is_gzipped(response):
     """Return True if the response is gzipped, or False otherwise"""
     ctype = response.headers.get('Content-Type', b'')
-    return ctype in (b'application/x-gzip', b'application/gzip')
+    return _is_gzipped_re.search(ctype) is not None

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
