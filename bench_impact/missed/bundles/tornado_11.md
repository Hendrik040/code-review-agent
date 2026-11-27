# tornado#11

Commit message of the reviewed change: Use HTTP1Connection in SimpleAsyncHTTPClient.

Oracle (fix location at buggy_commit): [{'file': 'tornado/http1connection.py', 'line_start': 568, 'line_end': 568}]

## Reviewed diff (introducing commit)
```diff
diff --git a/tornado/http1connection.py b/tornado/http1connection.py
index b491de6c..a7cd9cbc 100644
--- a/tornado/http1connection.py
+++ b/tornado/http1connection.py
@@ -31,15 +31,13 @@ class HTTP1Connection(object):
     We parse HTTP headers and bodies, and execute the request callback
     until the HTTP conection is closed.
     """
-    def __init__(self, stream, address, delegate, no_keep_alive=False,
-                 protocol=None):
+    def __init__(self, stream, address, no_keep_alive=False, protocol=None):
         self.stream = stream
         self.address = address
         # Save the socket's address family now so we know how to
         # interpret self.address even after the stream is closed
         # and its socket attribute replaced with None.
         self.address_family = stream.socket.family
-        self.delegate = delegate
         self.no_keep_alive = no_keep_alive
         if protocol:
             self.protocol = protocol
@@ -51,34 +49,65 @@ class HTTP1Connection(object):
         self._clear_request_state()
         self.stream.set_close_callback(self._on_connection_close)
         self._finish_future = None
+
+    def start_serving(self, delegate):
+        assert isinstance(delegate, httputil.HTTPConnectionDelegate)
         # Register the future on the IOLoop so its errors get logged.
-        stream.io_loop.add_future(self._process_requests(),
-                                  lambda f: f.result())
+        self.stream.io_loop.add_future(self._process_requests(delegate),
+                                       lambda f: f.result())
 
     @gen.coroutine
-    def _process_requests(self):
+    def _process_requests(self, delegate):
         while True:
+            request_delegate = delegate.start_request(self)
             try:
-                header_data = yield self.stream.read_until(b"\r\n\r\n")
-                request_delegate = self.delegate.start_request(self)
-                self._finish_future = Future()
-                start_line, headers = self._parse_headers(header_data)
-                self._disconnect_on_finish = not self._can_keep_alive(
-                    start_line, headers)
-                request_delegate.headers_received(start_line, headers)
-                body_future = self._read_body(headers)
-                if body_future is not None:
-                    request_delegate.data_received((yield body_future))
-                request_delegate.finish()
-                yield self._finish_future
-            except httputil.BadRequestException as e:
-                gen_log.info("Malformed HTTP request from %r: %s",
-                             self.address, e)
-                self.close()
-                return
+                ret = yield self._process_message(request_delegate, False)
             except iostream.StreamClosedError:
                 self.close()
                 return
+            if not ret:
+                return
+
+    def process_response(self, delegate, method):
+        return self._process_message(delegate, True, method=method)
+
+    @gen.coroutine
+    def _process_message(self, delegate, is_client, method=None):
+        assert isinstance(delegate, httputil.HTTPStreamDelegate)
+        try:
+            header_data = yield self.stream.read_until_regex(b"\r?\n\r?\n")
+            self._finish_future = Future()
+            start_line, headers = self._parse_headers(header_data)
+            self._disconnect_on_finish = not self._can_keep_alive(
+                start_line, headers)
+            ret = delegate.headers_received(start_line, headers)
+            # TODO: finalize the 'detach' interface.
+            if ret == 'detach':
+                return
+            skip_body = False
+            if is_client:
+                if method == 'HEAD':
+                    skip_body = True
+                code = httputil.parse_response_start_line(start_line).code
+                if code == 304:
+                    skip_body = True
+                if code >= 100 and code < 200:
+                    yield self._process_message(delegate, is_client, method=method)
+            else:
+                if headers.get("Expect") == "100-continue":
+                    self.stream.write(b"HTTP/1.1 100 (Continue)\r\n\r\n")
+            if not skip_body:
+                body_future = self._read_body(is_client, headers, delegate)
+                if body_future is not None:
+                    yield body_future
+            delegate.finish()
+            yield self._finish_future
+        except httputil.BadRequestException as e:
+            gen_log.info("Malformed HTTP request from %r: %s",
+                         self.address, e)
+            self.close()
+            raise gen.Return(False)
+        raise gen.Return(True)
 
 
     def _clear_request_state(self):
@@ -183,13 +212,38 @@ class HTTP1Connection(object):
             raise httputil.BadRequestException("Malformed HTTP headers")
         return start_line, headers
 
-    def _read_body(self, headers):
+    def _read_body(self, is_client, headers, delegate):
         content_length = headers.get("Content-Length")
         if content_length:
             content_length = int(content_length)
             if content_length > self.stream.max_buffer_size:
                 raise httputil.BadRequestException("Content-Length too long")
-            if headers.get("Expect") == "100-continue":
-                self.stream.write(b"HTTP/1.1 100 (Continue)\r\n\r\n")
-            return self.stream.read_bytes(content_length)
+            return self._read_fixed_body(content_length, delegate)
+        if headers.get("Transfer-Encoding") == "chunked":
+            return self._read_chunked_body(delegate)
+        if is_client:
+            return self._read_body_until_close(delegate)
         return None
+
+    @gen.coroutine
+    def _read_fixed_body(self, content_length, delegate):
+        body = yield self.stream.read_bytes(content_length)
+        delegate.data_received(body)
+
+    @gen.coroutine
+    def _read_chunked_body(self, delegate):
+        # TODO: "chunk extensions" http://tools.ietf.org/html/rfc2616#section-3.6.1
+        while True:
+            chunk_len = yield self.stream.read_until(b"\r\n")
+            chunk_len = int(chunk_len.strip(), 16)
+            if chunk_len == 0:
+                return
+            # chunk ends with \r\n
+            chunk = yield self.stream.read_bytes(chunk_len + 2)
+            assert chunk[-2:] == b"\r\n"
+            delegate.data_received(chunk[:-2])
+
+    @gen.coroutine
+    def _read_body_until_close(self, delegate):
+        body = yield self.stream.read_until_close()
+        delegate.data_received(body)
diff --git a/tornado/httpserver.py b/tornado/httpserver.py
index 44a2c94b..8454c3d7 100644
--- a/tornado/httpserver.py
+++ b/tornado/httpserver.py
@@ -143,7 +143,9 @@ class HTTPServer(TCPServer, httputil.HTTPConnectionDelegate):
                            **kwargs)
 
     def handle_stream(self, stream, address):
-        HTTPConnection(stream, address, self, self.no_keep_alive, self.protocol)
+        conn = HTTPConnection(stream, address, self.no_keep_alive,
+                              self.protocol)
+        conn.start_serving(self)
 
     def start_request(self, connection):
         return _ServerRequestProcessor(self, connection)
diff --git a/tornado/httputil.py b/tornado/httputil.py
index 8164d2eb..d7739d40 100644
--- a/tornado/httputil.py
+++ b/tornado/httputil.py
@@ -28,6 +28,7 @@ import copy
 import datetime
 import email.utils
 import numbers
+import re
 import time
 
 from tornado.escape import native_str, parse_qs_bytes, utf8
@@ -625,6 +626,24 @@ def format_timestamp(ts):
         raise TypeError("unknown timestamp type: %r" % ts)
     return email.utils.formatdate(ts, usegmt=True)
 
+
+ResponseStartLine = collections.namedtuple(
+    'ResponseStartLine', ['version', 'code', 'reason'])
+
+def parse_response_start_line(line):
+    """Returns a (version, code, reason) tuple for an HTTP 1.x response line.
+
+    The response is a `collections.namedtuple`.
+
+    >>> parse_response_start_line("HTTP/1.1 200 OK")
+    ResponseStartLine(version='HTTP/1.1', code=200, reason='OK')
+    """
+    line = native_str(line)
+    match = re.match("(HTTP/1.[01]) ([0-9]+) ([^\r]*)", line)
+    assert match
+    return ResponseStartLine(match.group(1), int(match.group(2)),
+                             match.group(3))
+
 # _parseparam and _parse_header are copied and modified from python2.7's cgi.py
 # The original 2.7 version of this code did not correctly support some
 # combinations of semicolons and double quotes.
diff --git a/tornado/simple_httpclient.py b/tornado/simple_httpclient.py
index 73bfee89..0bd92e29 100644
--- a/tornado/simple_httpclient.py
+++ b/tornado/simple_httpclient.py
@@ -1,10 +1,11 @@
 #!/usr/bin/env python
 from __future__ import absolute_import, division, print_function, with_statement
 
-from tornado.escape import utf8, _unicode, native_str
+from tornado.escape import utf8, _unicode
 from tornado.httpclient import HTTPResponse, HTTPError, AsyncHTTPClient, main, _RequestProxy
-from tornado.httputil import HTTPHeaders
-from tornado.iostream import IOStream, SSLIOStream
+from tornado import httputil
+from tornado.http1connection import HTTP1Connection
+from tornado.iostream import IOStream, SSLIOStream, StreamClosedError
 from tornado.netutil import Resolver, OverrideResolver
 from tornado.log import gen_log
 from tornado import stack_context
@@ -142,7 +143,7 @@ class SimpleAsyncHTTPClient(AsyncHTTPClient):
         del self.waiting[key]
 
 
-class _HTTPConnection(object):
+class _HTTPConnection(httputil.HTTPStreamDelegate):
     _SUPPORTED_METHODS = set(["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
 
     def __init__(self, io_loop, client, request, release_callback,
@@ -157,10 +158,11 @@ class _HTTPConnection(object):
         self.resolver = resolver
         self.code = None
         self.headers = None
-        self.chunks = None
+        self.chunks = []
         self._decompressor = None
         # Timeout handle returned by IOLoop.add_timeout
         self._timeout = None
+        self._sockaddr = None
         with stack_context.ExceptionStackContext(self._handle_exception):
             self.parsed = urlparse.urlsplit(_unicode(self.request.url))
             if self.parsed.scheme not in ("http", "https"):
@@ -205,8 +207,8 @@ class _HTTPConnection(object):
         self.stream.set_close_callback(self._on_close)
         # ipv6 addresses are broken (in self.parsed.hostname) until
         # 2.7, here is correctly parsed value calculated in __init__
-        sockaddr = addrinfo[0][1]
-        self.stream.connect(sockaddr, self._on_connect,
+        self._sockaddr = addrinfo[0][1]
+        self.stream.connect(self._sockaddr, self._on_connect,
                             server_hostname=self.parsed_hostname)
 
     def _create_stream(self, addrinfo):
@@ -333,7 +335,14 @@ class _HTTPConnection(object):
             request_str += self.request.body
         self.stream.set_nodelay(True)
         self.stream.write(request_str)
-        self.stream.read_until_regex(b"\r?\n\r?\n", self._on_headers)
+        self.connection = HTTP1Connection(
+            self.stream, self._sockaddr,
+            no_keep_alive=True, protocol=self.parsed.scheme)
+        # Ensure that any exception raised in process_response ends up in our
+        # stack context.
+        self.io_loop.add_future(
+            self.connection.process_response(self, method=self.request.method),
+            lambda f: f.result())
 
     def _release(self):
         if self.release_callback is not None:
@@ -351,19 +360,24 @@ class _HTTPConnection(object):
     def _handle_exception(self, typ, value, tb):
         if self.final_callback:
             self._remove_timeout()
+            if isinstance(value, StreamClosedError):
+                value = HTTPError(599, "Stream closed")
             self._run_callback(HTTPResponse(self.request, 599, error=value,
                                             request_time=self.io_loop.time() - self.start_time,
                                             ))
 
             if hasattr(self, "stream"):
+                # TODO: this may cause a StreamClosedError to be raised
+                # by the connection's Future.  Should we cancel the
+                # connection more gracefully?
                 self.stream.close()
             return True
         else:
             # If our callback has already been called, we are probably
             # catching an exception that is not caused by us but rather
             # some child of our callback. Rather than drop it on the floor,
-            # pass it along.
-            return False
+            # pass it along, unless it's just the stream being closed.
+            return isinstance(value, StreamClosedError)
 
     def _on_close(self):
         if self.final_callback is not None:
@@ -372,22 +386,11 @@ class _HTTPConnection(object):
                 message = str(self.stream.error)
             raise HTTPError(599, message)
 
-    def _handle_1xx(self, code):
-        self.stream.read_until_regex(b"\r?\n\r?\n", self._on_headers)
-
-    def _on_headers(self, data):
-        data = native_str(data.decode("latin1"))
-        first_line, _, header_data = data.partition("\n")
-        match = re.match("HTTP/1.[01] ([0-9]+) ([^\r]*)", first_line)
-        assert match
-        code = int(match.group(1))
-        self.headers = HTTPHeaders.parse(header_data)
-        if 100 <= code < 200:
-            self._handle_1xx(code)
-            return
-        else:
-            self.code = code
-            self.reason = match.group(2)
+    def headers_received(self, first_line, headers):
+        self.headers = headers
+        version, code, reason = httputil.parse_response_start_line(first_line)
+        self.code = code
+        self.reason = reason
 
         if "Content-Length" in self.headers:
             if "," in self.headers["Content-Length"]:
@@ -405,16 +408,11 @@ class _HTTPConnection(object):
 
         if self.request.header_callback is not None:
             # re-attach the newline we split on earlier
-            self.request.header_callback(first_line + _)
+            self.request.header_callback(first_line + '\r\n')
             for k, v in self.headers.get_all():
                 self.request.header_callback("%s: %s\r\n" % (k, v))
             self.request.header_callback('\r\n')
 
-        if self.request.method == "HEAD" or self.code == 304:
-            # HEAD requests and 304 responses never have content, even
-            # though they may have content-length headers
-            self._on_body(b"")
-            return
         if 100 <= self.code < 200 or self.code == 204:
             # These response codes never have bodies
             # http://www.w3.org/Protocols/rfc2616/rfc2616-sec4.html#sec4.3
@@ -422,21 +420,25 @@ class _HTTPConnection(object):
                     content_length not in (None, 0)):
                 raise ValueError("Response with code %d should not have body" %
                                  self.code)
-            self._on_body(b"")
-            return
 
         if (self.request.use_gzip and
                 self.headers.get("Content-Encoding") == "gzip"):
             self._decompressor = GzipDecompressor()
-        if self.headers.get("Transfer-Encoding") == "chunked":
-            self.chunks = []
-            self.stream.read_until(b"\r\n", self._on_chunk_length)
-        elif content_length is not None:
-            self.stream.read_bytes(content_length, self._on_body)
-        else:
-            self.stream.read_until_close(self._on_body)
 
-    def _on_body(self, data):
+    def finish(self):
+        if self._decompressor is not None:
+            tail = self._decompressor.flush()
+            if tail:
+                # I believe the tail will always be empty (i.e.
+                # decompress will return all it can).  The purpose
+                # of the flush call is to detect errors such
+                # as truncated input.  But in case it ever returns
+                # anything, treat it as an extra chunk
+                if self.request.streaming_callback is not None:
+                    self.request.streaming_callback(tail)
+                else:
+                    self.chunks.append(tail)
+        data = b''.join(self.chunks)
         self._remove_timeout()
         original_request = getattr(self.request, "original_request",
                                    self.request)
@@ -472,19 +474,12 @@ class _HTTPConnection(object):
             self.client.fetch(new_request, final_callback)
             self._on_end_request()
             return
-        if self._decompressor:
-            data = (self._decompressor.decompress(data) +
-                    self._decompressor.flush())
         if self.request.streaming_callback:
-            if self.chunks is None:
-                # if chunks is not None, we already called streaming_callback
-                # in _on_chunk_data
-                self.request.streaming_callback(data)
             buffer = BytesIO()
         else:
             buffer = BytesIO(data)  # TODO: don't require one big string?
         response = HTTPResponse(original_request,
-                                self.code, reason=self.reason,
+                                self.code, reason=getattr(self, 'reason', None),
                                 headers=self.headers,
                                 request_time=self.io_loop.time() - self.start_time,
                                 buffer=buffer,
@@ -495,40 +490,13 @@ class _HTTPConnection(object):
     def _on_end_request(self):
         self.stream.close()
 
-    def _on_chunk_length(self, data):
-        # TODO: "chunk extensions" http://tools.ietf.org/html/rfc2616#section-3.6.1
-        length = int(data.strip(), 16)
-        if length == 0:
-            if self._decompressor is not None:
-                tail = self._decompressor.flush()
-                if tail:
-                    # I believe the tail will always be empty (i.e.
-                    # decompress will return all it can).  The purpose
-                    # of the flush call is to detect errors such
-                    # as truncated input.  But in case it ever returns
-                    # anything, treat it as an extra chunk
-                    if self.request.streaming_callback is not None:
-                        self.request.streaming_callback(tail)
-                    else:
-                        self.chunks.append(tail)
-                # all the data has been decompressed, so we don't need to
-                # decompress again in _on_body
-                self._decompressor = None
-            self._on_body(b''.join(self.chunks))
-        else:
-            self.stream.read_bytes(length + 2,  # chunk ends with \r\n
-                                   self._on_chunk_data)
-
-    def _on_chunk_data(self, data):
-        assert data[-2:] == b"\r\n"
-        chunk = data[:-2]
+    def data_received(self, chunk):
         if self._decompressor:
             chunk = self._decompressor.decompress(chunk)
         if self.request.streaming_callback is not None:
             self.request.streaming_callback(chunk)
         else:
             self.chunks.append(chunk)
-        self.stream.read_until(b"\r\n", self._on_chunk_length)
 
 
 if __name__ == "__main__":
diff --git a/tornado/test/httpserver_test.py b/tornado/test/httpserver_test.py
index 5ca29935..19049991 100644
--- a/tornado/test/httpserver_test.py
+++ b/tornado/test/httpserver_test.py
@@ -4,8 +4,9 @@
 from __future__ import absolute_import, division, print_function, with_statement
 from tornado import httpclient, simple_httpclient, netutil
 from tornado.escape import json_decode, utf8, _unicode, recursive_unicode, native_str
+from tornado.http1connection import HTTP1Connection
 from tornado.httpserver import HTTPServer
-from tornado.httputil import HTTPHeaders
+from tornado.httputil import HTTPHeaders, HTTPStreamDelegate
 from tornado.iostream import IOStream
 from tornado.log import gen_log
 from tornado.netutil import ssl_options_to_context, Resolver
@@ -163,18 +164,7 @@ class MultipartTestHandler(RequestHandler):
                      })
 
 
-class RawRequestHTTPConnection(simple_httpclient._HTTPConnection):
-    def set_request(self, request):
-        self.__next_request = request
-
-    def _on_connect(self):
-        self.stream.write(self.__next_request)
-        self.__next_request = None
-        self.stream.read_until(b"\r\n\r\n", self._on_headers)
-
 # This test is also called from wsgi_test
-
-
 class HTTPConnectionTest(AsyncHTTPTestCase):
     def get_handlers(self):
         return [("/multipart", MultipartTestHandler),
@@ -184,23 +174,25 @@ class HTTPConnectionTest(AsyncHTTPTestCase):
         return Application(self.get_handlers())
 
     def raw_fetch(self, headers, body):
-        with closing(Resolver(io_loop=self.io_loop)) as resolver:
-            with closing(SimpleAsyncHTTPClient(self.io_loop,
-                                               resolver=resolver)) as client:
-                conn = RawRequestHTTPConnection(
-                    self.io_loop, client,
-                    httpclient._RequestProxy(
-                        httpclient.HTTPRequest(self.get_url("/")),
-                        dict(httpclient.HTTPRequest._DEFAULTS)),
-                    None, self.stop,
-                    1024 * 1024, resolver)
-                conn.set_request(
-                    b"\r\n".join(headers +
-                                 [utf8("Content-Length: %d\r\n" % len(body))]) +
-                    b"\r\n" + body)
-                response = self.wait()
-                response.rethrow()
-                return response
+        with closing(IOStream(socket.socket())) as stream:
+            stream.connect(('127.0.0.1', self.get_http_port()), self.stop)
+            self.wait()
+            stream.write(
+                b"\r\n".join(headers +
+                             [utf8("Content-Length: %d\r\n" % len(body))]) +
+                b"\r\n" + body)
+            chunks = []
+            test = self
+            class Delegate(HTTPStreamDelegate):
+                def data_received(self, chunk):
+                    chunks.append(chunk)
+
+                def finish(self):
+                    test.stop()
+            conn = HTTP1Connection(stream, None)
+            conn.process_response(Delegate(), method='GET')
+            self.wait()
+            return b''.join(chunks)
 
     def test_multipart_form(self):
         # Encodings here are tricky:  Headers are latin1, bodies can be
@@ -221,7 +213,7 @@ class HTTPConnectionTest(AsyncHTTPTestCase):
                 b"--1234567890--",
                 b"",
             ]))
-        data = json_decode(response.body)
+        data = json_decode(response)
         self.assertEqual(u("\u00e9"), data["header"])
         self.assertEqual(u("\u00e1"), data["argument"])
         self.assertEqual(u("\u00f3"), data["filename"])
diff --git a/tornado/test/simple_httpclient_test.py b/tornado/test/simple_httpclient_test.py
index ac98aaae..c10e7777 100644
--- a/tornado/test/simple_httpclient_test.py
+++ b/tornado/test/simple_httpclient_test.py
@@ -10,6 +10,7 @@ import re
 import socket
 import sys
 
+from tornado import gen
 from tornado.httpclient import AsyncHTTPClient
 from tornado.httputil import HTTPHeaders
 from tornado.ioloop import IOLoop
@@ -94,6 +95,18 @@ class HostEchoHandler(RequestHandler):
         self.write(self.request.headers["Host"])
 
 
+class NoContentLengthHandler(RequestHandler):
+    @gen.coroutine
+    def get(self):
+        # Emulate the old HTTP/1.0 behavior of returning a body with no
+        # content-length.  Tornado handles content-length at the framework
+        # level so we have to go around it.
+        stream = self.request.connection.stream
+        yield stream.write(b"HTTP/1.0 200 OK\r\n\r\n"
+                           b"hello")
+        stream.close()
+
+
 class SimpleHTTPClientTestMixin(object):
     def get_app(self):
         # callable objects to finish pending /trigger requests
@@ -112,6 +125,7 @@ class SimpleHTTPClientTestMixin(object):
             url("/see_other_post", SeeOtherPostHandler),
             url("/see_other_get", SeeOtherGetHandler),
             url("/host_echo", HostEchoHandler),
+            url("/no_content_length", NoContentLengthHandler),
         ], gzip=True)
 
     def test_singleton(self):
@@ -313,6 +327,10 @@ class SimpleHTTPClientTestMixin(object):
             self.triggers.popleft()()
             self.wait()
 
+    def test_no_content_length(self):
+        response = self.fetch("/no_content_length")
+        self.assertEquals(b"hello", response.body)
+
 
 class SimpleHTTPClientTestCase(SimpleHTTPClientTestMixin, AsyncHTTPTestCase):
     def setUp(self):
diff --git a/tornado/websocket.py b/tornado/websocket.py
index 1992b186..5e3bcd7d 100644
--- a/tornado/websocket.py
+++ b/tornado/websocket.py
@@ -860,8 +860,14 @@ class WebSocketClientConnection(simple_httpclient._HTTPConnection):
                 self.connect_future.set_exception(WebSocketError(
                     "Non-websocket response"))
 
-    def _handle_1xx(self, code):
-        assert code == 101
+    def headers_received(self, start_line, headers):
+        code = httputil.parse_response_start_line(start_line).code
+
+        if code != 101:
+            return super(WebSocketClientConnection, self).headers_received(
+                start_line, headers)
+
+        self.headers = headers
         assert self.headers['Upgrade'].lower() == 'websocket'
         assert self.headers['Connection'].lower() == 'upgrade'
         accept = WebSocketProtocol13.compute_accept_value(self.key)
@@ -874,7 +880,10 @@ class WebSocketClientConnection(simple_httpclient._HTTPConnection):
             self.io_loop.remove_timeout(self._timeout)
             self._timeout = None
 
+        self.stream.set_close_callback(self._on_close)
+
         self.connect_future.set_result(self)
+        return 'detach'
 
     def write_message(self, message, binary=False):
         """Sends a message to the WebSocket server."""

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/tornado/http1connection.py b/tornado/http1connection.py
index d0e91b82..7ee83161 100644
--- a/tornado/http1connection.py
+++ b/tornado/http1connection.py
@@ -563,11 +563,11 @@ class HTTP1Connection(httputil.HTTPConnection):
                     "Response with code %d should not have body" % code)
             content_length = 0
 
         if content_length is not None:
             return self._read_fixed_body(content_length, delegate)
-        if headers.get("Transfer-Encoding") == "chunked":
+        if headers.get("Transfer-Encoding", "").lower() == "chunked":
             return self._read_chunked_body(delegate)
         if self.is_client:
             return self._read_body_until_close(delegate)
         return None
 

```

## ODIS candidates: 8 total, path=small, tiers={'full': 8, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee tornado/concurrent.py:43 Future | class Future(object):
```python
  44      """Placeholder for an asynchronous result.
  45  
  46      Similar to `concurrent.futures.Future`, but not thread-safe (and
  47      therefore faster for use with single-threaded event loops.
  48  
  49      In addition to ``exception`` and ``set_exception``, methods ``exc_info``
  50      and ``set_exc_info`` are supported to capture tracebacks in Python 2.
  51      The traceback is automatically available in Python 3, but in the
  52      Python 2 futures backport this information is discarded.
  53      This functionality was previously available in a separate class
  54      ``TracebackFuture``, which is now a deprecated alias for this class.
  55      """
  56      def __init__(self):
  57          self._done = False
  58          self._result = None
  59          self._exception = None
  60          self._exc_info = None
  61          self._callbacks = []
  62  
  63      def cancel(self):
  64          return False
  65  
  66      def cancelled(self):
  67          return False
  68  
```
- [full] callee tornado/escape.py:91 json_decode | def json_decode(value):
```python
  81      """JSON-encodes the given Python object."""
  82      # JSON permits but does not require forward slashes to be escaped.
  83      # This is useful when json data is emitted in a <script> tag
  84      # in HTML, as it prevents </script> tags from prematurely terminating
  85      # the javscript.  Some json libraries do this escaping by default,
  86      # although python's standard library does not, so we do it here.
  87      # http://stackoverflow.com/questions/1580647/json-why-are-forward-slashes-escaped
  88      return json.dumps(value).replace("</", "<\\/")
  89  
  90  
  91  def json_decode(value):
  92      """Returns Python objects for the given JSON string."""
  93      return json.loads(to_basestring(value))
  94  
  95  
  96  def squeeze(value):
  97      """Replace all sequences of whitespace chars with a single space."""
  98      return re.sub(r"[\x00-\x20]+", " ", value).strip()
  99  
 100  
 101  def url_escape(value, plus=True):
```
- [full] callee tornado/escape.py:193 utf8 | def utf8(value):
```python
 183                             encoding='latin1', errors='strict')
 184          encoded = {}
 185          for k, v in result.items():
 186              encoded[k] = [i.encode('latin1') for i in v]
 187          return encoded
 188  
 189  
 190  _UTF8_TYPES = (bytes_type, type(None))
 191  
 192  
 193  def utf8(value):
 194      """Converts a string argument to a byte string.
 195  
 196      If the argument is already a byte string or None, it is returned unchanged.
 197      Otherwise it must be a unicode string and is encoded as utf8.
 198      """
 199      if isinstance(value, _UTF8_TYPES):
 200          return value
 201      if not isinstance(value, unicode_type):
 202          raise TypeError(
 203              "Expected bytes, unicode, or None; got %r" % type(value)
```
- [full] callee tornado/httpclient.py:497 HTTPError | class HTTPError(Exception):
```python
 499  
 500      Attributes:
 501  
 502      * ``code`` - HTTP error integer error code, e.g. 404.  Error code 599 is
 503        used when no HTTP response was received, e.g. for a timeout.
 504  
 505      * ``response`` - `HTTPResponse` object, if any.
 506  
 507      Note that if ``follow_redirects`` is False, redirects become HTTPErrors,
 508      and you can look at ``error.response.headers['Location']`` to see the
 509      destination of the redirect.
 510      """
 511      def __init__(self, code, message=None, response=None):
 512          self.code = code
 513          message = message or httputil.responses.get(code, "Unknown")
 514          self.response = response
 515          Exception.__init__(self, "HTTP %d: %s" % (self.code, message))
 516  
 517  
 518  class _RequestProxy(object):
 519      """Combines an object with a dictionary of defaults.
 520  
 521      Used internally by AsyncHTTPClient implementations.
 522      """
 523      def __init__(self, request, defaults):
```
- [full] callee tornado/iostream.py:668 IOStream | class IOStream(BaseIOStream):
```python
 697              stream.read_bytes(int(headers[b"Content-Length"]), on_body)
 698  
 699          def on_body(data):
 700              print data
 701              stream.close()
 702              tornado.ioloop.IOLoop.instance().stop()
 703  
 704          s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
 705          stream = tornado.iostream.IOStream(s)
 706          stream.connect(("friendfeed.com", 80), send_request)
 707          tornado.ioloop.IOLoop.instance().start()
 708      """
 709      def __init__(self, socket, *args, **kwargs):
 710          self.socket = socket
 711          self.socket.setblocking(False)
 712          super(IOStream, self).__init__(*args, **kwargs)
 713  
 714      def fileno(self):
 715          return self.socket
 716  
 717      def close_fd(self):
 718          self.socket.close()
 719          self.socket = None
 720  
 721      def get_fd_error(self):
```
- [full] caller tornado/simple_httpclient.py:122 call to _HTTPConnection | _HTTPConnection(self.io_loop, self, request, release_callback,
```python
 114                  if key not in self.waiting:
 115                      continue
 116                  self._remove_timeout(key)
 117                  self.active[key] = (request, callback)
 118                  release_callback = functools.partial(self._release_fetch, key)
 119                  self._handle_request(request, release_callback, callback)
 120  
 121      def _handle_request(self, request, release_callback, final_callback):
 122          _HTTPConnection(self.io_loop, self, request, release_callback,
 123                          final_callback, self.max_buffer_size, self.resolver)
 124  
 125      def _release_fetch(self, key):
 126          del self.active[key]
 127          self._process_queue()
 128  
 129      def _remove_timeout(self, key):
 130          if key in self.waiting:
```
- [full] callee tornado/util.py:33 GzipDecompressor | class GzipDecompressor(object):
```python
  27              raise AttributeError(name)
  28  
  29      def __setattr__(self, name, value):
  30          self[name] = value
  31  
  32  
  33  class GzipDecompressor(object):
  34      """Streaming gzip decompressor.
  35  
  36      The interface is like that of `zlib.decompressobj` (without the
  37      optional arguments, but it understands gzip headers and checksums.
  38      """
  39      def __init__(self):
  40          # Magic parameter makes zlib module understand gzip header
  41          # http://stackoverflow.com/questions/1838699/how-can-i-decompress-a-gzip-stream-with-zlib
  42          # This works on cpython and pypy, but not jython.
  43          self.decompressobj = zlib.decompressobj(16 + zlib.MAX_WBITS)
  44  
  45      def decompress(self, value):
  46          """Decompress a chunk, returning newly-available data.
  47  
  48          Some data may be buffered for later processing; `flush` must
  49          be called when there is no more input data to ensure that
  50          all data was processed.
  51          """
```
- [full] callee tornado/web.py:1733 HTTPError | class HTTPError(Exception):
```python
1740      :arg int status_code: HTTP status code.  Must be listed in
1741          `httplib.responses <http.client.responses>` unless the ``reason``
1742          keyword argument is given.
1743      :arg string log_message: Message to be written to the log for this error
1744          (will not be shown to the user unless the `Application` is in debug
1745          mode).  May contain ``%s``-style placeholders, which will be filled
1746          in with remaining positional parameters.
1747      :arg string reason: Keyword-only argument.  The HTTP "reason" phrase
1748          to pass in the status line along with ``status_code``.  Normally
1749          determined automatically from ``status_code``, but can be used
1750          to use a non-standard numeric code.
1751      """
1752      def __init__(self, status_code, log_message=None, *args, **kwargs):
1753          self.status_code = status_code
1754          self.log_message = log_message
1755          self.args = args
1756          self.reason = kwargs.get('reason', None)
1757  
1758      def __str__(self):
1759          message = "HTTP %d: %s" % (
1760              self.status_code,
1761              self.reason or httputil.responses.get(self.status_code, 'Unknown'))
1762          if self.log_message:
1763              return message + " (" + (self.log_message % self.args) + ")"
1764          else:
```
