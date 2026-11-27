# black#16

Commit message of the reviewed change: Fix missing leading slash due to `relative_to()` resolution

Oracle (fix location at buggy_commit): [{'file': 'black.py', 'line_start': 2948, 'line_end': 2948}]

## Reviewed diff (introducing commit)
```diff
diff --git a/black.py b/black.py
index b3b37ef..e59a1e5 100644
--- a/black.py
+++ b/black.py
@@ -2826,7 +2826,7 @@ def gen_python_files_in_dir(
     """
     assert root.is_absolute(), f"INTERNAL ERROR: `root` must be absolute but is {root}"
     for child in path.iterdir():
-        normalized_path = child.resolve().relative_to(root).as_posix()
+        normalized_path = "/" + child.resolve().relative_to(root).as_posix()
         if child.is_dir():
             normalized_path += "/"
         exclude_match = exclude.search(normalized_path)

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/black.py b/black.py
index 9d9bada..e3b3882 100644
--- a/black.py
+++ b/black.py
@@ -2939,15 +2939,28 @@ def gen_python_files_in_dir(
     report: "Report",
 ) -> Iterator[Path]:
     """Generate all files under `path` whose paths are not excluded by the
     `exclude` regex, but are included by the `include` regex.
 
+    Symbolic links pointing outside of the root directory are ignored.
+
     `report` is where output about exclusions goes.
     """
     assert root.is_absolute(), f"INTERNAL ERROR: `root` must be absolute but is {root}"
     for child in path.iterdir():
-        normalized_path = "/" + child.resolve().relative_to(root).as_posix()
+        try:
+            normalized_path = "/" + child.resolve().relative_to(root).as_posix()
+        except ValueError:
+            if child.is_symlink():
+                report.path_ignored(
+                    child,
+                    "is a symbolic link that points outside of the root directory",
+                )
+                continue
+
+            raise
+
         if child.is_dir():
             normalized_path += "/"
         exclude_match = exclude.search(normalized_path)
         if exclude_match and exclude_match.group(0):
             report.path_ignored(child, f"matches the --exclude regular expression")

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
