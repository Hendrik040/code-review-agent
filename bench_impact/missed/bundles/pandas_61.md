# pandas#61

Commit message of the reviewed change: CLN: dedent else part of Series._get_with (#22406)

Oracle (fix location at buggy_commit): [{'file': 'pandas/core/series.py', 'line_start': 922, 'line_end': 922}]

## Reviewed diff (introducing commit)
```diff
diff --git a/pandas/core/series.py b/pandas/core/series.py
index 66e572a3c8..adafc4514b 100644
--- a/pandas/core/series.py
+++ b/pandas/core/series.py
@@ -829,47 +829,46 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
         elif isinstance(key, ABCDataFrame):
             raise TypeError('Indexing a Series with DataFrame is not '
                             'supported, use the appropriate DataFrame column')
-        else:
-            if isinstance(key, tuple):
-                try:
-                    return self._get_values_tuple(key)
-                except Exception:
-                    if len(key) == 1:
-                        key = key[0]
-                        if isinstance(key, slice):
-                            return self._get_values(key)
-                    raise
+        elif isinstance(key, tuple):
+            try:
+                return self._get_values_tuple(key)
+            except Exception:
+                if len(key) == 1:
+                    key = key[0]
+                    if isinstance(key, slice):
+                        return self._get_values(key)
+                raise
 
-            # pragma: no cover
-            if not isinstance(key, (list, np.ndarray, Series, Index)):
-                key = list(key)
+        # pragma: no cover
+        if not isinstance(key, (list, np.ndarray, Series, Index)):
+            key = list(key)
 
-            if isinstance(key, Index):
-                key_type = key.inferred_type
-            else:
-                key_type = lib.infer_dtype(key)
+        if isinstance(key, Index):
+            key_type = key.inferred_type
+        else:
+            key_type = lib.infer_dtype(key)
 
-            if key_type == 'integer':
-                if self.index.is_integer() or self.index.is_floating():
-                    return self.loc[key]
-                else:
-                    return self._get_values(key)
-            elif key_type == 'boolean':
-                return self._get_values(key)
+        if key_type == 'integer':
+            if self.index.is_integer() or self.index.is_floating():
+                return self.loc[key]
             else:
-                try:
-                    # handle the dup indexing case (GH 4246)
-                    if isinstance(key, (list, tuple)):
-                        return self.loc[key]
+                return self._get_values(key)
+        elif key_type == 'boolean':
+            return self._get_values(key)
 
-                    return self.reindex(key)
-                except Exception:
-                    # [slice(0, 5, None)] will break if you convert to ndarray,
-                    # e.g. as requested by np.median
-                    # hack
-                    if isinstance(key[0], slice):
-                        return self._get_values(key)
-                    raise
+        try:
+            # handle the dup indexing case (GH 4246)
+            if isinstance(key, (list, tuple)):
+                return self.loc[key]
+
+            return self.reindex(key)
+        except Exception:
+            # [slice(0, 5, None)] will break if you convert to ndarray,
+            # e.g. as requested by np.median
+            # hack
+            if isinstance(key[0], slice):
+                return self._get_values(key)
+            raise
 
     def _get_values_tuple(self, key):
         # mpl hackaround

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/pandas/core/series.py b/pandas/core/series.py
index c54331f867..94818ab8da 100644
--- a/pandas/core/series.py
+++ b/pandas/core/series.py
@@ -917,11 +917,11 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
                 return self.loc[key]
             elif isinstance(self.index, IntervalIndex):
                 indexer = self.index.get_indexer_for(key)
                 return self.iloc[indexer]
             else:
-                return self._get_values(key)
+                return self.iloc[key]
 
         if isinstance(key, (list, tuple)):
             # TODO: de-dup with tuple case handled above?
             # handle the dup indexing case GH#4246
             if len(key) == 1 and isinstance(key[0], slice):

```

## ODIS candidates: 2 total, path=small, tiers={'full': 2, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee pandas/io/formats/format.py:308 len | def len(self, text):
```python
 298              result += '\n' + footer
 299  
 300          return compat.text_type(u('').join(result))
 301  
 302  
 303  class TextAdjustment(object):
 304  
 305      def __init__(self):
 306          self.encoding = get_option("display.encoding")
 307  
 308      def len(self, text):
 309          return compat.strlen(text, encoding=self.encoding)
 310  
 311      def justify(self, texts, max_len, mode='right'):
 312          return justify(texts, max_len, mode=mode)
 313  
 314      def adjoin(self, space, *lists, **kwargs):
 315          return adjoin(space, *lists, strlen=self.len,
 316                        justfunc=self.justify, **kwargs)
 317  
 318  
```
- [full] callee pandas/io/formats/format.py:328 len | def len(self, text):
```python
 318  
 319  class EastAsianTextAdjustment(TextAdjustment):
 320  
 321      def __init__(self):
 322          super(EastAsianTextAdjustment, self).__init__()
 323          if get_option("display.unicode.ambiguous_as_wide"):
 324              self.ambiguous_width = 2
 325          else:
 326              self.ambiguous_width = 1
 327  
 328      def len(self, text):
 329          return compat.east_asian_len(text, encoding=self.encoding,
 330                                       ambiguous_width=self.ambiguous_width)
 331  
 332      def justify(self, texts, max_len, mode='right'):
 333          # re-calculate padding space per str considering East Asian Width
 334          def _get_pad(t):
 335              return max_len - self.len(t) + len(t)
 336  
 337          if mode == 'left':
 338              return [x.ljust(_get_pad(x)) for x in texts]
```
