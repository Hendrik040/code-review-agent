# black#11

Commit message of the reviewed change: Always explode data structure literals

Oracle (fix location at buggy_commit): [{'file': 'black.py', 'line_start': 2115, 'line_end': 2116}]

## Reviewed diff (introducing commit)
```diff
diff --git a/README.md b/README.md
index 475954f..f587744 100644
--- a/README.md
+++ b/README.md
@@ -131,13 +131,13 @@ brackets and put that in a separate indented line.
 ```py3
 # in:
 
-l = [[n for n in list_bosses()], [n for n in list_employees()]]
+TracebackException.from_exception(exc, limit, lookup_lines, capture_locals)
 
 # out:
 
-l = [
-    [n for n in list_bosses()], [n for n in list_employees()]
-]
+TracebackException.from_exception(
+    exc, limit, lookup_lines, capture_locals
+)
 ```
 
 If that still doesn't fit the bill, it will decompose the internal
@@ -176,13 +176,13 @@ between two distinct sections of the code that otherwise share the same
 indentation level (like the arguments list and the docstring in the
 example above).
 
-If a line of "from" imports cannot fit in the allotted length, it's always split
-into one per line.  Imports tend to change often and this minimizes diffs, as well
-as enables readers of code to easily find which commit introduced a particular
-import.  This exception also makes *Black* compatible with
-[isort](https://pypi.org/p/isort/).  Use `multi_line_output=3`,
-`include_trailing_comma=True`, `force_grid_wrap=0`, and `line_length=88` in your
-isort config.
+If a data structure literal (tuple, list, set, dict) or a line of "from"
+imports cannot fit in the allotted length, it's always split into one
+per line.  This minimizes diffs as well as enables readers of code to
+find which commit introduced a particular entry.  This also makes
+*Black* compatible with [isort](https://pypi.org/p/isort/).  Use
+`multi_line_output=3`, `include_trailing_comma=True`,
+`force_grid_wrap=0`, and `line_length=88` in your isort config.
 
 
 ### Line length
@@ -630,7 +630,13 @@ More details can be found in [CONTRIBUTING](CONTRIBUTING.md).
 
 ### 18.5a0 (unreleased)
 
-* call chains are now formatted according to the [fluent interfaces](https://en.wikipedia.org/wiki/Fluent_interface) style (#67)
+* call chains are now formatted according to the
+  [fluent interfaces](https://en.wikipedia.org/wiki/Fluent_interface)
+  style (#67)
+
+* data structure literals (tuples, lists, dictionaries, and sets) are
+  now also always exploded like imports when they don't fit in a single
+  line (#152)
 
 * slices are now formatted according to PEP 8 (#178)
 
diff --git a/black.py b/black.py
index 298597b..c48b8d1 100644
--- a/black.py
+++ b/black.py
@@ -776,6 +776,7 @@ class Line:
     comments: List[Tuple[Index, Leaf]] = Factory(list)
     bracket_tracker: BracketTracker = Factory(BracketTracker)
     inside_brackets: bool = False
+    should_explode: bool = False
 
     def append(self, leaf: Leaf, preformatted: bool = False) -> None:
         """Add a new `leaf` to the end of the line.
@@ -1473,7 +1474,9 @@ def whitespace(leaf: Leaf, *, complex_subscript: bool) -> str:  # noqa C901
 
     assert p is not None, f"INTERNAL ERROR: hand-made leaf without parent: {leaf!r}"
     if t == token.COLON and p.type not in {
-        syms.subscript, syms.subscriptlist, syms.sliceop
+        syms.subscript,
+        syms.subscriptlist,
+        syms.sliceop,
     }:
         return NO
 
@@ -1495,7 +1498,10 @@ def whitespace(leaf: Leaf, *, complex_subscript: bool) -> str:  # noqa C901
         if prevp.type == token.EQUAL:
             if prevp.parent:
                 if prevp.parent.type in {
-                    syms.arglist, syms.argument, syms.parameters, syms.varargslist
+                    syms.arglist,
+                    syms.argument,
+                    syms.parameters,
+                    syms.varargslist,
                 }:
                     return NO
 
@@ -1649,7 +1655,8 @@ def whitespace(leaf: Leaf, *, complex_subscript: bool) -> str:  # noqa C901
             prevp_parent = prevp.parent
             assert prevp_parent is not None
             if prevp.type == token.COLON and prevp_parent.type in {
-                syms.subscript, syms.sliceop
+                syms.subscript,
+                syms.sliceop,
             }:
                 return NO
 
@@ -1902,15 +1909,15 @@ def split_line(
         return
 
     line_str = str(line).strip("\n")
-    if is_line_short_enough(line, line_length=line_length, line_str=line_str):
+    if not line.should_explode and is_line_short_enough(
+        line, line_length=line_length, line_str=line_str
+    ):
         yield line
         return
 
     split_funcs: List[SplitFunc]
     if line.is_def:
         split_funcs = [left_hand_split]
-    elif line.is_import:
-        split_funcs = [explode_split]
     else:
 
         def rhs(line: Line, py36: bool = False) -> Iterator[Line]:
@@ -2073,6 +2080,7 @@ def right_hand_split(
 
     ensure_visible(opening_bracket)
     ensure_visible(closing_bracket)
+    body.should_explode = should_explode(body, opening_bracket)
     for result in (head, body, tail):
         if result:
             yield result
@@ -2212,26 +2220,6 @@ def standalone_comment_split(line: Line, py36: bool = False) -> Iterator[Line]:
         yield current_line
 
 
-def explode_split(
-    line: Line, py36: bool = False, omit: Collection[LeafID] = ()
-) -> Iterator[Line]:
-    """Split by rightmost bracket and immediately split contents by a delimiter."""
-    new_lines = list(right_hand_split(line, py36, omit))
-    if len(new_lines) != 3:
-        yield from new_lines
-        return
-
-    yield new_lines[0]
-
-    try:
-        yield from delimiter_split(new_lines[1], py36)
-
-    except CannotSplit:
-        yield new_lines[1]
-
-    yield new_lines[2]
-
-
 def is_import(leaf: Leaf) -> bool:
     """Return True if the given leaf starts an import statement."""
     p = leaf.parent
@@ -2547,6 +2535,17 @@ def ensure_visible(leaf: Leaf) -> None:
         leaf.value = ")"
 
 
+def should_explode(line: Line, opening_bracket: Leaf) -> bool:
+    """Should `line` immediately be split with `delimiter_split()` after RHS?"""
+    return bool(
+        opening_bracket.parent
+        and opening_bracket.parent.type in {syms.atom, syms.import_from}
+        and opening_bracket.value in "[{("
+        and line.bracket_tracker.delimiters
+        and line.bracket_tracker.max_delimiter_priority() == COMMA_PRIORITY
+    )
+
+
 def is_python36(node: Node) -> bool:
     """Return True if the current file is using Python 3.6+ features.
 
@@ -2675,7 +2674,15 @@ def get_future_imports(node: Node) -> Set[str]:
 
 PYTHON_EXTENSIONS = {".py", ".pyi"}
 BLACKLISTED_DIRECTORIES = {
-    "build", "buck-out", "dist", "_build", ".git", ".hg", ".mypy_cache", ".tox", ".venv"
+    "build",
+    "buck-out",
+    "dist",
+    "_build",
+    ".git",
+    ".hg",
+    ".mypy_cache",
+    ".tox",
+    ".venv",
 }
 
 
diff --git a/docs/reference/reference_functions.rst b/docs/reference/reference_functions.rst
index 4e7a4f6..133f249 100644
--- a/docs/reference/reference_functions.rst
+++ b/docs/reference/reference_functions.rst
@@ -66,8 +66,6 @@ Split functions
 
 .. autofunction:: black.delimiter_split
 
-.. autofunction:: black.explode_split
-
 .. autofunction:: black.left_hand_split
 
 .. autofunction:: black.right_hand_split
diff --git a/tests/cantfit.py b/tests/cantfit.py
index 54f692c..bc38ed2 100644
--- a/tests/cantfit.py
+++ b/tests/cantfit.py
@@ -38,7 +38,9 @@ this_is_a_ridiculously_long_name_and_nobody_in_their_right_mind_would_use_one_li
     1
 )  # with a comment
 this_is_a_ridiculously_long_name_and_nobody_in_their_right_mind_would_use_one_like_it = [
-    1, 2, 3
+    1,
+    2,
+    3,
 ]
 this_is_a_ridiculously_long_name_and_nobody_in_their_right_mind_would_use_one_like_it = (
     function()
diff --git a/tests/comments2.py b/tests/comments2.py
index 44a4711..2045c93 100644
--- a/tests/comments2.py
+++ b/tests/comments2.py
@@ -35,9 +35,9 @@ else:
 def inline_comments_in_brackets_ruin_everything():
     if typedargslist:
         parameters.children = [
-            parameters.children[0],  # (1
+            children[0],  # (1
             body,
-            parameters.children[-1],  # )1
+            children[-1],  # )1
         ]
     else:
         parameters.children = [
@@ -163,9 +163,7 @@ else:
 # Comment before function.
 def inline_comments_in_brackets_ruin_everything():
     if typedargslist:
-        parameters.children = [
-            parameters.children[0], body, parameters.children[-1]  # (1  # )1
-        ]
+        parameters.children = [children[0], body, children[-1]]  # (1  # )1
     else:
         parameters.children = [
             parameters.children[0],  # (2 what if this was actually long
diff --git a/tests/expression.diff b/tests/expression.diff
index dfca37c..d7a0313 100644
--- a/tests/expression.diff
+++ b/tests/expression.diff
@@ -11,7 +11,7 @@
  True
  False
  1
-@@ -29,62 +29,82 @@
+@@ -29,62 +29,83 @@
  ~great
  +value
  -1
@@ -29,7 +29,8 @@
  manylambdas = lambda x=lambda y=lambda z=1: z: y(): x()
 -foo = (lambda port_id, ignore_missing: {"port1": port1_resource, "port2": port2_resource}[port_id])
 +foo = lambda port_id, ignore_missing: {
-+    "port1": port1_resource, "port2": port2_resource
++    "port1": port1_resource,
++    "port2": port2_resource,
 +}[port_id]
  1 if True else 2
  str or None if True else str or bytes or None
@@ -115,7 +116,7 @@
  call(**self.screen_kwargs)
  call(b, **self.screen_kwargs)
  lukasz.langa.pl
-@@ -93,11 +113,11 @@
+@@ -93,11 +114,11 @@
  1.0 .real
  ....__class__
  list[str]
@@ -128,7 +129,7 @@
  ]
  slice[0]
  slice[0:1]
-@@ -124,107 +144,159 @@
+@@ -124,107 +145,159 @@
  numpy[-(c + 1) :, d]
  numpy[:, l[-2]]
  numpy[:, ::-1]
diff --git a/tests/expression.py b/tests/expression.py
index cc6f399..9221c8e 100644
--- a/tests/expression.py
+++ b/tests/expression.py
@@ -273,7 +273,8 @@ lambda a, b, c=True, *, d=(1 << v2), e="str": a
 lambda a, b, c=True, *vararg, d=(v1 << 2), e="str", **kwargs: a + b
 manylambdas = lambda x=lambda y=lambda z=1: z: y(): x()
 foo = lambda port_id, ignore_missing: {
-    "port1": port1_resource, "port2": port2_resource
+    "port1": port1_resource,
+    "port2": port2_resource,
 }[port_id]
 1 if True else 2
 str or None if True else str or bytes or None

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/black.py b/black.py
index 52c5b0c..fb8e474 100644
--- a/black.py
+++ b/black.py
@@ -2110,12 +2110,23 @@ def split_line(
     if line.is_comment:
         yield line
         return
 
     line_str = str(line).strip("\n")
-    if not line.should_explode and is_line_short_enough(
-        line, line_length=line_length, line_str=line_str
+
+    # we don't want to split special comments like type annotations
+    # https://github.com/python/typing/issues/186
+    has_special_comment = False
+    for leaf in line.leaves:
+        for comment in line.comments_after(leaf):
+            if leaf.type == token.COMMA and is_special_comment(comment):
+                has_special_comment = True
+
+    if (
+        not has_special_comment
+        and not line.should_explode
+        and is_line_short_enough(line, line_length=line_length, line_str=line_str)
     ):
         yield line
         return
 
     split_funcs: List[SplitFunc]
@@ -2460,10 +2471,20 @@ def is_import(leaf: Leaf) -> bool:
             or (v == "from" and p and p.type == syms.import_from)
         )
     )
 
 
+def is_special_comment(leaf: Leaf) -> bool:
+    """Return True if the given leaf is a special comment.
+    Only returns true for type comments for now."""
+    t = leaf.type
+    v = leaf.value
+    return bool(
+        (t == token.COMMENT or t == STANDALONE_COMMENT) and (v.startswith("# type:"))
+    )
+
+
 def normalize_prefix(leaf: Leaf, *, inside_brackets: bool) -> None:
     """Leave existing extra newlines if not `inside_brackets`. Remove everything
     else.
 
     Note: don't use backslashes for formatting or you'll lose your voting rights.
@@ -2949,10 +2970,11 @@ def ensure_visible(leaf: Leaf) -> None:
         leaf.value = ")"
 
 
 def should_explode(line: Line, opening_bracket: Leaf) -> bool:
     """Should `line` immediately be split with `delimiter_split()` after RHS?"""
+
     if not (
         opening_bracket.parent
         and opening_bracket.parent.type in {syms.atom, syms.import_from}
         and opening_bracket.value in "[{("
     ):

```

## ODIS candidates: 1 total, path=small, tiers={'full': 1, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee black.py:2933 is_line_short_enough | def is_line_short_enough(line: Line, *, line_length: int, line_str: str = "") -> bool:
```python
2923  
2924  
2925  def enumerate_reversed(sequence: Sequence[T]) -> Iterator[Tuple[Index, T]]:
2926      """Like `reversed(enumerate(sequence))` if that were possible."""
2927      index = len(sequence) - 1
2928      for element in reversed(sequence):
2929          yield (index, element)
2930          index -= 1
2931  
2932  
2933  def is_line_short_enough(line: Line, *, line_length: int, line_str: str = "") -> bool:
2934      """Return True if `line` is no longer than `line_length`.
2935  
2936      Uses the provided `line_str` rendering, if any, otherwise computes a new one.
2937      """
2938      if not line_str:
2939          line_str = str(line).strip("\n")
2940      return (
2941          len(line_str) <= line_length
2942          and "\n" not in line_str  # multiline strings
2943          and not line.contains_standalone_comments()
```
