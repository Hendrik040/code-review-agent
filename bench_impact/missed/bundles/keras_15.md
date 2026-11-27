# keras#15

Commit message of the reviewed change: Fix CSV formatting for Windows with Python 2 (#6311)

Oracle (fix location at buggy_commit): [{'file': 'keras/callbacks.py', 'line_start': 1125, 'line_end': 1125}, {'file': 'keras/callbacks.py', 'line_start': 1133, 'line_end': 1133}, {'file': 'keras/callbacks.py', 'line_start': 1135, 'line_end': 1135}, {'file': 'keras/callbacks.py', 'line_start': 1159, 'line_end': 1159}, {'file': 'keras/callbacks.py', 'line_start': 1161, 'line_end': 1161}]

## Reviewed diff (introducing commit)
```diff
diff --git a/keras/callbacks.py b/keras/callbacks.py
index 042948f31..7b0cec0b5 100644
--- a/keras/callbacks.py
+++ b/keras/callbacks.py
@@ -3,6 +3,7 @@ from __future__ import print_function
 
 import os
 import csv
+import six
 
 import numpy as np
 import time
@@ -861,16 +862,17 @@ class CSVLogger(Callback):
         self.writer = None
         self.keys = None
         self.append_header = True
+        self.file_flags = 'b' if six.PY2 and os.name == 'nt' else ''
         super(CSVLogger, self).__init__()
 
     def on_train_begin(self, logs=None):
         if self.append:
             if os.path.exists(self.filename):
-                with open(self.filename) as f:
+                with open(self.filename, 'r' + self.file_flags) as f:
                     self.append_header = not bool(len(f.readline()))
-            self.csv_file = open(self.filename, 'a')
+            self.csv_file = open(self.filename, 'a' + self.file_flags)
         else:
-            self.csv_file = open(self.filename, 'w')
+            self.csv_file = open(self.filename, 'w' + self.file_flags)
 
     def on_epoch_end(self, epoch, logs=None):
         logs = logs or {}

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/keras/callbacks.py b/keras/callbacks.py
index ad3522d65..8c6f70c65 100644
--- a/keras/callbacks.py
+++ b/keras/callbacks.py
@@ -10,10 +10,12 @@ import six
 
 import numpy as np
 import time
 import json
 import warnings
+import io
+import sys
 
 from collections import deque
 from collections import OrderedDict
 from collections import Iterable
 from .utils.generic_utils import Progbar
@@ -1120,21 +1122,29 @@ class CSVLogger(Callback):
         self.filename = filename
         self.append = append
         self.writer = None
         self.keys = None
         self.append_header = True
-        self.file_flags = 'b' if six.PY2 and os.name == 'nt' else ''
+        if six.PY2:
+            self.file_flags = 'b'
+            self._open_args = {}
+        else:
+            self.file_flags = ''
+            self._open_args = {'newline': '\n'}
         super(CSVLogger, self).__init__()
 
     def on_train_begin(self, logs=None):
         if self.append:
             if os.path.exists(self.filename):
                 with open(self.filename, 'r' + self.file_flags) as f:
                     self.append_header = not bool(len(f.readline()))
-            self.csv_file = open(self.filename, 'a' + self.file_flags)
+            mode = 'a'
         else:
-            self.csv_file = open(self.filename, 'w' + self.file_flags)
+            mode = 'w'
+        self.csv_file = io.open(self.filename,
+                                mode + self.file_flags,
+                                **self._open_args)
 
     def on_epoch_end(self, epoch, logs=None):
         logs = logs or {}
 
         def handle_value(k):
@@ -1154,13 +1164,16 @@ class CSVLogger(Callback):
             logs = dict([(k, logs[k]) if k in logs else (k, 'NA') for k in self.keys])
 
         if not self.writer:
             class CustomDialect(csv.excel):
                 delimiter = self.sep
-
+            fieldnames = ['epoch'] + self.keys
+            if six.PY2:
+                fieldnames = [unicode(x) for x in fieldnames]
             self.writer = csv.DictWriter(self.csv_file,
-                                         fieldnames=['epoch'] + self.keys, dialect=CustomDialect)
+                                         fieldnames=fieldnames,
+                                         dialect=CustomDialect)
             if self.append_header:
                 self.writer.writeheader()
 
         row_dict = OrderedDict({'epoch': epoch})
         row_dict.update((key, handle_value(logs[key])) for key in self.keys)

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
