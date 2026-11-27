# keras#7

Commit message of the reviewed change: Further style fixes.

Oracle (fix location at buggy_commit): [{'file': 'keras/wrappers/scikit_learn.py', 'line_start': 323, 'line_end': 323}]

## Reviewed diff (introducing commit)
```diff
diff --git a/keras/layers/normalization.py b/keras/layers/normalization.py
index ecbbb8c40..c6d23b287 100644
--- a/keras/layers/normalization.py
+++ b/keras/layers/normalization.py
@@ -4,7 +4,9 @@ from .. import backend as K
 
 
 class BatchNormalization(Layer):
-    """Normalize the activations of the previous layer at each batch,
+    """Batch normalization layer (Ioffe and Szegedy, 2014).
+
+    Normalize the activations of the previous layer at each batch,
     i.e. applies a transformation that maintains the mean activation
     close to 0 and the activation standard deviation close to 1.
 
diff --git a/keras/wrappers/scikit_learn.py b/keras/wrappers/scikit_learn.py
index 2457fe870..c04737d7a 100644
--- a/keras/wrappers/scikit_learn.py
+++ b/keras/wrappers/scikit_learn.py
@@ -18,7 +18,7 @@ class BaseWrapper(object):
 
     # Arguments
         build_fn: callable function or class instance
-        sk_params: model parameters & fitting parameters
+        **sk_params: model parameters & fitting parameters
 
     The build_fn should construct, compile and return a Keras model, which
     will then be used to fit/predict. One of the following
@@ -57,18 +57,23 @@ class BaseWrapper(object):
         self.check_params(sk_params)
 
     def check_params(self, params):
-        """Check for user typos in "params" keys to avoid
+        """Checks for user typos in "params" keys to avoid
         unwanted usage of default values
 
         # Arguments
             params: dictionary
                 The parameters to be checked
+
+        # Raises
+            ValueError: if any member of `params` is not a valid
+                argument.
         """
         legal_params_fns = [Sequential.fit, Sequential.predict,
                             Sequential.predict_classes, Sequential.evaluate]
         if self.build_fn is None:
             legal_params_fns.append(self.__call__)
-        elif not isinstance(self.build_fn, types.FunctionType) and not isinstance(self.build_fn, types.MethodType):
+        elif (not isinstance(self.build_fn, types.FunctionType) and
+              not isinstance(self.build_fn, types.MethodType)):
             legal_params_fns.append(self.build_fn.__call__)
         else:
             legal_params_fns.append(self.build_fn)
@@ -83,7 +88,7 @@ class BaseWrapper(object):
                 raise ValueError('{} is not a legal parameter'.format(params_name))
 
     def get_params(self, deep=True):
-        """Get parameters for this estimator.
+        """Gets parameters for this estimator.
 
         # Arguments
             deep: boolean, optional
@@ -99,7 +104,7 @@ class BaseWrapper(object):
         return res
 
     def set_params(self, **params):
-        """Set the parameters of this estimator.
+        """Sets the parameters of this estimator.
 
         # Arguments
         params: dict
@@ -112,12 +117,12 @@ class BaseWrapper(object):
         self.sk_params.update(params)
         return self
 
-    def fit(self, X, y, **kwargs):
-        """Construct a new model with build_fn and fit the model according
+    def fit(self, x, y, **kwargs):
+        """Constructs a new model with build_fn and fit the model according
         to the given training data.
 
         # Arguments
-            X : array-like, shape `(n_samples, n_features)`
+            x : array-like, shape `(n_samples, n_features)`
                 Training samples where n_samples in the number of samples
                 and n_features is the number of features.
             y : array-like, shape `(n_samples,)` or `(n_samples, n_outputs)`
@@ -129,10 +134,10 @@ class BaseWrapper(object):
             history : object
                 details about the training history at each epoch.
         """
-
         if self.build_fn is None:
             self.model = self.__call__(**self.filter_sk_params(self.__call__))
-        elif not isinstance(self.build_fn, types.FunctionType) and not isinstance(self.build_fn, types.MethodType):
+        elif (not isinstance(self.build_fn, types.FunctionType) and
+              not isinstance(self.build_fn, types.MethodType)):
             self.model = self.build_fn(
                 **self.filter_sk_params(self.build_fn.__call__))
         else:
@@ -147,12 +152,12 @@ class BaseWrapper(object):
         fit_args = copy.deepcopy(self.filter_sk_params(Sequential.fit))
         fit_args.update(kwargs)
 
-        history = self.model.fit(X, y, **fit_args)
+        history = self.model.fit(x, y, **fit_args)
 
         return history
 
-    def filter_sk_params(self, fn, override={}):
-        """Filter sk_params and return those in fn's arguments
+    def filter_sk_params(self, fn, override=None):
+        """Filters sk_params and return those in fn's arguments
 
         # Arguments
             fn : arbitrary function
@@ -162,6 +167,7 @@ class BaseWrapper(object):
             res : dictionary dictionary containing variables
                 in both sk_params and fn's arguments.
         """
+        override = override or {}
         res = {}
         fn_args = inspect.getargspec(fn)[0]
         for name, value in self.sk_params.items():
@@ -175,32 +181,34 @@ class KerasClassifier(BaseWrapper):
     """Implementation of the scikit-learn classifier API for Keras.
     """
 
-    def predict(self, X, **kwargs):
+    def predict(self, x, **kwargs):
         """Returns the class predictions for the given test data.
 
         # Arguments
-            X: array-like, shape `(n_samples, n_features)`
+            x: array-like, shape `(n_samples, n_features)`
                 Test samples where n_samples in the number of samples
                 and n_features is the number of features.
             kwargs: dictionary arguments
-                Legal arguments are the arguments of `Sequential.predict_classes`.
+                Legal arguments are the arguments
+                of `Sequential.predict_classes`.
 
         # Returns
             preds: array-like, shape `(n_samples,)`
                 Class predictions.
         """
         kwargs = self.filter_sk_params(Sequential.predict_classes, kwargs)
-        return self.model.predict_classes(X, **kwargs)
+        return self.model.predict_classes(x, **kwargs)
 
-    def predict_proba(self, X, **kwargs):
+    def predict_proba(self, x, **kwargs):
         """Returns class probability estimates for the given test data.
 
         # Arguments
-            X: array-like, shape `(n_samples, n_features)`
+            x: array-like, shape `(n_samples, n_features)`
                 Test samples where n_samples in the number of samples
                 and n_features is the number of features.
             kwargs: dictionary arguments
-                Legal arguments are the arguments of `Sequential.predict_classes`.
+                Legal arguments are the arguments
+                of `Sequential.predict_classes`.
 
         # Returns
             proba: array-like, shape `(n_samples, n_outputs)`
@@ -211,7 +219,7 @@ class KerasClassifier(BaseWrapper):
                 (instead of `(n_sample, 1)` as in Keras).
         """
         kwargs = self.filter_sk_params(Sequential.predict_proba, kwargs)
-        probs = self.model.predict_proba(X, **kwargs)
+        probs = self.model.predict_proba(x, **kwargs)
 
         # check if binary classification
         if probs.shape[1] == 1:
@@ -219,21 +227,26 @@ class KerasClassifier(BaseWrapper):
             probs = np.hstack([1 - probs, probs])
         return probs
 
-    def score(self, X, y, **kwargs):
+    def score(self, x, y, **kwargs):
         """Returns the mean accuracy on the given test data and labels.
 
         # Arguments
-            X: array-like, shape `(n_samples, n_features)`
+            x: array-like, shape `(n_samples, n_features)`
                 Test samples where n_samples in the number of samples
                 and n_features is the number of features.
             y: array-like, shape `(n_samples,)` or `(n_samples, n_outputs)`
-                True labels for X.
+                True labels for x.
             kwargs: dictionary arguments
                 Legal arguments are the arguments of `Sequential.evaluate`.
 
         # Returns
             score: float
                 Mean accuracy of predictions on X wrt. y.
+
+        # Raises
+            ValueError: If the underlying model isn't configured to
+                compute accuracy. You should pass `metrics=["accuracy"]` to
+                the `.compile()` method of the model.
         """
         kwargs = self.filter_sk_params(Sequential.evaluate, kwargs)
 
@@ -243,7 +256,7 @@ class KerasClassifier(BaseWrapper):
         if loss_name == 'categorical_crossentropy' and len(y.shape) != 2:
             y = to_categorical(y)
 
-        outputs = self.model.evaluate(X, y, **kwargs)
+        outputs = self.model.evaluate(x, y, **kwargs)
         if not isinstance(outputs, list):
             outputs = [outputs]
         for name, output in zip(self.model.metrics_names, outputs):
@@ -258,27 +271,27 @@ class KerasRegressor(BaseWrapper):
     """Implementation of the scikit-learn regressor API for Keras.
     """
 
-    def predict(self, X, **kwargs):
+    def predict(self, x, **kwargs):
         """Returns predictions for the given test data.
 
         # Arguments
             X: array-like, shape `(n_samples, n_features)`
                 Test samples where n_samples in the number of samples
                 and n_features is the number of features.
-            kwargs: dictionary arguments
+            **kwargs: dictionary arguments
                 Legal arguments are the arguments of `Sequential.predict`.
         # Returns
             preds: array-like, shape `(n_samples,)`
                 Predictions.
         """
         kwargs = self.filter_sk_params(Sequential.predict, kwargs)
-        return np.squeeze(self.model.predict(X, **kwargs))
+        return np.squeeze(self.model.predict(x, **kwargs))
 
-    def score(self, X, y, **kwargs):
+    def score(self, x, y, **kwargs):
         """Returns the mean loss on the given test data and labels.
 
         # Arguments
-            X: array-like, shape `(n_samples, n_features)`
+            x: array-like, shape `(n_samples, n_features)`
                 Test samples where n_samples in the number of samples
                 and n_features is the number of features.
             y: array-like, shape `(n_samples,)`
@@ -291,7 +304,7 @@ class KerasRegressor(BaseWrapper):
                 Mean accuracy of predictions on X wrt. y.
         """
         kwargs = self.filter_sk_params(Sequential.evaluate, kwargs)
-        loss = self.model.evaluate(X, y, **kwargs)
+        loss = self.model.evaluate(x, y, **kwargs)
         if isinstance(loss, list):
             return loss[0]
         return loss

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/keras/wrappers/scikit_learn.py b/keras/wrappers/scikit_learn.py
index 6ebf6fc8d..83c3e3c44 100644
--- a/keras/wrappers/scikit_learn.py
+++ b/keras/wrappers/scikit_learn.py
@@ -318,11 +318,11 @@ class KerasRegressor(BaseWrapper):
         # Returns
             preds: array-like, shape `(n_samples,)`
                 Predictions.
         """
         kwargs = self.filter_sk_params(Sequential.predict, kwargs)
-        return np.squeeze(self.model.predict(x, **kwargs))
+        return np.squeeze(self.model.predict(x, **kwargs), axis=-1)
 
     def score(self, x, y, **kwargs):
         """Returns the mean loss on the given test data and labels.
 
         # Arguments

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
