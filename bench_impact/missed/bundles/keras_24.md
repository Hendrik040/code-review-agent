# keras#24

Commit message of the reviewed change: Rm legacy TF support from TensorBoard callback.

Oracle (fix location at buggy_commit): [{'file': 'keras/callbacks.py', 'line_start': 789, 'line_end': 790}]

## Reviewed diff (introducing commit)
```diff
diff --git a/keras/callbacks.py b/keras/callbacks.py
index e76f85028..1ec315445 100644
--- a/keras/callbacks.py
+++ b/keras/callbacks.py
@@ -612,56 +612,27 @@ class TensorBoard(Callback):
             for layer in self.model.layers:
 
                 for weight in layer.weights:
-                    if hasattr(tf, 'histogram_summary'):
-                        tf.histogram_summary(weight.name, weight)
-                    else:
-                        tf.summary.histogram(weight.name, weight)
-
+                    tf.summary.histogram(weight.name, weight)
                     if self.write_images:
                         w_img = tf.squeeze(weight)
-
                         shape = w_img.get_shape()
                         if len(shape) > 1 and shape[0] > shape[1]:
                             w_img = tf.transpose(w_img)
-
                         if len(shape) == 1:
                             w_img = tf.expand_dims(w_img, 0)
-
                         w_img = tf.expand_dims(tf.expand_dims(w_img, 0), -1)
-
-                        if hasattr(tf, 'image_summary'):
-                            tf.image_summary(weight.name, w_img)
-                        else:
-                            tf.summary.image(weight.name, w_img)
+                        tf.summary.image(weight.name, w_img)
 
                 if hasattr(layer, 'output'):
-                    if hasattr(tf, 'histogram_summary'):
-                        tf.histogram_summary('{}_out'.format(layer.name),
-                                             layer.output)
-                    else:
-                        tf.summary.histogram('{}_out'.format(layer.name),
-                                             layer.output)
-
-        if hasattr(tf, 'merge_all_summaries'):
-            self.merged = tf.merge_all_summaries()
-        else:
-            self.merged = tf.summary.merge_all()
+                    tf.summary.histogram('{}_out'.format(layer.name),
+                                         layer.output)
+        self.merged = tf.summary.merge_all()
 
         if self.write_graph:
-            if hasattr(tf, 'summary') and hasattr(tf.summary, 'FileWriter'):
-                self.writer = tf.summary.FileWriter(self.log_dir,
-                                                    self.sess.graph)
-            elif parse_version(tf.__version__) >= parse_version('0.8.0'):
-                self.writer = tf.train.SummaryWriter(self.log_dir,
-                                                     self.sess.graph)
-            else:
-                self.writer = tf.train.SummaryWriter(self.log_dir,
-                                                     self.sess.graph_def)
+            self.writer = tf.summary.FileWriter(self.log_dir,
+                                                self.sess.graph)
         else:
-            if hasattr(tf, 'summary') and hasattr(tf.summary, 'FileWriter'):
-                self.writer = tf.summary.FileWriter(self.log_dir)
-            else:
-                self.writer = tf.train.SummaryWriter(self.log_dir)
+            self.writer = tf.summary.FileWriter(self.log_dir)
 
     def on_epoch_end(self, epoch, logs=None):
         logs = logs or {}

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/keras/callbacks.py b/keras/callbacks.py
index 0a00a9507..e28e74b47 100644
--- a/keras/callbacks.py
+++ b/keras/callbacks.py
@@ -784,12 +784,16 @@ class TensorBoard(Callback):
                         shape = K.int_shape(w_img)
                         assert len(shape) == 4 and shape[-1] in [1, 3, 4]
                         tf.summary.image(mapped_weight_name, w_img)
 
                 if hasattr(layer, 'output'):
-                    tf.summary.histogram('{}_out'.format(layer.name),
-                                         layer.output)
+                    if isinstance(layer.output, list):
+                        for i, output in enumerate(layer.output):
+                            tf.summary.histogram('{}_out_{}'.format(layer.name, i), output)
+                    else:
+                        tf.summary.histogram('{}_out'.format(layer.name),
+                                             layer.output)
         self.merged = tf.summary.merge_all()
 
         if self.write_graph:
             self.writer = tf.summary.FileWriter(self.log_dir,
                                                 self.sess.graph)

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
