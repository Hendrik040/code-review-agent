# matplotlib#6

Commit message of the reviewed change: Further simplify scatter args parsing.

Oracle (fix location at buggy_commit): [{'file': 'lib/matplotlib/axes/_axes.py', 'line_start': 4286, 'line_end': 4286}]

## Reviewed diff (introducing commit)
```diff
diff --git a/lib/matplotlib/axes/_axes.py b/lib/matplotlib/axes/_axes.py
index 9e05e8e42b..50775ba65a 100644
--- a/lib/matplotlib/axes/_axes.py
+++ b/lib/matplotlib/axes/_axes.py
@@ -4229,29 +4229,26 @@ class Axes(_AxesBase):
             or (isinstance(c, collections.abc.Iterable) and len(c) > 0
                 and isinstance(cbook.safe_first_element(c), str)))
 
-        # After this block, c_array will be None unless c is an array for
-        # mapping.  The potential ambiguity with a sequence of 3 or 4 numbers
-        # is resolved in favor of mapping, not rgb or rgba.
-
-        def invalid_shape_exception(csize, nsize):
+        def invalid_shape_exception(csize, xsize):
             return ValueError(
                 f"'c' argument has {csize} elements, which is inconsistent "
                 f"with 'x' and 'y' with size {xsize}.")
 
-        c_array = None
-        # Convenience var to track shape mismatch *and* conversion failures.
-        valid_shape = True  # will be put to the test!
+        c_is_mapped = False  # Unless proven otherwise below.
+        valid_shape = True  # Unless proven otherwise below.
         if not c_was_none and kwcolor is None and not c_is_string_or_strings:
             try:  # First, does 'c' look suitable for value-mapping?
-                c_array = np.asanyarray(c, dtype=float)
+                c = np.asanyarray(c, dtype=float)
             except ValueError:
                 pass  # Failed to convert to float array; must be color specs.
             else:
-                csize = c_array.size
-                if csize == xsize:
-                    c = c_array.ravel()
+                # If c can be either mapped values or a RGB(A) color, prefer
+                # the former if shapes match, the latter otherwise.
+                if c.size == xsize:
+                    c = c.ravel()
+                    c_is_mapped = True
                 else:  # Wrong size; it must not be intended for mapping.
-                    if c_array.shape in ((3,), (4,)):
+                    if c.shape in ((3,), (4,)):
                         _log.warning(
                             "'c' argument looks like a single numeric RGB or "
                             "RGBA sequence, which should be avoided as value-"
@@ -4260,24 +4257,22 @@ class Axes(_AxesBase):
                             "with a single row if you really want to specify "
                             "the same RGB or RGBA value for all points.")
                     valid_shape = False
-                    c_array = None
-        if c_array is None:
+        if not c_is_mapped:
             try:  # Is 'c' acceptable as PathCollection facecolors?
                 colors = mcolors.to_rgba_array(c)
             except ValueError:
                 if not valid_shape:
-                    raise invalid_shape_exception(csize, xsize)
+                    raise invalid_shape_exception(c.size, xsize)
                 # Both the mapping *and* the RGBA conversion failed: pretty
                 # severe failure => one may appreciate a verbose feedback.
                 raise ValueError(
                     f"'c' argument must be a mpl color, a sequence of mpl "
                     f"colors, or a sequence of numbers, not {c}.")
             else:
-                csize = colors.shape[0]
-                if csize not in (0, 1, xsize):
+                if len(colors) not in (0, 1, xsize):
                     # NB: remember that a single color is also acceptable.
                     # Besides *colors* will be an empty array if c == 'none'.
-                    raise invalid_shape_exception(csize, xsize)
+                    raise invalid_shape_exception(len(colors), xsize)
         else:
             colors = None  # use cmap, norm after collection is created
         return c, colors, edgecolors

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/lib/matplotlib/axes/_axes.py b/lib/matplotlib/axes/_axes.py
index 1eb12b4ca9..7008e4c9ea 100644
--- a/lib/matplotlib/axes/_axes.py
+++ b/lib/matplotlib/axes/_axes.py
@@ -4279,13 +4279,19 @@ class Axes(_AxesBase):
             try:  # First, does 'c' look suitable for value-mapping?
                 c = np.asanyarray(c, dtype=float)
             except ValueError:
                 pass  # Failed to convert to float array; must be color specs.
             else:
+                # handle the documented special case of a 2D array with 1
+                # row which as RGB(A) to broadcast.
+                if c.shape == (1, 4) or c.shape == (1, 3):
+                    c_is_mapped = False
+                    if c.size != xsize:
+                        valid_shape = False
                 # If c can be either mapped values or a RGB(A) color, prefer
                 # the former if shapes match, the latter otherwise.
-                if c.size == xsize:
+                elif c.size == xsize:
                     c = c.ravel()
                     c_is_mapped = True
                 else:  # Wrong size; it must not be intended for mapping.
                     if c.shape in ((3,), (4,)):
                         _log.warning(

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
