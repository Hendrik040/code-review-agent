# pandas#21

Commit message of the reviewed change: Continue simplifying indexing code (#27619)

Oracle (fix location at buggy_commit): [{'file': 'pandas/core/series.py', 'line_start': 952, 'line_end': 956}]

## Reviewed diff (introducing commit)
```diff
diff --git a/pandas/core/frame.py b/pandas/core/frame.py
index cdbe0e9d22..9fd956c40c 100644
--- a/pandas/core/frame.py
+++ b/pandas/core/frame.py
@@ -2836,11 +2836,13 @@ class DataFrame(NDFrame):
         # Do we have a slicer (on rows)?
         indexer = convert_to_index_sliceable(self, key)
         if indexer is not None:
+            # either we have a slice or we have a string that can be converted
+            #  to a slice for partial-string date indexing
             return self._slice(indexer, axis=0)
 
         # Do we have a (boolean) DataFrame?
         if isinstance(key, DataFrame):
-            return self._getitem_frame(key)
+            return self.where(key)
 
         # Do we have a (boolean) 1d indexer?
         if com.is_bool_indexer(key):
@@ -2938,11 +2940,6 @@ class DataFrame(NDFrame):
         else:
             return self._get_item_cache(key)
 
-    def _getitem_frame(self, key):
-        if key.values.size and not is_bool_dtype(key.values):
-            raise ValueError("Must pass DataFrame with boolean values only")
-        return self.where(key)
-
     def _get_value(self, index, col, takeable: bool = False):
         """
         Quickly retrieve single value at passed column and index.
@@ -2986,6 +2983,8 @@ class DataFrame(NDFrame):
         # see if we can slice the rows
         indexer = convert_to_index_sliceable(self, key)
         if indexer is not None:
+            # either we have a slice or we have a string that can be converted
+            #  to a slice for partial-string date indexing
             return self._setitem_slice(indexer, value)
 
         if isinstance(key, DataFrame) or getattr(key, "ndim", None) == 2:
diff --git a/pandas/core/indexing.py b/pandas/core/indexing.py
index a1a8619fab..df89dbe6db 100755
--- a/pandas/core/indexing.py
+++ b/pandas/core/indexing.py
@@ -117,6 +117,7 @@ class _NDFrameIndexer(_NDFrameIndexerBase):
         raise NotImplementedError("ix is not iterable")
 
     def __getitem__(self, key):
+        # Used in ix and downstream in geopandas _CoordinateIndexer
         if type(key) is tuple:
             # Note: we check the type exactly instead of with isinstance
             #  because NamedTuple is checked separately.
@@ -181,7 +182,7 @@ class _NDFrameIndexer(_NDFrameIndexerBase):
                 pass
 
         if isinstance(key, range):
-            return self._convert_range(key, is_setter=True)
+            return list(key)
 
         axis = self.axis or 0
         try:
@@ -258,10 +259,6 @@ class _NDFrameIndexer(_NDFrameIndexerBase):
                 keyidx.append(idx)
         return tuple(keyidx)
 
-    def _convert_range(self, key: range, is_setter: bool = False):
-        """ convert a range argument """
-        return list(key)
-
     def _convert_scalar_indexer(self, key, axis: int):
         # if we are accessing via lowered dim, use the last dim
         ax = self.obj._get_axis(min(axis, self.ndim - 1))
diff --git a/pandas/core/series.py b/pandas/core/series.py
index c7fcab56e1..f840b6ce64 100644
--- a/pandas/core/series.py
+++ b/pandas/core/series.py
@@ -1131,8 +1131,7 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
     def _get_with(self, key):
         # other: fancy integer or otherwise
         if isinstance(key, slice):
-            indexer = self.index._convert_slice_indexer(key, kind="getitem")
-            return self._get_values(indexer)
+            return self._slice(key)
         elif isinstance(key, ABCDataFrame):
             raise TypeError(
                 "Indexing a Series with DataFrame is not "
@@ -1148,7 +1147,6 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
                         return self._get_values(key)
                 raise
 
-        # pragma: no cover
         if not isinstance(key, (list, np.ndarray, Series, Index)):
             key = list(key)
 
@@ -1165,19 +1163,18 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
         elif key_type == "boolean":
             return self._get_values(key)
 
-        try:
-            # handle the dup indexing case (GH 4246)
-            if isinstance(key, (list, tuple)):
-                return self.loc[key]
-
-            return self.reindex(key)
-        except Exception:
-            # [slice(0, 5, None)] will break if you convert to ndarray,
-            # e.g. as requested by np.median
-            # hack
-            if isinstance(key[0], slice):
+        if isinstance(key, (list, tuple)):
+            # TODO: de-dup with tuple case handled above?
+            # handle the dup indexing case GH#4246
+            if len(key) == 1 and isinstance(key[0], slice):
+                # [slice(0, 5, None)] will break if you convert to ndarray,
+                # e.g. as requested by np.median
+                # FIXME: hack
                 return self._get_values(key)
-            raise
+
+            return self.loc[key]
+
+        return self.reindex(key)
 
     def _get_values_tuple(self, key):
         # mpl hackaround
@@ -1220,33 +1217,28 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
 
     def __setitem__(self, key, value):
         key = com.apply_if_callable(key, self)
+        cacher_needs_updating = self._check_is_chained_assignment_possible()
 
-        def setitem(key, value):
-            try:
-                self._set_with_engine(key, value)
-                return
-            except com.SettingWithCopyError:
-                raise
-            except (KeyError, ValueError):
-                values = self._values
-                if is_integer(key) and not self.index.inferred_type == "integer":
-
-                    values[key] = value
-                    return
-                elif key is Ellipsis:
-                    self[:] = value
-                    return
-
+        try:
+            self._set_with_engine(key, value)
+        except com.SettingWithCopyError:
+            raise
+        except (KeyError, ValueError):
+            values = self._values
+            if is_integer(key) and not self.index.inferred_type == "integer":
+                values[key] = value
+            elif key is Ellipsis:
+                self[:] = value
+            else:
                 self.loc[key] = value
-                return
 
-            except TypeError as e:
-                if isinstance(key, tuple) and not isinstance(self.index, MultiIndex):
-                    raise ValueError("Can only tuple-index with a MultiIndex")
+        except TypeError as e:
+            if isinstance(key, tuple) and not isinstance(self.index, MultiIndex):
+                raise ValueError("Can only tuple-index with a MultiIndex")
 
-                # python 3 type errors should be raised
-                if _is_unorderable_exception(e):
-                    raise IndexError(key)
+            # python 3 type errors should be raised
+            if _is_unorderable_exception(e):
+                raise IndexError(key)
 
             if com.is_bool_indexer(key):
                 key = check_bool_indexer(self.index, key)
@@ -1258,9 +1250,6 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
 
             self._set_with(key, value)
 
-        # do the setitem
-        cacher_needs_updating = self._check_is_chained_assignment_possible()
-        setitem(key, value)
         if cacher_needs_updating:
             self._maybe_update_cacher()
 
@@ -1282,6 +1271,14 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
         if isinstance(key, slice):
             indexer = self.index._convert_slice_indexer(key, kind="getitem")
             return self._set_values(indexer, value)
+
+        elif is_scalar(key) and not is_integer(key) and key not in self.index:
+            # GH#12862 adding an new key to the Series
+            # Note: have to exclude integers because that is ambiguously
+            #  position-based
+            self.loc[key] = value
+            return
+
         else:
             if isinstance(key, tuple):
                 try:
@@ -1289,13 +1286,6 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
                 except Exception:
                     pass
 
-            if is_scalar(key) and not is_integer(key) and key not in self.index:
-                # GH#12862 adding an new key to the Series
-                # Note: have to exclude integers because that is ambiguously
-                #  position-based
-                self.loc[key] = value
-                return
-
             if is_scalar(key):
                 key = [key]
             elif not isinstance(key, (list, Series, np.ndarray)):
@@ -1306,6 +1296,7 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
 
             if isinstance(key, Index):
                 key_type = key.inferred_type
+                key = key._values
             else:
                 key_type = lib.infer_dtype(key, skipna=False)
 
@@ -1320,10 +1311,7 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
                 self._set_labels(key, value)
 
     def _set_labels(self, key, value):
-        if isinstance(key, Index):
-            key = key.values
-        else:
-            key = com.asarray_tuplesafe(key)
+        key = com.asarray_tuplesafe(key)
         indexer = self.index.get_indexer(key)
         mask = indexer == -1
         if mask.any():
diff --git a/pandas/core/sparse/series.py b/pandas/core/sparse/series.py
index fc51c06b14..d81cab77f0 100644
--- a/pandas/core/sparse/series.py
+++ b/pandas/core/sparse/series.py
@@ -324,7 +324,7 @@ class SparseSeries(Series):
         Parameters
         ----------
         i : int
-        axis: int
+        axis : int
             default 0, ignored
 
         Returns
diff --git a/pandas/tests/frame/test_indexing.py b/pandas/tests/frame/test_indexing.py
index 814a99701b..ae14563e59 100644
--- a/pandas/tests/frame/test_indexing.py
+++ b/pandas/tests/frame/test_indexing.py
@@ -269,7 +269,7 @@ class TestDataFrameIndexing(TestData):
         subframe_obj = datetime_frame[indexer_obj]
         assert_frame_equal(subframe_obj, subframe)
 
-        with pytest.raises(ValueError, match="boolean values only"):
+        with pytest.raises(ValueError, match="Boolean array expected"):
             datetime_frame[datetime_frame]
 
         # test that Series work

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/pandas/core/series.py b/pandas/core/series.py
index 854c87071e..5a1d7f3b90 100644
--- a/pandas/core/series.py
+++ b/pandas/core/series.py
@@ -947,15 +947,12 @@ class Series(base.IndexOpsMixin, generic.NDFrame):
             if not self.index._should_fallback_to_positional():
                 return self.loc[key]
             else:
                 return self.iloc[key]
 
-        if isinstance(key, list):
-            # handle the dup indexing case GH#4246
-            return self.loc[key]
-
-        return self.reindex(key)
+        # handle the dup indexing case GH#4246
+        return self.loc[key]
 
     def _get_values_tuple(self, key):
         # mpl hackaround
         if com.any_none(*key):
             # suppress warning from slicing the index with a 2d indexer.

```

## ODIS candidates: 6 total, path=small, tiers={'full': 6, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee pandas/core/computation/ops.py:123 is_scalar | def is_scalar(self):
```python
 113          """
 114          key = self.name
 115  
 116          # if it's a variable name (otherwise a constant)
 117          if isinstance(key, str):
 118              self.env.swapkey(self.local_name, key, new_value=value)
 119  
 120          self.value = value
 121  
 122      @property
 123      def is_scalar(self):
 124          return is_scalar(self._value)
 125  
 126      @property
 127      def type(self):
 128          try:
 129              # potentially very slow for large, mixed dtype frames
 130              return self._value.values.dtype
 131          except AttributeError:
 132              try:
 133                  # ndarray
```
- [full] callee pandas/core/computation/ops.py:232 is_scalar | def is_scalar(self):
```python
 222      def has_invalid_return_type(self):
 223          types = self.operand_types
 224          obj_dtype_set = frozenset([np.dtype("object")])
 225          return self.return_type == object and types - obj_dtype_set
 226  
 227      @property
 228      def operand_types(self):
 229          return frozenset(term.type for term in com.flatten(self))
 230  
 231      @property
 232      def is_scalar(self):
 233          return all(operand.is_scalar for operand in self.operands)
 234  
 235      @property
 236      def is_datetime(self):
 237          try:
 238              t = self.return_type.type
 239          except AttributeError:
 240              t = self.return_type
 241  
 242          return issubclass(t, (datetime, np.datetime64))
```
- [full] callee pandas/core/dtypes/common.py:1324 _is_unorderable_exception | def _is_unorderable_exception(e: TypeError) -> bool:
```python
1314      False
1315      >>> is_datetime_or_timedelta_dtype(np.array([], dtype=np.timedelta64))
1316      True
1317      >>> is_datetime_or_timedelta_dtype(np.array([], dtype=np.datetime64))
1318      True
1319      """
1320  
1321      return _is_dtype_type(arr_or_dtype, classes(np.datetime64, np.timedelta64))
1322  
1323  
1324  def _is_unorderable_exception(e: TypeError) -> bool:
1325      """
1326      Check if the exception raised is an unorderable exception.
1327  
1328      The error message differs for 3 <= PY <= 3.5 and PY >= 3.6, so
1329      we need to condition based on Python version.
1330  
1331      Parameters
1332      ----------
1333      e : Exception or sub-class
1334          The exception object to check.
```
- [full] callee pandas/core/indexes/base.py:1784 is_integer | def is_integer(self):
```python
1774          """
1775          return self._engine.is_unique
1776  
1777      @property
1778      def has_duplicates(self):
1779          return not self.is_unique
1780  
1781      def is_boolean(self):
1782          return self.inferred_type in ["boolean"]
1783  
1784      def is_integer(self):
1785          return self.inferred_type in ["integer"]
1786  
1787      def is_floating(self):
1788          return self.inferred_type in ["floating", "mixed-integer-float"]
1789  
1790      def is_numeric(self):
1791          return self.inferred_type in ["integer", "floating"]
1792  
1793      def is_object(self):
1794          return is_object_dtype(self.dtype)
```
- [full] callee pandas/io/formats/format.py:383 len | def len(self, text: str) -> int:
```python
 373          if footer:
 374              result += "\n" + footer
 375  
 376          return str("".join(result))
 377  
 378  
 379  class TextAdjustment:
 380      def __init__(self):
 381          self.encoding = get_option("display.encoding")
 382  
 383      def len(self, text: str) -> int:
 384          return len(text)
 385  
 386      def justify(self, texts: Any, max_len: int, mode: str = "right") -> List[str]:
 387          return justify(texts, max_len, mode=mode)
 388  
 389      def adjoin(self, space: int, *lists, **kwargs) -> str:
 390          return adjoin(space, *lists, strlen=self.len, justfunc=self.justify, **kwargs)
 391  
 392  
 393  class EastAsianTextAdjustment(TextAdjustment):
```
- [full] callee pandas/io/formats/format.py:406 len | def len(self, text: str) -> int:
```python
 396          if get_option("display.unicode.ambiguous_as_wide"):
 397              self.ambiguous_width = 2
 398          else:
 399              self.ambiguous_width = 1
 400  
 401          # Definition of East Asian Width
 402          # http://unicode.org/reports/tr11/
 403          # Ambiguous width can be changed by option
 404          self._EAW_MAP = {"Na": 1, "N": 1, "W": 2, "F": 2, "H": 1}
 405  
 406      def len(self, text: str) -> int:
 407          """
 408          Calculate display width considering unicode East Asian Width
 409          """
 410          if not isinstance(text, str):
 411              return len(text)
 412  
 413          return sum(
 414              self._EAW_MAP.get(east_asian_width(c), self.ambiguous_width) for c in text
 415          )
 416  
```
