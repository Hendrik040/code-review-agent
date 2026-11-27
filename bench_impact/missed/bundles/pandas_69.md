# pandas#69

Commit message of the reviewed change: BUG #19860 Corrected use of mixed indexes with .at (#22436)

Oracle (fix location at buggy_commit): [{'file': 'pandas/core/indexing.py', 'line_start': 2127, 'line_end': 2127}]

## Reviewed diff (introducing commit)
```diff
diff --git a/doc/source/whatsnew/v0.24.0.txt b/doc/source/whatsnew/v0.24.0.txt
index 3e22084d98..e70f3f0f61 100644
--- a/doc/source/whatsnew/v0.24.0.txt
+++ b/doc/source/whatsnew/v0.24.0.txt
@@ -663,6 +663,7 @@ Indexing
 - Fixed ``DataFrame[np.nan]`` when columns are non-unique (:issue:`21428`)
 - Bug when indexing :class:`DatetimeIndex` with nanosecond resolution dates and timezones (:issue:`11679`)
 - Bug where indexing with a Numpy array containing negative values would mutate the indexer (:issue:`21867`)
+- Bug where mixed indexes wouldn't allow integers for ``.at`` (:issue:`19860`)
 - ``Float64Index.get_loc`` now raises ``KeyError`` when boolean key passed. (:issue:`19087`)
 
 Missing
diff --git a/pandas/core/indexes/base.py b/pandas/core/indexes/base.py
index 2a0f164887..7b7fb968b3 100644
--- a/pandas/core/indexes/base.py
+++ b/pandas/core/indexes/base.py
@@ -3125,8 +3125,8 @@ class Index(IndexOpsMixin, PandasObject):
                 iloc = self.get_loc(key)
                 return s[iloc]
             except KeyError:
-                if (len(self) > 0 and
-                        self.inferred_type in ['integer', 'boolean']):
+                if (len(self) > 0
+                        and (self.holds_integer() or self.is_boolean())):
                     raise
                 elif is_integer(key):
                     return s[key]
@@ -3139,7 +3139,7 @@ class Index(IndexOpsMixin, PandasObject):
             return self._engine.get_value(s, k,
                                           tz=getattr(series.dtype, 'tz', None))
         except KeyError as e1:
-            if len(self) > 0 and self.inferred_type in ['integer', 'boolean']:
+            if len(self) > 0 and (self.holds_integer() or self.is_boolean()):
                 raise
 
             try:
diff --git a/pandas/core/indexing.py b/pandas/core/indexing.py
index 80b3d579d5..a245ecfa00 100755
--- a/pandas/core/indexing.py
+++ b/pandas/core/indexing.py
@@ -2354,7 +2354,7 @@ class _AtIndexer(_ScalarAccessIndexer):
                     raise ValueError("At based indexing on an integer index "
                                      "can only have integer indexers")
             else:
-                if is_integer(i):
+                if is_integer(i) and not ax.holds_integer():
                     raise ValueError("At based indexing on an non-integer "
                                      "index can only have non-integer "
                                      "indexers")
diff --git a/pandas/tests/indexing/test_indexing.py b/pandas/tests/indexing/test_indexing.py
index 9c992770fc..f64c506994 100644
--- a/pandas/tests/indexing/test_indexing.py
+++ b/pandas/tests/indexing/test_indexing.py
@@ -610,6 +610,22 @@ class TestFancy(Base):
     def test_index_not_contains(self, index, val):
         assert val not in index
 
+    @pytest.mark.parametrize("index,val", [
+        (Index([0, 1, '2']), 0),
+        (Index([0, 1, '2']), '2'),
+    ])
+    def test_mixed_index_contains(self, index, val):
+        # GH 19860
+        assert val in index
+
+    @pytest.mark.parametrize("index,val", [
+        (Index([0, 1, '2']), '1'),
+        (Index([0, 1, '2']), 2),
+    ])
+    def test_mixed_index_not_contains(self, index, val):
+        # GH 19860
+        assert val not in index
+
     def test_index_type_coercion(self):
 
         with catch_warnings(record=True):
@@ -710,6 +726,22 @@ class TestMisc(Base):
         for i in range(len(s)):
             assert s.iat[i] == i + 1
 
+    def test_mixed_index_assignment(self):
+        # GH 19860
+        s = Series([1, 2, 3, 4, 5], index=['a', 'b', 'c', 1, 2])
+        s.at['a'] = 11
+        assert s.iat[0] == 11
+        s.at[1] = 22
+        assert s.iat[3] == 22
+
+    def test_mixed_index_no_fallback(self):
+        # GH 19860
+        s = Series([1, 2, 3, 4, 5], index=['a', 'b', 'c', 1, 2])
+        with pytest.raises(KeyError):
+            s.at[0]
+        with pytest.raises(KeyError):
+            s.at[4]
+
     def test_rhs_alignment(self):
         # GH8258, tests that both rows & columns are aligned to what is
         # assigned to. covers both uniform data-type & multi-type cases
diff --git a/pandas/tests/indexing/test_scalar.py b/pandas/tests/indexing/test_scalar.py
index 7314ff6619..91f006e23e 100644
--- a/pandas/tests/indexing/test_scalar.py
+++ b/pandas/tests/indexing/test_scalar.py
@@ -170,3 +170,33 @@ class TestScalar(Base):
 
         result = df.at[0, 'date']
         assert result == expected
+
+    def test_mixed_index_at_iat_loc_iloc_series(self):
+        # GH 19860
+        s = Series([1, 2, 3, 4, 5], index=['a', 'b', 'c', 1, 2])
+        for el, item in s.iteritems():
+            assert s.at[el] == s.loc[el] == item
+        for i in range(len(s)):
+            assert s.iat[i] == s.iloc[i] == i + 1
+
+        with pytest.raises(KeyError):
+            s.at[4]
+        with pytest.raises(KeyError):
+            s.loc[4]
+
+    def test_mixed_index_at_iat_loc_iloc_dataframe(self):
+        # GH 19860
+        df = DataFrame([[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]],
+                       columns=['a', 'b', 'c', 1, 2])
+        for rowIdx, row in df.iterrows():
+            for el, item in row.iteritems():
+                assert df.at[rowIdx, el] == df.loc[rowIdx, el] == item
+
+        for row in range(2):
+            for i in range(5):
+                assert df.iat[row, i] == df.iloc[row, i] == row * 5 + i
+
+        with pytest.raises(KeyError):
+            df.at[0, 3]
+        with pytest.raises(KeyError):
+            df.loc[0, 3]

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/pandas/core/indexing.py b/pandas/core/indexing.py
index 6a67970820..7e56148b75 100755
--- a/pandas/core/indexing.py
+++ b/pandas/core/indexing.py
@@ -2122,11 +2122,11 @@ class _AtIndexer(_ScalarAccessIndexer):
                     raise ValueError(
                         "At based indexing on an integer index "
                         "can only have integer indexers"
                     )
             else:
-                if is_integer(i) and not ax.holds_integer():
+                if is_integer(i) and not (ax.holds_integer() or ax.is_floating()):
                     raise ValueError(
                         "At based indexing on an non-integer "
                         "index can only have non-integer "
                         "indexers"
                     )

```

## ODIS candidates: 6 total, path=small, tiers={'full': 6, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee pandas/core/frame.py:263 DataFrame | class DataFrame(NDFrame):
```python
 335          return DataFrame
 336  
 337      _constructor_sliced = Series
 338      _deprecations = NDFrame._deprecations | frozenset(
 339          ['sortlevel', 'get_value', 'set_value', 'from_csv', 'from_items'])
 340      _accessors = set()
 341  
 342      @property
 343      def _constructor_expanddim(self):
 344          from pandas.core.panel import Panel
 345          return Panel
 346  
 347      def __init__(self, data=None, index=None, columns=None, dtype=None,
 348                   copy=False):
 349          if data is None:
 350              data = {}
 351          if dtype is not None:
 352              dtype = self._validate_dtype(dtype)
 353  
 354          if isinstance(data, DataFrame):
 355              data = data._data
 356  
 357          if isinstance(data, BlockManager):
 358              mgr = self._init_mgr(data, axes=dict(index=index, columns=columns),
 359                                   dtype=dtype, copy=copy)
```
- [full] callee pandas/core/indexes/base.py:181 Index | class Index(IndexOpsMixin, PandasObject):
```python
 169  def _new_Index(cls, d):
 170      """ This is called upon unpickling, rather than the default which doesn't
 171      have arguments and breaks __new__
 172      """
 173      # required for backward compat, because PI can't be instantiated with
 174      # ordinals through __new__ GH #13277
 175      if issubclass(cls, ABCPeriodIndex):
 176          from pandas.core.indexes.period import _new_PeriodIndex
 177          return _new_PeriodIndex(cls, **d)
 178      return cls.__new__(cls, **d)
 179  
 180  
 181  class Index(IndexOpsMixin, PandasObject):
 182      """
 183      Immutable ndarray implementing an ordered, sliceable set. The basic object
 184      storing axis labels for all pandas objects
 185  
 186      Parameters
 187      ----------
 188      data : array-like (1-dimensional)
 189      dtype : NumPy dtype (default: object)
 190          If dtype is None, we find the dtype that best fits the data.
 191          If an actual dtype is provided, we coerce to that dtype if it's safe.
 192          Otherwise, an error will be raised.
 193      copy : bool
```
- [full] callee pandas/core/indexes/base.py:1548 is_integer | def is_integer(self):
```python
1538          """ return if the index has unique values """
1539          return self._engine.is_unique
1540  
1541      @property
1542      def has_duplicates(self):
1543          return not self.is_unique
1544  
1545      def is_boolean(self):
1546          return self.inferred_type in ['boolean']
1547  
1548      def is_integer(self):
1549          return self.inferred_type in ['integer']
1550  
1551      def is_floating(self):
1552          return self.inferred_type in ['floating', 'mixed-integer-float']
1553  
1554      def is_numeric(self):
1555          return self.inferred_type in ['integer', 'floating']
1556  
1557      def is_object(self):
1558          return is_object_dtype(self.dtype)
```
- [full] callee pandas/core/series.py:132 Series | class Series(base.IndexOpsMixin, generic.NDFrame):
```python
 164          Copy input data
 165      """
 166      _metadata = ['name']
 167      _accessors = {'dt', 'cat', 'str'}
 168      _deprecations = generic.NDFrame._deprecations | frozenset(
 169          ['asobject', 'sortlevel', 'reshape', 'get_value', 'set_value',
 170           'from_csv', 'valid'])
 171  
 172      # Override cache_readonly bc Series is mutable
 173      hasnans = property(base.IndexOpsMixin.hasnans.func,
 174                         doc=base.IndexOpsMixin.hasnans.__doc__)
 175  
 176      def __init__(self, data=None, index=None, dtype=None, name=None,
 177                   copy=False, fastpath=False):
 178  
 179          # we are called internally, so short-circuit
 180          if fastpath:
 181  
 182              # data is an ndarray, index is defined
 183              if not isinstance(data, SingleBlockManager):
 184                  data = SingleBlockManager(data, index, fastpath=True)
 185              if copy:
 186                  data = data.copy()
 187              if index is None:
 188                  index = data.index
```
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
