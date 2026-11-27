# keras#26

Commit message of the reviewed change: tensorflow 0.12 fixes (#4815)

Oracle (fix location at buggy_commit): [{'file': 'keras/backend/tensorflow_backend.py', 'line_start': 2874, 'line_end': 2874}]

## Reviewed diff (introducing commit)
```diff
diff --git a/.travis.yml b/.travis.yml
index 5b2a1c9fd..889a44077 100644
--- a/.travis.yml
+++ b/.travis.yml
@@ -49,9 +49,9 @@ install:
 
   # install TensorFlow
   - if [[ "$TRAVIS_PYTHON_VERSION" == "2.7" ]]; then
-      pip install https://storage.googleapis.com/tensorflow/linux/cpu/tensorflow-0.11.0-cp27-none-linux_x86_64.whl;
+      pip install https://storage.googleapis.com/tensorflow/linux/cpu/tensorflow-0.12.1-cp27-none-linux_x86_64.whl;
     elif [[ "$TRAVIS_PYTHON_VERSION" == "3.4" ]]; then
-      pip install https://storage.googleapis.com/tensorflow/linux/cpu/tensorflow-0.11.0-cp34-cp34m-linux_x86_64.whl;
+      pip install https://storage.googleapis.com/tensorflow/linux/cpu/tensorflow-0.12.1-cp34-cp34m-linux_x86_64.whl;
     fi
 # command to run tests
 script:
diff --git a/keras/backend/tensorflow_backend.py b/keras/backend/tensorflow_backend.py
index 106d73d35..f4c03c2a4 100644
--- a/keras/backend/tensorflow_backend.py
+++ b/keras/backend/tensorflow_backend.py
@@ -867,10 +867,14 @@ def batch_dot(x, y, axes=None):
     else:
         adj_x = None
         adj_y = None
-    try:
-        out = tf.batch_matmul(x, y, adj_a=adj_x, adj_b=adj_y)
-    except TypeError:
-        out = tf.batch_matmul(x, y, adj_x=adj_x, adj_y=adj_y)
+    # TODO: remove later.
+    if hasattr(tf, 'batch_matmul'):
+        try:
+            out = tf.batch_matmul(x, y, adj_a=adj_x, adj_b=adj_y)
+        except TypeError:
+            out = tf.batch_matmul(x, y, adj_x=adj_x, adj_y=adj_y)
+    else:
+        out = tf.matmul(x, y, adjoint_a=adj_x, adjoint_b=adj_y)
     if ndim(out) == 1:
         out = expand_dims(out, 1)
     return out
@@ -1697,6 +1701,10 @@ def rnn(step_function, inputs, initial_states,
     if constants is None:
         constants = []
 
+    # TODO: remove later.
+    if hasattr(tf, 'select'):
+        tf.where = tf.select
+        
     if unroll:
         if not inputs.get_shape()[0]:
             raise ValueError('Unrolling requires a '
@@ -1717,7 +1725,7 @@ def rnn(step_function, inputs, initial_states,
             for input, mask_t in zip(input_list, mask_list):
                 output, new_states = step_function(input, states + constants)
 
-                # tf.select needs its condition tensor
+                # tf.where needs its condition tensor
                 # to be the same shape as its two
                 # result tensors, but in our case
                 # the condition (mask) tensor is
@@ -1735,16 +1743,16 @@ def rnn(step_function, inputs, initial_states,
                 else:
                     prev_output = successive_outputs[-1]
 
-                output = tf.select(tiled_mask_t, output, prev_output)
+                output = tf.where(tiled_mask_t, output, prev_output)
 
                 return_states = []
                 for state, new_state in zip(states, new_states):
                     # (see earlier comment for tile explanation)
                     tiled_mask_t = tf.tile(mask_t,
                                            stack([1, tf.shape(new_state)[1]]))
-                    return_states.append(tf.select(tiled_mask_t,
-                                                   new_state,
-                                                   state))
+                    return_states.append(tf.where(tiled_mask_t,
+                                                  new_state,
+                                                  state))
                 states = return_states
                 successive_outputs.append(output)
                 successive_states.append(states)
@@ -1805,8 +1813,8 @@ def rnn(step_function, inputs, initial_states,
                     new_state.set_shape(state.get_shape())
                 tiled_mask_t = tf.tile(mask_t,
                                        stack([1, tf.shape(output)[1]]))
-                output = tf.select(tiled_mask_t, output, states[0])
-                new_states = [tf.select(tiled_mask_t, new_states[i], states[i]) for i in range(len(states))]
+                output = tf.where(tiled_mask_t, output, states[0])
+                new_states = [tf.where(tiled_mask_t, new_states[i], states[i]) for i in range(len(states))]
                 output_ta_t = output_ta_t.write(time, output)
                 return (time + 1, output_ta_t) + tuple(new_states)
         else:
@@ -1939,7 +1947,7 @@ def elu(x, alpha=1.):
     if alpha == 1:
         return res
     else:
-        return tf.select(x > 0, res, alpha * res)
+        return tf.where(x > 0, res, alpha * res)
 
 
 def softmax(x):
@@ -2426,9 +2434,9 @@ def random_binomial(shape, p=0.0, dtype=None, seed=None):
         dtype = floatx()
     if seed is None:
         seed = np.random.randint(10e6)
-    return tf.select(tf.random_uniform(shape, dtype=dtype, seed=seed) <= p,
-                     tf.ones(shape, dtype=dtype),
-                     tf.zeros(shape, dtype=dtype))
+    return tf.where(tf.random_uniform(shape, dtype=dtype, seed=seed) <= p,
+                    tf.ones(shape, dtype=dtype),
+                    tf.zeros(shape, dtype=dtype))
 
 
 # CTC
diff --git a/keras/optimizers.py b/keras/optimizers.py
index b534433ec..354f6c58f 100644
--- a/keras/optimizers.py
+++ b/keras/optimizers.py
@@ -1,7 +1,9 @@
 from __future__ import absolute_import
+
+from six.moves import zip
+
 from . import backend as K
 from .utils.generic_utils import get_from_module
-from six.moves import zip
 
 
 def clip_norm(g, c, n):
diff --git a/tests/keras/test_optimizers.py b/tests/keras/test_optimizers.py
index cde6c9394..12a79dc1b 100644
--- a/tests/keras/test_optimizers.py
+++ b/tests/keras/test_optimizers.py
@@ -74,5 +74,15 @@ def test_nadam():
     _test_optimizer(Nadam())
 
 
+def test_clipnorm():
+    sgd = SGD(lr=0.01, momentum=0.9, clipnorm=0.5)
+    _test_optimizer(sgd)
+
+
+def test_clipvalue():
+    sgd = SGD(lr=0.01, momentum=0.9, clipvalue=0.5)
+    _test_optimizer(sgd)
+
+
 if __name__ == '__main__':
     pytest.main([__file__])

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/keras/backend/tensorflow_backend.py b/keras/backend/tensorflow_backend.py
index cd57dfbe0..117c72e57 100644
--- a/keras/backend/tensorflow_backend.py
+++ b/keras/backend/tensorflow_backend.py
@@ -2869,11 +2869,14 @@ def rnn(step_function, inputs, initial_states,
                 for state, new_state in zip(states, new_states):
                     new_state.set_shape(state.get_shape())
                 tiled_mask_t = tf.tile(mask_t,
                                        tf.stack([1, tf.shape(output)[1]]))
                 output = tf.where(tiled_mask_t, output, states[0])
-                new_states = [tf.where(tiled_mask_t, new_states[i], states[i]) for i in range(len(states))]
+                new_states = [
+                    tf.where(tf.tile(mask_t, tf.stack([1, tf.shape(new_states[i])[1]])),
+                             new_states[i], states[i]) for i in range(len(states))
+                ]
                 output_ta_t = output_ta_t.write(time, output)
                 return (time + 1, output_ta_t) + tuple(new_states)
         else:
             def _step(time, output_ta_t, *states):
                 """RNN step function.

```

## ODIS candidates: 2 total, path=small, tiers={'full': 2, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee keras/optimizers.py:127 SGD | class SGD(Optimizer):
```python
 125  
 126  
 127  class SGD(Optimizer):
 128      """Stochastic gradient descent, with support for momentum,
 129      learning rate decay, and Nesterov momentum.
 130  
 131      # Arguments
 132          lr: float >= 0. Learning rate.
 133          momentum: float >= 0. Parameter updates momentum.
 134          decay: float >= 0. Learning rate decay over each update.
 135          nesterov: boolean. Whether to apply Nesterov momentum.
 136      """
 137      def __init__(self, lr=0.01, momentum=0., decay=0.,
 138                   nesterov=False, **kwargs):
 139          super(SGD, self).__init__(**kwargs)
 140          self.iterations = K.variable(0.)
 141          self.lr = K.variable(lr)
 142          self.momentum = K.variable(momentum)
 143          self.decay = K.variable(decay)
 144          self.initial_decay = decay
 145          self.nesterov = nesterov
 146  
 147      def get_updates(self, params, constraints, loss):
 148          grads = self.get_gradients(loss, params)
 149          self.updates = []
```
- [full] callee tests/keras/test_optimizers.py:31 _test_optimizer | def _test_optimizer(optimizer, target=0.89):
```python
  21  
  22  def get_model(input_dim, nb_hidden, output_dim):
  23      model = Sequential()
  24      model.add(Dense(nb_hidden, input_shape=(input_dim,)))
  25      model.add(Activation('relu'))
  26      model.add(Dense(output_dim))
  27      model.add(Activation('softmax'))
  28      return model
  29  
  30  
  31  def _test_optimizer(optimizer, target=0.89):
  32      model = get_model(X_train.shape[1], 10, y_train.shape[1])
  33      model.compile(loss='categorical_crossentropy',
  34                    optimizer=optimizer,
  35                    metrics=['accuracy'])
  36      history = model.fit(X_train, y_train, nb_epoch=12, batch_size=16,
  37                          validation_data=(X_test, y_test), verbose=2)
  38      config = optimizer.get_config()
  39      assert type(config) == dict
  40      assert history.history['val_acc'][-1] >= target
  41  
```
