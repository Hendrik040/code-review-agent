# thefuck#12

Commit message of the reviewed change: #475: Try to use already used executable in `no_command`

Oracle (fix location at buggy_commit): [{'file': 'thefuck/rules/no_command.py', 'line_start': 3, 'line_end': 3}, {'file': 'thefuck/rules/no_command.py', 'line_start': 9, 'line_end': 9}]

## Reviewed diff (introducing commit)
```diff
diff --git a/tests/rules/test_history.py b/tests/rules/test_history.py
index a9b2505..87129f7 100644
--- a/tests/rules/test_history.py
+++ b/tests/rules/test_history.py
@@ -3,38 +3,23 @@ from thefuck.rules.history import match, get_new_command
 from tests.utils import Command
 
 
-@pytest.fixture
-def history(mocker):
-    return mocker.patch('thefuck.shells.shell.get_history',
-                        return_value=['le cat', 'fuck', 'ls cat',
-                                      'diff x', 'nocommand x'])
+@pytest.fixture(autouse=True)
+def history_without_current(mocker):
+    return mocker.patch(
+        'thefuck.rules.history.get_valid_history_without_current',
+        return_value=['ls cat', 'diff x'])
 
 
-@pytest.fixture
-def alias(mocker):
-    return mocker.patch('thefuck.rules.history.get_alias',
-                        return_value='fuck')
-
-
-@pytest.fixture
-def callables(mocker):
-    return mocker.patch('thefuck.rules.history.get_all_executables',
-                        return_value=['diff', 'ls'])
-
-
-@pytest.mark.usefixtures('history', 'callables', 'no_memoize', 'alias')
 @pytest.mark.parametrize('script', ['ls cet', 'daff x'])
 def test_match(script):
     assert match(Command(script=script))
 
 
-@pytest.mark.usefixtures('history', 'callables', 'no_memoize', 'alias')
 @pytest.mark.parametrize('script', ['apt-get', 'nocommand y'])
 def test_not_match(script):
     assert not match(Command(script=script))
 
 
-@pytest.mark.usefixtures('history', 'callables', 'no_memoize', 'alias')
 @pytest.mark.parametrize('script, result', [
     ('ls cet', 'ls cat'),
     ('daff x', 'diff x')])
diff --git a/tests/rules/test_no_command.py b/tests/rules/test_no_command.py
index a8a21cb..5249c2b 100644
--- a/tests/rules/test_no_command.py
+++ b/tests/rules/test_no_command.py
@@ -6,22 +6,37 @@ from tests.utils import Command
 @pytest.fixture(autouse=True)
 def get_all_executables(mocker):
     mocker.patch('thefuck.rules.no_command.get_all_executables',
-                 return_value=['vim', 'apt-get', 'fsck'])
+                 return_value=['vim', 'fsck', 'git', 'go'])
+
+
+@pytest.fixture(autouse=True)
+def history_without_current(mocker):
+    return mocker.patch(
+        'thefuck.rules.no_command.get_valid_history_without_current',
+        return_value=['git commit'])
+
+
+@pytest.mark.usefixtures('no_memoize')
+@pytest.mark.parametrize('script, stderr', [
+    ('vom file.py', 'vom: not found'),
+    ('fucck', 'fucck: not found'),
+    ('got commit', 'got: command not found')])
+def test_match(script, stderr):
+    assert match(Command(script, stderr=stderr))
 
 
 @pytest.mark.usefixtures('no_memoize')
-def test_match():
-    assert match(Command(stderr='vom: not found', script='vom file.py'))
-    assert match(Command(stderr='fucck: not found', script='fucck'))
-    assert not match(Command(stderr='qweqwe: not found', script='qweqwe'))
-    assert not match(Command(stderr='some text', script='vom file.py'))
+@pytest.mark.parametrize('script, stderr', [
+    ('qweqwe', 'qweqwe: not found'),
+    ('vom file.py', 'some text')])
+def test_not_match(script, stderr):
+    assert not match(Command(script, stderr=stderr))
 
 
 @pytest.mark.usefixtures('no_memoize')
-def test_get_new_command():
-    assert get_new_command(
-        Command(stderr='vom: not found',
-                script='vom file.py')) == ['vim file.py']
-    assert get_new_command(
-        Command(stderr='fucck: not found',
-                script='fucck')) == ['fsck']
+@pytest.mark.parametrize('script, result', [
+    ('vom file.py', ['vim file.py']),
+    ('fucck', ['fsck']),
+    ('got commit', ['git commit', 'go commit'])])
+def test_get_new_command(script, result):
+    assert get_new_command(Command(script)) == result
diff --git a/tests/test_utils.py b/tests/test_utils.py
index 7207827..4441a8e 100644
--- a/tests/test_utils.py
+++ b/tests/test_utils.py
@@ -3,7 +3,8 @@ from mock import Mock
 import six
 from thefuck.utils import default_settings, \
     memoize, get_closest, get_all_executables, replace_argument, \
-    get_all_matched_commands, is_app, for_app, cache, compatibility_call
+    get_all_matched_commands, is_app, for_app, cache, compatibility_call, \
+    get_valid_history_without_current
 from tests.utils import Command
 
 
@@ -229,3 +230,29 @@ class TestCompatibilityCall(object):
             return True
 
         assert compatibility_call(side_effect, Command(), Command())
+
+
+class TestGetValidHistoryWithoutCurrent(object):
+    @pytest.fixture(autouse=True)
+    def history(self, mocker):
+        return mocker.patch('thefuck.shells.shell.get_history',
+                            return_value=['le cat', 'fuck', 'ls cat',
+                                          'diff x', 'nocommand x'])
+
+    @pytest.fixture(autouse=True)
+    def alias(self, mocker):
+        return mocker.patch('thefuck.utils.get_alias',
+                            return_value='fuck')
+
+    @pytest.fixture(autouse=True)
+    def callables(self, mocker):
+        return mocker.patch('thefuck.utils.get_all_executables',
+                            return_value=['diff', 'ls'])
+
+    @pytest.mark.parametrize('script, result', [
+        ('le cat', ['ls cat', 'diff x']),
+        ('diff x', ['ls cat']),
+        ('fuck', ['ls cat', 'diff x'])])
+    def test_get_valid_history_without_current(self, script, result):
+        command = Command(script=script)
+        assert get_valid_history_without_current(command) == result
diff --git a/thefuck/rules/history.py b/thefuck/rules/history.py
index 96f8450..8294963 100644
--- a/thefuck/rules/history.py
+++ b/thefuck/rules/history.py
@@ -1,37 +1,15 @@
 from difflib import get_close_matches
-from thefuck.shells import shell
-from thefuck.utils import get_closest, memoize, get_all_executables, get_alias
-
-
-def _not_corrected(history, tf_alias):
-    """Returns all lines from history except that comes before `fuck`."""
-    previous = None
-    for line in history:
-        if previous is not None and line != tf_alias:
-            yield previous
-        previous = line
-    if history:
-        yield history[-1]
-
-
-@memoize
-def _history_of_exists_without_current(command):
-    history = shell.get_history()
-    tf_alias = get_alias()
-    executables = get_all_executables()
-    return [line for line in _not_corrected(history, tf_alias)
-            if not line.startswith(tf_alias) and not line == command.script
-            and line.split(' ')[0] in executables]
+from thefuck.utils import get_closest, get_valid_history_without_current
 
 
 def match(command):
     return len(get_close_matches(command.script,
-                                 _history_of_exists_without_current(command)))
+                                 get_valid_history_without_current(command)))
 
 
 def get_new_command(command):
     return get_closest(command.script,
-                       _history_of_exists_without_current(command))
+                       get_valid_history_without_current(command))
 
 
 priority = 9999
diff --git a/thefuck/rules/no_command.py b/thefuck/rules/no_command.py
index f67cda5..34b7a4b 100644
--- a/thefuck/rules/no_command.py
+++ b/thefuck/rules/no_command.py
@@ -1,5 +1,6 @@
 from difflib import get_close_matches
-from thefuck.utils import get_all_executables
+from thefuck.utils import get_all_executables, \
+    get_valid_history_without_current, get_closest
 from thefuck.specific.sudo import sudo_support
 
 
@@ -11,10 +12,29 @@ def match(command):
                                        get_all_executables())))
 
 
+def _get_used_executables(command):
+    for script in get_valid_history_without_current(command):
+        yield script.split(' ')[0]
+
+
 @sudo_support
 def get_new_command(command):
     old_command = command.script_parts[0]
-    new_cmds = get_close_matches(old_command, get_all_executables(), cutoff=0.1)
+
+    # One from history:
+    already_used = get_closest(
+        old_command, _get_used_executables(command),
+        fallback_to_first=False)
+    if already_used:
+        new_cmds = [already_used]
+    else:
+        new_cmds = []
+
+    # Other from all executables:
+    new_cmds += [cmd for cmd in get_close_matches(old_command,
+                                                  get_all_executables())
+                 if cmd not in new_cmds]
+
     return [' '.join([new_command] + command.script_parts[1:])
             for new_command in new_cmds]
 
diff --git a/thefuck/utils.py b/thefuck/utils.py
index 3089661..83079e3 100644
--- a/thefuck/utils.py
+++ b/thefuck/utils.py
@@ -269,3 +269,24 @@ def get_installation_info():
 
 def get_alias():
     return os.environ.get('TF_ALIAS', 'fuck')
+
+
+@memoize
+def get_valid_history_without_current(command):
+    def _not_corrected(history, tf_alias):
+        """Returns all lines from history except that comes before `fuck`."""
+        previous = None
+        for line in history:
+            if previous is not None and line != tf_alias:
+                yield previous
+            previous = line
+        if history:
+            yield history[-1]
+
+    from thefuck.shells import shell
+    history = shell.get_history()
+    tf_alias = get_alias()
+    executables = get_all_executables()
+    return [line for line in _not_corrected(history, tf_alias)
+            if not line.startswith(tf_alias) and not line == command.script
+            and line.split(' ')[0] in executables]

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/thefuck/rules/no_command.py b/thefuck/rules/no_command.py
index 34b7a4b..174ee78 100644
--- a/thefuck/rules/no_command.py
+++ b/thefuck/rules/no_command.py
@@ -1,14 +1,14 @@
 from difflib import get_close_matches
 from thefuck.utils import get_all_executables, \
-    get_valid_history_without_current, get_closest
+    get_valid_history_without_current, get_closest, which
 from thefuck.specific.sudo import sudo_support
 
 
 @sudo_support
 def match(command):
-    return (command.script_parts
+    return (not which(command.script_parts[0])
             and 'not found' in command.stderr
             and bool(get_close_matches(command.script_parts[0],
                                        get_all_executables())))
 
 

```

## ODIS candidates: 169 total, path=jev, tiers={'full': 2, 'signature': 1, 'counted': 166}
Shown to the reviewer (full = whole snippet, signature = one line):
- [signature] callee thefuck/types.py:15 Command | class Command(object):
- [full] callee thefuck/utils.py:89 get_closest | def get_closest(word, possibilities, n=3, cutoff=0.6, fallback_to_first=True):
```python
  79              print(settings.apt)
  80  
  81      """
  82      def _default_settings(fn, command):
  83          for k, w in params.items():
  84              settings.setdefault(k, w)
  85          return fn(command)
  86      return decorator(_default_settings)
  87  
  88  
  89  def get_closest(word, possibilities, n=3, cutoff=0.6, fallback_to_first=True):
  90      """Returns closest match or just first from possibilities."""
  91      possibilities = list(possibilities)
  92      try:
  93          return get_close_matches(word, possibilities, n, cutoff)[0]
  94      except IndexError:
  95          if fallback_to_first:
  96              return possibilities[0]
  97  
  98  
  99  @memoize
```
- [full] callee thefuck/utils.py:100 get_all_executables | def get_all_executables():
```python
  90      """Returns closest match or just first from possibilities."""
  91      possibilities = list(possibilities)
  92      try:
  93          return get_close_matches(word, possibilities, n, cutoff)[0]
  94      except IndexError:
  95          if fallback_to_first:
  96              return possibilities[0]
  97  
  98  
  99  @memoize
 100  def get_all_executables():
 101      from thefuck.shells import shell
 102  
 103      def _safe(fn, fallback):
 104          try:
 105              return fn()
 106          except OSError:
 107              return fallback
 108  
 109      tf_alias = get_alias()
 110      tf_entry_points = get_installation_info().get_entry_map()\
```
Counted only (166), first 15:
- callee tests/test_utils.py:118 match
- callee tests/test_utils.py:190 match
- callee tests/test_utils.py:197 match
- callee tests/test_utils.py:205 get_new_command
- callee tests/test_utils.py:212 get_new_command
- callee tests/utils.py:5 Command
- callee thefuck/rules/apt_get.py:25 match
- callee thefuck/rules/apt_get.py:29 get_new_command
- callee thefuck/rules/apt_get_search.py:9 match
- callee thefuck/rules/apt_get_search.py:13 get_new_command
- callee thefuck/rules/apt_invalid_operation.py:11 match
- callee thefuck/rules/apt_invalid_operation.py:53 get_new_command
- callee thefuck/rules/brew_install.py:26 match
- callee thefuck/rules/brew_install.py:37 get_new_command
- callee thefuck/rules/brew_unknown_command.py:68 match
