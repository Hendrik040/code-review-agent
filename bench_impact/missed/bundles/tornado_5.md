# tornado#5

Commit message of the reviewed change: ioloop: Factor out the math of PeriodicCallback for easier testing

Oracle (fix location at buggy_commit): [{'file': 'tornado/ioloop.py', 'line_start': 1221, 'line_end': 1221}]

## Reviewed diff (introducing commit)
```diff
diff --git a/tornado/ioloop.py b/tornado/ioloop.py
index f6ec177b..45d2d223 100644
--- a/tornado/ioloop.py
+++ b/tornado/ioloop.py
@@ -1213,11 +1213,11 @@ class PeriodicCallback(object):
 
     def _schedule_next(self):
         if self._running:
-            current_time = self.io_loop.time()
-
-            if self._next_timeout <= current_time:
-                callback_time_sec = self.callback_time / 1000.0
-                self._next_timeout += (math.floor((current_time - self._next_timeout) /
-                                                  callback_time_sec) + 1) * callback_time_sec
-
+            self._update_next(self.io_loop.time())
             self._timeout = self.io_loop.add_timeout(self._next_timeout, self._run)
+
+    def _update_next(self, current_time):
+        if self._next_timeout <= current_time:
+            callback_time_sec = self.callback_time / 1000.0
+            self._next_timeout += (math.floor((current_time - self._next_timeout) /
+                                              callback_time_sec) + 1) * callback_time_sec
diff --git a/tornado/test/ioloop_test.py b/tornado/test/ioloop_test.py
index 09f71c5d..a165ce71 100644
--- a/tornado/test/ioloop_test.py
+++ b/tornado/test/ioloop_test.py
@@ -789,6 +789,44 @@ class TestPeriodicCallback(unittest.TestCase):
         io_loop.close()
 
 
+class TestPeriodicCallbackMath(unittest.TestCase):
+    def simulate_calls(self, pc, durations):
+        """Simulate a series of calls to the PeriodicCallback.
+
+        Pass a list of call durations in seconds. This method
+        returns the times at which each call would be made.
+        """
+        calls = []
+        now = 1000
+        pc._next_timeout = now
+        for d in durations:
+            pc._update_next(now)
+            calls.append(pc._next_timeout)
+            now = pc._next_timeout + d
+        return calls
+
+    def test_basic(self):
+        pc = PeriodicCallback(None, 10000)
+        self.assertEqual(self.simulate_calls(pc, [0] * 5),
+                         [1010, 1020, 1030, 1040, 1050])
+
+    def test_overrun(self):
+        # If a call runs for too long, we skip entire cycles to get
+        # back on schedule.
+        call_durations = [9, 9, 10, 11, 20, 20, 35, 35, 0, 0, 0]
+        expected = [
+            1010, 1020, 1030,  # first 3 calls on schedule
+            1050, 1070,  # next 2 delayed one cycle
+            1100, 1130,  # next 2 delayed 2 cycles
+            1170, 1210,  # next 2 delayed 3 cycles
+            1220, 1230,  # then back on schedule.
+        ]
+
+        pc = PeriodicCallback(None, 10000)
+        self.assertEqual(self.simulate_calls(pc, call_durations),
+                         expected)
+
+
 class TestIOLoopConfiguration(unittest.TestCase):
     def run_python(self, *statements):
         statements = [

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/tornado/ioloop.py b/tornado/ioloop.py
index 45d2d223..48700139 100644
--- a/tornado/ioloop.py
+++ b/tornado/ioloop.py
@@ -1215,9 +1215,29 @@ class PeriodicCallback(object):
         if self._running:
             self._update_next(self.io_loop.time())
             self._timeout = self.io_loop.add_timeout(self._next_timeout, self._run)
 
     def _update_next(self, current_time):
+        callback_time_sec = self.callback_time / 1000.0
         if self._next_timeout <= current_time:
-            callback_time_sec = self.callback_time / 1000.0
+            # The period should be measured from the start of one call
+            # to the start of the next. If one call takes too long,
+            # skip cycles to get back to a multiple of the original
+            # schedule.
             self._next_timeout += (math.floor((current_time - self._next_timeout) /
                                               callback_time_sec) + 1) * callback_time_sec
+        else:
+            # If the clock moved backwards, ensure we advance the next
+            # timeout instead of recomputing the same value again.
+            # This may result in long gaps between callbacks if the
+            # clock jumps backwards by a lot, but the far more common
+            # scenario is a small NTP adjustment that should just be
+            # ignored.
+            #
+            # Note that on some systems if time.time() runs slower
+            # than time.monotonic() (most common on windows), we
+            # effectively experience a small backwards time jump on
+            # every iteration because PeriodicCallback uses
+            # time.time() while asyncio schedules callbacks using
+            # time.monotonic().
+            # https://github.com/tornadoweb/tornado/issues/2333
+            self._next_timeout += callback_time_sec

```

## ODIS candidates: 1 total, path=small, tiers={'full': 1, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee tornado/ioloop.py:1157 PeriodicCallback | class PeriodicCallback(object):
```python
1160      The callback is called every ``callback_time`` milliseconds.
1161      Note that the timeout is given in milliseconds, while most other
1162      time-related functions in Tornado use seconds.
1163  
1164      If the callback runs for longer than ``callback_time`` milliseconds,
1165      subsequent invocations will be skipped to get back on schedule.
1166  
1167      `start` must be called after the `PeriodicCallback` is created.
1168  
1169      .. versionchanged:: 5.0
1170         The ``io_loop`` argument (deprecated since version 4.1) has been removed.
1171      """
1172      def __init__(self, callback, callback_time):
1173          self.callback = callback
1174          if callback_time <= 0:
1175              raise ValueError("Periodic callback must have a positive callback_time")
1176          self.callback_time = callback_time
1177          self._running = False
1178          self._timeout = None
1179  
1180      def start(self):
1181          """Starts the timer."""
1182          # Looking up the IOLoop here allows to first instantiate the
1183          # PeriodicCallback in another thread, then start it using
1184          # IOLoop.add_callback().
```
