# keras#4

Commit message of the reviewed change: Add basic support for TF optimizers

Oracle (fix location at buggy_commit): [{'file': 'keras/optimizers.py', 'line_start': 706, 'line_end': 706}]

## Reviewed diff (introducing commit)
```diff
diff --git a/keras/optimizers.py b/keras/optimizers.py
index 8ae8aa01b..ee587d949 100644
--- a/keras/optimizers.py
+++ b/keras/optimizers.py
@@ -19,6 +19,7 @@ def optimizer_from_config(config, custom_objects={}):
         'adam': Adam,
         'adamax': Adamax,
         'nadam': Nadam,
+        'tfoptimizer': TFOptimizer,
     }
     class_name = config['class_name']
     if class_name in custom_objects:
@@ -53,14 +54,6 @@ class Optimizer(object):
         self.updates = []
         self.weights = []
 
-    def get_state(self):
-        return [K.get_value(u[0]) for u in self.updates]
-
-    def set_state(self, value_list):
-        assert len(self.updates) == len(value_list)
-        for u, v in zip(self.updates, value_list):
-            K.set_value(u[0], v)
-
     def get_updates(self, params, constraints, loss):
         raise NotImplementedError
 
@@ -570,6 +563,37 @@ class Nadam(Optimizer):
         return dict(list(base_config.items()) + list(config.items()))
 
 
+class TFOptimizer(Optimizer):
+
+    def __init__(self, optimizer):
+        self.optimizer = optimizer
+        self.iterations = K.variable(0.)
+        self.updates = []
+
+    def get_updates(self, params, constraints, loss):
+        if constraints:
+            raise ValueError('TF optimizers do not support '
+                             'weights constraints. Either remove '
+                             'all weights constraints in your model, '
+                             'or use a Keras optimizer.')
+        grads = self.optimizer.compute_gradients(loss, params)
+        self.updates.append(K.update_add(self.iterations, 1))
+        opt_update = self.optimizer.apply_gradients(
+            grads, global_step=self.iterations)
+        self.updates.append(opt_update)
+        return self.updates
+
+    @property
+    def weights(self):
+        raise NotImplementedError
+
+    def get_config(self):
+        raise NotImplementedError
+
+    def from_config(self, config):
+        raise NotImplementedError
+
+
 # aliases
 sgd = SGD
 rmsprop = RMSprop
@@ -581,5 +605,11 @@ nadam = Nadam
 
 
 def get(identifier, kwargs=None):
+    if K.backend() == 'tensorflow':
+        # Wrap TF optimizer instances
+        import tensorflow as tf
+        if isinstance(identifier, tf.train.Optimizer):
+            return TFOptimizer(identifier)
+    # Instantiate a Keras optimizer
     return get_from_module(identifier, globals(), 'optimizer',
                            instantiate=True, kwargs=kwargs)

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/keras/optimizers.py b/keras/optimizers.py
index 0dade2fde..89fe29678 100644
--- a/keras/optimizers.py
+++ b/keras/optimizers.py
@@ -701,11 +701,11 @@ class TFOptimizer(Optimizer):
         with K.name_scope(self.__class__.__name__):
             self.iterations = K.variable(0, dtype='int64', name='iterations')
 
     @interfaces.legacy_get_updates_support
     def get_updates(self, loss, params):
-        grads = self.optimizer.compute_gradients(loss, params)
+        grads = self.optimizer.compute_gradients(loss, var_list=params)
         self.updates = [K.update_add(self.iterations, 1)]
         opt_update = self.optimizer.apply_gradients(
             grads, global_step=self.iterations)
         self.updates.append(opt_update)
         return self.updates

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
