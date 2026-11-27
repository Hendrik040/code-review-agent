# matplotlib#14

Commit message of the reviewed change: Fix `text.set(bbox=None)`.

Oracle (fix location at buggy_commit): [{'file': 'lib/matplotlib/text.py', 'line_start': 177, 'line_end': 177}]

## Reviewed diff (introducing commit)
```diff
diff --git a/lib/matplotlib/text.py b/lib/matplotlib/text.py
index caa5dcdaf7..207b57ba0c 100644
--- a/lib/matplotlib/text.py
+++ b/lib/matplotlib/text.py
@@ -239,10 +239,12 @@ class Text(Artist):
         """
         Update properties from a dictionary.
         """
-        bbox = kwargs.pop('bbox', None)
+        # Update bbox last, as it depends on font properties.
+        sentinel = object()  # bbox can be None, so use another sentinel.
+        bbox = kwargs.pop("bbox", sentinel)
         super(Text, self).update(kwargs)
-        if bbox:
-            self.set_bbox(bbox)  # depends on font properties
+        if bbox is not sentinel:
+            self.set_bbox(bbox)
 
     def __getstate__(self):
         d = super(Text, self).__getstate__()

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/lib/matplotlib/text.py b/lib/matplotlib/text.py
index 78fb5c57f7..2a8a708e7c 100644
--- a/lib/matplotlib/text.py
+++ b/lib/matplotlib/text.py
@@ -172,12 +172,16 @@ class Text(Artist):
         self.set_rotation_mode(rotation_mode)
         self.update(kwargs)
 
     def update(self, kwargs):
         # docstring inherited
-        # Update bbox last, as it depends on font properties.
         sentinel = object()  # bbox can be None, so use another sentinel.
+        # Update fontproperties first, as it has lowest priority.
+        fontproperties = kwargs.pop("fontproperties", sentinel)
+        if fontproperties is not sentinel:
+            self.set_fontproperties(fontproperties)
+        # Update bbox last, as it depends on font properties.
         bbox = kwargs.pop("bbox", sentinel)
         super().update(kwargs)
         if bbox is not sentinel:
             self.set_bbox(bbox)
 

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
