# Code Review Context

## 1. Git Diff (What Changed)

<diff>
diff --git a/calc.py b/calc.py
index 1063fcc..0e7b1c8 100644
--- a/calc.py
+++ b/calc.py
@@ -1,6 +1,6 @@
-def add(a, b):
-    """Sum two numbers."""
-    return a + b
+def add(a, b, c):
+    """Sum three numbers."""
+    return a + b + c
 
 
 def total(items):

</diff>

## 2. Changed Code (Modified Files with Context)

<file name="calc.py" lines="1-3" type="changed">
```python
   1  def add(a, b, c):
   2      """Sum three numbers."""
   3      return a + b + c
   4  
   5  
   6  def total(items):
   7      """Sum a list."""
   8      return sum(items)
```
</file>

## 3. Impact Code (Contracts & Call Sites)

### CALLEES: Definitions that the changed code CALLS (check if changed code respects these contracts)
<callees>
None
</callees>

### CALLERS: Call sites that invoke the changed functions/classes (check if callers pass correct arguments)
<callers>
<file name="main.py" symbol="call to add">
```python
   1  from calc import add, total
   2  
   3  
   4  def report():
   5      x = add(1, 2)
   6      y = total([1, 2, 3])
   7      return x + y
```
</file>
</callers>
