# cookiecutter#1

Commit message of the reviewed change: Use open context manager to read context_file in generate

Oracle (fix location at buggy_commit): [{'file': 'cookiecutter/generate.py', 'line_start': 85, 'line_end': 85}]

## Reviewed diff (introducing commit)
```diff
diff --git a/cookiecutter/generate.py b/cookiecutter/generate.py
index 7a4d461..aa98734 100755
--- a/cookiecutter/generate.py
+++ b/cookiecutter/generate.py
@@ -87,9 +87,9 @@ def generate_context(context_file='cookiecutter.json', default_context=None,
 
     context = {}
 
-    file_handle = open(context_file)
     try:
-        obj = json.load(file_handle, object_pairs_hook=OrderedDict)
+        with open(context_file) as file_handle:
+            obj = json.load(file_handle, object_pairs_hook=OrderedDict)
     except ValueError as e:
         # JSON decoding error.  Let's throw a new exception that is more
         # friendly for the developer or user.

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/cookiecutter/generate.py b/cookiecutter/generate.py
index 37365a4..c526b97 100644
--- a/cookiecutter/generate.py
+++ b/cookiecutter/generate.py
@@ -80,11 +80,11 @@ def generate_context(
     :param extra_context: Dictionary containing configuration overrides
     """
     context = OrderedDict([])
 
     try:
-        with open(context_file) as file_handle:
+        with open(context_file, encoding='utf-8') as file_handle:
             obj = json.load(file_handle, object_pairs_hook=OrderedDict)
     except ValueError as e:
         # JSON decoding error.  Let's throw a new exception that is more
         # friendly for the developer or user.
         full_fpath = os.path.abspath(context_file)

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
