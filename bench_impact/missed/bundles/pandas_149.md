# pandas#149

Commit message of the reviewed change: BUG: read_parquet, to_parquet for s3 destinations (#19135)

Oracle (fix location at buggy_commit): [{'file': 'pandas/io/parquet.py', 'line_start': 10, 'line_end': 10}, {'file': 'pandas/io/parquet.py', 'line_start': 162, 'line_end': 163}, {'file': 'pandas/io/parquet.py', 'line_start': 167, 'line_end': 167}]

## Reviewed diff (introducing commit)
```diff
diff --git a/doc/source/whatsnew/v0.23.0.txt b/doc/source/whatsnew/v0.23.0.txt
index 84485d5ee0..c59222bf91 100644
--- a/doc/source/whatsnew/v0.23.0.txt
+++ b/doc/source/whatsnew/v0.23.0.txt
@@ -466,6 +466,7 @@ I/O
 - Bug in :func:`read_sas` where a file with 0 variables gave an ``AttributeError`` incorrectly. Now it gives an ``EmptyDataError`` (:issue:`18184`)
 - Bug in :func:`DataFrame.to_latex()` where pairs of braces meant to serve as invisible placeholders were escaped (:issue:`18667`)
 - Bug in :func:`read_json` where large numeric values were causing an ``OverflowError`` (:issue:`18842`)
+- Bug in :func:`DataFrame.to_parquet` where an exception was raised if the write destination is S3 (:issue:`19134`)
 -
 
 Plotting
diff --git a/pandas/io/common.py b/pandas/io/common.py
index da60698fe5..c2d1da5a10 100644
--- a/pandas/io/common.py
+++ b/pandas/io/common.py
@@ -91,14 +91,6 @@ def _is_url(url):
         return False
 
 
-def _is_s3_url(url):
-    """Check for an s3, s3n, or s3a url"""
-    try:
-        return parse_url(url).scheme in ['s3', 's3n', 's3a']
-    except:
-        return False
-
-
 def _expand_user(filepath_or_buffer):
     """Return the argument with an initial component of ~ or ~user
        replaced by that user's home directory.
@@ -168,8 +160,16 @@ def _stringify_path(filepath_or_buffer):
     return filepath_or_buffer
 
 
+def is_s3_url(url):
+    """Check for an s3, s3n, or s3a url"""
+    try:
+        return parse_url(url).scheme in ['s3', 's3n', 's3a']
+    except:  # noqa
+        return False
+
+
 def get_filepath_or_buffer(filepath_or_buffer, encoding=None,
-                           compression=None):
+                           compression=None, mode=None):
     """
     If the filepath_or_buffer is a url, translate and return the buffer.
     Otherwise passthrough.
@@ -179,10 +179,11 @@ def get_filepath_or_buffer(filepath_or_buffer, encoding=None,
     filepath_or_buffer : a url, filepath (str, py.path.local or pathlib.Path),
                          or buffer
     encoding : the encoding to use to decode py3 bytes, default is 'utf-8'
+    mode : str, optional
 
     Returns
     -------
-    a filepath_or_buffer, the encoding, the compression
+    a filepath_ or buffer or S3File instance, the encoding, the compression
     """
     filepath_or_buffer = _stringify_path(filepath_or_buffer)
 
@@ -195,11 +196,12 @@ def get_filepath_or_buffer(filepath_or_buffer, encoding=None,
         reader = BytesIO(req.read())
         return reader, encoding, compression
 
-    if _is_s3_url(filepath_or_buffer):
+    if is_s3_url(filepath_or_buffer):
         from pandas.io import s3
         return s3.get_filepath_or_buffer(filepath_or_buffer,
                                          encoding=encoding,
-                                         compression=compression)
+                                         compression=compression,
+                                         mode=mode)
 
     if isinstance(filepath_or_buffer, (compat.string_types,
                                        compat.binary_type,
diff --git a/pandas/io/parquet.py b/pandas/io/parquet.py
index f67b03d924..1d3fd8552e 100644
--- a/pandas/io/parquet.py
+++ b/pandas/io/parquet.py
@@ -5,7 +5,7 @@ from distutils.version import LooseVersion
 from pandas import DataFrame, RangeIndex, Int64Index, get_option
 from pandas.compat import string_types
 from pandas.core.common import AbstractMethodError
-from pandas.io.common import get_filepath_or_buffer
+from pandas.io.common import get_filepath_or_buffer, is_s3_url
 
 
 def get_engine(engine):
@@ -107,7 +107,7 @@ class PyArrowImpl(BaseImpl):
         self.validate_dataframe(df)
         if self._pyarrow_lt_070:
             self._validate_write_lt_070(df)
-        path, _, _ = get_filepath_or_buffer(path)
+        path, _, _ = get_filepath_or_buffer(path, mode='wb')
 
         if self._pyarrow_lt_060:
             table = self.api.Table.from_pandas(df, timestamps_to_ms=True)
@@ -194,14 +194,32 @@ class FastParquetImpl(BaseImpl):
         # thriftpy/protocol/compact.py:339:
         # DeprecationWarning: tostring() is deprecated.
         # Use tobytes() instead.
-        path, _, _ = get_filepath_or_buffer(path)
+
+        if is_s3_url(path):
+            # path is s3:// so we need to open the s3file in 'wb' mode.
+            # TODO: Support 'ab'
+
+            path, _, _ = get_filepath_or_buffer(path, mode='wb')
+            # And pass the opened s3file to the fastparquet internal impl.
+            kwargs['open_with'] = lambda path, _: path
+        else:
+            path, _, _ = get_filepath_or_buffer(path)
+
         with catch_warnings(record=True):
             self.api.write(path, df,
                            compression=compression, **kwargs)
 
     def read(self, path, columns=None, **kwargs):
-        path, _, _ = get_filepath_or_buffer(path)
-        parquet_file = self.api.ParquetFile(path)
+        if is_s3_url(path):
+            # When path is s3:// an S3File is returned.
+            # We need to retain the original path(str) while also
+            # pass the S3File().open function to fsatparquet impl.
+            s3, _, _ = get_filepath_or_buffer(path)
+            parquet_file = self.api.ParquetFile(path, open_with=s3.s3.open)
+        else:
+            path, _, _ = get_filepath_or_buffer(path)
+            parquet_file = self.api.ParquetFile(path)
+
         return parquet_file.to_pandas(columns=columns, **kwargs)
 
 
diff --git a/pandas/io/s3.py b/pandas/io/s3.py
index 5e48de757d..e2650e29c0 100644
--- a/pandas/io/s3.py
+++ b/pandas/io/s3.py
@@ -19,10 +19,14 @@ def _strip_schema(url):
 
 
 def get_filepath_or_buffer(filepath_or_buffer, encoding=None,
-                           compression=None):
+                           compression=None, mode=None):
+
+    if mode is None:
+        mode = 'rb'
+
     fs = s3fs.S3FileSystem(anon=False)
     try:
-        filepath_or_buffer = fs.open(_strip_schema(filepath_or_buffer))
+        filepath_or_buffer = fs.open(_strip_schema(filepath_or_buffer), mode)
     except (OSError, NoCredentialsError):
         # boto3 has troubles when trying to access a public file
         # when credentialed...
@@ -31,5 +35,5 @@ def get_filepath_or_buffer(filepath_or_buffer, encoding=None,
         # A NoCredentialsError is raised if you don't have creds
         # for that bucket.
         fs = s3fs.S3FileSystem(anon=True)
-        filepath_or_buffer = fs.open(_strip_schema(filepath_or_buffer))
+        filepath_or_buffer = fs.open(_strip_schema(filepath_or_buffer), mode)
     return filepath_or_buffer, None, compression
diff --git a/pandas/tests/io/test_parquet.py b/pandas/tests/io/test_parquet.py
index 31c2ded49b..d472a5ed23 100644
--- a/pandas/tests/io/test_parquet.py
+++ b/pandas/tests/io/test_parquet.py
@@ -204,6 +204,22 @@ def test_cross_engine_fp_pa(df_cross_compat, pa, fp):
         tm.assert_frame_equal(result, df[['a', 'd']])
 
 
+def check_round_trip_equals(df, path, engine,
+                            write_kwargs, read_kwargs,
+                            expected, check_names):
+
+    df.to_parquet(path, engine, **write_kwargs)
+    actual = read_parquet(path, engine, **read_kwargs)
+    tm.assert_frame_equal(expected, actual,
+                          check_names=check_names)
+
+    # repeat
+    df.to_parquet(path, engine, **write_kwargs)
+    actual = read_parquet(path, engine, **read_kwargs)
+    tm.assert_frame_equal(expected, actual,
+                          check_names=check_names)
+
+
 class Base(object):
 
     def check_error_on_write(self, df, engine, exc):
@@ -212,28 +228,32 @@ class Base(object):
             with tm.ensure_clean() as path:
                 to_parquet(df, path, engine, compression=None)
 
-    def check_round_trip(self, df, engine, expected=None,
+    def check_round_trip(self, df, engine, expected=None, path=None,
                          write_kwargs=None, read_kwargs=None,
                          check_names=True):
+
         if write_kwargs is None:
-            write_kwargs = {}
+            write_kwargs = {'compression': None}
+
         if read_kwargs is None:
             read_kwargs = {}
-        with tm.ensure_clean() as path:
-            df.to_parquet(path, engine, **write_kwargs)
-            result = read_parquet(path, engine, **read_kwargs)
 
-            if expected is None:
-                expected = df
-            tm.assert_frame_equal(result, expected, check_names=check_names)
-
-            # repeat
-            to_parquet(df, path, engine, **write_kwargs)
-            result = pd.read_parquet(path, engine, **read_kwargs)
+        if expected is None:
+            expected = df
 
-            if expected is None:
-                expected = df
-            tm.assert_frame_equal(result, expected, check_names=check_names)
+        if path is None:
+            with tm.ensure_clean() as path:
+                check_round_trip_equals(df, path, engine,
+                                        write_kwargs=write_kwargs,
+                                        read_kwargs=read_kwargs,
+                                        expected=expected,
+                                        check_names=check_names)
+        else:
+            check_round_trip_equals(df, path, engine,
+                                    write_kwargs=write_kwargs,
+                                    read_kwargs=read_kwargs,
+                                    expected=expected,
+                                    check_names=check_names)
 
 
 class TestBasic(Base):
@@ -251,7 +271,7 @@ class TestBasic(Base):
 
         # unicode
         df.columns = [u'foo', u'bar']
-        self.check_round_trip(df, engine, write_kwargs={'compression': None})
+        self.check_round_trip(df, engine)
 
     def test_columns_dtypes_invalid(self, engine):
 
@@ -292,7 +312,6 @@ class TestBasic(Base):
 
         expected = pd.DataFrame({'string': list('abc')})
         self.check_round_trip(df, engine, expected=expected,
-                              write_kwargs={'compression': None},
                               read_kwargs={'columns': ['string']})
 
     def test_write_index(self, engine):
@@ -304,7 +323,7 @@ class TestBasic(Base):
                 pytest.skip("pyarrow is < 0.7.0")
 
         df = pd.DataFrame({'A': [1, 2, 3]})
-        self.check_round_trip(df, engine, write_kwargs={'compression': None})
+        self.check_round_trip(df, engine)
 
         indexes = [
             [2, 3, 4],
@@ -315,15 +334,12 @@ class TestBasic(Base):
         # non-default index
         for index in indexes:
             df.index = index
-            self.check_round_trip(
-                df, engine,
-                write_kwargs={'compression': None},
-                check_names=check_names)
+            self.check_round_trip(df, engine, check_names=check_names)
 
         # index with meta-data
         df.index = [0, 1, 2]
         df.index.name = 'foo'
-        self.check_round_trip(df, engine, write_kwargs={'compression': None})
+        self.check_round_trip(df, engine)
 
     def test_write_multiindex(self, pa_ge_070):
         # Not suppoprted in fastparquet as of 0.1.3 or older pyarrow version
@@ -332,7 +348,7 @@ class TestBasic(Base):
         df = pd.DataFrame({'A': [1, 2, 3]})
         index = pd.MultiIndex.from_tuples([('a', 1), ('a', 2), ('b', 1)])
         df.index = index
-        self.check_round_trip(df, engine, write_kwargs={'compression': None})
+        self.check_round_trip(df, engine)
 
     def test_write_column_multiindex(self, engine):
         # column multi-index
@@ -426,6 +442,11 @@ class TestParquetPyArrow(Base):
         df = pd.DataFrame({'a': pd.Categorical(list('abc'))})
         self.check_error_on_write(df, pa, NotImplementedError)
 
+    def test_s3_roundtrip(self, df_compat, s3_resource, pa):
+        # GH #19134
+        self.check_round_trip(df_compat, pa,
+                              path='s3://pandas-test/pyarrow.parquet')
+
 
 class TestParquetFastParquet(Base):
 
@@ -436,7 +457,7 @@ class TestParquetFastParquet(Base):
         # additional supported types for fastparquet
         df['timedelta'] = pd.timedelta_range('1 day', periods=3)
 
-        self.check_round_trip(df, fp, write_kwargs={'compression': None})
+        self.check_round_trip(df, fp)
 
     @pytest.mark.skip(reason="not supported")
     def test_duplicate_columns(self, fp):
@@ -449,8 +470,7 @@ class TestParquetFastParquet(Base):
     def test_bool_with_none(self, fp):
         df = pd.DataFrame({'a': [True, None, False]})
         expected = pd.DataFrame({'a': [1.0, np.nan, 0.0]}, dtype='float16')
-        self.check_round_trip(df, fp, expected=expected,
-                              write_kwargs={'compression': None})
+        self.check_round_trip(df, fp, expected=expected)
 
     def test_unsupported(self, fp):
 
@@ -466,7 +486,7 @@ class TestParquetFastParquet(Base):
         if LooseVersion(fastparquet.__version__) < LooseVersion("0.1.3"):
             pytest.skip("CategoricalDtype not supported for older fp")
         df = pd.DataFrame({'a': pd.Categorical(list('abc'))})
-        self.check_round_trip(df, fp, write_kwargs={'compression': None})
+        self.check_round_trip(df, fp)
 
     def test_datetime_tz(self, fp):
         # doesn't preserve tz
@@ -475,8 +495,7 @@ class TestParquetFastParquet(Base):
 
         # warns on the coercion
         with catch_warnings(record=True):
-            self.check_round_trip(df, fp, df.astype('datetime64[ns]'),
-                                  write_kwargs={'compression': None})
+            self.check_round_trip(df, fp, df.astype('datetime64[ns]'))
 
     def test_filter_row_groups(self, fp):
         d = {'a': list(range(0, 3))}
@@ -486,3 +505,8 @@ class TestParquetFastParquet(Base):
                           row_group_offsets=1)
             result = read_parquet(path, fp, filters=[('a', '==', 0)])
         assert len(result) == 1
+
+    def test_s3_roundtrip(self, df_compat, s3_resource, fp):
+        # GH #19134
+        self.check_round_trip(df_compat, fp,
+                              path='s3://pandas-test/fastparquet.parquet')
diff --git a/pandas/tests/io/test_s3.py b/pandas/tests/io/test_s3.py
index 8c2a32af33..7a3062f470 100644
--- a/pandas/tests/io/test_s3.py
+++ b/pandas/tests/io/test_s3.py
@@ -1,8 +1,8 @@
-from pandas.io.common import _is_s3_url
+from pandas.io.common import is_s3_url
 
 
 class TestS3URL(object):
 
     def test_is_s3_url(self):
-        assert _is_s3_url("s3://pandas/somethingelse.com")
-        assert not _is_s3_url("s4://pandas/somethingelse.com")
+        assert is_s3_url("s3://pandas/somethingelse.com")
+        assert not is_s3_url("s4://pandas/somethingelse.com")

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/pandas/io/parquet.py b/pandas/io/parquet.py
index 3612099d98..69ee6583d1 100644
--- a/pandas/io/parquet.py
+++ b/pandas/io/parquet.py
@@ -5,11 +5,11 @@ from warnings import catch_warnings
 from pandas.compat._optional import import_optional_dependency
 from pandas.errors import AbstractMethodError
 
 from pandas import DataFrame, get_option
 
-from pandas.io.common import get_filepath_or_buffer, is_s3_url
+from pandas.io.common import get_filepath_or_buffer, is_gcs_url, is_s3_url
 
 
 def get_engine(engine):
     """ return our implementation """
 
@@ -157,16 +157,16 @@ class FastParquetImpl(BaseImpl):
             partition_cols = kwargs.pop("partition_on")
 
         if partition_cols is not None:
             kwargs["file_scheme"] = "hive"
 
-        if is_s3_url(path):
-            # path is s3:// so we need to open the s3file in 'wb' mode.
+        if is_s3_url(path) or is_gcs_url(path):
+            # if path is s3:// or gs:// we need to open the file in 'wb' mode.
             # TODO: Support 'ab'
 
             path, _, _, _ = get_filepath_or_buffer(path, mode="wb")
-            # And pass the opened s3file to the fastparquet internal impl.
+            # And pass the opened file to the fastparquet internal impl.
             kwargs["open_with"] = lambda path, _: path
         else:
             path, _, _, _ = get_filepath_or_buffer(path)
 
         with catch_warnings(record=True):

```

## ODIS candidates: 1 total, path=small, tiers={'full': 1, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee pandas/io/parquet.py:248 read_parquet | def read_parquet(path, engine='auto', columns=None, **kwargs):
```python
 238          library to be installed is used.
 239      compression : {'snappy', 'gzip', 'brotli', None}, default 'snappy'
 240          Name of the compression to use. Use ``None`` for no compression.
 241      kwargs
 242          Additional keyword arguments passed to the engine
 243      """
 244      impl = get_engine(engine)
 245      return impl.write(df, path, compression=compression, **kwargs)
 246  
 247  
 248  def read_parquet(path, engine='auto', columns=None, **kwargs):
 249      """
 250      Load a parquet object from the file path, returning a DataFrame.
 251  
 252      .. versionadded 0.21.0
 253  
 254      Parameters
 255      ----------
 256      path : string
 257          File path
 258      columns: list, default=None
```
