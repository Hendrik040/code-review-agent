# thefuck#32

Commit message of the reviewed change: #118 Make `ls_lah` disabled by default

Oracle (fix location at buggy_commit): [{'file': 'thefuck/rules/ls_lah.py', 'line_start': 2, 'line_end': 2}]

## Reviewed diff (introducing commit)
```diff
diff --git a/README.md b/README.md
index 85cbdbb..9f55b53 100644
--- a/README.md
+++ b/README.md
@@ -156,7 +156,6 @@ using matched rule and run it. Rules enabled by default:
 * `git_no_command` &ndash; fixes wrong git commands like `git brnch`;
 * `git_push` &ndash; adds `--set-upstream origin $branch` to previous failed `git push`;
 * `has_exists_script` &ndash; prepends `./` when script/binary exists;
-* `ls_lah` &ndash; adds -lah to ls;
 * `lein_not_task` &ndash; fixes wrong `lein` tasks like `lein rpl`;
 * `mkdir_p` &ndash; adds `-p` when you trying to create directory without parent;
 * `no_command` &ndash; fixes wrong console commands, for example `vom/vim`;
@@ -170,6 +169,7 @@ using matched rule and run it. Rules enabled by default:
 
 Bundled, but not enabled by default:
 
+* `ls_lah` &ndash; adds -lah to ls;
 * `rm_root` &ndash; adds `--no-preserve-root` to `rm -rf /` command.
 
 ## Creating your own rules
diff --git a/tests/rules/test_ls_lah.py b/tests/rules/test_ls_lah.py
index f7eb3ed..c453f6e 100644
--- a/tests/rules/test_ls_lah.py
+++ b/tests/rules/test_ls_lah.py
@@ -3,11 +3,11 @@ from thefuck.rules.ls_lah import match, get_new_command
 
 
 def test_match():
-        assert match(Mock(script='ls file.py'), None)
-        assert match(Mock(script='ls /opt'), None)
-        assert not match(Mock(script='ls -lah /opt'), None)
+    assert match(Mock(script='ls file.py'), None)
+    assert match(Mock(script='ls /opt'), None)
+    assert not match(Mock(script='ls -lah /opt'), None)
 
 
 def test_get_new_command():
-        assert get_new_command( Mock(script='ls file.py'), None) == 'ls -lah file.py'
-        assert get_new_command( Mock(script='ls'), None) == 'ls -lah'
+    assert get_new_command(Mock(script='ls file.py'), None) == 'ls -lah file.py'
+    assert get_new_command(Mock(script='ls'), None) == 'ls -lah'
diff --git a/thefuck/rules/ls_lah.py b/thefuck/rules/ls_lah.py
index 1de0283..50fe9f5 100644
--- a/thefuck/rules/ls_lah.py
+++ b/thefuck/rules/ls_lah.py
@@ -1,5 +1,9 @@
+enabled_by_default = False
+
+
 def match(command, settings):
-    return ('ls' in command.script and not ('ls -' in command.script))
+    return 'ls' in command.script and not ('ls -' in command.script)
+
 
 def get_new_command(command, settings):
     command = command.script.split(' ')

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/thefuck/rules/ls_lah.py b/thefuck/rules/ls_lah.py
index 7eba5bd..70f6baa 100644
--- a/thefuck/rules/ls_lah.py
+++ b/thefuck/rules/ls_lah.py
@@ -1,7 +1,9 @@
 def match(command, settings):
-    return 'ls' in command.script and not ('ls -' in command.script)
+    return (command.script == 'ls'
+            or command.script.startswith('ls ')
+            and not ('ls -' in command.script))
 
 
 def get_new_command(command, settings):
     command = command.script.split(' ')
     command[0] = 'ls -lah'

```

## ODIS candidates: 44 total, path=jev, tiers={'full': 0, 'signature': 0, 'counted': 44}
Shown to the reviewer (full = whole snippet, signature = one line):
Counted only (44), first 15:
- callee thefuck/rules/apt_get.py:7 match
- callee thefuck/rules/apt_get.py:19 get_new_command
- callee thefuck/rules/brew_install.py:25 match
- callee thefuck/rules/brew_install.py:38 get_new_command
- callee thefuck/rules/brew_unknown_command.py:15 match
- callee thefuck/rules/brew_unknown_command.py:28 get_new_command
- callee thefuck/rules/cd_mkdir.py:6 match
- callee thefuck/rules/cd_mkdir.py:13 get_new_command
- callee thefuck/rules/cd_parent.py:10 match
- callee thefuck/rules/cd_parent.py:13 get_new_command
- callee thefuck/rules/composer_not_command.py:4 match
- callee thefuck/rules/composer_not_command.py:10 get_new_command
- callee thefuck/rules/cp_omitting_directory.py:6 match
- callee thefuck/rules/cp_omitting_directory.py:12 get_new_command
- callee thefuck/rules/fix_alt_space.py:8 match
