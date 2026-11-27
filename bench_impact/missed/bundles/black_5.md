# black#5

Commit message of the reviewed change: fix handling of comments in from imports (#829)

Oracle (fix location at buggy_commit): [{'file': 'black.py', 'line_start': 1355, 'line_end': 1355}, {'file': 'black.py', 'line_start': 2491, 'line_end': 2493}]

## Reviewed diff (introducing commit)
```diff
diff --git a/black.py b/black.py
index dd6e372..9ecfbe1 100644
--- a/black.py
+++ b/black.py
@@ -2405,10 +2405,17 @@ def bracket_split_build_line(
         if leaves:
             # Since body is a new indent level, remove spurious leading whitespace.
             normalize_prefix(leaves[0], inside_brackets=True)
-            # Ensure a trailing comma when expected.
+            # Ensure a trailing comma for imports, but be careful not to add one after
+            # any comments.
             if original.is_import:
-                if leaves[-1].type != token.COMMA:
-                    leaves.append(Leaf(token.COMMA, ","))
+                for i in range(len(leaves) - 1, -1, -1):
+                    if leaves[i].type == STANDALONE_COMMENT:
+                        continue
+                    elif leaves[i].type == token.COMMA:
+                        break
+                    else:
+                        leaves.insert(i + 1, Leaf(token.COMMA, ","))
+                        break
     # Populate the line
     for leaf in leaves:
         result.append(leaf, preformatted=True)
diff --git a/tests/data/comments7.py b/tests/data/comments7.py
new file mode 100644
index 0000000..4159d84
--- /dev/null
+++ b/tests/data/comments7.py
@@ -0,0 +1,51 @@
+from .config import (
+    Any,
+    Bool,
+    ConfigType,
+    ConfigTypeAttributes,
+    Int,
+    Path,
+    #  String,
+    #  resolve_to_config_type,
+    #  DEFAULT_TYPE_ATTRIBUTES,
+)
+
+
+from .config import (
+    Any,
+    Bool,
+    ConfigType,
+    ConfigTypeAttributes,
+    Int,
+    no_comma_here_yet
+    #  and some comments,
+    #  resolve_to_config_type,
+    #  DEFAULT_TYPE_ATTRIBUTES,
+)
+
+# output
+
+from .config import (
+    Any,
+    Bool,
+    ConfigType,
+    ConfigTypeAttributes,
+    Int,
+    Path,
+    #  String,
+    #  resolve_to_config_type,
+    #  DEFAULT_TYPE_ATTRIBUTES,
+)
+
+
+from .config import (
+    Any,
+    Bool,
+    ConfigType,
+    ConfigTypeAttributes,
+    Int,
+    no_comma_here_yet,
+    #  and some comments,
+    #  resolve_to_config_type,
+    #  DEFAULT_TYPE_ATTRIBUTES,
+)
diff --git a/tests/test_black.py b/tests/test_black.py
index 3e0b8a1..86175aa 100644
--- a/tests/test_black.py
+++ b/tests/test_black.py
@@ -388,6 +388,14 @@ class BlackTestCase(unittest.TestCase):
         black.assert_equivalent(source, actual)
         black.assert_stable(source, actual, black.FileMode())
 
+    @patch("black.dump_to_file", dump_to_stderr)
+    def test_comments7(self) -> None:
+        source, expected = read_data("comments7")
+        actual = fs(source)
+        self.assertFormatEqual(expected, actual)
+        black.assert_equivalent(source, actual)
+        black.assert_stable(source, actual, black.FileMode())
+
     @patch("black.dump_to_file", dump_to_stderr)
     def test_cantfit(self) -> None:
         source, expected = read_data("cantfit")

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/black.py b/black.py
index 635eba2..8318674 100644
--- a/black.py
+++ b/black.py
@@ -1350,11 +1350,14 @@ def maybe_remove_trailing_comma(self, closing: Leaf) -> bool:
                 break
 
             bracket_depth = leaf.bracket_depth
             if bracket_depth == depth and leaf.type == token.COMMA:
                 commas += 1
-                if leaf.parent and leaf.parent.type == syms.arglist:
+                if leaf.parent and leaf.parent.type in {
+                    syms.arglist,
+                    syms.typedargslist,
+                }:
                     commas += 1
                     break
 
         if commas > 1:
             self.remove_trailing_comma()
@@ -2486,13 +2489,17 @@ def bracket_split_build_line(
         result.inside_brackets = True
         result.depth += 1
         if leaves:
             # Since body is a new indent level, remove spurious leading whitespace.
             normalize_prefix(leaves[0], inside_brackets=True)
-            # Ensure a trailing comma for imports, but be careful not to add one after
-            # any comments.
-            if original.is_import:
+            # Ensure a trailing comma for imports and standalone function arguments, but
+            # be careful not to add one after any comments.
+            no_commas = original.is_def and not any(
+                l.type == token.COMMA for l in leaves
+            )
+
+            if original.is_import or no_commas:
                 for i in range(len(leaves) - 1, -1, -1):
                     if leaves[i].type == STANDALONE_COMMENT:
                         continue
                     elif leaves[i].type == token.COMMA:
                         break

```

## ODIS candidates: 2 total, path=small, tiers={'full': 2, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee blib2to3/pytree.py:331 Leaf | class Leaf(Base):
```python
 328              previous = current
 329          _next[id(current)] = None
 330  
 331  class Leaf(Base):
 332  
 333      """Concrete implementation for leaf nodes."""
 334  
 335      # Default values for instance variables
 336      _prefix = ""  # Whitespace and comments preceding this token in the input
 337      lineno = 0    # Line where this token starts in the input
 338      column = 0    # Column where this token tarts in the input
 339  
 340      def __init__(self, type, value,
 341                   context=None,
 342                   prefix=None,
 343                   fixers_applied=[]):
 344          """
 345          Initializer.
 346  
 347          Takes a type constant (a token number < 256), a string value, and an
 348          optional context keyword argument.
 349          """
 350          assert 0 <= type < 256, type
 351          if context is not None:
 352              self._prefix, (self.lineno, self.column) = context
```
- [full] callee tests/test_black.py:57 read_data | def read_data(name: str, data: bool = True) -> Tuple[str, str]:
```python
  47      f"--target-version={version.name.lower()}" for version in black.PY36_VERSIONS
  48  ]
  49  T = TypeVar("T")
  50  R = TypeVar("R")
  51  
  52  
  53  def dump_to_stderr(*output: str) -> str:
  54      return "\n" + "\n".join(output) + "\n"
  55  
  56  
  57  def read_data(name: str, data: bool = True) -> Tuple[str, str]:
  58      """read_data('test_name') -> 'input', 'output'"""
  59      if not name.endswith((".py", ".pyi", ".out", ".diff")):
  60          name += ".py"
  61      _input: List[str] = []
  62      _output: List[str] = []
  63      base_dir = THIS_DIR / "data" if data else THIS_DIR
  64      with open(base_dir / name, "r", encoding="utf8") as test:
  65          lines = test.readlines()
  66      result = _input
  67      for line in lines:
```
