# pandas#48

Commit message of the reviewed change: REGR: Fixed AssertionError in groupby (#31616)

Oracle (fix location at buggy_commit): [{'file': 'pandas/core/groupby/generic.py', 'line_start': 1086, 'line_end': 1086}]

## Reviewed diff (introducing commit)
```diff
diff --git a/doc/source/whatsnew/v1.0.1.rst b/doc/source/whatsnew/v1.0.1.rst
index bf9fa5f9d0..5863ff7367 100644
--- a/doc/source/whatsnew/v1.0.1.rst
+++ b/doc/source/whatsnew/v1.0.1.rst
@@ -19,6 +19,7 @@ Fixed regressions
 - Fixed regression when indexing a ``Series`` or ``DataFrame`` indexed by ``DatetimeIndex`` with a slice containg a :class:`datetime.date` (:issue:`31501`)
 - Fixed regression in ``DataFrame.__setitem__`` raising an ``AttributeError`` with a :class:`MultiIndex` and a non-monotonic indexer (:issue:`31449`)
 - Fixed regression in :class:`Series` multiplication when multiplying a numeric :class:`Series` with >10000 elements with a timedelta-like scalar (:issue:`31457`)
+- Fixed regression in ``.groupby().agg()`` raising an ``AssertionError`` for some reductions like ``min`` on object-dtype columns (:issue:`31522`)
 - Fixed regression in ``.groupby()`` aggregations with categorical dtype using Cythonized reduction functions (e.g. ``first``) (:issue:`31450`)
 - Fixed regression in :meth:`GroupBy.apply` if called with a function which returned a non-pandas non-scalar object (e.g. a list or numpy array) (:issue:`31441`)
 - Fixed regression in :meth:`DataFrame.groupby` whereby taking the minimum or maximum of a column with period dtype would raise a ``TypeError``. (:issue:`31471`)
diff --git a/pandas/core/groupby/generic.py b/pandas/core/groupby/generic.py
index 27dd6e953c..f194c774cf 100644
--- a/pandas/core/groupby/generic.py
+++ b/pandas/core/groupby/generic.py
@@ -1022,6 +1022,10 @@ class DataFrameGroupBy(GroupBy):
         agg_blocks: List[Block] = []
         new_items: List[np.ndarray] = []
         deleted_items: List[np.ndarray] = []
+        # Some object-dtype blocks might be split into List[Block[T], Block[U]]
+        split_items: List[np.ndarray] = []
+        split_frames: List[DataFrame] = []
+
         no_result = object()
         for block in data.blocks:
             # Avoid inheriting result from earlier in the loop
@@ -1061,40 +1065,56 @@ class DataFrameGroupBy(GroupBy):
                 else:
                     result = cast(DataFrame, result)
                     # unwrap DataFrame to get array
+                    if len(result._data.blocks) != 1:
+                        # We've split an object block! Everything we've assumed
+                        # about a single block input returning a single block output
+                        # is a lie. To keep the code-path for the typical non-split case
+                        # clean, we choose to clean up this mess later on.
+                        split_items.append(locs)
+                        split_frames.append(result)
+                        continue
+
                     assert len(result._data.blocks) == 1
                     result = result._data.blocks[0].values
                     if isinstance(result, np.ndarray) and result.ndim == 1:
                         result = result.reshape(1, -1)
 
-            finally:
-                assert not isinstance(result, DataFrame)
-
-                if result is not no_result:
-                    # see if we can cast the block back to the original dtype
-                    result = maybe_downcast_numeric(result, block.dtype)
-
-                    if block.is_extension and isinstance(result, np.ndarray):
-                        # e.g. block.values was an IntegerArray
-                        # (1, N) case can occur if block.values was Categorical
-                        #  and result is ndarray[object]
-                        assert result.ndim == 1 or result.shape[0] == 1
-                        try:
-                            # Cast back if feasible
-                            result = type(block.values)._from_sequence(
-                                result.ravel(), dtype=block.values.dtype
-                            )
-                        except ValueError:
-                            # reshape to be valid for non-Extension Block
-                            result = result.reshape(1, -1)
+            assert not isinstance(result, DataFrame)
+
+            if result is not no_result:
+                # see if we can cast the block back to the original dtype
+                result = maybe_downcast_numeric(result, block.dtype)
+
+                if block.is_extension and isinstance(result, np.ndarray):
+                    # e.g. block.values was an IntegerArray
+                    # (1, N) case can occur if block.values was Categorical
+                    #  and result is ndarray[object]
+                    assert result.ndim == 1 or result.shape[0] == 1
+                    try:
+                        # Cast back if feasible
+                        result = type(block.values)._from_sequence(
+                            result.ravel(), dtype=block.values.dtype
+                        )
+                    except ValueError:
+                        # reshape to be valid for non-Extension Block
+                        result = result.reshape(1, -1)
 
-                    agg_block: Block = block.make_block(result)
+                agg_block: Block = block.make_block(result)
 
             new_items.append(locs)
             agg_blocks.append(agg_block)
 
-        if not agg_blocks:
+        if not (agg_blocks or split_frames):
             raise DataError("No numeric types to aggregate")
 
+        if split_items:
+            # Clean up the mess left over from split blocks.
+            for locs, result in zip(split_items, split_frames):
+                assert len(locs) == result.shape[1]
+                for i, loc in enumerate(locs):
+                    new_items.append(np.array([loc], dtype=locs.dtype))
+                    agg_blocks.append(result.iloc[:, [i]]._data.blocks[0])
+
         # reset the locs in the blocks to correspond to our
         # current ordering
         indexer = np.concatenate(new_items)
diff --git a/pandas/tests/groupby/aggregate/test_aggregate.py b/pandas/tests/groupby/aggregate/test_aggregate.py
index 4eb073a28d..ff99081521 100644
--- a/pandas/tests/groupby/aggregate/test_aggregate.py
+++ b/pandas/tests/groupby/aggregate/test_aggregate.py
@@ -377,6 +377,49 @@ def test_agg_index_has_complex_internals(index):
     tm.assert_frame_equal(result, expected)
 
 
+def test_agg_split_block():
+    # https://github.com/pandas-dev/pandas/issues/31522
+    df = pd.DataFrame(
+        {
+            "key1": ["a", "a", "b", "b", "a"],
+            "key2": ["one", "two", "one", "two", "one"],
+            "key3": ["three", "three", "three", "six", "six"],
+        }
+    )
+    result = df.groupby("key1").min()
+    expected = pd.DataFrame(
+        {"key2": ["one", "one"], "key3": ["six", "six"]},
+        index=pd.Index(["a", "b"], name="key1"),
+    )
+    tm.assert_frame_equal(result, expected)
+
+
+def test_agg_split_object_part_datetime():
+    # https://github.com/pandas-dev/pandas/pull/31616
+    df = pd.DataFrame(
+        {
+            "A": pd.date_range("2000", periods=4),
+            "B": ["a", "b", "c", "d"],
+            "C": [1, 2, 3, 4],
+            "D": ["b", "c", "d", "e"],
+            "E": pd.date_range("2000", periods=4),
+            "F": [1, 2, 3, 4],
+        }
+    ).astype(object)
+    result = df.groupby([0, 0, 0, 0]).min()
+    expected = pd.DataFrame(
+        {
+            "A": [pd.Timestamp("2000")],
+            "B": ["a"],
+            "C": [1],
+            "D": ["b"],
+            "E": [pd.Timestamp("2000")],
+            "F": [1],
+        }
+    )
+    tm.assert_frame_equal(result, expected)
+
+
 def test_agg_cython_category_not_implemented_fallback():
     # https://github.com/pandas-dev/pandas/issues/31450
     df = pd.DataFrame({"col_num": [1, 1, 2, 3]})

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/pandas/core/groupby/generic.py b/pandas/core/groupby/generic.py
index b7ac304863..a9a608e6f7 100644
--- a/pandas/core/groupby/generic.py
+++ b/pandas/core/groupby/generic.py
@@ -1081,11 +1081,11 @@ class DataFrameGroupBy(GroupBy):
                     try:
                         # Cast back if feasible
                         result = type(block.values)._from_sequence(
                             result.ravel(), dtype=block.values.dtype
                         )
-                    except ValueError:
+                    except (ValueError, TypeError):
                         # reshape to be valid for non-Extension Block
                         result = result.reshape(1, -1)
 
                 agg_block: Block = block.make_block(result)
 

```

## ODIS candidates: 10 total, path=small, tiers={'full': 10, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee pandas/core/arrays/boolean.py:77 type | def type(self) -> Type[np.bool_]:
```python
  67          """
  68          BooleanDtype uses :attr:`pandas.NA` as the missing NA value.
  69  
  70          .. warning::
  71  
  72             `na_value` may change in a future release.
  73          """
  74          return libmissing.NA
  75  
  76      @property
  77      def type(self) -> Type[np.bool_]:
  78          return np.bool_
  79  
  80      @property
  81      def kind(self) -> str:
  82          return "b"
  83  
  84      @classmethod
  85      def construct_array_type(cls) -> Type["BooleanArray"]:
  86          """
  87          Return the array type associated with this dtype.
```
- [full] callee pandas/core/arrays/numpy_.py:68 type | def type(self) -> Type[np.generic]:
```python
  58          return self._dtype
  59  
  60      @property
  61      def name(self) -> str:
  62          """
  63          A bit-width name for this data-type.
  64          """
  65          return self._dtype.name
  66  
  67      @property
  68      def type(self) -> Type[np.generic]:
  69          """
  70          The type object used to instantiate a scalar of this NumPy data-type.
  71          """
  72          return self._dtype.type
  73  
  74      @property
  75      def _is_numeric(self) -> bool:
  76          # exclude object, str, unicode, void.
  77          return self.kind in set("biufc")
  78  
```
- [full] callee pandas/core/arrays/sparse/dtype.py:158 type | def type(self):
```python
 148          return is_bool_dtype(self.subtype)
 149  
 150      @property
 151      def kind(self):
 152          """
 153          The sparse kind. Either 'integer', or 'block'.
 154          """
 155          return self.subtype.kind
 156  
 157      @property
 158      def type(self):
 159          return self.subtype.type
 160  
 161      @property
 162      def subtype(self):
 163          return self._dtype
 164  
 165      @property
 166      def name(self):
 167          return f"Sparse[{self.subtype.name}, {self.fill_value}]"
 168  
```
- [full] callee pandas/core/arrays/string_.py:60 type | def type(self) -> Type[str]:
```python
  50      >>> pd.StringDtype()
  51      StringDtype
  52      """
  53  
  54      name = "string"
  55  
  56      #: StringDtype.na_value uses pandas.NA
  57      na_value = libmissing.NA
  58  
  59      @property
  60      def type(self) -> Type[str]:
  61          return str
  62  
  63      @classmethod
  64      def construct_array_type(cls) -> Type["StringArray"]:
  65          """
  66          Return the array type associated with this dtype.
  67  
  68          Returns
  69          -------
  70          type
```
- [full] callee pandas/core/computation/ops.py:132 type | def type(self):
```python
 122          if isinstance(key, str):
 123              self.env.swapkey(self.local_name, key, new_value=value)
 124  
 125          self.value = value
 126  
 127      @property
 128      def is_scalar(self) -> bool:
 129          return is_scalar(self._value)
 130  
 131      @property
 132      def type(self):
 133          try:
 134              # potentially very slow for large, mixed dtype frames
 135              return self._value.values.dtype
 136          except AttributeError:
 137              try:
 138                  # ndarray
 139                  return self._value.dtype
 140              except AttributeError:
 141                  # scalar
 142                  return type(self._value)
```
- [full] callee pandas/core/dtypes/base.py:137 type | def type(self) -> Type:
```python
 127          """
 128          Default NA value to use for this type.
 129  
 130          This is used in e.g. ExtensionArray.take. This should be the
 131          user-facing "boxed" version of the NA value, not the physical NA value
 132          for storage.  e.g. for JSONArray, this is an empty dictionary.
 133          """
 134          return np.nan
 135  
 136      @property
 137      def type(self) -> Type:
 138          """
 139          The scalar type for the array, e.g. ``int``
 140  
 141          It's expected ``ExtensionArray[item]`` returns an instance
 142          of ``ExtensionDtype.type`` for scalar ``item``, assuming
 143          that value is valid (not NA). NA values do not need to be
 144          instances of `type`.
 145          """
 146          raise AbstractMethodError(self)
 147  
```
- [full] callee pandas/core/dtypes/cast.py:174 maybe_downcast_numeric | def maybe_downcast_numeric(result, dtype, do_round: bool = False):
```python
 164          try:
 165              return PeriodArray(result, freq=dtype.freq)
 166          except TypeError:
 167              # e.g. TypeError: int() argument must be a string, a
 168              #  bytes-like object or a number, not 'Period
 169              pass
 170  
 171      return result
 172  
 173  
 174  def maybe_downcast_numeric(result, dtype, do_round: bool = False):
 175      """
 176      Subset of maybe_downcast_to_dtype restricted to numeric dtypes.
 177  
 178      Parameters
 179      ----------
 180      result : ndarray or ExtensionArray
 181      dtype : np.dtype or ExtensionDtype
 182      do_round : bool
 183  
 184      Returns
```
- [full] callee pandas/core/dtypes/dtypes.py:1098 type | def type(self):
```python
1088  
1089          msg = (
1090              f"Cannot construct a 'IntervalDtype' from '{string}'.\n\n"
1091              "Incorrectly formatted string passed to constructor. "
1092              "Valid formats include Interval or Interval[dtype] "
1093              "where dtype is numeric, datetime, or timedelta"
1094          )
1095          raise TypeError(msg)
1096  
1097      @property
1098      def type(self):
1099          return Interval
1100  
1101      def __str__(self) -> str_type:
1102          if self.subtype is None:
1103              return "interval"
1104          return f"interval[{self.subtype}]"
1105  
1106      def __hash__(self) -> int:
1107          # make myself hashable
1108          return hash(str(self))
```
- [full] callee pandas/io/formats/format.py:402 len | def len(self, text: str) -> int:
```python
 392          if footer:
 393              result += "\n" + footer
 394  
 395          return str("".join(result))
 396  
 397  
 398  class TextAdjustment:
 399      def __init__(self):
 400          self.encoding = get_option("display.encoding")
 401  
 402      def len(self, text: str) -> int:
 403          return len(text)
 404  
 405      def justify(self, texts: Any, max_len: int, mode: str = "right") -> List[str]:
 406          return justify(texts, max_len, mode=mode)
 407  
 408      def adjoin(self, space: int, *lists, **kwargs) -> str:
 409          return adjoin(space, *lists, strlen=self.len, justfunc=self.justify, **kwargs)
 410  
 411  
 412  class EastAsianTextAdjustment(TextAdjustment):
```
- [full] callee pandas/io/formats/format.py:425 len | def len(self, text: str) -> int:
```python
 415          if get_option("display.unicode.ambiguous_as_wide"):
 416              self.ambiguous_width = 2
 417          else:
 418              self.ambiguous_width = 1
 419  
 420          # Definition of East Asian Width
 421          # https://unicode.org/reports/tr11/
 422          # Ambiguous width can be changed by option
 423          self._EAW_MAP = {"Na": 1, "N": 1, "W": 2, "F": 2, "H": 1}
 424  
 425      def len(self, text: str) -> int:
 426          """
 427          Calculate display width considering unicode East Asian Width
 428          """
 429          if not isinstance(text, str):
 430              return len(text)
 431  
 432          return sum(
 433              self._EAW_MAP.get(east_asian_width(c), self.ambiguous_width) for c in text
 434          )
 435  
```
