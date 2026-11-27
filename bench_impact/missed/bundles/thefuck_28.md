# thefuck#28

Commit message of the reviewed change: #320 Add the `fix_file` rule

Oracle (fix location at buggy_commit): [{'file': 'thefuck/rules/fix_file.py', 'line_start': 3, 'line_end': 3}, {'file': 'thefuck/rules/fix_file.py', 'line_start': 23, 'line_end': 23}, {'file': 'thefuck/rules/fix_file.py', 'line_start': 26, 'line_end': 27}, {'file': 'thefuck/rules/fix_file.py', 'line_start': 63, 'line_end': 66}]

## Reviewed diff (introducing commit)
```diff
diff --git a/README.md b/README.md
index 8a6c8c1..c73b12f 100644
--- a/README.md
+++ b/README.md
@@ -146,6 +146,7 @@ using the matched rule and runs it. Rules enabled by default are as follows:
 * `docker_not_command` &ndash; fixes wrong docker commands like `docker tags`;
 * `dry` &ndash; fixes repetitions like `git git push`;
 * `fix_alt_space` &ndash; replaces Alt+Space with Space character;
+* `fix_file` &ndash; opens a file with an error in your `$EDITOR`;
 * `git_add` &ndash; fixes *"Did you forget to 'git add'?"*;
 * `git_branch_delete` &ndash; changes `git branch -d` to `git branch -D`;
 * `git_branch_list` &ndash; catches `git branch list` in place of `git branch` and removes created branch;
diff --git a/tests/rules/test_fix_file.py b/tests/rules/test_fix_file.py
new file mode 100644
index 0000000..c9411b4
--- /dev/null
+++ b/tests/rules/test_fix_file.py
@@ -0,0 +1,167 @@
+import pytest
+from thefuck.rules.fix_file import match, get_new_command
+from tests.utils import Command
+
+
+# (script, file, line, col (or None), stderr)
+tests = (
+('gcc a.c', 'a.c', 3, 1,
+"""
+a.c: In function 'main':
+a.c:3:1: error: expected expression before '}' token
+ }
+  ^
+"""),
+
+('clang a.c', 'a.c', 3, 1,
+"""
+a.c:3:1: error: expected expression
+}
+^
+"""),
+
+('perl a.pl', 'a.pl', 3, None,
+"""
+syntax error at a.pl line 3, at EOF
+Execution of a.pl aborted due to compilation errors.
+"""),
+
+('perl a.pl', 'a.pl', 2, None,
+"""
+Search pattern not terminated at a.pl line 2.
+"""),
+
+('sh a.sh', 'a.sh', 2, None,
+"""
+a.sh: line 2: foo: command not found
+"""),
+
+('zsh a.sh', 'a.sh', 2, None,
+"""
+a.sh:2: command not found: foo
+"""),
+
+('bash a.sh', 'a.sh', 2, None,
+"""
+a.sh: line 2: foo: command not found
+"""),
+
+('rustc a.rs', 'a.rs', 2, 5,
+"""
+a.rs:2:5: 2:6 error: unexpected token: `+`
+a.rs:2     +
+           ^
+"""),
+
+('cargo build', 'src/lib.rs', 3, 5,
+"""
+   Compiling test v0.1.0 (file:///tmp/fix-error/test)
+   src/lib.rs:3:5: 3:6 error: unexpected token: `+`
+   src/lib.rs:3     +
+                    ^
+Could not compile `test`.
+
+To learn more, run the command again with --verbose.
+"""),
+
+('python a.py', 'a.py', 2, None,
+"""
+  File "a.py", line 2
+      +
+          ^
+SyntaxError: invalid syntax
+"""),
+
+('python a.py', 'a.py', 8, None,
+"""
+Traceback (most recent call last):
+  File "a.py", line 8, in <module>
+    match("foo")
+  File "a.py", line 5, in match
+    m = re.search(None, command)
+  File "/usr/lib/python3.4/re.py", line 170, in search
+    return _compile(pattern, flags).search(string)
+  File "/usr/lib/python3.4/re.py", line 293, in _compile
+    raise TypeError("first argument must be string or compiled pattern")
+TypeError: first argument must be string or compiled pattern
+"""
+),
+
+('ruby a.rb', 'a.rb', 3, None,
+"""
+a.rb:3: syntax error, unexpected keyword_end
+"""),
+
+('lua a.lua', 'a.lua', 2, None,
+"""
+lua: a.lua:2: unexpected symbol near '+'
+"""),
+
+('fish a.sh', '/tmp/fix-error/a.sh', 2, None,
+"""
+fish: Unknown command 'foo'
+/tmp/fix-error/a.sh (line 2): foo
+                              ^
+"""),
+
+('./a', './a', 2, None,
+"""
+awk: ./a:2: BEGIN { print "Hello, world!" + }
+awk: ./a:2:                                 ^ syntax error
+"""),
+
+('llc a.ll', 'a.ll', 1, None,
+"""
+llc: a.ll:1:1: error: expected top-level entity
++
+^
+"""),
+
+('go build a.go', 'a.go', 1, None,
+"""
+can't load package:
+a.go:1:1: expected 'package', found '+'
+"""),
+
+('make', 'Makefile', 2, None,
+"""
+bidule
+make: bidule: Command not found
+Makefile:2: recipe for target 'target' failed
+make: *** [target] Error 127
+"""),
+
+('git st', '/home/martin/.config/git/config', 1, None,
+"""
+fatal: bad config file line 1 in /home/martin/.config/git/config
+"""),
+
+('node fuck.js asdf qwer', '/Users/pablo/Workspace/barebones/fuck.js', '2', 5,
+"""
+/Users/pablo/Workspace/barebones/fuck.js:2
+conole.log(arg);  // this should read console.log(arg);
+^
+ReferenceError: conole is not defined
+    at /Users/pablo/Workspace/barebones/fuck.js:2:5
+    at Array.forEach (native)
+    at Object.<anonymous> (/Users/pablo/Workspace/barebones/fuck.js:1:85)
+    at Module._compile (module.js:460:26)
+    at Object.Module._extensions..js (module.js:478:10)
+    at Module.load (module.js:355:32)
+    at Function.Module._load (module.js:310:12)
+    at Function.Module.runMain (module.js:501:10)
+    at startup (node.js:129:16)
+    at node.js:814:3
+"""),
+)
+
+
+@pytest.mark.parametrize('test', tests)
+def test_match(test):
+    assert match(Command(stderr=test[4]), None)
+
+
+@pytest.mark.parametrize('test', tests)
+def test_get_new_command(monkeypatch, test):
+    assert (get_new_command(Command(script=test[0], stderr=test[4]), None) ==
+        '$EDITOR {} +{} && {}'.format(test[1], test[2], test[0]))
diff --git a/thefuck/rules/fix_file.py b/thefuck/rules/fix_file.py
new file mode 100644
index 0000000..4b7626b
--- /dev/null
+++ b/thefuck/rules/fix_file.py
@@ -0,0 +1,61 @@
+import re
+from thefuck.utils import memoize
+from thefuck import shells
+
+
+patterns = (
+        # js, node:
+        '^    at {file}:{line}:{col}',
+        # cargo:
+        '^   {file}:{line}:{col}',
+        # python, thefuck:
+        '^  File "{file}", line {line}',
+        # awk:
+        '^awk: {file}:{line}:',
+        # git
+        '^fatal: bad config file line {line} in {file}',
+        # llc:
+        '^llc: {file}:{line}:{col}:',
+        # lua:
+        '^lua: {file}:{line}:',
+        # fish:
+        '^{file} \(line {line}\):',
+        # bash, sh, ssh:
+        '^{file}: line {line}: ',
+        # ghc, make, ruby, zsh:
+        '^{file}:{line}:',
+        # cargo, clang, gcc, go, rustc:
+        '^{file}:{line}:{col}',
+        # perl:
+        'at {file} line {line}',
+    )
+
+
+# for the sake of readability do not use named groups above
+def _make_pattern(pattern):
+    pattern = pattern.replace('{file}', '(?P<file>[^:\n]+)')
+    pattern = pattern.replace('{line}', '(?P<line>[0-9]+)')
+    pattern = pattern.replace('{col}',  '(?P<col>[0-9]+)')
+    return re.compile(pattern, re.MULTILINE)
+patterns = [_make_pattern(p) for p in patterns]
+
+
+@memoize
+def _search(stderr):
+    for pattern in patterns:
+        m = re.search(pattern, stderr)
+        if m:
+            return m
+
+
+def match(command, settings):
+    return _search(command.stderr)
+
+
+def get_new_command(command, settings):
+    m = _search(command.stderr)
+
+    # Note: there does not seem to be a standard for columns, so they are just
+    # ignored for now
+    return shells.and_('$EDITOR {} +{}'.format(m.group('file'), m.group('line')),
+                       command.script)

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/thefuck/rules/fix_file.py b/thefuck/rules/fix_file.py
index a64b10c..caa59f0 100644
--- a/thefuck/rules/fix_file.py
+++ b/thefuck/rules/fix_file.py
@@ -1,11 +1,12 @@
 import re
 import os
-from thefuck.utils import memoize
+from thefuck.utils import memoize, wrap_settings
 from thefuck import shells
 
 
+# order is important: only the first match is considered
 patterns = (
         # js, node:
         '^    at {file}:{line}:{col}',
         # cargo:
         '^   {file}:{line}:{col}',
@@ -18,17 +19,17 @@ patterns = (
         # llc:
         '^llc: {file}:{line}:{col}:',
         # lua:
         '^lua: {file}:{line}:',
         # fish:
-        '^{file} \(line {line}\):',
+        '^{file} \\(line {line}\\):',
         # bash, sh, ssh:
         '^{file}: line {line}: ',
-        # ghc, make, ruby, zsh:
-        '^{file}:{line}:',
         # cargo, clang, gcc, go, pep8, rustc:
         '^{file}:{line}:{col}',
+        # ghc, make, ruby, zsh:
+        '^{file}:{line}:',
         # perl:
         'at {file} line {line}',
     )
 
 
@@ -54,14 +55,23 @@ def match(command, settings):
         return False
 
     return _search(command.stderr) or _search(command.stdout)
 
 
+@wrap_settings({'fixlinecmd': '{editor} {file} +{line}',
+                'fixcolcmd': None})
 def get_new_command(command, settings):
     m = _search(command.stderr) or _search(command.stdout)
 
     # Note: there does not seem to be a standard for columns, so they are just
-    # ignored for now
-    editor_call = '{} {} +{}'.format(os.environ['EDITOR'],
-                                     m.group('file'),
-                                     m.group('line'))
+    # ignored by default
+    if settings.fixcolcmd and 'col' in m.groupdict():
+        editor_call = settings.fixcolcmd.format(editor=os.environ['EDITOR'],
+                                                file=m.group('file'),
+                                                line=m.group('line'),
+                                                col=m.group('col'))
+    else:
+        editor_call = settings.fixlinecmd.format(editor=os.environ['EDITOR'],
+                                                 file=m.group('file'),
+                                                 line=m.group('line'))
+
     return shells.and_(editor_call, command.script)

```

## ODIS candidates: 362 total, path=jev, tiers={'full': 0, 'signature': 1, 'counted': 361}
Shown to the reviewer (full = whole snippet, signature = one line):
- [signature] callee tests/utils.py:5 Command | def Command(script='', stdout='', stderr=''):
Counted only (361), first 15:
- caller tests/rules/test_apt_get.py:14 call to match
- caller tests/rules/test_apt_get.py:25 call to match
- caller tests/rules/test_apt_get.py:33 call to match
- caller tests/rules/test_apt_get.py:43 call to get_new_command
- caller tests/rules/test_apt_get.py:57 call to get_new_command
- caller tests/rules/test_brew_install.py:32 call to match
- caller tests/rules/test_brew_install.py:34 call to match
- caller tests/rules/test_brew_install.py:36 call to match
- caller tests/rules/test_brew_install.py:43 call to get_new_command
- caller tests/rules/test_brew_install.py:47 call to get_new_command
- caller tests/rules/test_brew_unknown_command.py:18 call to match
- caller tests/rules/test_brew_unknown_command.py:24 call to get_new_command
- caller tests/rules/test_brew_unknown_command.py:27 call to get_new_command
- caller tests/rules/test_brew_unknown_command.py:20 call to match
- caller tests/rules/test_brew_upgrade.py:9 call to match
