# scrapy#24

Commit message of the reviewed change: Using CRLF as line marker according to http 1.1 definition

Oracle (fix location at buggy_commit): [{'file': 'scrapy/core/downloader/handlers/http11.py', 'line_start': 81, 'line_end': 81}, {'file': 'scrapy/core/downloader/handlers/http11.py', 'line_start': 95, 'line_end': 96}, {'file': 'scrapy/core/downloader/handlers/http11.py', 'line_start': 98, 'line_end': 99}]

## Reviewed diff (introducing commit)
```diff
diff --git a/scrapy/core/downloader/handlers/http11.py b/scrapy/core/downloader/handlers/http11.py
index 52eb35eb..617a68ea 100644
--- a/scrapy/core/downloader/handlers/http11.py
+++ b/scrapy/core/downloader/handlers/http11.py
@@ -66,12 +66,11 @@ class TunnelingTCP4ClientEndpoint(TCP4ClientEndpoint):
 
     def requestTunnel(self, protocol):
         """Asks the proxy to open a tunnel."""
-        tunnelReq = 'CONNECT %s:%s HTTP/1.1\n' % (self._tunneledHost,
+        tunnelReq = 'CONNECT %s:%s HTTP/1.1\r\n' % (self._tunneledHost,
                                                   self._tunneledPort)
         if self._proxyAuthHeader:
-            tunnelReq += 'Proxy-Authorization: %s \n\n' % self._proxyAuthHeader
-        else:
-            tunnelReq += '\n'
+            tunnelReq += 'Proxy-Authorization: %s\r\n' % self._proxyAuthHeader
+        tunnelReq += '\r\n'
         protocol.transport.write(tunnelReq)
         self._protocolDataReceived = protocol.dataReceived
         protocol.dataReceived = self.processProxyResponse

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/scrapy/core/downloader/handlers/http11.py b/scrapy/core/downloader/handlers/http11.py
index d81093a9..729b80b0 100644
--- a/scrapy/core/downloader/handlers/http11.py
+++ b/scrapy/core/downloader/handlers/http11.py
@@ -76,11 +76,11 @@ class TunnelingTCP4ClientEndpoint(TCP4ClientEndpoint):
     be improved as the CONNECT will be redundant if the connection associated
     with this endpoint comes from the pool and a CONNECT has already been issued
     for it.
     """
 
-    _responseMatcher = re.compile('HTTP/1\.. 200')
+    _responseMatcher = re.compile(b'HTTP/1\.. 200')
 
     def __init__(self, reactor, host, port, proxyConf, contextFactory,
                  timeout=30, bindAddress=None):
         proxyHost, proxyPort, self._proxyAuthHeader = proxyConf
         super(TunnelingTCP4ClientEndpoint, self).__init__(reactor, proxyHost,
@@ -90,15 +90,19 @@ class TunnelingTCP4ClientEndpoint(TCP4ClientEndpoint):
         self._tunneledPort = port
         self._contextFactory = contextFactory
 
     def requestTunnel(self, protocol):
         """Asks the proxy to open a tunnel."""
-        tunnelReq = 'CONNECT %s:%s HTTP/1.1\r\n' % (self._tunneledHost,
-                                                  self._tunneledPort)
+        tunnelReq = (
+            b'CONNECT ' +
+            to_bytes(self._tunneledHost, encoding='ascii') + b':' +
+            to_bytes(str(self._tunneledPort)) +
+            b' HTTP/1.1\r\n')
         if self._proxyAuthHeader:
-            tunnelReq += 'Proxy-Authorization: %s\r\n' % self._proxyAuthHeader
-        tunnelReq += '\r\n'
+            tunnelReq += \
+                b'Proxy-Authorization: ' + self._proxyAuthHeader + b'\r\n'
+        tunnelReq += b'\r\n'
         protocol.transport.write(tunnelReq)
         self._protocolDataReceived = protocol.dataReceived
         protocol.dataReceived = self.processProxyResponse
         self._protocol = protocol
         return protocol

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
