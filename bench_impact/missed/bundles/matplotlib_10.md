# matplotlib#10

Commit message of the reviewed change: Simplify update logic

Oracle (fix location at buggy_commit): [{'file': 'lib/matplotlib/axis.py', 'line_start': 827, 'line_end': 827}]

## Reviewed diff (introducing commit)
```diff
diff --git a/lib/matplotlib/axis.py b/lib/matplotlib/axis.py
index fdf8d62308..5a1778cb31 100644
--- a/lib/matplotlib/axis.py
+++ b/lib/matplotlib/axis.py
@@ -888,33 +888,29 @@ class Axis(martist.Artist):
         For documentation of keyword arguments, see
         :meth:`matplotlib.axes.Axes.tick_params`.
         """
-        dicts = []
         cbook._check_in_list(['major', 'minor', 'both'], which=which)
-        if which in ['major', 'both']:
-            dicts.append(self._major_tick_kw)
-        if which in ['minor', 'both']:
-            dicts.append(self._minor_tick_kw)
         kwtrans = self._translate_tick_kw(kw)
 
-        # this stashes the parameter changes so any new ticks will
-        # automatically get them
-        for d in dicts:
-            if reset:
-                d.clear()
-            d.update(kwtrans)
-
+        # the kwargs are stored in self._major/minor_tick_kw so that any
+        # future new ticks will automatically get them
         if reset:
+            if which in ['major', 'both']:
+                self._major_tick_kw.clear()
+                self._major_tick_kw.update(kwtrans)
+            if which in ['minor', 'both']:
+                self._minor_tick_kw.clear()
+                self._minor_tick_kw.update(kwtrans)
             self.reset_ticks()
         else:
-            # apply the new kwargs to the existing ticks
             if which in ['major', 'both']:
+                self._major_tick_kw.update(kwtrans)
                 for tick in self.majorTicks:
                     tick._apply_params(**kwtrans)
             if which in ['minor', 'both']:
+                self._minor_tick_kw.update(kwtrans)
                 for tick in self.minorTicks:
                     tick._apply_params(**kwtrans)
-            # special-case label color to also apply to the offset
-            # text
+            # special-case label color to also apply to the offset text
             if 'labelcolor' in kwtrans:
                 self.offsetText.set_color(kwtrans['labelcolor'])
 

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/lib/matplotlib/axis.py b/lib/matplotlib/axis.py
index b252f8d3aa..cfc7739d86 100644
--- a/lib/matplotlib/axis.py
+++ b/lib/matplotlib/axis.py
@@ -822,11 +822,15 @@ class Axis(martist.Artist):
                     tick._apply_params(**kwtrans)
             if which in ['minor', 'both']:
                 self._minor_tick_kw.update(kwtrans)
                 for tick in self.minorTicks:
                     tick._apply_params(**kwtrans)
-            # special-case label color to also apply to the offset text
+            # labelOn and labelcolor also apply to the offset text.
+            if 'label1On' in kwtrans or 'label2On' in kwtrans:
+                self.offsetText.set_visible(
+                    self._major_tick_kw.get('label1On', False)
+                    or self._major_tick_kw.get('label2On', False))
             if 'labelcolor' in kwtrans:
                 self.offsetText.set_color(kwtrans['labelcolor'])
 
         self.stale = True
 

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
