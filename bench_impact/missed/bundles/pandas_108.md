# pandas#108

Commit message of the reviewed change: Remove _DtypeOpsMixin (#26331)

Oracle (fix location at buggy_commit): [{'file': 'pandas/core/dtypes/cast.py', 'line_start': 44, 'line_end': 44}]

## Reviewed diff (introducing commit)
```diff
diff --git a/pandas/core/dtypes/base.py b/pandas/core/dtypes/base.py
index 3fc5acf7de..da8908ec39 100644
--- a/pandas/core/dtypes/base.py
+++ b/pandas/core/dtypes/base.py
@@ -8,141 +8,7 @@ from pandas.errors import AbstractMethodError
 from pandas.core.dtypes.generic import ABCDataFrame, ABCIndexClass, ABCSeries
 
 
-class _DtypeOpsMixin:
-    # Not all of pandas' extension dtypes are compatibile with
-    # the new ExtensionArray interface. This means PandasExtensionDtype
-    # can't subclass ExtensionDtype yet, as is_extension_array_dtype would
-    # incorrectly say that these types are extension types.
-    #
-    # In the interim, we put methods that are shared between the two base
-    # classes ExtensionDtype and PandasExtensionDtype here. Both those base
-    # classes will inherit from this Mixin. Once everything is compatible, this
-    # class's methods can be moved to ExtensionDtype and removed.
-
-    # na_value is the default NA value to use for this type. This is used in
-    # e.g. ExtensionArray.take. This should be the user-facing "boxed" version
-    # of the NA value, not the physical NA vaalue for storage.
-    # e.g. for JSONArray, this is an empty dictionary.
-    na_value = np.nan
-    _metadata = ()  # type: Tuple[str, ...]
-
-    def __eq__(self, other):
-        """Check whether 'other' is equal to self.
-
-        By default, 'other' is considered equal if either
-
-        * it's a string matching 'self.name'.
-        * it's an instance of this type and all of the
-          the attributes in ``self._metadata`` are equal between
-          `self` and `other`.
-
-        Parameters
-        ----------
-        other : Any
-
-        Returns
-        -------
-        bool
-        """
-        if isinstance(other, str):
-            try:
-                other = self.construct_from_string(other)
-            except TypeError:
-                return False
-        if isinstance(other, type(self)):
-            return all(
-                getattr(self, attr) == getattr(other, attr)
-                for attr in self._metadata
-            )
-        return False
-
-    def __hash__(self):
-        return hash(tuple(getattr(self, attr) for attr in self._metadata))
-
-    def __ne__(self, other):
-        return not self.__eq__(other)
-
-    @property
-    def names(self) -> Optional[List[str]]:
-        """Ordered list of field names, or None if there are no fields.
-
-        This is for compatibility with NumPy arrays, and may be removed in the
-        future.
-        """
-        return None
-
-    @classmethod
-    def is_dtype(cls, dtype):
-        """Check if we match 'dtype'.
-
-        Parameters
-        ----------
-        dtype : object
-            The object to check.
-
-        Returns
-        -------
-        is_dtype : bool
-
-        Notes
-        -----
-        The default implementation is True if
-
-        1. ``cls.construct_from_string(dtype)`` is an instance
-           of ``cls``.
-        2. ``dtype`` is an object and is an instance of ``cls``
-        3. ``dtype`` has a ``dtype`` attribute, and any of the above
-           conditions is true for ``dtype.dtype``.
-        """
-        dtype = getattr(dtype, 'dtype', dtype)
-
-        if isinstance(dtype, (ABCSeries, ABCIndexClass,
-                              ABCDataFrame, np.dtype)):
-            # https://github.com/pandas-dev/pandas/issues/22960
-            # avoid passing data to `construct_from_string`. This could
-            # cause a FutureWarning from numpy about failing elementwise
-            # comparison from, e.g., comparing DataFrame == 'category'.
-            return False
-        elif dtype is None:
-            return False
-        elif isinstance(dtype, cls):
-            return True
-        try:
-            return cls.construct_from_string(dtype) is not None
-        except TypeError:
-            return False
-
-    @property
-    def _is_numeric(self) -> bool:
-        """
-        Whether columns with this dtype should be considered numeric.
-
-        By default ExtensionDtypes are assumed to be non-numeric.
-        They'll be excluded from operations that exclude non-numeric
-        columns, like (groupby) reductions, plotting, etc.
-        """
-        return False
-
-    @property
-    def _is_boolean(self) -> bool:
-        """
-        Whether this dtype should be considered boolean.
-
-        By default, ExtensionDtypes are assumed to be non-numeric.
-        Setting this to True will affect the behavior of several places,
-        e.g.
-
-        * is_bool
-        * boolean indexing
-
-        Returns
-        -------
-        bool
-        """
-        return False
-
-
-class ExtensionDtype(_DtypeOpsMixin):
+class ExtensionDtype:
     """
     A custom data type, to be paired with an ExtensionArray.
 
@@ -202,10 +68,52 @@ class ExtensionDtype(_DtypeOpsMixin):
     ``pandas.errors.AbstractMethodError`` and no ``register`` method is
     provided for registering virtual subclasses.
     """
+    # na_value is the default NA value to use for this type. This is used in
+    # e.g. ExtensionArray.take. This should be the user-facing "boxed" version
+    # of the NA value, not the physical NA value for storage.
+    # e.g. for JSONArray, this is an empty dictionary.
+    na_value = np.nan
+    _metadata = ()  # type: Tuple[str, ...]
 
     def __str__(self):
         return self.name
 
+    def __eq__(self, other):
+        """Check whether 'other' is equal to self.
+
+        By default, 'other' is considered equal if either
+
+        * it's a string matching 'self.name'.
+        * it's an instance of this type and all of the
+          the attributes in ``self._metadata`` are equal between
+          `self` and `other`.
+
+        Parameters
+        ----------
+        other : Any
+
+        Returns
+        -------
+        bool
+        """
+        if isinstance(other, str):
+            try:
+                other = self.construct_from_string(other)
+            except TypeError:
+                return False
+        if isinstance(other, type(self)):
+            return all(
+                getattr(self, attr) == getattr(other, attr)
+                for attr in self._metadata
+            )
+        return False
+
+    def __hash__(self):
+        return hash(tuple(getattr(self, attr) for attr in self._metadata))
+
+    def __ne__(self, other):
+        return not self.__eq__(other)
+
     @property
     def type(self) -> Type:
         """
@@ -243,6 +151,15 @@ class ExtensionDtype(_DtypeOpsMixin):
         """
         raise AbstractMethodError(self)
 
+    @property
+    def names(self) -> Optional[List[str]]:
+        """Ordered list of field names, or None if there are no fields.
+
+        This is for compatibility with NumPy arrays, and may be removed in the
+        future.
+        """
+        return None
+
     @classmethod
     def construct_array_type(cls):
         """
@@ -286,3 +203,73 @@ class ExtensionDtype(_DtypeOpsMixin):
         ...                         "'{}'".format(cls, string))
         """
         raise AbstractMethodError(cls)
+
+    @classmethod
+    def is_dtype(cls, dtype):
+        """Check if we match 'dtype'.
+
+        Parameters
+        ----------
+        dtype : object
+            The object to check.
+
+        Returns
+        -------
+        is_dtype : bool
+
+        Notes
+        -----
+        The default implementation is True if
+
+        1. ``cls.construct_from_string(dtype)`` is an instance
+           of ``cls``.
+        2. ``dtype`` is an object and is an instance of ``cls``
+        3. ``dtype`` has a ``dtype`` attribute, and any of the above
+           conditions is true for ``dtype.dtype``.
+        """
+        dtype = getattr(dtype, 'dtype', dtype)
+
+        if isinstance(dtype, (ABCSeries, ABCIndexClass,
+                              ABCDataFrame, np.dtype)):
+            # https://github.com/pandas-dev/pandas/issues/22960
+            # avoid passing data to `construct_from_string`. This could
+            # cause a FutureWarning from numpy about failing elementwise
+            # comparison from, e.g., comparing DataFrame == 'category'.
+            return False
+        elif dtype is None:
+            return False
+        elif isinstance(dtype, cls):
+            return True
+        try:
+            return cls.construct_from_string(dtype) is not None
+        except TypeError:
+            return False
+
+    @property
+    def _is_numeric(self) -> bool:
+        """
+        Whether columns with this dtype should be considered numeric.
+
+        By default ExtensionDtypes are assumed to be non-numeric.
+        They'll be excluded from operations that exclude non-numeric
+        columns, like (groupby) reductions, plotting, etc.
+        """
+        return False
+
+    @property
+    def _is_boolean(self) -> bool:
+        """
+        Whether this dtype should be considered boolean.
+
+        By default, ExtensionDtypes are assumed to be non-numeric.
+        Setting this to True will affect the behavior of several places,
+        e.g.
+
+        * is_bool
+        * boolean indexing
+
+        Returns
+        -------
+        bool
+        """
+        return False
diff --git a/pandas/core/dtypes/cast.py b/pandas/core/dtypes/cast.py
index a02f50f088..d0f392df70 100644
--- a/pandas/core/dtypes/cast.py
+++ b/pandas/core/dtypes/cast.py
@@ -18,8 +18,7 @@ from .common import (
     is_integer, is_integer_dtype, is_object_dtype, is_scalar, is_string_dtype,
     is_timedelta64_dtype, is_timedelta64_ns_dtype, is_unsigned_integer_dtype,
     pandas_dtype)
-from .dtypes import (
-    DatetimeTZDtype, ExtensionDtype, PandasExtensionDtype, PeriodDtype)
+from .dtypes import DatetimeTZDtype, ExtensionDtype, PeriodDtype
 from .generic import (
     ABCDatetimeArray, ABCDatetimeIndex, ABCPeriodArray, ABCPeriodIndex,
     ABCSeries)
@@ -1108,8 +1107,7 @@ def find_common_type(types):
     if all(is_dtype_equal(first, t) for t in types[1:]):
         return first
 
-    if any(isinstance(t, (PandasExtensionDtype, ExtensionDtype))
-           for t in types):
+    if any(isinstance(t, ExtensionDtype) for t in types):
         return np.object
 
     # take lowest unit
diff --git a/pandas/core/dtypes/common.py b/pandas/core/dtypes/common.py
index a942ea49a0..a19304f1a3 100644
--- a/pandas/core/dtypes/common.py
+++ b/pandas/core/dtypes/common.py
@@ -9,7 +9,7 @@ from pandas.compat import PY36
 
 from pandas.core.dtypes.dtypes import (
     CategoricalDtype, DatetimeTZDtype, ExtensionDtype, IntervalDtype,
-    PandasExtensionDtype, PeriodDtype, registry)
+    PeriodDtype, registry)
 from pandas.core.dtypes.generic import (
     ABCCategorical, ABCDateOffset, ABCDatetimeIndex, ABCIndexClass,
     ABCPeriodArray, ABCPeriodIndex, ABCSeries)
@@ -1888,7 +1888,7 @@ def _is_dtype_type(arr_or_dtype, condition):
     if isinstance(arr_or_dtype, np.dtype):
         return condition(arr_or_dtype.type)
     elif isinstance(arr_or_dtype, type):
-        if issubclass(arr_or_dtype, (PandasExtensionDtype, ExtensionDtype)):
+        if issubclass(arr_or_dtype, ExtensionDtype):
             arr_or_dtype = arr_or_dtype.type
         return condition(np.dtype(arr_or_dtype).type)
     elif arr_or_dtype is None:
@@ -1936,7 +1936,7 @@ def infer_dtype_from_object(dtype):
     if isinstance(dtype, type) and issubclass(dtype, np.generic):
         # Type object from a dtype
         return dtype
-    elif isinstance(dtype, (np.dtype, PandasExtensionDtype, ExtensionDtype)):
+    elif isinstance(dtype, (np.dtype, ExtensionDtype)):
         # dtype object
         try:
             _validate_date_like_dtype(dtype)
@@ -2021,7 +2021,7 @@ def pandas_dtype(dtype):
     # short-circuit
     if isinstance(dtype, np.ndarray):
         return dtype.dtype
-    elif isinstance(dtype, (np.dtype, PandasExtensionDtype, ExtensionDtype)):
+    elif isinstance(dtype, (np.dtype, ExtensionDtype)):
         return dtype
 
     # registered extension types
diff --git a/pandas/core/dtypes/dtypes.py b/pandas/core/dtypes/dtypes.py
index 6eca8313e1..da762978f5 100644
--- a/pandas/core/dtypes/dtypes.py
+++ b/pandas/core/dtypes/dtypes.py
@@ -12,7 +12,7 @@ from pandas._libs.tslibs import NaT, Period, Timestamp, timezones
 from pandas.core.dtypes.generic import (
     ABCCategoricalIndex, ABCDateOffset, ABCIndexClass)
 
-from .base import ExtensionDtype, _DtypeOpsMixin
+from .base import ExtensionDtype
 from .inference import is_list_like
 
 str_type = str
@@ -68,7 +68,7 @@ class Registry:
         ----------
         dtype : ExtensionDtype
         """
-        if not issubclass(dtype, (PandasExtensionDtype, ExtensionDtype)):
+        if not issubclass(dtype, ExtensionDtype):
             raise ValueError("can only register pandas extension dtypes")
 
         self.dtypes.append(dtype)
@@ -104,7 +104,7 @@ class Registry:
 registry = Registry()
 
 
-class PandasExtensionDtype(_DtypeOpsMixin):
+class PandasExtensionDtype(ExtensionDtype):
     """
     A np.dtype duck-typed class, suitable for holding a custom dtype.
 
@@ -577,7 +577,7 @@ class CategoricalDtype(PandasExtensionDtype, ExtensionDtype):
 
 
 @register_extension_dtype
-class DatetimeTZDtype(PandasExtensionDtype, ExtensionDtype):
+class DatetimeTZDtype(PandasExtensionDtype):
     """
     An ExtensionDtype for timezone-aware datetime data.
 
@@ -737,7 +737,7 @@ class DatetimeTZDtype(PandasExtensionDtype, ExtensionDtype):
 
 
 @register_extension_dtype
-class PeriodDtype(ExtensionDtype, PandasExtensionDtype):
+class PeriodDtype(PandasExtensionDtype):
     """
     An ExtensionDtype for Period data.
 
@@ -894,7 +894,7 @@ class PeriodDtype(ExtensionDtype, PandasExtensionDtype):
 
 
 @register_extension_dtype
-class IntervalDtype(PandasExtensionDtype, ExtensionDtype):
+class IntervalDtype(PandasExtensionDtype):
     """
     An ExtensionDtype for Interval data.
 
diff --git a/pandas/core/indexes/multi.py b/pandas/core/indexes/multi.py
index ff670e5524..7a933bdcb0 100644
--- a/pandas/core/indexes/multi.py
+++ b/pandas/core/indexes/multi.py
@@ -17,7 +17,7 @@ from pandas.core.dtypes.common import (
     ensure_int64, ensure_platform_int, is_categorical_dtype, is_hashable,
     is_integer, is_iterator, is_list_like, is_object_dtype, is_scalar,
     pandas_dtype)
-from pandas.core.dtypes.dtypes import ExtensionDtype, PandasExtensionDtype
+from pandas.core.dtypes.dtypes import ExtensionDtype
 from pandas.core.dtypes.generic import ABCDataFrame
 from pandas.core.dtypes.missing import array_equivalent, isna
 
@@ -1173,7 +1173,7 @@ class MultiIndex(Index):
             vals = self._get_level_values(i)
             if is_categorical_dtype(vals):
                 vals = vals.get_values()
-            if (isinstance(vals.dtype, (PandasExtensionDtype, ExtensionDtype))
+            if (isinstance(vals.dtype, ExtensionDtype)
                     or hasattr(vals, '_box_values')):
                 vals = vals.astype(object)
             vals = np.array(vals, copy=False)
diff --git a/pandas/core/internals/blocks.py b/pandas/core/internals/blocks.py
index 519975f34f..0c49ebb55a 100644
--- a/pandas/core/internals/blocks.py
+++ b/pandas/core/internals/blocks.py
@@ -23,8 +23,7 @@ from pandas.core.dtypes.common import (
     is_list_like, is_numeric_v_string_like, is_object_dtype, is_period_dtype,
     is_re, is_re_compilable, is_sparse, is_timedelta64_dtype, pandas_dtype)
 import pandas.core.dtypes.concat as _concat
-from pandas.core.dtypes.dtypes import (
-    CategoricalDtype, ExtensionDtype, PandasExtensionDtype)
+from pandas.core.dtypes.dtypes import CategoricalDtype, ExtensionDtype
 from pandas.core.dtypes.generic import (
     ABCDataFrame, ABCDatetimeIndex, ABCExtensionArray, ABCIndexClass,
     ABCPandasArray, ABCSeries)
@@ -544,7 +543,7 @@ class Block(PandasObject):
             raise ValueError(invalid_arg)
 
         if (inspect.isclass(dtype) and
-                issubclass(dtype, (PandasExtensionDtype, ExtensionDtype))):
+                issubclass(dtype, ExtensionDtype)):
             msg = ("Expected an instance of {}, but got the class instead. "
                    "Try instantiating 'dtype'.".format(dtype.__name__))
             raise TypeError(msg)

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/pandas/core/dtypes/cast.py b/pandas/core/dtypes/cast.py
index b398a197a4..1ab21f18f3 100644
--- a/pandas/core/dtypes/cast.py
+++ b/pandas/core/dtypes/cast.py
@@ -39,11 +39,11 @@ from .common import (
     is_timedelta64_dtype,
     is_timedelta64_ns_dtype,
     is_unsigned_integer_dtype,
     pandas_dtype,
 )
-from .dtypes import DatetimeTZDtype, ExtensionDtype, PeriodDtype
+from .dtypes import DatetimeTZDtype, ExtensionDtype, IntervalDtype, PeriodDtype
 from .generic import (
     ABCDataFrame,
     ABCDatetimeArray,
     ABCDatetimeIndex,
     ABCPeriodArray,
@@ -599,10 +599,13 @@ def infer_dtype_from_scalar(val, pandas_dtype: bool = False):
 
     elif pandas_dtype:
         if lib.is_period(val):
             dtype = PeriodDtype(freq=val.freq)
             val = val.ordinal
+        elif lib.is_interval(val):
+            subtype = infer_dtype_from_scalar(val.left, pandas_dtype=True)[0]
+            dtype = IntervalDtype(subtype=subtype)
 
     return dtype, val
 
 
 def infer_dtype_from_array(arr, pandas_dtype: bool = False):

```

## ODIS candidates: 175 total, path=jev, tiers={'full': 0, 'signature': 20, 'counted': 142}
Shown to the reviewer (full = whole snippet, signature = one line):
- [signature] caller pandas/tests/arrays/test_period.py:20 call to PeriodDtype | expected = PeriodDtype("D")
- [signature] caller pandas/tests/dtypes/cast/test_find_common_type.py:79 call to DatetimeTZDtype | dtype = DatetimeTZDtype(unit="ns", tz="US/Eastern")
- [signature] caller pandas/tests/dtypes/cast/test_find_common_type.py:88 call to DatetimeTZDtype | dtype = DatetimeTZDtype(unit="ns", tz="US/Eastern")
- [signature] caller pandas/tests/dtypes/cast/test_find_common_type.py:94 call to PeriodDtype | dtype = PeriodDtype(freq="D")
- [signature] caller pandas/tests/dtypes/cast/test_find_common_type.py:104 call to PeriodDtype | dtype = PeriodDtype(freq="D")
- [signature] caller pandas/tests/dtypes/cast/test_find_common_type.py:84 call to DatetimeTZDtype | DatetimeTZDtype(unit="ns", tz="Asia/Tokyo"),
- [signature] caller pandas/tests/dtypes/cast/test_find_common_type.py:99 call to DatetimeTZDtype | DatetimeTZDtype(unit="ns", tz="Asia/Tokyo"),
- [signature] caller pandas/tests/dtypes/cast/test_find_common_type.py:100 call to PeriodDtype | PeriodDtype(freq="2D"), PeriodDtype(freq="H"),
- [signature] caller pandas/tests/dtypes/test_common.py:544 call to DatetimeTZDtype | dtype = DatetimeTZDtype("ns", tz="US/Eastern")
- [signature] caller pandas/tests/dtypes/test_common.py:71 call to PeriodDtype | assert com.pandas_dtype(dtype) is PeriodDtype(dtype)
- [signature] caller pandas/tests/dtypes/test_common.py:72 call to PeriodDtype | assert com.pandas_dtype(dtype) == PeriodDtype(dtype)
- [signature] caller pandas/tests/dtypes/test_common.py:645 call to PeriodDtype | (PeriodDtype(freq='D'), pd.Period),
- [signature] caller pandas/tests/dtypes/test_dtypes.py:188 call to DatetimeTZDtype | dtype2 = DatetimeTZDtype('ns', 'US/Eastern')
- [signature] caller pandas/tests/dtypes/test_dtypes.py:323 call to PeriodDtype | dtype3 = PeriodDtype(dtype2)
- [signature] caller pandas/tests/dtypes/test_dtypes.py:243 call to DatetimeTZDtype | assert DatetimeTZDtype.is_dtype(DatetimeTZDtype('ns', 'US/Pacific'))
- [signature] caller pandas/tests/dtypes/test_dtypes.py:361 call to PeriodDtype | assert PeriodDtype('period[D]') == PeriodDtype('period[D]')
- [signature] caller pandas/tests/dtypes/test_dtypes.py:397 call to PeriodDtype | assert PeriodDtype.is_dtype(PeriodDtype('3D'))
- [signature] caller pandas/tests/dtypes/test_dtypes.py:400 call to PeriodDtype | assert PeriodDtype.is_dtype(PeriodDtype('U'))
- [signature] caller pandas/tests/dtypes/test_dtypes.py:554 call to IntervalDtype | assert IntervalDtype.is_dtype(IntervalDtype('float64'))
- [signature] caller pandas/tests/dtypes/test_dtypes.py:555 call to IntervalDtype | assert IntervalDtype.is_dtype(IntervalDtype('int64'))
Counted only (142), first 15:
- caller pandas/core/arrays/datetimes.py:69 call to DatetimeTZDtype
- caller pandas/core/arrays/datetimes.py:337 call to DatetimeTZDtype
- caller pandas/core/arrays/datetimes.py:283 call to DatetimeTZDtype
- caller pandas/core/arrays/interval.py:129 call to IntervalDtype
- caller pandas/core/arrays/interval.py:576 call to IntervalDtype
- callee pandas/core/arrays/numpy_.py:57 type
- callee pandas/core/arrays/numpy_.py:307 any
- callee pandas/core/arrays/numpy_.py:311 all
- caller pandas/core/arrays/period.py:177 call to PeriodDtype
- caller pandas/core/arrays/period.py:784 call to PeriodDtype
- callee pandas/core/arrays/sparse.py:190 type
- callee pandas/core/arrays/sparse.py:1461 all
- callee pandas/core/arrays/sparse.py:1482 any
- caller pandas/core/arrays/timedeltas.py:421 call to DatetimeTZDtype
- callee pandas/core/computation/ops.py:111 type
