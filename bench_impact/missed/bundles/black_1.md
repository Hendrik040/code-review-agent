# black#1

Commit message of the reviewed change: don't run more than 61 workers on Windows (#838)

Oracle (fix location at buggy_commit): [{'file': 'black.py', 'line_start': 621, 'line_end': 621}, {'file': 'black.py', 'line_start': 636, 'line_end': 636}, {'file': 'black.py', 'line_start': 646, 'line_end': 646}]

## Reviewed diff (introducing commit)
```diff
diff --git a/README.md b/README.md
index afc9e8e..28c4fbe 100644
--- a/README.md
+++ b/README.md
@@ -986,6 +986,8 @@ More details can be found in [CONTRIBUTING](CONTRIBUTING.md).
 
 ### 19.5b0
 
+* don't crash when run on a Windows machine with more than 61 cores (#838)
+
 * remove unnecessary parentheses around `yield` expressions (#834)
 
 * add parentheses around long tuples in unpacking assignments (#832)
diff --git a/black.py b/black.py
index e7dce5b..18d60c0 100644
--- a/black.py
+++ b/black.py
@@ -440,22 +440,10 @@ def main(
             report=report,
         )
     else:
-        loop = asyncio.get_event_loop()
-        executor = ProcessPoolExecutor(max_workers=os.cpu_count())
-        try:
-            loop.run_until_complete(
-                schedule_formatting(
-                    sources=sources,
-                    fast=fast,
-                    write_back=write_back,
-                    mode=mode,
-                    report=report,
-                    loop=loop,
-                    executor=executor,
-                )
-            )
-        finally:
-            shutdown(loop)
+        reformat_many(
+            sources=sources, fast=fast, write_back=write_back, mode=mode, report=report
+        )
+
     if verbose or not quiet:
         bang = "💥 💔 💥" if report.return_code else "✨ 🍰 ✨"
         out(f"All done! {bang}")
@@ -497,6 +485,36 @@ def reformat_one(
         report.failed(src, str(exc))
 
 
+def reformat_many(
+    sources: Set[Path],
+    fast: bool,
+    write_back: WriteBack,
+    mode: FileMode,
+    report: "Report",
+) -> None:
+    """Reformat multiple files using a ProcessPoolExecutor."""
+    loop = asyncio.get_event_loop()
+    worker_count = os.cpu_count()
+    if sys.platform == "win32":
+        # Work around https://bugs.python.org/issue26903
+        worker_count = min(worker_count, 61)
+    executor = ProcessPoolExecutor(max_workers=worker_count)
+    try:
+        loop.run_until_complete(
+            schedule_formatting(
+                sources=sources,
+                fast=fast,
+                write_back=write_back,
+                mode=mode,
+                report=report,
+                loop=loop,
+                executor=executor,
+            )
+        )
+    finally:
+        shutdown(loop)
+
+
 async def schedule_formatting(
     sources: Set[Path],
     fast: bool,

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/black.py b/black.py
index 2a913fc..fc1597a 100644
--- a/black.py
+++ b/black.py
@@ -616,11 +616,18 @@ def reformat_many(
     loop = asyncio.get_event_loop()
     worker_count = os.cpu_count()
     if sys.platform == "win32":
         # Work around https://bugs.python.org/issue26903
         worker_count = min(worker_count, 61)
-    executor = ProcessPoolExecutor(max_workers=worker_count)
+    try:
+        executor = ProcessPoolExecutor(max_workers=worker_count)
+    except OSError:
+        # we arrive here if the underlying system does not support multi-processing
+        # like in AWS Lambda, in which case we gracefully fallback to the default
+        # mono-process Executor by using None
+        executor = None
+
     try:
         loop.run_until_complete(
             schedule_formatting(
                 sources=sources,
                 fast=fast,
@@ -631,21 +638,22 @@ def reformat_many(
                 executor=executor,
             )
         )
     finally:
         shutdown(loop)
-        executor.shutdown()
+        if executor is not None:
+            executor.shutdown()
 
 
 async def schedule_formatting(
     sources: Set[Path],
     fast: bool,
     write_back: WriteBack,
     mode: Mode,
     report: "Report",
     loop: asyncio.AbstractEventLoop,
-    executor: Executor,
+    executor: Optional[Executor],
 ) -> None:
     """Run formatting of `sources` in parallel using the provided `executor`.
 
     (Use ProcessPoolExecutors for actual parallelism.)
 

```

## ODIS candidates: 1 total, path=small, tiers={'full': 1, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee black.py:3497 shutdown | def shutdown(loop: BaseEventLoop) -> None:
```python
3487      )
3488  
3489  
3490  def cancel(tasks: Iterable[asyncio.Task]) -> None:
3491      """asyncio signal handler that cancels all `tasks` and reports to stderr."""
3492      err("Aborted!")
3493      for task in tasks:
3494          task.cancel()
3495  
3496  
3497  def shutdown(loop: BaseEventLoop) -> None:
3498      """Cancel all pending tasks on `loop`, wait for them, and close the loop."""
3499      try:
3500          if sys.version_info[:2] >= (3, 7):
3501              all_tasks = asyncio.all_tasks
3502          else:
3503              all_tasks = asyncio.Task.all_tasks
3504          # This part is borrowed from asyncio/runners.py in Python 3.7b2.
3505          to_cancel = [task for task in all_tasks(loop) if not task.done()]
3506          if not to_cancel:
3507              return
```
