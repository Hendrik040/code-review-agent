# thefuck#8

Commit message of the reviewed change: Slightly more comments

Oracle (fix location at buggy_commit): [{'file': 'thefuck/rules/dnf_no_such_command.py', 'line_start': 18, 'line_end': 21}, {'file': 'thefuck/rules/dnf_no_such_command.py', 'line_start': 29, 'line_end': 29}]

## Reviewed diff (introducing commit)
```diff
diff --git a/thefuck/rules/dnf_no_such_command.py b/thefuck/rules/dnf_no_such_command.py
index 27d353a..70c7939 100644
--- a/thefuck/rules/dnf_no_such_command.py
+++ b/thefuck/rules/dnf_no_such_command.py
@@ -15,6 +15,9 @@ def match(command):
 
 
 def _parse_operations(help_text_lines):
+    # The regex has to be a bytes-style regex since reading from a file
+    # like stdin returns a bytes-style object and a string-style regex
+    # wouldn't work.
     operation_regex = re.compile(b'^([a-z-]+) +', re.MULTILINE)
     return operation_regex.findall(help_text_lines)
 

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/thefuck/rules/dnf_no_such_command.py b/thefuck/rules/dnf_no_such_command.py
index 70c7939..9a70c4f 100644
--- a/thefuck/rules/dnf_no_such_command.py
+++ b/thefuck/rules/dnf_no_such_command.py
@@ -13,22 +13,19 @@ regex = re.compile(r'No such command: (.*)\.')
 def match(command):
     return 'no such command' in command.output.lower()
 
 
 def _parse_operations(help_text_lines):
-    # The regex has to be a bytes-style regex since reading from a file
-    # like stdin returns a bytes-style object and a string-style regex
-    # wouldn't work.
-    operation_regex = re.compile(b'^([a-z-]+) +', re.MULTILINE)
+    operation_regex = re.compile(r'^([a-z-]+) +', re.MULTILINE)
     return operation_regex.findall(help_text_lines)
 
 
 def _get_operations():
     proc = subprocess.Popen(["dnf", '--help'],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
-    lines = proc.stdout.read()
+    lines = proc.stdout.read().decode("utf-8")
 
     return _parse_operations(lines)
 
 
 @sudo_support

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
