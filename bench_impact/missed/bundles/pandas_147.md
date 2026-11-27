# pandas#147

Commit message of the reviewed change: PERF: 3x speedup in Series of dicts with datetime keys by not having error message scale with input (#24743)

Oracle (fix location at buggy_commit): [{'file': 'pandas/core/dtypes/dtypes.py', 'line_start': 688, 'line_end': 688}, {'file': 'pandas/core/dtypes/dtypes.py', 'line_start': 740, 'line_end': 743}, {'file': 'pandas/core/dtypes/dtypes.py', 'line_start': 745, 'line_end': 747}]

## Reviewed diff (introducing commit)
```diff
diff --git a/pandas/core/dtypes/dtypes.py b/pandas/core/dtypes/dtypes.py
index 79756d4c0c..f84471c3b0 100644
--- a/pandas/core/dtypes/dtypes.py
+++ b/pandas/core/dtypes/dtypes.py
@@ -686,16 +686,19 @@ class DatetimeTZDtype(PandasExtensionDtype, ExtensionDtype):
         >>> DatetimeTZDtype.construct_from_string('datetime64[ns, UTC]')
         datetime64[ns, UTC]
         """
-        msg = "Could not construct DatetimeTZDtype from '{}'"
-        try:
-            match = cls._match.match(string)
-            if match:
-                d = match.groupdict()
-                return cls(unit=d['unit'], tz=d['tz'])
-        except Exception:
-            # TODO(py3): Change this pass to `raise TypeError(msg) from e`
-            pass
-        raise TypeError(msg.format(string))
+        if isinstance(string, compat.string_types):
+            msg = "Could not construct DatetimeTZDtype from '{}'"
+            try:
+                match = cls._match.match(string)
+                if match:
+                    d = match.groupdict()
+                    return cls(unit=d['unit'], tz=d['tz'])
+            except Exception:
+                # TODO(py3): Change this pass to `raise TypeError(msg) from e`
+                pass
+            raise TypeError(msg.format(string))
+
+        raise TypeError("Could not construct DatetimeTZDtype")
 
     def __unicode__(self):
         return "datetime64[{unit}, {tz}]".format(unit=self.unit, tz=self.tz)
diff --git a/pandas/tests/dtypes/test_dtypes.py b/pandas/tests/dtypes/test_dtypes.py
index 40b8f7afa3..0fe0a845f5 100644
--- a/pandas/tests/dtypes/test_dtypes.py
+++ b/pandas/tests/dtypes/test_dtypes.py
@@ -232,6 +232,10 @@ class TestDatetimeTZDtype(Base):
         with pytest.raises(TypeError, match="notatz"):
             DatetimeTZDtype.construct_from_string('datetime64[ns, notatz]')
 
+        with pytest.raises(TypeError,
+                           match="^Could not construct DatetimeTZDtype$"):
+            DatetimeTZDtype.construct_from_string(['datetime64[ns, notatz]'])
+
     def test_is_dtype(self):
         assert not DatetimeTZDtype.is_dtype(None)
         assert DatetimeTZDtype.is_dtype(self.dtype)

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/pandas/core/dtypes/dtypes.py b/pandas/core/dtypes/dtypes.py
index aa7e6801ba..fcdb89dd8a 100644
--- a/pandas/core/dtypes/dtypes.py
+++ b/pandas/core/dtypes/dtypes.py
@@ -683,11 +683,11 @@ class DatetimeTZDtype(PandasExtensionDtype):
         if tz:
             tz = timezones.maybe_get_tz(tz)
             tz = timezones.tz_standardize(tz)
         elif tz is not None:
             raise pytz.UnknownTimeZoneError(tz)
-        elif tz is None:
+        if tz is None:
             raise TypeError("A 'tz' is required.")
 
         self._unit = unit
         self._tz = tz
 
@@ -735,18 +735,21 @@ class DatetimeTZDtype(PandasExtensionDtype):
         >>> DatetimeTZDtype.construct_from_string('datetime64[ns, UTC]')
         datetime64[ns, UTC]
         """
         if isinstance(string, str):
             msg = "Could not construct DatetimeTZDtype from '{}'"
-            try:
-                match = cls._match.match(string)
-                if match:
-                    d = match.groupdict()
+            match = cls._match.match(string)
+            if match:
+                d = match.groupdict()
+                try:
                     return cls(unit=d["unit"], tz=d["tz"])
-            except Exception:
-                # TODO(py3): Change this pass to `raise TypeError(msg) from e`
-                pass
+                except (KeyError, TypeError, ValueError) as err:
+                    # KeyError if maybe_get_tz tries and fails to get a
+                    #  pytz timezone (actually pytz.UnknownTimeZoneError).
+                    # TypeError if we pass a nonsense tz;
+                    # ValueError if we pass a unit other than "ns"
+                    raise TypeError(msg.format(string)) from err
             raise TypeError(msg.format(string))
 
         raise TypeError("Could not construct DatetimeTZDtype")
 
     def __str__(self):

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
