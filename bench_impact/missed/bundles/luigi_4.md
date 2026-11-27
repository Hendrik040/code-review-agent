# luigi#4

Commit message of the reviewed change: Use columns defined for COPY to Redshift so we never rely on order (#2245)

Oracle (fix location at buggy_commit): [{'file': 'luigi/contrib/redshift.py', 'line_start': 356, 'line_end': 356}]

## Reviewed diff (introducing commit)
```diff
diff --git a/luigi/contrib/redshift.py b/luigi/contrib/redshift.py
index e8f1a7a..2d3a80c 100644
--- a/luigi/contrib/redshift.py
+++ b/luigi/contrib/redshift.py
@@ -334,12 +334,18 @@ class S3CopyToTable(rdbms.CopyToTable, _CredentialsMixin):
         If both key-based and role-based credentials are provided, role-based will be used.
         """
         logger.info("Inserting file: %s", f)
+        colnames = ''
+        if len(self.columns) > 0:
+            colnames = ",".join([x[0] for x in self.columns])
+            colnames = '({})'.format(colnames)
+
         cursor.execute("""
-         COPY {table} from '{source}'
+         COPY {table} {colnames} from '{source}'
          CREDENTIALS '{creds}'
          {options}
          ;""".format(
             table=self.table,
+            colnames=colnames,
             source=f,
             creds=self._credentials(),
             options=self.copy_options)

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/luigi/contrib/redshift.py b/luigi/contrib/redshift.py
index 5901685..0ab50dc 100644
--- a/luigi/contrib/redshift.py
+++ b/luigi/contrib/redshift.py
@@ -351,11 +351,11 @@ class S3CopyToTable(rdbms.CopyToTable, _CredentialsMixin):
 
         If both key-based and role-based credentials are provided, role-based will be used.
         """
         logger.info("Inserting file: %s", f)
         colnames = ''
-        if len(self.columns) > 0:
+        if self.columns and len(self.columns) > 0:
             colnames = ",".join([x[0] for x in self.columns])
             colnames = '({})'.format(colnames)
 
         cursor.execute("""
          COPY {table} {colnames} from '{source}'

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
