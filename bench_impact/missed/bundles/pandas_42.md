# pandas#42

Commit message of the reviewed change: CLN: remove check_series_type (#32513)

Oracle (fix location at buggy_commit): [{'file': 'pandas/_testing.py', 'line_start': 1163, 'line_end': 1163}, {'file': 'pandas/_testing.py', 'line_start': 1173, 'line_end': 1173}]

## Reviewed diff (introducing commit)
```diff
diff --git a/pandas/_testing.py b/pandas/_testing.py
index 33ec4e4886..5e94ac3b3d 100644
--- a/pandas/_testing.py
+++ b/pandas/_testing.py
@@ -34,6 +34,7 @@ from pandas.core.dtypes.common import (
     is_interval_dtype,
     is_list_like,
     is_number,
+    is_numeric_dtype,
     is_period_dtype,
     is_sequence,
     is_timedelta64_dtype,
@@ -1064,7 +1065,6 @@ def assert_series_equal(
     right,
     check_dtype=True,
     check_index_type="equiv",
-    check_series_type=True,
     check_less_precise=False,
     check_names=True,
     check_exact=False,
@@ -1085,8 +1085,6 @@ def assert_series_equal(
     check_index_type : bool or {'equiv'}, default 'equiv'
         Whether to check the Index class, dtype and inferred_type
         are identical.
-    check_series_type : bool, default True
-        Whether to check the Series class is identical.
     check_less_precise : bool or int, default False
         Specify comparison precision. Only used when check_exact is False.
         5 digits (False) or 3 digits (True) after decimal points are compared.
@@ -1118,11 +1116,10 @@ def assert_series_equal(
     # instance validation
     _check_isinstance(left, right, Series)
 
-    if check_series_type:
-        # ToDo: There are some tests using rhs is sparse
-        # lhs is dense. Should use assert_class_equal in future
-        assert isinstance(left, type(right))
-        # assert_class_equal(left, right, obj=obj)
+    # TODO: There are some tests using rhs is sparse
+    # lhs is dense. Should use assert_class_equal in future
+    assert isinstance(left, type(right))
+    # assert_class_equal(left, right, obj=obj)
 
     # length comparison
     if len(left) != len(right):
@@ -1147,8 +1144,8 @@ def assert_series_equal(
         # is False. We'll still raise if only one is a `Categorical`,
         # regardless of `check_categorical`
         if (
-            is_categorical_dtype(left)
-            and is_categorical_dtype(right)
+            is_categorical_dtype(left.dtype)
+            and is_categorical_dtype(right.dtype)
             and not check_categorical
         ):
             pass
@@ -1156,38 +1153,31 @@ def assert_series_equal(
             assert_attr_equal("dtype", left, right, obj=f"Attributes of {obj}")
 
     if check_exact:
+        if not is_numeric_dtype(left.dtype):
+            raise AssertionError("check_exact may only be used with numeric Series")
+
         assert_numpy_array_equal(
-            left._internal_get_values(),
-            right._internal_get_values(),
-            check_dtype=check_dtype,
-            obj=str(obj),
+            left._values, right._values, check_dtype=check_dtype, obj=str(obj)
         )
-    elif check_datetimelike_compat:
+    elif check_datetimelike_compat and (
+        needs_i8_conversion(left.dtype) or needs_i8_conversion(right.dtype)
+    ):
         # we want to check only if we have compat dtypes
         # e.g. integer and M|m are NOT compat, but we can simply check
         # the values in that case
-        if needs_i8_conversion(left) or needs_i8_conversion(right):
-
-            # datetimelike may have different objects (e.g. datetime.datetime
-            # vs Timestamp) but will compare equal
-            if not Index(left._values).equals(Index(right._values)):
-                msg = (
-                    f"[datetimelike_compat=True] {left._values} "
-                    f"is not equal to {right._values}."
-                )
-                raise AssertionError(msg)
-        else:
-            assert_numpy_array_equal(
-                left._internal_get_values(),
-                right._internal_get_values(),
-                check_dtype=check_dtype,
+
+        # datetimelike may have different objects (e.g. datetime.datetime
+        # vs Timestamp) but will compare equal
+        if not Index(left._values).equals(Index(right._values)):
+            msg = (
+                f"[datetimelike_compat=True] {left._values} "
+                f"is not equal to {right._values}."
             )
-    elif is_interval_dtype(left) or is_interval_dtype(right):
+            raise AssertionError(msg)
+    elif is_interval_dtype(left.dtype) or is_interval_dtype(right.dtype):
         assert_interval_array_equal(left.array, right.array)
-    elif is_extension_array_dtype(left.dtype) and is_datetime64tz_dtype(left.dtype):
+    elif is_datetime64tz_dtype(left.dtype):
         # .values is an ndarray, but ._values is the ExtensionArray.
-        # TODO: Use .array
-        assert is_extension_array_dtype(right.dtype)
         assert_extension_array_equal(left._values, right._values)
     elif (
         is_extension_array_dtype(left)
diff --git a/pandas/tests/io/pytables/test_store.py b/pandas/tests/io/pytables/test_store.py
index fcc48daa59..34f6a73812 100644
--- a/pandas/tests/io/pytables/test_store.py
+++ b/pandas/tests/io/pytables/test_store.py
@@ -2312,7 +2312,7 @@ class TestHDFStore:
             values = np.random.randn(2)
 
             func = lambda l, r: tm.assert_series_equal(
-                l, r, check_dtype=True, check_index_type=True, check_series_type=True
+                l, r, check_dtype=True, check_index_type=True
             )
 
         with catch_warnings(record=True):

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/pandas/_testing.py b/pandas/_testing.py
index d473b453d7..f96e3872eb 100644
--- a/pandas/_testing.py
+++ b/pandas/_testing.py
@@ -1158,21 +1158,21 @@ def assert_series_equal(
             msg = (
                 f"[datetimelike_compat=True] {left._values} "
                 f"is not equal to {right._values}."
             )
             raise AssertionError(msg)
-    elif is_interval_dtype(left.dtype) or is_interval_dtype(right.dtype):
+    elif is_interval_dtype(left.dtype) and is_interval_dtype(right.dtype):
         assert_interval_array_equal(left.array, right.array)
     elif is_categorical_dtype(left.dtype) or is_categorical_dtype(right.dtype):
         _testing.assert_almost_equal(
             left._values,
             right._values,
             check_less_precise=check_less_precise,
             check_dtype=check_dtype,
             obj=str(obj),
         )
-    elif is_extension_array_dtype(left.dtype) or is_extension_array_dtype(right.dtype):
+    elif is_extension_array_dtype(left.dtype) and is_extension_array_dtype(right.dtype):
         assert_extension_array_equal(left._values, right._values)
     elif needs_i8_conversion(left.dtype) or needs_i8_conversion(right.dtype):
         # DatetimeArray or TimedeltaArray
         assert_extension_array_equal(left._values, right._values)
     else:

```

## ODIS candidates: 13 total, path=small, tiers={'full': 13, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee pandas/core/arrays/boolean.py:78 type | def type(self) -> Type[np.bool_]:
```python
  68          """
  69          BooleanDtype uses :attr:`pandas.NA` as the missing NA value.
  70  
  71          .. warning::
  72  
  73             `na_value` may change in a future release.
  74          """
  75          return libmissing.NA
  76  
  77      @property
  78      def type(self) -> Type[np.bool_]:
  79          return np.bool_
  80  
  81      @property
  82      def kind(self) -> str:
  83          return "b"
  84  
  85      @classmethod
  86      def construct_array_type(cls) -> Type["BooleanArray"]:
  87          """
  88          Return the array type associated with this dtype.
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
- [full] callee pandas/core/computation/ops.py:133 type | def type(self):
```python
 123          if isinstance(key, str):
 124              self.env.swapkey(self.local_name, key, new_value=value)
 125  
 126          self.value = value
 127  
 128      @property
 129      def is_scalar(self) -> bool:
 130          return is_scalar(self._value)
 131  
 132      @property
 133      def type(self):
 134          try:
 135              # potentially very slow for large, mixed dtype frames
 136              return self._value.values.dtype
 137          except AttributeError:
 138              try:
 139                  # ndarray
 140                  return self._value.dtype
 141              except AttributeError:
 142                  # scalar
 143                  return type(self._value)
```
- [full] callee pandas/core/dtypes/base.py:142 type | def type(self) -> Type:
```python
 132          """
 133          Default NA value to use for this type.
 134  
 135          This is used in e.g. ExtensionArray.take. This should be the
 136          user-facing "boxed" version of the NA value, not the physical NA value
 137          for storage.  e.g. for JSONArray, this is an empty dictionary.
 138          """
 139          return np.nan
 140  
 141      @property
 142      def type(self) -> Type:
 143          """
 144          The scalar type for the array, e.g. ``int``
 145  
 146          It's expected ``ExtensionArray[item]`` returns an instance
 147          of ``ExtensionDtype.type`` for scalar ``item``, assuming
 148          that value is valid (not NA). NA values do not need to be
 149          instances of `type`.
 150          """
 151          raise AbstractMethodError(self)
 152  
```
- [full] callee pandas/core/dtypes/common.py:393 is_datetime64tz_dtype | def is_datetime64tz_dtype(arr_or_dtype) -> bool:
```python
 383      >>> is_datetime64_dtype(np.array([], dtype=int))
 384      False
 385      >>> is_datetime64_dtype(np.array([], dtype=np.datetime64))
 386      True
 387      >>> is_datetime64_dtype([1, 2, 3])
 388      False
 389      """
 390      return _is_dtype_type(arr_or_dtype, classes(np.datetime64))
 391  
 392  
 393  def is_datetime64tz_dtype(arr_or_dtype) -> bool:
 394      """
 395      Check whether an array-like or dtype is of a DatetimeTZDtype dtype.
 396  
 397      Parameters
 398      ----------
 399      arr_or_dtype : array-like
 400          The array-like or dtype to check.
 401  
 402      Returns
 403      -------
```
- [full] callee pandas/core/dtypes/common.py:493 is_interval_dtype | def is_interval_dtype(arr_or_dtype) -> bool:
```python
 483      False
 484      >>> is_period_dtype(pd.PeriodIndex([], freq="A"))
 485      True
 486      """
 487      # TODO: Consider making Period an instance of PeriodDtype
 488      if arr_or_dtype is None:
 489          return False
 490      return PeriodDtype.is_dtype(arr_or_dtype)
 491  
 492  
 493  def is_interval_dtype(arr_or_dtype) -> bool:
 494      """
 495      Check whether an array-like or dtype is of the Interval dtype.
 496  
 497      Parameters
 498      ----------
 499      arr_or_dtype : array-like
 500          The array-like or dtype to check.
 501  
 502      Returns
 503      -------
```
- [full] callee pandas/core/dtypes/common.py:528 is_categorical_dtype | def is_categorical_dtype(arr_or_dtype) -> bool:
```python
 518      False
 519      >>> is_interval_dtype(pd.IntervalIndex([interval]))
 520      True
 521      """
 522      # TODO: Consider making Interval an instance of IntervalDtype
 523      if arr_or_dtype is None:
 524          return False
 525      return IntervalDtype.is_dtype(arr_or_dtype)
 526  
 527  
 528  def is_categorical_dtype(arr_or_dtype) -> bool:
 529      """
 530      Check whether an array-like or dtype is of the Categorical dtype.
 531  
 532      Parameters
 533      ----------
 534      arr_or_dtype : array-like
 535          The array-like or dtype to check.
 536  
 537      Returns
 538      -------
```
- [full] callee pandas/core/dtypes/common.py:1187 needs_i8_conversion | def needs_i8_conversion(arr_or_dtype) -> bool:
```python
1177          """
1178          Check if an object has a numeric dtype (i.e. integer or float).
1179          """
1180          return is_integer_dtype(x) or is_float_dtype(x)
1181  
1182      return (needs_i8_conversion(a) and is_numeric(b)) or (
1183          needs_i8_conversion(b) and is_numeric(a)
1184      )
1185  
1186  
1187  def needs_i8_conversion(arr_or_dtype) -> bool:
1188      """
1189      Check whether the array or dtype should be converted to int64.
1190  
1191      An array-like or dtype "needs" such a conversion if the array-like
1192      or dtype is of a datetime-like dtype
1193  
1194      Parameters
1195      ----------
1196      arr_or_dtype : array-like
1197          The array or dtype to check.
```
- [full] callee pandas/core/dtypes/common.py:1230 is_numeric_dtype | def is_numeric_dtype(arr_or_dtype) -> bool:
```python
1220      """
1221      if arr_or_dtype is None:
1222          return False
1223      return (
1224          is_datetime_or_timedelta_dtype(arr_or_dtype)
1225          or is_datetime64tz_dtype(arr_or_dtype)
1226          or is_period_dtype(arr_or_dtype)
1227      )
1228  
1229  
1230  def is_numeric_dtype(arr_or_dtype) -> bool:
1231      """
1232      Check whether the provided array or dtype is of a numeric dtype.
1233  
1234      Parameters
1235      ----------
1236      arr_or_dtype : array-like
1237          The array or dtype to check.
1238  
1239      Returns
1240      -------
```
- [full] callee pandas/core/dtypes/dtypes.py:1113 type | def type(self):
```python
1103  
1104          msg = (
1105              f"Cannot construct a 'IntervalDtype' from '{string}'.\n\n"
1106              "Incorrectly formatted string passed to constructor. "
1107              "Valid formats include Interval or Interval[dtype] "
1108              "where dtype is numeric, datetime, or timedelta"
1109          )
1110          raise TypeError(msg)
1111  
1112      @property
1113      def type(self):
1114          return Interval
1115  
1116      def __str__(self) -> str_type:
1117          if self.subtype is None:
1118              return "interval"
1119          return f"interval[{self.subtype}]"
1120  
1121      def __hash__(self) -> int:
1122          # make myself hashable
1123          return hash(str(self))
```
- [full] callee pandas/core/indexes/base.py:184 Index | class Index(IndexOpsMixin, PandasObject):
```python
 172          from pandas.core.indexes.period import _new_PeriodIndex
 173  
 174          return _new_PeriodIndex(cls, **d)
 175  
 176      if issubclass(cls, ABCMultiIndex):
 177          if "labels" in d and "codes" not in d:
 178              # GH#23752 "labels" kwarg has been replaced with "codes"
 179              d["codes"] = d.pop("labels")
 180  
 181      return cls.__new__(cls, **d)
 182  
 183  
 184  class Index(IndexOpsMixin, PandasObject):
 185      """
 186      Immutable ndarray implementing an ordered, sliceable set. The basic object
 187      storing axis labels for all pandas objects.
 188  
 189      Parameters
 190      ----------
 191      data : array-like (1-dimensional)
 192      dtype : NumPy dtype (default: object)
 193          If dtype is None, we find the dtype that best fits the data.
 194          If an actual dtype is provided, we coerce to that dtype if it's safe.
 195          Otherwise, an error will be raised.
 196      copy : bool
```
