# keras#3

Commit message of the reviewed change: [RELNOTES] Add `clone_model`. (#7631)

Oracle (fix location at buggy_commit): [{'file': 'keras/models.py', 'line_start': 140, 'line_end': 142}, {'file': 'keras/models.py', 'line_start': 153, 'line_end': 155}]

## Reviewed diff (introducing commit)
```diff
diff --git a/keras/engine/topology.py b/keras/engine/topology.py
index 79ee3bb0f..90ceb3110 100644
--- a/keras/engine/topology.py
+++ b/keras/engine/topology.py
@@ -1790,7 +1790,8 @@ class Container(Layer):
                 raise RuntimeError('The name "' + name + '" is used ' +
                                    str(all_names.count(name)) +
                                    ' times in the model. '
-                                   'All layer names should be unique.')
+                                   'All layer names should be unique. '
+                                   'Layer names: ', all_names)
 
         # Layer parameters.
         # The new container starts with a single inbound node
diff --git a/keras/models.py b/keras/models.py
index 818c002e5..fa3e85019 100644
--- a/keras/models.py
+++ b/keras/models.py
@@ -13,6 +13,7 @@ from . import backend as K
 from . import optimizers
 from . import layers as layer_module
 from .utils.io_utils import ask_to_proceed_with_overwrite
+from .utils.generic_utils import has_arg
 from .engine.training import Model
 from .engine import topology
 from .engine.topology import Layer
@@ -560,7 +561,6 @@ class Sequential(Model):
         # Make sure child model callbacks
         # will call the parent Sequential model.
         self.model.callback_model = self
-
         self.built = True
 
     @property
@@ -1299,3 +1299,231 @@ class Sequential(Model):
             layer = get_or_create_layer(conf)
             model.add(layer)
         return model
+
+
+def _clone_functional_model(model, input_tensors=None):
+    """Clone a functional `Model` instance.
+
+    Model cloning is similar to calling a model on new inputs,
+    except that it creates new layers (and thus new weights) instead
+    of sharing the weights of the existing layers.
+
+    # Arguments
+        model: Instance of `Model`.
+        input_tensors: optional list of input tensors
+            to build the model upon. If not provided,
+            placeholders will be created.
+
+    # Returns
+        An instance of `Model` reproducing the behavior
+        of the original model, on top of new inputs tensors,
+        using newly instantiated weights.
+
+    # Raises
+        ValueError: in case of invalid `model` argument value.
+    """
+    if not isinstance(model, Model):
+        raise ValueError('Expected `model` argument '
+                         'to be a `Model` instance, got ', model)
+    if isinstance(model, Sequential):
+        raise ValueError('Expected `model` argument '
+                         'to be a functional `Model` instance, '
+                         'got a `Sequential` instance instead:', model)
+
+    layer_map = {}  # Cache for created layers.
+    tensor_map = {}  # Map {reference_tensor: (corresponding_tensor, mask)}
+    if input_tensors is None:
+        # Create placeholders to build the model on top of.
+        input_layers = []
+        input_tensors = []
+        for layer in model.input_layers:
+            input_tensor = Input(batch_shape=layer.batch_input_shape,
+                                 dtype=layer.dtype,
+                                 sparse=layer.sparse,
+                                 name=layer.name)
+            input_tensors.append(input_tensor)
+            # Cache newly created input layer.
+            newly_created_input_layer = input_tensor._keras_history[0]
+            layer_map[layer] = newly_created_input_layer
+        for original_input_layer, cloned_input_layer in zip(model.input_layers, input_layers):
+            layer_map[original_input_layer] = cloned_input_layer
+    else:
+        # Make sure that all input tensors come from a Keras layer.
+        # If tensor comes from an input layer: cache the input layer.
+        input_tensors = topology._to_list(input_tensors)
+        _input_tensors = []
+        for i, x in enumerate(input_tensors):
+            if not K.is_keras_tensor(x):
+                name = model.input_layers[i].name
+                input_tensor = Input(tensor=x,
+                                     name='input_wrapper_for_' + name)
+                _input_tensors.append(input_tensor)
+                # Cache newly created input layer.
+                original_input_layer = x._keras_history[0]
+                newly_created_input_layer = input_tensor._keras_history[0]
+                layer_map[original_input_layer] = newly_created_input_layer
+            else:
+                _input_tensors.append(x)
+        input_tensors = _input_tensors
+
+    for x, y in zip(model.inputs, input_tensors):
+        tensor_map[x] = (y, None)  # tensor, mask
+
+    # Iterated over every node in the reference model, in depth order.
+    depth_keys = list(model.nodes_by_depth.keys())
+    depth_keys.sort(reverse=True)
+    for depth in depth_keys:
+        nodes = model.nodes_by_depth[depth]
+        for node in nodes:
+            # Recover the corresponding layer.
+            layer = node.outbound_layer
+
+            # Get or create layer.
+            if layer not in layer_map:
+                # Clone layer.
+                new_layer = layer.__class__.from_config(layer.get_config())
+                layer_map[layer] = new_layer
+                layer = new_layer
+            else:
+                # Reuse previously cloned layer.
+                layer = layer_map[layer]
+                # Don't call InputLayer multiple times.
+                if isinstance(layer, topology.InputLayer):
+                    continue
+
+            # Gather inputs to call the new layer.
+            reference_input_tensors = node.input_tensors
+            reference_output_tensors = node.output_tensors
+
+            # If all previous input tensors are available in tensor_map,
+            # then call node.inbound_layer on them.
+            computed_data = []  # List of tuples (input, mask).
+            for x in reference_input_tensors:
+                if x in tensor_map:
+                    computed_data.append(tensor_map[x])
+
+            if len(computed_data) == len(reference_input_tensors):
+                # Call layer.
+                if node.arguments:
+                    kwargs = node.arguments
+                else:
+                    kwargs = {}
+                if len(computed_data) == 1:
+                    computed_tensor, computed_mask = computed_data[0]
+                    if has_arg(layer.call, 'mask'):
+                        if 'mask' not in kwargs:
+                            kwargs['mask'] = computed_mask
+                    output_tensors = topology._to_list(
+                        layer(computed_tensor, **kwargs))
+                    output_masks = topology._to_list(
+                        layer.compute_mask(computed_tensor,
+                                           computed_mask))
+                    computed_tensors = [computed_tensor]
+                    computed_masks = [computed_mask]
+                else:
+                    computed_tensors = [x[0] for x in computed_data]
+                    computed_masks = [x[1] for x in computed_data]
+                    if has_arg(layer.call, 'mask'):
+                        if 'mask' not in kwargs:
+                            kwargs['mask'] = computed_masks
+                    output_tensors = topology._to_list(
+                        layer(computed_tensors, **kwargs))
+                    output_masks = topology._to_list(
+                        layer.compute_mask(computed_tensors,
+                                           computed_masks))
+                # Update tensor_map.
+                for x, y, mask in zip(reference_output_tensors,
+                                      output_tensors,
+                                      output_masks):
+                    tensor_map[x] = (y, mask)
+
+    # Check that we did compute the model outputs,
+    # then instantiate a new model from inputs and outputs.
+    output_tensors = []
+    for x in model.outputs:
+        assert x in tensor_map, 'Could not compute output ' + str(x)
+        tensor, _ = tensor_map[x]
+        output_tensors.append(tensor)
+    return Model(input_tensors, output_tensors, name=model.name)
+
+
+def _clone_sequential_model(model, input_tensors=None):
+    """Clone a `Sequential` model instance.
+
+    Model cloning is similar to calling a model on new inputs,
+    except that it creates new layers (and thus new weights) instead
+    of sharing the weights of the existing layers.
+
+    # Arguments
+        model: Instance of `Sequential`.
+        input_tensors: optional list of input tensors
+            to build the model upon. If not provided,
+            placeholders will be created.
+
+    # Returns
+        An instance of `Sequential` reproducing the behavior
+        of the original model, on top of new inputs tensors,
+        using newly instantiated weights.
+
+    # Raises
+        ValueError: in case of invalid `model` argument value.
+    """
+    if not isinstance(model, Sequential):
+        raise ValueError('Expected `model` argument '
+                         'to be a `Sequential` model instance, '
+                         'but got:', model)
+
+    def clone(layer):
+        return layer.__class__.from_config(layer.get_config())
+
+    layers = [clone(layer) for layer in model.layers]
+    if input_tensors is None:
+        return Sequential(layers=layers, name=model.name)
+    else:
+        if len(topology._to_list(input_tensors)) != 1:
+            raise ValueError('To clone a `Sequential` model, we expect '
+                             ' at most one tensor '
+                             'as part of `input_tensors`.')
+        x = topology._to_list(input_tensors)[0]
+        if K.is_keras_tensor(x):
+            origin_layer = x._keras_history[0]
+            if isinstance(origin_layer, topology.InputLayer):
+                return Sequential(layers=[origin_layer] + layers,
+                                  name=model.name)
+            else:
+                raise ValueError('Cannot clone a `Sequential` model on top '
+                                 'of a tensor that comes from a Keras layer '
+                                 'other than an `InputLayer`. '
+                                 'Use the functional API instead.')
+        input_tensor = Input(tensor=x,
+                             name='input_wrapper_for_' + str(x.name))
+        input_layer = input_tensor._keras_history[0]
+        return Sequential(layers=[input_layer] + layers, name=model.name)
+
+
+def clone_model(model, input_tensors=None):
+    """Clone any `Model` instance.
+
+    Model cloning is similar to calling a model on new inputs,
+    except that it creates new layers (and thus new weights) instead
+    of sharing the weights of the existing layers.
+
+    # Arguments
+        model: Instance of `Model`
+            (could be a functional model or a Sequential model).
+        input_tensors: optional list of input tensors
+            to build the model upon. If not provided,
+            placeholders will be created.
+
+    # Returns
+        An instance of `Model` reproducing the behavior
+        of the original model, on top of new inputs tensors,
+        using newly instantiated weights.
+
+    # Raises
+        ValueError: in case of invalid `model` argument value.
+    """
+    if isinstance(model, Sequential):
+        return _clone_sequential_model(model, input_tensors=input_tensors)
+    else:
+        return _clone_functional_model(model, input_tensors=input_tensors)
diff --git a/tests/keras/test_sequential_model.py b/tests/keras/test_sequential_model.py
index c948f1e12..48ecd1d70 100644
--- a/tests/keras/test_sequential_model.py
+++ b/tests/keras/test_sequential_model.py
@@ -5,6 +5,7 @@ import os
 import numpy as np
 
 from keras import backend as K
+import keras
 from keras.models import Sequential
 from keras.layers import Dense, Activation
 from keras.utils import np_utils
@@ -267,5 +268,83 @@ def test_rebuild_model():
     assert(model.get_layer(index=-1).output_shape == (None, 32))
 
 
+@keras_test
+def test_clone_functional_model():
+    val_a = np.random.random((10, 4))
+    val_b = np.random.random((10, 4))
+    val_out = np.random.random((10, 4))
+
+    input_a = keras.Input(shape=(4,))
+    input_b = keras.Input(shape=(4,))
+    dense_1 = keras.layers.Dense(4,)
+    dense_2 = keras.layers.Dense(4,)
+
+    x_a = dense_1(input_a)
+    x_a = keras.layers.Dropout(0.5)(x_a)
+    x_b = dense_1(input_b)
+    x_a = dense_2(x_a)
+    outputs = keras.layers.add([x_a, x_b])
+    model = keras.models.Model([input_a, input_b], outputs)
+
+    if K.backend() == 'tensorflow':
+        # Everything should work in a new session.
+        K.clear_session()
+
+    # With placeholder creation
+    new_model = keras.models.clone_model(model)
+    new_model.compile('rmsprop', 'mse')
+    new_model.train_on_batch([val_a, val_b], val_out)
+
+    # On top of new tensors
+    input_a = keras.Input(shape=(4,), name='a')
+    input_b = keras.Input(shape=(4,), name='b')
+    new_model = keras.models.clone_model(
+        model, input_tensors=[input_a, input_b])
+    new_model.compile('rmsprop', 'mse')
+    new_model.train_on_batch([val_a, val_b], val_out)
+
+    # On top of new, non-Keras tensors
+    input_a = keras.backend.variable(val_a)
+    input_b = keras.backend.variable(val_b)
+    new_model = keras.models.clone_model(
+        model, input_tensors=[input_a, input_b])
+    new_model.compile('rmsprop', 'mse')
+    new_model.train_on_batch(None, val_out)
+
+
+@keras_test
+def test_clone_sequential_model():
+    val_a = np.random.random((10, 4))
+    val_out = np.random.random((10, 4))
+
+    model = keras.models.Sequential()
+    model.add(keras.layers.Dense(4, input_shape=(4,)))
+    model.add(keras.layers.Dropout(0.5))
+    model.add(keras.layers.Dense(4))
+
+    if K.backend() == 'tensorflow':
+        # Everything should work in a new session.
+        K.clear_session()
+
+    # With placeholder creation
+    new_model = keras.models.clone_model(model)
+    new_model.compile('rmsprop', 'mse')
+    new_model.train_on_batch(val_a, val_out)
+
+    # On top of new tensor
+    input_a = keras.Input(shape=(4,))
+    new_model = keras.models.clone_model(
+        model, input_tensors=input_a)
+    new_model.compile('rmsprop', 'mse')
+    new_model.train_on_batch(val_a, val_out)
+
+    # On top of new, non-Keras tensor
+    input_a = keras.backend.variable(val_a)
+    new_model = keras.models.clone_model(
+        model, input_tensors=input_a)
+    new_model.compile('rmsprop', 'mse')
+    new_model.train_on_batch(None, val_out)
+
+
 if __name__ == '__main__':
     pytest.main([__file__])

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/keras/models.py b/keras/models.py
index a03b09ab9..03c487dd8 100644
--- a/keras/models.py
+++ b/keras/models.py
@@ -135,26 +135,32 @@ def _clone_functional_model(model, input_tensors=None):
                     if has_arg(layer.call, 'mask'):
                         if 'mask' not in kwargs:
                             kwargs['mask'] = computed_mask
                     output_tensors = to_list(
                         layer(computed_tensor, **kwargs))
-                    output_masks = to_list(
-                        layer.compute_mask(computed_tensor,
-                                           computed_mask))
+                    if layer.supports_masking:
+                        output_masks = to_list(
+                            layer.compute_mask(computed_tensor,
+                                               computed_mask))
+                    else:
+                        output_masks = [None] * len(output_tensors)
                     computed_tensors = [computed_tensor]
                     computed_masks = [computed_mask]
                 else:
                     computed_tensors = [x[0] for x in computed_data]
                     computed_masks = [x[1] for x in computed_data]
                     if has_arg(layer.call, 'mask'):
                         if 'mask' not in kwargs:
                             kwargs['mask'] = computed_masks
                     output_tensors = to_list(
                         layer(computed_tensors, **kwargs))
-                    output_masks = to_list(
-                        layer.compute_mask(computed_tensors,
-                                           computed_masks))
+                    if layer.supports_masking:
+                        output_masks = to_list(
+                            layer.compute_mask(computed_tensors,
+                                               computed_masks))
+                    else:
+                        output_masks = [None] * len(output_tensors)
                 # Update tensor_map.
                 for x, y, mask in zip(reference_output_tensors,
                                       output_tensors,
                                       output_masks):
                     tensor_map[x] = (y, mask)

```

## ODIS candidates: 4 total, path=small, tiers={'full': 4, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee keras/engine/topology.py:1359 Input | def Input(shape=None, batch_shape=None,
```python
1349               output_shapes=[batch_input_shape])
1350  
1351      def get_config(self):
1352          config = {'batch_input_shape': self.batch_input_shape,
1353                    'dtype': self.dtype,
1354                    'sparse': self.sparse,
1355                    'name': self.name}
1356          return config
1357  
1358  
1359  def Input(shape=None, batch_shape=None,
1360            name=None, dtype=K.floatx(), sparse=False,
1361            tensor=None):
1362      """`Input()` is used to instantiate a Keras tensor.
1363  
1364      A Keras tensor is a tensor object from the underlying backend
1365      (Theano or TensorFlow), which we augment with certain
1366      attributes that allow us to build a Keras model
1367      just by knowing the inputs and outputs of the model.
1368  
1369      For instance, if a, b and c are Keras tensors,
```
- [full] callee keras/engine/training.py:562 Model | class Model(Container):
```python
 550              raise ValueError('`class_weight` must contain all classes in the data.'
 551                               ' The classes %s exist in the data but not in '
 552                               '`class_weight`.'
 553                               % (existing_classes - existing_class_weight))
 554          return weights
 555      else:
 556          if sample_weight_mode is None:
 557              return np.ones((y.shape[0],), dtype=K.floatx())
 558          else:
 559              return np.ones((y.shape[0], y.shape[1]), dtype=K.floatx())
 560  
 561  
 562  class Model(Container):
 563      """The `Model` class adds training & evaluation routines to a `Container`.
 564      """
 565  
 566      def compile(self, optimizer, loss, metrics=None, loss_weights=None,
 567                  sample_weight_mode=None, weighted_metrics=None, **kwargs):
 568          """Configures the model for training.
 569  
 570          # Arguments
 571              optimizer: str (name of optimizer) or optimizer object.
 572                  See [optimizers](/optimizers).
 573              loss: str (name of objective function) or objective function.
 574                  See [losses](/losses).
```
- [full] callee keras/models.py:348 Sequential | class Sequential(Model):
```python
 373              model.add(Dense(32, input_shape=(500,)))
 374              model.add(Dense(32))
 375  
 376              # also possible (equivalent to the above):
 377              model = Sequential()
 378              # here the batch dimension is None,
 379              # which means any batch size will be accepted by the model.
 380              model.add(Dense(32, batch_input_shape=(None, 500)))
 381              model.add(Dense(32))
 382          ```
 383      """
 384  
 385      def __init__(self, layers=None, name=None):
 386          self.layers = []  # Stack of layers.
 387          self.model = None  # Internal Model instance.
 388          self.inputs = []  # List of input tensors
 389          self.outputs = []  # List of length 1: the output tensor (unique).
 390          self._trainable = True
 391          self._initial_weights = None
 392  
 393          # Model attributes.
 394          self.inbound_nodes = []
 395          self.outbound_nodes = []
 396          self.built = False
 397  
```
- [full] callee keras/utils/generic_utils.py:209 has_arg | def has_arg(fn, name, accept_all=False):
```python
 199              defaults = tuple(defaults)
 200      code = marshal.loads(code.encode('raw_unicode_escape'))
 201      if globs is None:
 202          globs = globals()
 203      return python_types.FunctionType(code, globs,
 204                                       name=code.co_name,
 205                                       argdefs=defaults,
 206                                       closure=closure)
 207  
 208  
 209  def has_arg(fn, name, accept_all=False):
 210      """Checks if a callable accepts a given keyword argument.
 211  
 212      For Python 2, checks if there is an argument with the given name.
 213  
 214      For Python 3, checks if there is an argument with the given name, and
 215      also whether this argument can be called with a keyword (i.e. if it is
 216      not a positional-only argument).
 217  
 218      # Arguments
 219          fn: Callable to inspect.
```
