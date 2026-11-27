# pandas#22

Commit message of the reviewed change: ERR: Raise NotImplementedError with BaseIndexer and certain rolling operations (#33057)

Oracle (fix location at buggy_commit): [{'file': 'pandas/core/window/rolling.py', 'line_start': 1174, 'line_end': 1175}, {'file': 'pandas/core/window/rolling.py', 'line_start': 1942, 'line_end': 1942}]

## Reviewed diff (introducing commit)
```diff
diff --git a/doc/source/whatsnew/v1.1.0.rst b/doc/source/whatsnew/v1.1.0.rst
index 570a5e3ce9..dffb2fd9a7 100644
--- a/doc/source/whatsnew/v1.1.0.rst
+++ b/doc/source/whatsnew/v1.1.0.rst
@@ -85,6 +85,7 @@ Other API changes
 - Added :meth:`DataFrame.value_counts` (:issue:`5377`)
 - :meth:`Groupby.groups` now returns an abbreviated representation when called on large dataframes (:issue:`1135`)
 - ``loc`` lookups with an object-dtype :class:`Index` and an integer key will now raise ``KeyError`` instead of ``TypeError`` when key is missing (:issue:`31905`)
+- Using a :func:`pandas.api.indexers.BaseIndexer` with ``min``, ``max``, ``std``, ``var``, ``count``, ``skew``, ``cov``, ``corr`` will now raise a ``NotImplementedError`` (:issue:`32865`)
 -
 
 Backwards incompatible API changes
diff --git a/pandas/core/window/common.py b/pandas/core/window/common.py
index fcde494f7f..8abc47886d 100644
--- a/pandas/core/window/common.py
+++ b/pandas/core/window/common.py
@@ -323,3 +323,13 @@ def get_weighted_roll_func(cfunc: Callable) -> Callable:
         return cfunc(arg, window, min_periods)
 
     return func
+
+
+def validate_baseindexer_support(func_name: Optional[str]) -> None:
+    # GH 32865: These functions work correctly with a BaseIndexer subclass
+    BASEINDEXER_WHITELIST = {"mean", "sum", "median", "kurt", "quantile"}
+    if isinstance(func_name, str) and func_name not in BASEINDEXER_WHITELIST:
+        raise NotImplementedError(
+            f"{func_name} is not supported with using a BaseIndexer "
+            f"subclasses. You can use .apply() with {func_name}."
+        )
diff --git a/pandas/core/window/rolling.py b/pandas/core/window/rolling.py
index aeab51149e..dc8cf839d0 100644
--- a/pandas/core/window/rolling.py
+++ b/pandas/core/window/rolling.py
@@ -46,6 +46,7 @@ from pandas.core.window.common import (
     calculate_center_offset,
     calculate_min_periods,
     get_weighted_roll_func,
+    validate_baseindexer_support,
     zsqrt,
 )
 from pandas.core.window.indexers import (
@@ -391,11 +392,12 @@ class _Window(PandasObject, ShallowMixin, SelectionMixin):
             return self._get_roll_func(f"{func}_variable")
         return partial(self._get_roll_func(f"{func}_fixed"), win=self._get_window())
 
-    def _get_window_indexer(self, window: int) -> BaseIndexer:
+    def _get_window_indexer(self, window: int, func_name: Optional[str]) -> BaseIndexer:
         """
         Return an indexer class that will compute the window start and end bounds
         """
         if isinstance(self.window, BaseIndexer):
+            validate_baseindexer_support(func_name)
             return self.window
         if self.is_freq_type:
             return VariableWindowIndexer(index_array=self._on.asi8, window_size=window)
@@ -441,7 +443,7 @@ class _Window(PandasObject, ShallowMixin, SelectionMixin):
 
         blocks, obj = self._create_blocks()
         block_list = list(blocks)
-        window_indexer = self._get_window_indexer(window)
+        window_indexer = self._get_window_indexer(window, name)
 
         results = []
         exclude: List[Scalar] = []
@@ -1173,6 +1175,8 @@ class _Rolling_and_Expanding(_Rolling):
     )
 
     def count(self):
+        if isinstance(self.window, BaseIndexer):
+            validate_baseindexer_support("count")
 
         blocks, obj = self._create_blocks()
         results = []
@@ -1627,6 +1631,9 @@ class _Rolling_and_Expanding(_Rolling):
     """
 
     def cov(self, other=None, pairwise=None, ddof=1, **kwargs):
+        if isinstance(self.window, BaseIndexer):
+            validate_baseindexer_support("cov")
+
         if other is None:
             other = self._selected_obj
             # only default unset
@@ -1770,6 +1777,9 @@ class _Rolling_and_Expanding(_Rolling):
     )
 
     def corr(self, other=None, pairwise=None, **kwargs):
+        if isinstance(self.window, BaseIndexer):
+            validate_baseindexer_support("corr")
+
         if other is None:
             other = self._selected_obj
             # only default unset
diff --git a/pandas/tests/window/test_base_indexer.py b/pandas/tests/window/test_base_indexer.py
index 606520c6d6..e9190dfde4 100644
--- a/pandas/tests/window/test_base_indexer.py
+++ b/pandas/tests/window/test_base_indexer.py
@@ -80,3 +80,18 @@ def test_win_type_not_implemented():
     indexer = CustomIndexer()
     with pytest.raises(NotImplementedError, match="BaseIndexer subclasses not"):
         df.rolling(indexer, win_type="boxcar")
+
+
+@pytest.mark.parametrize(
+    "func", ["min", "max", "std", "var", "count", "skew", "cov", "corr"]
+)
+def test_notimplemented_functions(func):
+    # GH 32865
+    class CustomIndexer(BaseIndexer):
+        def get_window_bounds(self, num_values, min_periods, center, closed):
+            return np.array([0, 1]), np.array([1, 2])
+
+    df = DataFrame({"values": range(2)})
+    indexer = CustomIndexer()
+    with pytest.raises(NotImplementedError, match=f"{func} is not supported"):
+        getattr(df.rolling(indexer), func)()

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/pandas/core/window/rolling.py b/pandas/core/window/rolling.py
index 3fdf81c4bb..62f470060b 100644
--- a/pandas/core/window/rolling.py
+++ b/pandas/core/window/rolling.py
@@ -1169,12 +1169,13 @@ class _Rolling_and_Expanding(_Rolling):
     dtype: float64
     """
     )
 
     def count(self):
-        if isinstance(self.window, BaseIndexer):
-            validate_baseindexer_support("count")
+        # GH 32865. Using count with custom BaseIndexer subclass
+        # implementations shouldn't end up here
+        assert not isinstance(self.window, BaseIndexer)
 
         blocks, obj = self._create_blocks()
         results = []
         for b in blocks:
             result = b.notna().astype(int)
@@ -1937,11 +1938,13 @@ class Rolling(_Rolling_and_Expanding):
     @Substitution(name="rolling")
     @Appender(_shared_docs["count"])
     def count(self):
 
         # different impl for freq counting
-        if self.is_freq_type:
+        # GH 32865. Use a custom count function implementation
+        # when using a BaseIndexer subclass as a window
+        if self.is_freq_type or isinstance(self.window, BaseIndexer):
             window_func = self._get_roll_func("roll_count")
             return self._apply(window_func, center=self.center, name="count")
 
         return super().count()
 

```

## ODIS candidates: 5 total, path=small, tiers={'full': 5, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee pandas/core/frame.py:326 DataFrame | class DataFrame(NDFrame):
```python
 410  
 411      _constructor_sliced: Type[Series] = Series
 412      _deprecations: FrozenSet[str] = NDFrame._deprecations | frozenset([])
 413      _accessors: Set[str] = {"sparse"}
 414  
 415      @property
 416      def _constructor_expanddim(self):
 417          raise NotImplementedError("Not supported for DataFrames!")
 418  
 419      # ----------------------------------------------------------------------
 420      # Constructors
 421  
 422      def __init__(
 423          self,
 424          data=None,
 425          index: Optional[Axes] = None,
 426          columns: Optional[Axes] = None,
 427          dtype: Optional[Dtype] = None,
 428          copy: bool = False,
 429      ):
 430          if data is None:
 431              data = {}
 432          if dtype is not None:
 433              dtype = self._validate_dtype(dtype)
 434  
```
- [full] callee pandas/tests/window/test_base_indexer.py:33 CustomIndexer | class CustomIndexer(BaseIndexer):
```python
  21      s = Series(range(10))
  22      indexer = ExpandingIndexer()
  23      result = s.rolling(indexer).mean()
  24      expected = s.expanding().mean()
  25      tm.assert_series_equal(result, expected)
  26  
  27  
  28  def test_indexer_constructor_arg():
  29      # Example found in computation.rst
  30      use_expanding = [True, False, True, False, True]
  31      df = DataFrame({"values": range(5)})
  32  
  33      class CustomIndexer(BaseIndexer):
  34          def get_window_bounds(self, num_values, min_periods, center, closed):
  35              start = np.empty(num_values, dtype=np.int64)
  36              end = np.empty(num_values, dtype=np.int64)
  37              for i in range(num_values):
  38                  if self.use_expanding[i]:
  39                      start[i] = 0
  40                      end[i] = i + 1
  41                  else:
  42                      start[i] = i
  43                      end[i] = i + self.window_size
  44              return start, end
  45  
```
- [full] callee pandas/tests/window/test_base_indexer.py:55 CustomIndexer | class CustomIndexer(BaseIndexer):
```python
  43                      end[i] = i + self.window_size
  44              return start, end
  45  
  46      indexer = CustomIndexer(window_size=1, use_expanding=use_expanding)
  47      result = df.rolling(indexer).sum()
  48      expected = DataFrame({"values": [0.0, 1.0, 3.0, 3.0, 10.0]})
  49      tm.assert_frame_equal(result, expected)
  50  
  51  
  52  def test_indexer_accepts_rolling_args():
  53      df = DataFrame({"values": range(5)})
  54  
  55      class CustomIndexer(BaseIndexer):
  56          def get_window_bounds(self, num_values, min_periods, center, closed):
  57              start = np.empty(num_values, dtype=np.int64)
  58              end = np.empty(num_values, dtype=np.int64)
  59              for i in range(num_values):
  60                  if center and min_periods == 1 and closed == "both" and i == 2:
  61                      start[i] = 0
  62                      end[i] = num_values
  63                  else:
  64                      start[i] = i
  65                      end[i] = i + self.window_size
  66              return start, end
  67  
```
- [full] caller pandas/tests/window/test_base_indexer.py:46 call to CustomIndexer | indexer = CustomIndexer(window_size=1, use_expanding=use_expanding)
```python
  38                  if self.use_expanding[i]:
  39                      start[i] = 0
  40                      end[i] = i + 1
  41                  else:
  42                      start[i] = i
  43                      end[i] = i + self.window_size
  44              return start, end
  45  
  46      indexer = CustomIndexer(window_size=1, use_expanding=use_expanding)
  47      result = df.rolling(indexer).sum()
  48      expected = DataFrame({"values": [0.0, 1.0, 3.0, 3.0, 10.0]})
  49      tm.assert_frame_equal(result, expected)
  50  
  51  
  52  def test_indexer_accepts_rolling_args():
  53      df = DataFrame({"values": range(5)})
  54  
```
- [full] caller pandas/tests/window/test_base_indexer.py:68 call to CustomIndexer | indexer = CustomIndexer(window_size=1)
```python
  60                  if center and min_periods == 1 and closed == "both" and i == 2:
  61                      start[i] = 0
  62                      end[i] = num_values
  63                  else:
  64                      start[i] = i
  65                      end[i] = i + self.window_size
  66              return start, end
  67  
  68      indexer = CustomIndexer(window_size=1)
  69      result = df.rolling(indexer, center=True, min_periods=1, closed="both").sum()
  70      expected = DataFrame({"values": [0.0, 1.0, 10.0, 3.0, 4.0]})
  71      tm.assert_frame_equal(result, expected)
  72  
  73  
  74  def test_win_type_not_implemented():
  75      class CustomIndexer(BaseIndexer):
  76          def get_window_bounds(self, num_values, min_periods, center, closed):
```
