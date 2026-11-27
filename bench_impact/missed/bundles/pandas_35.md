# pandas#35

Commit message of the reviewed change: PERF: Break reference cycle for all Index types (#27840)

Oracle (fix location at buggy_commit): [{'file': 'pandas/core/indexes/period.py', 'line_start': 327, 'line_end': 328}]

## Reviewed diff (introducing commit)
```diff
diff --git a/doc/source/whatsnew/v0.25.1.rst b/doc/source/whatsnew/v0.25.1.rst
index dfa216b1db..21f1fa7dde 100644
--- a/doc/source/whatsnew/v0.25.1.rst
+++ b/doc/source/whatsnew/v0.25.1.rst
@@ -83,7 +83,7 @@ Indexing
 ^^^^^^^^
 
 - Bug in partial-string indexing returning a NumPy array rather than a ``Series`` when indexing with a scalar like ``.loc['2015']`` (:issue:`27516`)
-- Break reference cycle involving :class:`Index` to allow garbage collection of :class:`Index` objects without running the GC. (:issue:`27585`)
+- Break reference cycle involving :class:`Index` and other index classes to allow garbage collection of index objects without running the GC. (:issue:`27585`, :issue:`27840`)
 - Fix regression in assigning values to a single column of a DataFrame with a ``MultiIndex`` columns (:issue:`27841`).
 -
 
diff --git a/pandas/core/indexes/base.py b/pandas/core/indexes/base.py
index 7272d4e275..d13e41eed7 100644
--- a/pandas/core/indexes/base.py
+++ b/pandas/core/indexes/base.py
@@ -665,7 +665,7 @@ class Index(IndexOpsMixin, PandasObject):
     def _engine(self):
         # property, for now, slow to look up
 
-        # to avoid a refernce cycle, bind `_ndarray_values` to a local variable, so
+        # to avoid a reference cycle, bind `_ndarray_values` to a local variable, so
         # `self` is not passed into the lambda.
         _ndarray_values = self._ndarray_values
         return self._engine_type(lambda: _ndarray_values, len(self))
diff --git a/pandas/core/indexes/category.py b/pandas/core/indexes/category.py
index 8bfa7e8d20..82806c7351 100644
--- a/pandas/core/indexes/category.py
+++ b/pandas/core/indexes/category.py
@@ -446,9 +446,11 @@ class CategoricalIndex(Index, accessor.PandasDelegate):
 
     @cache_readonly
     def _engine(self):
-
-        # we are going to look things up with the codes themselves
-        return self._engine_type(lambda: self.codes, len(self))
+        # we are going to look things up with the codes themselves.
+        # To avoid a reference cycle, bind `codes` to a local variable, so
+        # `self` is not passed into the lambda.
+        codes = self.codes
+        return self._engine_type(lambda: codes, len(self))
 
     # introspection
     @cache_readonly
diff --git a/pandas/core/indexes/period.py b/pandas/core/indexes/period.py
index b0cc386f77..5a2ca10959 100644
--- a/pandas/core/indexes/period.py
+++ b/pandas/core/indexes/period.py
@@ -1,5 +1,6 @@
 from datetime import datetime, timedelta
 import warnings
+import weakref
 
 import numpy as np
 
@@ -441,7 +442,9 @@ class PeriodIndex(DatetimeIndexOpsMixin, Int64Index, PeriodDelegateMixin):
 
     @cache_readonly
     def _engine(self):
-        return self._engine_type(lambda: self, len(self))
+        # To avoid a reference cycle, pass a weakref of self to _engine_type.
+        period = weakref.ref(self)
+        return self._engine_type(period, len(self))
 
     @Appender(_index_shared_docs["contains"])
     def __contains__(self, key):
diff --git a/pandas/tests/indexes/common.py b/pandas/tests/indexes/common.py
index 9459069f0e..0e74c87388 100644
--- a/pandas/tests/indexes/common.py
+++ b/pandas/tests/indexes/common.py
@@ -1,3 +1,5 @@
+import gc
+
 import numpy as np
 import pytest
 
@@ -908,3 +910,10 @@ class Base:
         # multiple NA should not be unique
         index_na_dup = index_na.insert(0, np.nan)
         assert index_na_dup.is_unique is False
+
+    def test_engine_reference_cycle(self):
+        # GH27585
+        index = self.create_index()
+        nrefs_pre = len(gc.get_referrers(index))
+        index._engine
+        assert len(gc.get_referrers(index)) == nrefs_pre
diff --git a/pandas/tests/indexes/test_base.py b/pandas/tests/indexes/test_base.py
index fe1eb96df1..d1ed79118d 100644
--- a/pandas/tests/indexes/test_base.py
+++ b/pandas/tests/indexes/test_base.py
@@ -1,6 +1,5 @@
 from collections import defaultdict
 from datetime import datetime, timedelta
-import gc
 from io import StringIO
 import math
 import operator
@@ -2425,13 +2424,6 @@ Index(['a', 'bb', 'ccc', 'a', 'bb', 'ccc', 'a', 'bb', 'ccc', 'a',
             with tm.assert_produces_warning(FutureWarning):
                 index.contains(1)
 
-    def test_engine_reference_cycle(self):
-        # https://github.com/pandas-dev/pandas/issues/27585
-        index = pd.Index([1, 2, 3])
-        nrefs_pre = len(gc.get_referrers(index))
-        index._engine
-        assert len(gc.get_referrers(index)) == nrefs_pre
-
 
 class TestMixedIntIndex(Base):
     # Mostly the tests from common.py for which the results differ

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/pandas/core/indexes/period.py b/pandas/core/indexes/period.py
index 0646acab57..8aaf828787 100644
--- a/pandas/core/indexes/period.py
+++ b/pandas/core/indexes/period.py
@@ -322,12 +322,12 @@ class PeriodIndex(DatetimeIndexOpsMixin, Int64Index):
     # ------------------------------------------------------------------------
     # Indexing
 
     @cache_readonly
     def _engine(self):
-        # To avoid a reference cycle, pass a weakref of self to _engine_type.
-        period = weakref.ref(self)
+        # To avoid a reference cycle, pass a weakref of self._values to _engine_type.
+        period = weakref.ref(self._values)
         return self._engine_type(period, len(self))
 
     @doc(Index.__contains__)
     def __contains__(self, key: Any) -> bool:
         if isinstance(key, Period):

```

## ODIS candidates: 2 total, path=small, tiers={'full': 2, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee pandas/io/formats/format.py:391 len | def len(self, text: str) -> int:
```python
 381          if footer:
 382              result += "\n" + footer
 383  
 384          return str("".join(result))
 385  
 386  
 387  class TextAdjustment:
 388      def __init__(self):
 389          self.encoding = get_option("display.encoding")
 390  
 391      def len(self, text: str) -> int:
 392          return len(text)
 393  
 394      def justify(self, texts: Any, max_len: int, mode: str = "right") -> List[str]:
 395          return justify(texts, max_len, mode=mode)
 396  
 397      def adjoin(self, space: int, *lists, **kwargs) -> str:
 398          return adjoin(space, *lists, strlen=self.len, justfunc=self.justify, **kwargs)
 399  
 400  
 401  class EastAsianTextAdjustment(TextAdjustment):
```
- [full] callee pandas/io/formats/format.py:414 len | def len(self, text: str) -> int:
```python
 404          if get_option("display.unicode.ambiguous_as_wide"):
 405              self.ambiguous_width = 2
 406          else:
 407              self.ambiguous_width = 1
 408  
 409          # Definition of East Asian Width
 410          # http://unicode.org/reports/tr11/
 411          # Ambiguous width can be changed by option
 412          self._EAW_MAP = {"Na": 1, "N": 1, "W": 2, "F": 2, "H": 1}
 413  
 414      def len(self, text: str) -> int:
 415          """
 416          Calculate display width considering unicode East Asian Width
 417          """
 418          if not isinstance(text, str):
 419              return len(text)
 420  
 421          return sum(
 422              self._EAW_MAP.get(east_asian_width(c), self.ambiguous_width) for c in text
 423          )
 424  
```
