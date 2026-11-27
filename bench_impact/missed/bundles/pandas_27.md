# pandas#27

Commit message of the reviewed change: CLN: Move some PI/DTI methods to EA subclasses, implement tests (#22961)

Oracle (fix location at buggy_commit): [{'file': 'pandas/core/arrays/datetimes.py', 'line_start': 1100, 'line_end': 1100}]

## Reviewed diff (introducing commit)
```diff
diff --git a/pandas/core/arrays/datetimes.py b/pandas/core/arrays/datetimes.py
index a0a9b57712..7daaa8de17 100644
--- a/pandas/core/arrays/datetimes.py
+++ b/pandas/core/arrays/datetimes.py
@@ -31,7 +31,7 @@ import pandas.core.common as com
 from pandas.core.algorithms import checked_add_with_arr
 from pandas.core import ops
 
-from pandas.tseries.frequencies import to_offset
+from pandas.tseries.frequencies import to_offset, get_period_alias
 from pandas.tseries.offsets import Tick, generate_range
 
 from pandas.core.arrays import datetimelike as dtl
@@ -200,6 +200,10 @@ class DatetimeArrayMixin(dtl.DatetimeLikeArrayMixin):
             # e.g. DatetimeIndex
             tz = values.tz
 
+        if freq is None and hasattr(values, "freq"):
+            # i.e. DatetimeArray, DatetimeIndex
+            freq = values.freq
+
         freq, freq_infer = dtl.maybe_infer_freq(freq)
 
         # if dtype has an embedded tz, capture it
@@ -764,6 +768,67 @@ class DatetimeArrayMixin(dtl.DatetimeLikeArrayMixin):
         new_values = conversion.normalize_i8_timestamps(self.asi8, self.tz)
         return type(self)(new_values, freq='infer').tz_localize(self.tz)
 
+    def to_period(self, freq=None):
+        """
+        Cast to PeriodArray/Index at a particular frequency.
+
+        Converts DatetimeArray/Index to PeriodArray/Index.
+
+        Parameters
+        ----------
+        freq : string or Offset, optional
+            One of pandas' :ref:`offset strings <timeseries.offset_aliases>`
+            or an Offset object. Will be inferred by default.
+
+        Returns
+        -------
+        PeriodArray/Index
+
+        Raises
+        ------
+        ValueError
+            When converting a DatetimeArray/Index with non-regular values,
+            so that a frequency cannot be inferred.
+
+        Examples
+        --------
+        >>> df = pd.DataFrame({"y": [1,2,3]},
+        ...                   index=pd.to_datetime(["2000-03-31 00:00:00",
+        ...                                         "2000-05-31 00:00:00",
+        ...                                         "2000-08-31 00:00:00"]))
+        >>> df.index.to_period("M")
+        PeriodIndex(['2000-03', '2000-05', '2000-08'],
+                    dtype='period[M]', freq='M')
+
+        Infer the daily frequency
+
+        >>> idx = pd.date_range("2017-01-01", periods=2)
+        >>> idx.to_period()
+        PeriodIndex(['2017-01-01', '2017-01-02'],
+                    dtype='period[D]', freq='D')
+
+        See also
+        --------
+        pandas.PeriodIndex: Immutable ndarray holding ordinal values
+        pandas.DatetimeIndex.to_pydatetime: Return DatetimeIndex as object
+        """
+        from pandas.core.arrays.period import PeriodArrayMixin
+
+        if self.tz is not None:
+            warnings.warn("Converting to PeriodArray/Index representation "
+                          "will drop timezone information.", UserWarning)
+
+        if freq is None:
+            freq = self.freqstr or self.inferred_freq
+
+            if freq is None:
+                raise ValueError("You must pass a freq argument as "
+                                 "current index has none.")
+
+            freq = get_period_alias(freq)
+
+        return PeriodArrayMixin(self.values, freq=freq)
+
     # -----------------------------------------------------------------
     # Properties - Vectorized Timestamp Properties/Methods
 
diff --git a/pandas/core/arrays/period.py b/pandas/core/arrays/period.py
index 96a18a628f..6d13fb9eca 100644
--- a/pandas/core/arrays/period.py
+++ b/pandas/core/arrays/period.py
@@ -10,14 +10,15 @@ from pandas._libs.tslibs.period import (
     Period, IncompatibleFrequency, DIFFERENT_FREQ_INDEX,
     get_period_field_arr, period_asfreq_arr)
 from pandas._libs.tslibs import period as libperiod
-from pandas._libs.tslibs.timedeltas import delta_to_nanoseconds
+from pandas._libs.tslibs.timedeltas import delta_to_nanoseconds, Timedelta
 from pandas._libs.tslibs.fields import isleapyear_arr
 
 from pandas import compat
 from pandas.util._decorators import (cache_readonly, deprecate_kwarg)
 
 from pandas.core.dtypes.common import (
-    is_integer_dtype, is_float_dtype, is_period_dtype)
+    is_integer_dtype, is_float_dtype, is_period_dtype,
+    is_datetime64_dtype)
 from pandas.core.dtypes.dtypes import PeriodDtype
 from pandas.core.dtypes.generic import ABCSeries
 
@@ -127,6 +128,10 @@ class PeriodArrayMixin(DatetimeLikeArrayMixin):
             freq = values.freq
             values = values.asi8
 
+        elif is_datetime64_dtype(values):
+            # TODO: what if it has tz?
+            values = dt64arr_to_periodarr(values, freq)
+
         return cls._simple_new(values, freq, **kwargs)
 
     @classmethod
@@ -207,6 +212,14 @@ class PeriodArrayMixin(DatetimeLikeArrayMixin):
         """ Logical indicating if the date belongs to a leap year """
         return isleapyear_arr(np.asarray(self.year))
 
+    @property
+    def start_time(self):
+        return self.to_timestamp(how='start')
+
+    @property
+    def end_time(self):
+        return self.to_timestamp(how='end')
+
     def asfreq(self, freq=None, how='E'):
         """
         Convert the Period Array/Index to the specified frequency `freq`.
@@ -266,6 +279,48 @@ class PeriodArrayMixin(DatetimeLikeArrayMixin):
 
         return self._shallow_copy(new_data, freq=freq)
 
+    def to_timestamp(self, freq=None, how='start'):
+        """
+        Cast to DatetimeArray/Index
+
+        Parameters
+        ----------
+        freq : string or DateOffset, optional
+            Target frequency. The default is 'D' for week or longer,
+            'S' otherwise
+        how : {'s', 'e', 'start', 'end'}
+
+        Returns
+        -------
+        DatetimeArray/Index
+        """
+        from pandas.core.arrays.datetimes import DatetimeArrayMixin
+
+        how = libperiod._validate_end_alias(how)
+
+        end = how == 'E'
+        if end:
+            if freq == 'B':
+                # roll forward to ensure we land on B date
+                adjust = Timedelta(1, 'D') - Timedelta(1, 'ns')
+                return self.to_timestamp(how='start') + adjust
+            else:
+                adjust = Timedelta(1, 'ns')
+                return (self + 1).to_timestamp(how='start') - adjust
+
+        if freq is None:
+            base, mult = frequencies.get_freq_code(self.freq)
+            freq = frequencies.get_to_timestamp_base(base)
+        else:
+            freq = Period._maybe_convert_freq(freq)
+
+        base, mult = frequencies.get_freq_code(freq)
+        new_data = self.asfreq(freq, how=how)
+
+        new_data = libperiod.periodarr_to_dt64arr(new_data._ndarray_values,
+                                                  base)
+        return DatetimeArrayMixin(new_data, freq='infer')
+
     # ------------------------------------------------------------------
     # Arithmetic Methods
 
@@ -407,6 +462,15 @@ PeriodArrayMixin._add_datetimelike_methods()
 # -------------------------------------------------------------------
 # Constructor Helpers
 
+def dt64arr_to_periodarr(data, freq, tz=None):
+    if data.dtype != np.dtype('M8[ns]'):
+        raise ValueError('Wrong dtype: %s' % data.dtype)
+
+    freq = Period._maybe_convert_freq(freq)
+    base, mult = frequencies.get_freq_code(freq)
+    return libperiod.dt64arr_to_periodarr(data.view('i8'), base, tz)
+
+
 def _get_ordinal_range(start, end, periods, freq, mult=1):
     if com.count_not_none(start, end, periods) != 2:
         raise ValueError('Of the three parameters: start, end, and periods, '
diff --git a/pandas/core/indexes/datetimes.py b/pandas/core/indexes/datetimes.py
index a6cdaa0c21..e40ceadc1a 100644
--- a/pandas/core/indexes/datetimes.py
+++ b/pandas/core/indexes/datetimes.py
@@ -36,7 +36,7 @@ from pandas.core.arrays import datetimelike as dtl
 from pandas.core.indexes.base import Index, _index_shared_docs
 from pandas.core.indexes.numeric import Int64Index, Float64Index
 import pandas.compat as compat
-from pandas.tseries.frequencies import to_offset, get_period_alias, Resolution
+from pandas.tseries.frequencies import to_offset, Resolution
 from pandas.core.indexes.datetimelike import (
     DatelikeOps, TimelikeOps, DatetimeIndexOpsMixin)
 from pandas.tseries.offsets import (
@@ -302,7 +302,8 @@ class DatetimeIndex(DatetimeArrayMixin, DatelikeOps, TimelikeOps,
                                        tz=tz, normalize=normalize,
                                        closed=closed, ambiguous=ambiguous)
 
-        if not isinstance(data, (np.ndarray, Index, ABCSeries)):
+        if not isinstance(data, (np.ndarray, Index, ABCSeries,
+                                 DatetimeArrayMixin)):
             if is_scalar(data):
                 raise ValueError('DatetimeIndex() must be called with a '
                                  'collection of some kind, %s was passed'
@@ -673,67 +674,12 @@ class DatetimeIndex(DatetimeArrayMixin, DatelikeOps, TimelikeOps,
 
         return Series(values, index=index, name=name)
 
+    @Appender(DatetimeArrayMixin.to_period.__doc__)
     def to_period(self, freq=None):
-        """
-        Cast to PeriodIndex at a particular frequency.
-
-        Converts DatetimeIndex to PeriodIndex.
-
-        Parameters
-        ----------
-        freq : string or Offset, optional
-            One of pandas' :ref:`offset strings <timeseries.offset_aliases>`
-            or an Offset object. Will be inferred by default.
-
-        Returns
-        -------
-        PeriodIndex
-
-        Raises
-        ------
-        ValueError
-            When converting a DatetimeIndex with non-regular values, so that a
-            frequency cannot be inferred.
-
-        Examples
-        --------
-        >>> df = pd.DataFrame({"y": [1,2,3]},
-        ...                   index=pd.to_datetime(["2000-03-31 00:00:00",
-        ...                                         "2000-05-31 00:00:00",
-        ...                                         "2000-08-31 00:00:00"]))
-        >>> df.index.to_period("M")
-        PeriodIndex(['2000-03', '2000-05', '2000-08'],
-                    dtype='period[M]', freq='M')
-
-        Infer the daily frequency
-
-        >>> idx = pd.date_range("2017-01-01", periods=2)
-        >>> idx.to_period()
-        PeriodIndex(['2017-01-01', '2017-01-02'],
-                    dtype='period[D]', freq='D')
-
-        See also
-        --------
-        pandas.PeriodIndex: Immutable ndarray holding ordinal values
-        pandas.DatetimeIndex.to_pydatetime: Return DatetimeIndex as object
-        """
         from pandas.core.indexes.period import PeriodIndex
 
-        if self.tz is not None:
-            warnings.warn("Converting to PeriodIndex representation will "
-                          "drop timezone information.", UserWarning)
-
-        if freq is None:
-            freq = self.freqstr or self.inferred_freq
-
-            if freq is None:
-                msg = ("You must pass a freq argument as "
-                       "current index has none.")
-                raise ValueError(msg)
-
-            freq = get_period_alias(freq)
-
-        return PeriodIndex(self.values, name=self.name, freq=freq)
+        result = DatetimeArrayMixin.to_period(self, freq=freq)
+        return PeriodIndex(result, name=self.name)
 
     def snap(self, freq='S'):
         """
@@ -758,6 +704,7 @@ class DatetimeIndex(DatetimeArrayMixin, DatelikeOps, TimelikeOps,
 
         # we know it conforms; skip check
         return DatetimeIndex(snapped, freq=freq, verify_integrity=False)
+        # TODO: what about self.name?  if so, use shallow_copy?
 
     def unique(self, level=None):
         # Override here since IndexOpsMixin.unique uses self._values.unique
@@ -769,8 +716,7 @@ class DatetimeIndex(DatetimeArrayMixin, DatelikeOps, TimelikeOps,
         else:
             naive = self
         result = super(DatetimeIndex, naive).unique(level=level)
-        return self._simple_new(result.values, name=self.name, tz=self.tz,
-                                freq=self.freq)
+        return self._shallow_copy(result.values)
 
     def union(self, other):
         """
@@ -1421,8 +1367,7 @@ class DatetimeIndex(DatetimeArrayMixin, DatelikeOps, TimelikeOps,
         try:
             new_dates = np.concatenate((self[:loc].asi8, [item.view(np.int64)],
                                         self[loc:].asi8))
-            return DatetimeIndex(new_dates, name=self.name, freq=freq,
-                                 tz=self.tz)
+            return self._shallow_copy(new_dates, freq=freq)
         except (AttributeError, TypeError):
 
             # fall back to object index
@@ -1458,7 +1403,7 @@ class DatetimeIndex(DatetimeArrayMixin, DatelikeOps, TimelikeOps,
                 if (loc.start in (0, None) or loc.stop in (len(self), None)):
                     freq = self.freq
 
-        return DatetimeIndex(new_dates, name=self.name, freq=freq, tz=self.tz)
+        return self._shallow_copy(new_dates, freq=freq)
 
     def indexer_at_time(self, time, asof=False):
         """
diff --git a/pandas/core/indexes/period.py b/pandas/core/indexes/period.py
index cc008694a8..7833dd851d 100644
--- a/pandas/core/indexes/period.py
+++ b/pandas/core/indexes/period.py
@@ -17,7 +17,6 @@ from pandas.core.dtypes.common import (
     pandas_dtype,
     ensure_object)
 
-import pandas.tseries.frequencies as frequencies
 from pandas.tseries.frequencies import get_freq_code as _gfc
 
 from pandas.core.indexes.datetimes import DatetimeIndex, Int64Index, Index
@@ -25,13 +24,13 @@ from pandas.core.indexes.datetimelike import DatelikeOps, DatetimeIndexOpsMixin
 from pandas.core.tools.datetimes import parse_time_string
 
 from pandas._libs.lib import infer_dtype
-from pandas._libs import tslib, index as libindex, Timedelta
+from pandas._libs import tslib, index as libindex
 from pandas._libs.tslibs.period import (Period, IncompatibleFrequency,
-                                        DIFFERENT_FREQ_INDEX,
-                                        _validate_end_alias)
+                                        DIFFERENT_FREQ_INDEX)
 from pandas._libs.tslibs import resolution, period
 
-from pandas.core.arrays.period import PeriodArrayMixin
+from pandas.core.arrays import datetimelike as dtl
+from pandas.core.arrays.period import PeriodArrayMixin, dt64arr_to_periodarr
 from pandas.core.base import _shared_docs
 from pandas.core.indexes.base import _index_shared_docs, ensure_index
 
@@ -56,14 +55,6 @@ def _wrap_field_accessor(name):
     return property(f)
 
 
-def dt64arr_to_periodarr(data, freq, tz):
-    if data.dtype != np.dtype('M8[ns]'):
-        raise ValueError('Wrong dtype: %s' % data.dtype)
-
-    freq = Period._maybe_convert_freq(freq)
-    base, mult = _gfc(freq)
-    return period.dt64arr_to_periodarr(data.view('i8'), base, tz)
-
 # --- Period index sketch
 
 
@@ -185,12 +176,7 @@ class PeriodIndex(PeriodArrayMixin, DatelikeOps, DatetimeIndexOpsMixin,
             raise TypeError('__new__() got an unexpected keyword argument {}'.
                             format(list(set(fields) - valid_field_set)[0]))
 
-        if periods is not None:
-            if is_float(periods):
-                periods = int(periods)
-            elif not is_integer(periods):
-                msg = 'periods must be a number, got {periods}'
-                raise TypeError(msg.format(periods=periods))
+        periods = dtl.validate_periods(periods)
 
         if name is None and hasattr(data, 'name'):
             name = data.name
@@ -461,55 +447,23 @@ class PeriodIndex(PeriodArrayMixin, DatelikeOps, DatetimeIndexOpsMixin,
     daysinmonth = days_in_month
 
     @property
+    @Appender(PeriodArrayMixin.start_time.__doc__)
     def start_time(self):
-        return self.to_timestamp(how='start')
+        return PeriodArrayMixin.start_time.fget(self)
 
     @property
+    @Appender(PeriodArrayMixin.end_time.__doc__)
     def end_time(self):
-        return self.to_timestamp(how='end')
+        return PeriodArrayMixin.end_time.fget(self)
 
     def _mpl_repr(self):
         # how to represent ourselves to matplotlib
         return self.astype(object).values
 
+    @Appender(PeriodArrayMixin.to_timestamp.__doc__)
     def to_timestamp(self, freq=None, how='start'):
-        """
-        Cast to DatetimeIndex
-
-        Parameters
-        ----------
-        freq : string or DateOffset, optional
-            Target frequency. The default is 'D' for week or longer,
-            'S' otherwise
-        how : {'s', 'e', 'start', 'end'}
-
-        Returns
-        -------
-        DatetimeIndex
-        """
-        how = _validate_end_alias(how)
-
-        end = how == 'E'
-        if end:
-            if freq == 'B':
-                # roll forward to ensure we land on B date
-                adjust = Timedelta(1, 'D') - Timedelta(1, 'ns')
-                return self.to_timestamp(how='start') + adjust
-            else:
-                adjust = Timedelta(1, 'ns')
-                return (self + 1).to_timestamp(how='start') - adjust
-
-        if freq is None:
-            base, mult = _gfc(self.freq)
-            freq = frequencies.get_to_timestamp_base(base)
-        else:
-            freq = Period._maybe_convert_freq(freq)
-
-        base, mult = _gfc(freq)
-        new_data = self.asfreq(freq, how)
-
-        new_data = period.periodarr_to_dt64arr(new_data._ndarray_values, base)
-        return DatetimeIndex(new_data, freq='infer', name=self.name)
+        result = PeriodArrayMixin.to_timestamp(self, freq=freq, how=how)
+        return DatetimeIndex(result, name=self.name)
 
     @property
     def inferred_type(self):
diff --git a/pandas/core/indexes/timedeltas.py b/pandas/core/indexes/timedeltas.py
index 933bc6233d..ee604f44b9 100644
--- a/pandas/core/indexes/timedeltas.py
+++ b/pandas/core/indexes/timedeltas.py
@@ -668,7 +668,7 @@ class TimedeltaIndex(TimedeltaArrayMixin, DatetimeIndexOpsMixin,
         try:
             new_tds = np.concatenate((self[:loc].asi8, [item.view(np.int64)],
                                       self[loc:].asi8))
-            return TimedeltaIndex(new_tds, name=self.name, freq=freq)
+            return self._shallow_copy(new_tds, freq=freq)
 
         except (AttributeError, TypeError):
 
diff --git a/pandas/tests/arrays/test_datetimelike.py b/pandas/tests/arrays/test_datetimelike.py
index 24f34884dc..6bb4241451 100644
--- a/pandas/tests/arrays/test_datetimelike.py
+++ b/pandas/tests/arrays/test_datetimelike.py
@@ -1,13 +1,50 @@
 # -*- coding: utf-8 -*-
 import numpy as np
+import pytest
 
 import pandas as pd
+import pandas.util.testing as tm
 
 from pandas.core.arrays.datetimes import DatetimeArrayMixin
 from pandas.core.arrays.timedeltas import TimedeltaArrayMixin
 from pandas.core.arrays.period import PeriodArrayMixin
 
 
+# TODO: more freq variants
+@pytest.fixture(params=['D', 'B', 'W', 'M', 'Q', 'Y'])
+def period_index(request):
+    """
+    A fixture to provide PeriodIndex objects with different frequencies.
+
+    Most PeriodArray behavior is already tested in PeriodIndex tests,
+    so here we just test that the PeriodArray behavior matches
+    the PeriodIndex behavior.
+    """
+    freqstr = request.param
+    # TODO: non-monotone indexes; NaTs, different start dates
+    pi = pd.period_range(start=pd.Timestamp('2000-01-01'),
+                         periods=100,
+                         freq=freqstr)
+    return pi
+
+
+@pytest.fixture(params=['D', 'B', 'W', 'M', 'Q', 'Y'])
+def datetime_index(request):
+    """
+    A fixture to provide DatetimeIndex objects with different frequencies.
+
+    Most DatetimeArray behavior is already tested in DatetimeIndex tests,
+    so here we just test that the DatetimeIndex behavior matches
+    the DatetimeIndex behavior.
+    """
+    freqstr = request.param
+    # TODO: non-monotone indexes; NaTs, different start dates, timezones
+    pi = pd.date_range(start=pd.Timestamp('2000-01-01'),
+                       periods=100,
+                       freq=freqstr)
+    return pi
+
+
 class TestDatetimeArray(object):
 
     def test_from_dti(self, tz_naive_fixture):
@@ -30,6 +67,41 @@ class TestDatetimeArray(object):
         assert asobj.dtype == 'O'
         assert list(asobj) == list(dti)
 
+    @pytest.mark.parametrize('freqstr', ['D', 'B', 'W', 'M', 'Q', 'Y'])
+    def test_to_period(self, datetime_index, freqstr):
+        dti = datetime_index
+        arr = DatetimeArrayMixin(dti)
+
+        expected = dti.to_period(freq=freqstr)
+        result = arr.to_period(freq=freqstr)
+        assert isinstance(result, PeriodArrayMixin)
+
+        # placeholder until these become actual EA subclasses and we can use
+        #  an EA-specific tm.assert_ function
+        tm.assert_index_equal(pd.Index(result), pd.Index(expected))
+
+    @pytest.mark.parametrize('propname', pd.DatetimeIndex._bool_ops)
+    def test_bool_properties(self, datetime_index, propname):
+        # in this case _bool_ops is just `is_leap_year`
+        dti = datetime_index
+        arr = DatetimeArrayMixin(dti)
+        assert dti.freq == arr.freq
+
+        result = getattr(arr, propname)
+        expected = np.array(getattr(dti, propname), dtype=result.dtype)
+
+        tm.assert_numpy_array_equal(result, expected)
+
+    @pytest.mark.parametrize('propname', pd.DatetimeIndex._field_ops)
+    def test_int_properties(self, datetime_index, propname):
+        dti = datetime_index
+        arr = DatetimeArrayMixin(dti)
+
+        result = getattr(arr, propname)
+        expected = np.array(getattr(dti, propname), dtype=result.dtype)
+
+        tm.assert_numpy_array_equal(result, expected)
+
 
 class TestTimedeltaArray(object):
     def test_from_tdi(self):
@@ -53,20 +125,54 @@ class TestTimedeltaArray(object):
 
 class TestPeriodArray(object):
 
-    def test_from_pi(self):
-        pi = pd.period_range('2016', freq='Q', periods=3)
+    def test_from_pi(self, period_index):
+        pi = period_index
         arr = PeriodArrayMixin(pi)
         assert list(arr) == list(pi)
 
-        # Check that Index.__new__ knows what to do with TimedeltaArray
+        # Check that Index.__new__ knows what to do with PeriodArray
         pi2 = pd.Index(arr)
         assert isinstance(pi2, pd.PeriodIndex)
         assert list(pi2) == list(arr)
 
-    def test_astype_object(self):
-        pi = pd.period_range('2016', freq='Q', periods=3)
+    def test_astype_object(self, period_index):
+        pi = period_index
         arr = PeriodArrayMixin(pi)
         asobj = arr.astype('O')
         assert isinstance(asobj, np.ndarray)
         assert asobj.dtype == 'O'
         assert list(asobj) == list(pi)
+
+    @pytest.mark.parametrize('how', ['S', 'E'])
+    def test_to_timestamp(self, how, period_index):
+        pi = period_index
+        arr = PeriodArrayMixin(pi)
+
+        expected = DatetimeArrayMixin(pi.to_timestamp(how=how))
+        result = arr.to_timestamp(how=how)
+        assert isinstance(result, DatetimeArrayMixin)
+
+        # placeholder until these become actual EA subclasses and we can use
+        #  an EA-specific tm.assert_ function
+        tm.assert_index_equal(pd.Index(result), pd.Index(expected))
+
+    @pytest.mark.parametrize('propname', pd.PeriodIndex._bool_ops)
+    def test_bool_properties(self, period_index, propname):
+        # in this case _bool_ops is just `is_leap_year`
+        pi = period_index
+        arr = PeriodArrayMixin(pi)
+
+        result = getattr(arr, propname)
+        expected = np.array(getattr(pi, propname))
+
+        tm.assert_numpy_array_equal(result, expected)
+
+    @pytest.mark.parametrize('propname', pd.PeriodIndex._field_ops)
+    def test_int_properties(self, period_index, propname):
+        pi = period_index
+        arr = PeriodArrayMixin(pi)
+
+        result = getattr(arr, propname)
+        expected = np.array(getattr(pi, propname))
+
+        tm.assert_numpy_array_equal(result, expected)

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/pandas/core/arrays/datetimes.py b/pandas/core/arrays/datetimes.py
index d6af11a442..2ccc0ff2fa 100644
--- a/pandas/core/arrays/datetimes.py
+++ b/pandas/core/arrays/datetimes.py
@@ -16,10 +16,11 @@ from pandas._libs.tslibs import (
     normalize_date,
     resolution as libresolution,
     timezones,
     tzconversion,
 )
+import pandas._libs.tslibs.frequencies as libfrequencies
 from pandas.errors import PerformanceWarning
 
 from pandas.core.dtypes.common import (
     _INT64_DTYPE,
     DT64NS_DTYPE,
@@ -1095,11 +1096,18 @@ default 'raise'
             if freq is None:
                 raise ValueError(
                     "You must pass a freq argument as current index has none."
                 )
 
-            freq = get_period_alias(freq)
+            res = get_period_alias(freq)
+
+            #  https://github.com/pandas-dev/pandas/issues/33358
+            if res is None:
+                base, stride = libfrequencies._base_and_stride(freq)
+                res = f"{stride}{base}"
+
+            freq = res
 
         return PeriodArray._from_datetime64(self._data, freq, tz=self.tz)
 
     def to_perioddelta(self, freq):
         """

```

## ODIS candidates: 8 total, path=small, tiers={'full': 8, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee asv_bench/benchmarks/timeseries.py:14 DatetimeIndex | class DatetimeIndex(object):
```python
   2  
   3  import numpy as np
   4  from pandas import to_datetime, date_range, Series, DataFrame, period_range
   5  from pandas.tseries.frequencies import infer_freq
   6  try:
   7      from pandas.plotting._converter import DatetimeConverter
   8  except ImportError:
   9      from pandas.tseries.converter import DatetimeConverter
  10  
  11  from .pandas_vb_common import setup  # noqa
  12  
  13  
  14  class DatetimeIndex(object):
  15  
  16      goal_time = 0.2
  17      params = ['dst', 'repeated', 'tz_aware', 'tz_naive']
  18      param_names = ['index_type']
  19  
  20      def setup(self, index_type):
  21          N = 100000
  22          dtidxes = {'dst': date_range(start='10/29/2000 1:00:00',
  23                                       end='10/29/2000 1:59:59', freq='S'),
  24                     'repeated': date_range(start='2000',
  25                                            periods=N / 10,
  26                                            freq='s').repeat(10),
```
- [full] callee pandas/core/arrays/datetimes.py:153 DatetimeArrayMixin | class DatetimeArrayMixin(dtl.DatetimeLikeArrayMixin):
```python
 141              o_mask = np.array(isna(other))
 142              if o_mask.any():
 143                  result[o_mask] = nat_result
 144  
 145          if self.hasnans:
 146              result[self._isnan] = nat_result
 147  
 148          return result
 149  
 150      return compat.set_function_name(wrapper, opname, cls)
 151  
 152  
 153  class DatetimeArrayMixin(dtl.DatetimeLikeArrayMixin):
 154      """
 155      Assumes that subclass __new__/__init__ defines:
 156          tz
 157          _freq
 158          _data
 159      """
 160      _bool_ops = ['is_month_start', 'is_month_end',
 161                   'is_quarter_start', 'is_quarter_end', 'is_year_start',
 162                   'is_year_end', 'is_leap_year']
 163      _object_ops = ['weekday_name', 'freq', 'tz']
 164  
 165      # dummy attribute so that datetime.__eq__(DatetimeArray) defers
```
- [full] callee pandas/core/arrays/period.py:86 PeriodArrayMixin | class PeriodArrayMixin(DatetimeLikeArrayMixin):
```python
  74          else:
  75              other = Period(other, freq=self.freq)
  76              result = op(other.ordinal)
  77  
  78          if self.hasnans:
  79              result[self._isnan] = nat_result
  80  
  81          return result
  82  
  83      return compat.set_function_name(wrapper, opname, cls)
  84  
  85  
  86  class PeriodArrayMixin(DatetimeLikeArrayMixin):
  87      @property
  88      def _box_func(self):
  89          return lambda x: Period._from_ordinal(ordinal=x, freq=self.freq)
  90  
  91      @cache_readonly
  92      def dtype(self):
  93          return PeriodDtype.construct_from_string(self.freq)
  94  
  95      @property
  96      def _ndarray_values(self):
  97          # Ordinals
  98          return self._data
```
- [full] callee pandas/core/dtypes/common.py:364 is_datetime64_dtype | def is_datetime64_dtype(arr_or_dtype):
```python
 354      False
 355      >>> is_period(pd.PeriodIndex(["2017-01-01"], freq="D"))
 356      True
 357      """
 358  
 359      # TODO: do we need this function?
 360      # It seems like a repeat of is_period_arraylike.
 361      return isinstance(arr, ABCPeriodIndex) or is_period_arraylike(arr)
 362  
 363  
 364  def is_datetime64_dtype(arr_or_dtype):
 365      """
 366      Check whether an array-like or dtype is of the datetime64 dtype.
 367  
 368      Parameters
 369      ----------
 370      arr_or_dtype : array-like
 371          The array-like or dtype to check.
 372  
 373      Returns
 374      -------
```
- [full] callee pandas/core/indexes/datetimes.py:114 DatetimeIndex | class DatetimeIndex(DatetimeArrayMixin, DatelikeOps, TimelikeOps,
```python
 102      have arguments and breaks __new__ """
 103  
 104      # data are already in UTC
 105      # so need to localize
 106      tz = d.pop('tz', None)
 107  
 108      result = cls.__new__(cls, verify_integrity=False, **d)
 109      if tz is not None:
 110          result = result.tz_localize('UTC').tz_convert(tz)
 111      return result
 112  
 113  
 114  class DatetimeIndex(DatetimeArrayMixin, DatelikeOps, TimelikeOps,
 115                      DatetimeIndexOpsMixin, Int64Index):
 116      """
 117      Immutable ndarray of datetime64 data, represented internally as int64, and
 118      which can be boxed to Timestamp objects that are subclasses of datetime and
 119      carry metadata such as frequency information.
 120  
 121      Parameters
 122      ----------
 123      data  : array-like (1-dimensional), optional
 124          Optional datetime-like data to construct index with
 125      copy  : bool
 126          Make a copy of input ndarray
```
- [full] caller pandas/core/indexes/period.py:232 call to dt64arr_to_periodarr | data = dt64arr_to_periodarr(data, freq, tz)
```python
 224              # other iterable of some kind
 225              if not isinstance(data, (list, tuple)):
 226                  data = list(data)
 227  
 228              data = np.asarray(data)
 229  
 230          # datetime other than period
 231          if is_datetime64_dtype(data.dtype):
 232              data = dt64arr_to_periodarr(data, freq, tz)
 233              return cls._from_ordinals(data, name=name, freq=freq)
 234  
 235          # check not floats
 236          if infer_dtype(data) == 'floating' and len(data) > 0:
 237              raise TypeError("PeriodIndex does not allow "
 238                              "floating point in construction")
 239  
 240          # anything else, likely an array of strings or periods
```
- [full] callee pandas/tseries/frequencies.py:74 get_period_alias | def get_period_alias(offset_str):
```python
  64                                      BYearBegin, BYearEnd, prefix_mapping)
  65  try:
  66      cday = CDay()
  67  except NotImplementedError:
  68      cday = None
  69  
  70  #: cache of previously seen offsets
  71  _offset_map = {}
  72  
  73  
  74  def get_period_alias(offset_str):
  75      """ alias to closest period strings BQ->Q etc"""
  76      return _offset_to_period_map.get(offset_str, None)
  77  
  78  
  79  _name_to_offset_map = {'days': Day(1),
  80                         'hours': Hour(1),
  81                         'minutes': Minute(1),
  82                         'seconds': Second(1),
  83                         'milliseconds': Milli(1),
  84                         'microseconds': Micro(1),
```
- [full] callee pandas/util/_decorators.py:272 Appender | class Appender(object):
```python
 280      Usage: construct a docstring.Appender with a string to be joined to
 281      the original docstring. An optional 'join' parameter may be supplied
 282      which will be used to join the docstring and addendum. e.g.
 283  
 284      add_copyright = Appender("Copyright (c) 2009", join='\n')
 285  
 286      @add_copyright
 287      def my_dog(has='fleas'):
 288          "This docstring will have a copyright below"
 289          pass
 290      """
 291  
 292      def __init__(self, addendum, join='', indents=0):
 293          if indents > 0:
 294              self.addendum = indent(addendum, indents=indents)
 295          else:
 296              self.addendum = addendum
 297          self.join = join
 298  
 299      def __call__(self, func):
 300          func.__doc__ = func.__doc__ if func.__doc__ else ''
 301          self.addendum = self.addendum if self.addendum else ''
 302          docitems = [func.__doc__, self.addendum]
 303          func.__doc__ = dedent(self.join.join(docitems))
 304          return func
```
