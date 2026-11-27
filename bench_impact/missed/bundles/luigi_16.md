# luigi#16

Commit message of the reviewed change: Enables task failure on worker death while assistant is running

Oracle (fix location at buggy_commit): [{'file': 'luigi/scheduler.py', 'line_start': 570, 'line_end': 570}]

## Reviewed diff (introducing commit)
```diff
diff --git a/luigi/scheduler.py b/luigi/scheduler.py
index a90628a..69c0aec 100644
--- a/luigi/scheduler.py
+++ b/luigi/scheduler.py
@@ -415,16 +415,7 @@ class SimpleTaskState(object):
         self._status_tasks[new_status][task.id] = task
         task.status = new_status
 
-    def prune(self, task, config, assistants):
-        remove = False
-
-        # Mark tasks with no remaining active stakeholders for deletion
-        if not task.stakeholders:
-            if task.remove is None:
-                logger.info("Task %r has stakeholders %r but none remain connected -> will remove "
-                            "task in %s seconds", task.id, task.stakeholders, config.remove_delay)
-                task.remove = time.time() + config.remove_delay
-
+    def fail_dead_worker_task(self, task, config, assistants):
         # If a running worker disconnects, tag all its jobs as FAILED and subject it to the same retry logic
         if task.status == RUNNING and task.worker_running and task.worker_running not in task.stakeholders | assistants:
             logger.info("Task %r is marked as running by disconnected worker %r -> marking as "
@@ -434,6 +425,16 @@ class SimpleTaskState(object):
             self.set_status(task, FAILED, config)
             task.retry = time.time() + config.retry_delay
 
+    def prune(self, task, config):
+        remove = False
+
+        # Mark tasks with no remaining active stakeholders for deletion
+        if not task.stakeholders:
+            if task.remove is None:
+                logger.info("Task %r has stakeholders %r but none remain connected -> will remove "
+                            "task in %s seconds", task.id, task.stakeholders, config.remove_delay)
+                task.remove = time.time() + config.remove_delay
+
         # Re-enable task after the disable time expires
         if task.status == DISABLED and task.scheduler_disable_time:
             if time.time() - fix_time(task.scheduler_disable_time) > config.disable_persist:
@@ -548,7 +549,8 @@ class CentralPlannerScheduler(Scheduler):
             necessary_tasks = ()
 
         for task in self._state.get_active_tasks():
-            if task.id not in necessary_tasks and self._state.prune(task, self._config, assistant_ids):
+            self._state.fail_dead_worker_task(task, self._config, assistant_ids)
+            if task.id not in necessary_tasks and self._state.prune(task, self._config):
                 remove_tasks.append(task.id)
 
         self._state.inactivate_tasks(remove_tasks)
diff --git a/test/central_planner_test.py b/test/central_planner_test.py
index bd11b40..4a9d9b9 100644
--- a/test/central_planner_test.py
+++ b/test/central_planner_test.py
@@ -226,6 +226,18 @@ class CentralPlannerTest(unittest.TestCase):
         self.sch.prune()
         self.assertFalse(list(self.sch.task_list('', '')))
 
+    def test_fail_job_from_dead_worker_with_live_assistant(self):
+        self.setTime(0)
+        self.sch.add_task(worker='X', task_id='A')
+        self.assertEqual('A', self.sch.get_work(worker='X')['task_id'])
+        self.sch.add_worker('Y', [('assistant', True)])
+
+        self.setTime(600)
+        self.sch.ping(worker='Y')
+        self.sch.prune()
+
+        self.assertEqual(['A'], list(self.sch.task_list('FAILED', '').keys()))
+
     def test_prune_done_tasks(self, expected=None):
         self.setTime(0)
         self.sch.add_task(worker=WORKER, task_id='A', status=DONE)

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/luigi/scheduler.py b/luigi/scheduler.py
index 8f5bead..3a08956 100644
--- a/luigi/scheduler.py
+++ b/luigi/scheduler.py
@@ -565,11 +565,12 @@ class CentralPlannerScheduler(Scheduler):
         else:
             necessary_tasks = ()
 
         for task in self._state.get_active_tasks():
             self._state.fail_dead_worker_task(task, self._config, assistant_ids)
-            if task.id not in necessary_tasks and self._state.prune(task, self._config):
+            removed = self._state.prune(task, self._config)
+            if removed and task.id not in necessary_tasks:
                 remove_tasks.append(task.id)
 
         self._state.inactivate_tasks(remove_tasks)
 
         logger.info("Done pruning task graph")

```

## ODIS candidates: 1 total, path=small, tiers={'full': 1, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee luigi/s3.py:285 list | def list(self, path):  # backwards compat
```python
 275          (bucket, key) = self._path_to_bucket_and_key(path)
 276  
 277          # grab and validate the bucket
 278          s3_bucket = self.s3.get_bucket(bucket, validate=True)
 279  
 280          key_path = self._add_path_delimiter(key)
 281          key_path_len = len(key_path)
 282          for item in s3_bucket.list(prefix=key_path):
 283              yield self._add_path_delimiter(path) + item.key[key_path_len:]
 284  
 285      def list(self, path):  # backwards compat
 286          key_path_len = len(self._add_path_delimiter(path))
 287          for item in self.listdir(path):
 288              yield item[key_path_len:]
 289  
 290      def isdir(self, path):
 291          """
 292          Is the parameter S3 path a directory?
 293          """
 294          (bucket, key) = self._path_to_bucket_and_key(path)
 295  
```
