# spacy#5

Commit message of the reviewed change: Fix handling of kwargs in Language.evaluate

Oracle (fix location at buggy_commit): [{'file': 'spacy/language.py', 'line_start': 681, 'line_end': 681}]

## Reviewed diff (introducing commit)
```diff
diff --git a/spacy/language.py b/spacy/language.py
index b839be1f6..f87cb4e31 100644
--- a/spacy/language.py
+++ b/spacy/language.py
@@ -633,7 +633,7 @@ class Language(object):
             kwargs = component_cfg.get(name, {})
             kwargs.setdefault("batch_size", batch_size)
             if not hasattr(pipe, "pipe"):
-                docs = (pipe(doc, **kwargs) for doc in docs)
+                docs = _pipe(pipe, docs, kwargs)
             else:
                 docs = pipe.pipe(docs, **kwargs)
         for doc, gold in zip(docs, golds):

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/spacy/language.py b/spacy/language.py
index 72044a0c5..266a1727d 100644
--- a/spacy/language.py
+++ b/spacy/language.py
@@ -676,11 +676,11 @@ class Language(object):
         golds = list(golds)
         for name, pipe in self.pipeline:
             kwargs = component_cfg.get(name, {})
             kwargs.setdefault("batch_size", batch_size)
             if not hasattr(pipe, "pipe"):
-                docs = _pipe(pipe, docs, kwargs)
+                docs = _pipe(docs, pipe, kwargs)
             else:
                 docs = pipe.pipe(docs, **kwargs)
         for doc, gold in zip(docs, golds):
             if not isinstance(gold, GoldParse):
                 gold = GoldParse(doc, **gold)

```

## ODIS candidates: 1 total, path=small, tiers={'full': 1, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee spacy/language.py:944 _pipe | def _pipe(func, docs, kwargs):
```python
 934          """Restore the pipeline to its state when DisabledPipes was created."""
 935          current, self.nlp.pipeline = self.nlp.pipeline, self.original_pipeline
 936          unexpected = [name for name, pipe in current if not self.nlp.has_pipe(name)]
 937          if unexpected:
 938              # Don't change the pipeline if we're raising an error.
 939              self.nlp.pipeline = current
 940              raise ValueError(Errors.E008.format(names=unexpected))
 941          self[:] = []
 942  
 943  
 944  def _pipe(func, docs, kwargs):
 945      # We added some args for pipe that __call__ doesn't expect.
 946      kwargs = dict(kwargs)
 947      for arg in ["n_threads", "batch_size"]:
 948          if arg in kwargs:
 949              kwargs.pop(arg)
 950      for doc in docs:
 951          doc = func(doc, **kwargs)
 952          yield doc
```
