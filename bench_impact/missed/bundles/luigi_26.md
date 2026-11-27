# luigi#26

Commit message of the reviewed change: Support running a remote hadoop jar command

Oracle (fix location at buggy_commit): [{'file': 'luigi/contrib/hadoop_jar.py', 'line_start': 86, 'line_end': 86}]

## Reviewed diff (introducing commit)
```diff
diff --git a/luigi/contrib/hadoop_jar.py b/luigi/contrib/hadoop_jar.py
index 09bc100..2b31554 100644
--- a/luigi/contrib/hadoop_jar.py
+++ b/luigi/contrib/hadoop_jar.py
@@ -64,23 +64,40 @@ class HadoopJarJobRunner(luigi.contrib.hadoop.JobRunner):
         pass
 
     def run_job(self, job):
+        ssh_config = job.ssh()
+        if ssh_config:
+            host = ssh_config.get("host", None)
+            key_file = ssh_config.get("key_file", None)
+            username = ssh_config.get("username", None)
+            if not host or not key_file or not username or not job.jar():
+                raise Exception("missing some config for HadoopRemoteJarJobRunner")
+            arglist = ['ssh', '-i', key_file,
+                       '-o', 'BatchMode=yes']  # no password prompts etc
+            if ssh_config.get("no_host_key_check", False):
+                arglist += ['-o', 'UserKnownHostsFile=/dev/null',
+                            '-o', 'StrictHostKeyChecking=no']
+            arglist.append('%s@%s' % (username, host))
+        else:
+            arglist = []
+            if not job.jar() or not os.path.exists(job.jar()):
+                logger.error("Can't find jar: %s, full path %s", job.jar(), os.path.abspath(job.jar()))
+                raise Exception("job jar does not exist")
+
         # TODO(jcrobak): libjars, files, etc. Can refactor out of
         # hadoop.HadoopJobRunner
-        if not job.jar() or not os.path.exists(job.jar()):
-            logger.error("Can't find jar: %s, full path %s", job.jar(), os.path.abspath(job.jar()))
-            raise Exception("job jar does not exist")
-        arglist = luigi.contrib.hdfs.load_hadoop_cmd() + ['jar', job.jar()]
+        hadoop_arglist = luigi.contrib.hdfs.load_hadoop_cmd() + ['jar', job.jar()]
         if job.main():
-            arglist.append(job.main())
+            hadoop_arglist.append(job.main())
 
         jobconfs = job.jobconfs()
 
         for jc in jobconfs:
-            arglist += ['-D' + jc]
+            hadoop_arglist += ['-D' + jc]
 
         (tmp_files, job_args) = fix_paths(job)
 
-        arglist += job_args
+        hadoop_arglist += job_args
+        arglist.extend(hadoop_arglist)
 
         luigi.contrib.hadoop.run_and_track_hadoop_job(arglist)
 
@@ -116,6 +133,13 @@ class HadoopJarJobTask(luigi.contrib.hadoop.BaseHadoopJobTask):
         """
         return True
 
+    def ssh(self):
+        """
+        Set this to run hadoop command remotely via ssh. It needs to be a dict that looks like
+        {"host": "myhost", "key_file": None, "username": None, ["no_host_key_check": False]}
+        """
+        return None
+
     def args(self):
         """
         Returns an array of args to pass to the job (after hadoop jar <jar> <main>).

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/luigi/contrib/hadoop_jar.py b/luigi/contrib/hadoop_jar.py
index 1419c54..3b352b2 100644
--- a/luigi/contrib/hadoop_jar.py
+++ b/luigi/contrib/hadoop_jar.py
@@ -81,11 +81,13 @@ class HadoopJarJobRunner(luigi.contrib.hadoop.JobRunner):
                 arglist += ['-o', 'UserKnownHostsFile=/dev/null',
                             '-o', 'StrictHostKeyChecking=no']
             arglist.append('{}@{}'.format(username, host))
         else:
             arglist = []
-            if not job.jar() or not os.path.exists(job.jar()):
+            if not job.jar():
+                raise HadoopJarJobError("Jar not defined")
+            if not os.path.exists(job.jar()):
                 logger.error("Can't find jar: %s, full path %s", job.jar(), os.path.abspath(job.jar()))
                 raise HadoopJarJobError("job jar does not exist")
 
         # TODO(jcrobak): libjars, files, etc. Can refactor out of
         # hadoop.HadoopJobRunner

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
