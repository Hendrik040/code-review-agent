# matplotlib#21

Commit message of the reviewed change: Normalize properties passed to bxp().

Oracle (fix location at buggy_commit): [{'file': 'lib/matplotlib/axes/_axes.py', 'line_start': 3913, 'line_end': 3913}, {'file': 'lib/matplotlib/axes/_axes.py', 'line_start': 3937, 'line_end': 3937}, {'file': 'lib/matplotlib/axes/_axes.py', 'line_start': 3939, 'line_end': 3939}, {'file': 'lib/matplotlib/axes/_axes.py', 'line_start': 3941, 'line_end': 3941}, {'file': 'lib/matplotlib/axes/_axes.py', 'line_start': 3945, 'line_end': 3945}]

## Reviewed diff (introducing commit)
```diff
diff --git a/lib/matplotlib/axes/_axes.py b/lib/matplotlib/axes/_axes.py
index affc329f1b..08d67014ff 100644
--- a/lib/matplotlib/axes/_axes.py
+++ b/lib/matplotlib/axes/_axes.py
@@ -3899,12 +3899,13 @@ class Axes(_AxesBase):
 
         zdelta = 0.1
 
-        def with_rcdefaults(subkey, explicit, zdelta=0):
+        def line_props_with_rcdefaults(subkey, explicit, zdelta=0):
             d = {k.split('.')[-1]: v for k, v in rcParams.items()
                  if k.startswith(f'boxplot.{subkey}')}
             d['zorder'] = zorder + zdelta
             if explicit is not None:
-                d.update(explicit)
+                d.update(
+                    cbook.normalize_kwargs(explicit, mlines.Line2D._alias_map))
             return d
 
         # box properties
@@ -3918,14 +3919,21 @@ class Axes(_AxesBase):
                 zorder=zorder,
             )
             if boxprops is not None:
-                final_boxprops.update(boxprops)
+                final_boxprops.update(
+                    cbook.normalize_kwargs(
+                        boxprops, mpatches.PathPatch._alias_map))
         else:
-            final_boxprops = with_rcdefaults('boxprops', boxprops)
-        final_whiskerprops = with_rcdefaults('whiskerprops', whiskerprops)
-        final_capprops = with_rcdefaults('capprops', capprops)
-        final_flierprops = with_rcdefaults('flierprops', flierprops)
-        final_medianprops = with_rcdefaults('medianprops', medianprops, zdelta)
-        final_meanprops = with_rcdefaults('meanprops', meanprops, zdelta)
+            final_boxprops = line_props_with_rcdefaults('boxprops', boxprops)
+        final_whiskerprops = line_props_with_rcdefaults(
+            'whiskerprops', whiskerprops)
+        final_capprops = line_props_with_rcdefaults(
+            'capprops', capprops)
+        final_flierprops = line_props_with_rcdefaults(
+            'flierprops', flierprops)
+        final_medianprops = line_props_with_rcdefaults(
+            'medianprops', medianprops, zdelta)
+        final_meanprops = line_props_with_rcdefaults(
+            'meanprops', meanprops, zdelta)
         removed_prop = 'marker' if meanline else 'linestyle'
         # Only remove the property if it's not set explicitly as a parameter.
         if meanprops is None or removed_prop not in meanprops:
diff --git a/lib/matplotlib/tests/test_axes.py b/lib/matplotlib/tests/test_axes.py
index 8142829756..90356b9d7c 100644
--- a/lib/matplotlib/tests/test_axes.py
+++ b/lib/matplotlib/tests/test_axes.py
@@ -2236,7 +2236,7 @@ def test_bxp_patchartist():
 def test_bxp_custompatchartist():
     _bxp_test_helper(bxp_kwargs=dict(
         patch_artist=True,
-        boxprops=dict(facecolor='yellow', edgecolor='green', linestyle=':')))
+        boxprops=dict(facecolor='yellow', edgecolor='green', ls=':')))
 
 
 @image_comparison(baseline_images=['bxp_customoutlier'],
@@ -2245,7 +2245,7 @@ def test_bxp_custompatchartist():
                   style='default')
 def test_bxp_customoutlier():
     _bxp_test_helper(bxp_kwargs=dict(
-        flierprops=dict(linestyle='none', marker='d', markerfacecolor='g')))
+        flierprops=dict(linestyle='none', marker='d', mfc='g')))
 
 
 @image_comparison(baseline_images=['bxp_withmean_custompoint'],
@@ -2255,7 +2255,7 @@ def test_bxp_customoutlier():
 def test_bxp_showcustommean():
     _bxp_test_helper(bxp_kwargs=dict(
         showmeans=True,
-        meanprops=dict(linestyle='none', marker='d', markerfacecolor='green'),
+        meanprops=dict(linestyle='none', marker='d', mfc='green'),
     ))
 
 
@@ -2265,7 +2265,7 @@ def test_bxp_showcustommean():
                   style='default')
 def test_bxp_custombox():
     _bxp_test_helper(bxp_kwargs=dict(
-        boxprops=dict(linestyle='--', color='b', linewidth=3)))
+        boxprops=dict(linestyle='--', color='b', lw=3)))
 
 
 @image_comparison(baseline_images=['bxp_custommedian'],
@@ -2274,7 +2274,7 @@ def test_bxp_custombox():
                   style='default')
 def test_bxp_custommedian():
     _bxp_test_helper(bxp_kwargs=dict(
-        medianprops=dict(linestyle='--', color='b', linewidth=3)))
+        medianprops=dict(linestyle='--', color='b', lw=3)))
 
 
 @image_comparison(baseline_images=['bxp_customcap'],
@@ -2283,7 +2283,7 @@ def test_bxp_custommedian():
                   style='default')
 def test_bxp_customcap():
     _bxp_test_helper(bxp_kwargs=dict(
-        capprops=dict(linestyle='--', color='g', linewidth=3)))
+        capprops=dict(linestyle='--', color='g', lw=3)))
 
 
 @image_comparison(baseline_images=['bxp_customwhisker'],
@@ -2292,7 +2292,7 @@ def test_bxp_customcap():
                   style='default')
 def test_bxp_customwhisker():
     _bxp_test_helper(bxp_kwargs=dict(
-        whiskerprops=dict(linestyle='-', color='m', linewidth=3)))
+        whiskerprops=dict(linestyle='-', color='m', lw=3)))
 
 
 @image_comparison(baseline_images=['bxp_withnotch'],

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/lib/matplotlib/axes/_axes.py b/lib/matplotlib/axes/_axes.py
index 152d00b0e4..212c405b55 100644
--- a/lib/matplotlib/axes/_axes.py
+++ b/lib/matplotlib/axes/_axes.py
@@ -3908,14 +3908,17 @@ class Axes(_AxesBase):
         if zorder is None:
             zorder = mlines.Line2D.zorder
 
         zdelta = 0.1
 
-        def line_props_with_rcdefaults(subkey, explicit, zdelta=0):
+        def line_props_with_rcdefaults(subkey, explicit, zdelta=0,
+                                       use_marker=True):
             d = {k.split('.')[-1]: v for k, v in rcParams.items()
                  if k.startswith(f'boxplot.{subkey}')}
             d['zorder'] = zorder + zdelta
+            if not use_marker:
+                d['marker'] = ''
             if explicit is not None:
                 d.update(
                     cbook.normalize_kwargs(explicit, mlines.Line2D._alias_map))
             return d
 
@@ -3932,19 +3935,20 @@ class Axes(_AxesBase):
             if boxprops is not None:
                 final_boxprops.update(
                     cbook.normalize_kwargs(
                         boxprops, mpatches.PathPatch._alias_map))
         else:
-            final_boxprops = line_props_with_rcdefaults('boxprops', boxprops)
+            final_boxprops = line_props_with_rcdefaults('boxprops', boxprops,
+                                                        use_marker=False)
         final_whiskerprops = line_props_with_rcdefaults(
-            'whiskerprops', whiskerprops)
+            'whiskerprops', whiskerprops, use_marker=False)
         final_capprops = line_props_with_rcdefaults(
-            'capprops', capprops)
+            'capprops', capprops, use_marker=False)
         final_flierprops = line_props_with_rcdefaults(
             'flierprops', flierprops)
         final_medianprops = line_props_with_rcdefaults(
-            'medianprops', medianprops, zdelta)
+            'medianprops', medianprops, zdelta, use_marker=False)
         final_meanprops = line_props_with_rcdefaults(
             'meanprops', meanprops, zdelta)
         removed_prop = 'marker' if meanline else 'linestyle'
         # Only remove the property if it's not set explicitly as a parameter.
         if meanprops is None or removed_prop not in meanprops:

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
