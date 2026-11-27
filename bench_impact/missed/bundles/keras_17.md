# keras#17

Commit message of the reviewed change: Make accuracy metrics work with masked outputs (#5866)

Oracle (fix location at buggy_commit): [{'file': 'keras/metrics.py', 'line_start': 37, 'line_end': 37}]

## Reviewed diff (introducing commit)
```diff
diff --git a/keras/metrics.py b/keras/metrics.py
index 3abef5d19..5d33f1fe1 100644
--- a/keras/metrics.py
+++ b/keras/metrics.py
@@ -21,13 +21,15 @@ def binary_accuracy(y_true, y_pred):
 
 
 def categorical_accuracy(y_true, y_pred):
-    return K.equal(K.argmax(y_true, axis=-1),
-                   K.argmax(y_pred, axis=-1))
+    return K.cast(K.equal(K.argmax(y_true, axis=-1),
+                          K.argmax(y_pred, axis=-1)),
+                  K.floatx())
 
 
 def sparse_categorical_accuracy(y_true, y_pred):
-    return K.equal(K.max(y_true, axis=-1),
-                   K.cast(K.argmax(y_pred, axis=-1), K.floatx()))
+    return K.cast(K.equal(K.max(y_true, axis=-1),
+                          K.cast(K.argmax(y_pred, axis=-1), K.floatx())),
+                  K.floatx())
 
 
 def top_k_categorical_accuracy(y_true, y_pred, k=5):

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/keras/metrics.py b/keras/metrics.py
index 3d5df23b9..7c89702e6 100644
--- a/keras/metrics.py
+++ b/keras/metrics.py
@@ -32,11 +32,12 @@ def categorical_accuracy(y_true, y_pred):
                           K.argmax(y_pred, axis=-1)),
                   K.floatx())
 
 
 def sparse_categorical_accuracy(y_true, y_pred):
-    return K.cast(K.equal(K.max(y_true, axis=-1),
+    # flatten y_true in case it's in shape (num_samples, 1) instead of (num_samples,)
+    return K.cast(K.equal(K.flatten(y_true),
                           K.cast(K.argmax(y_pred, axis=-1), K.floatx())),
                   K.floatx())
 
 
 def top_k_categorical_accuracy(y_true, y_pred, k=5):

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
