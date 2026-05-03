---
name: ast-grep
description: Use when the model needs to write a non-trivial ast-grep pattern, or when basic `add($$$)` style isn't enough. Covers meta-variables, kind/relational rules, multi-language quirks, and what to do when a pattern returns no matches.
---

# ast-grep Patterns for the Reviewer

## Overview

`ast_search` runs `ast-grep run -p <pattern> --lang <language>`. Patterns are
written in real code syntax of the target language; ast-grep parses them with
the same Tree-sitter grammar it uses on the source, then matches structurally.
A pattern is not a regex over text. If it doesn't parse, it won't match.

## Meta-variables (the only special syntax)

| Token        | Matches                                                   |
| ------------ | --------------------------------------------------------- |
| `$NAME`      | Exactly one AST node (identifier, expression, statement). |
| `$$$`        | Zero or more nodes in a sequence (args, params, stmts).   |
| `$$$ARGS`    | Same, but captured under the name `ARGS`.                 |
| `$_`         | One node, non-capturing (re-use freely).                  |
| `$$NAME`     | One *unnamed* tree-sitter node (rarely needed).           |

Rules:
- Names must be uppercase / digits / underscore: `$X`, `$FN`, `$_TMP`. Lower-case won't be treated as a meta-var.
- Re-using the same name forces structural equality: `$A == $A` matches `x == x`, not `x == y`. Use `$_` if you don't care.
- `$$$` only makes sense in positions that are sequences in the grammar (call args, parameters, block bodies, array elements).

## When the bare `pattern:` form isn't enough

`ast_search` only ships a pattern + language. If you find yourself wishing for
`kind:` / `inside:` / `has:` (the YAML rule forms below), that's a signal to
either (a) write a tighter pattern that pins down the surrounding context, or
(b) report back that the query needs richer rule support and fall back to
`grep` for now. The reference below exists so you recognise those features
when you read ast-grep docs or error messages.

YAML rule shapes you may see in docs:

```yaml
# kind: match by AST node type when a literal pattern is awkward.
rule: { kind: field_definition }

# inside / has: relational filters.
rule:
  pattern: await $P
  inside: { kind: for_in_statement, stopBy: end }
```

`stopBy: end` means "search up/down through any depth", default is direct neighbour only.

## Eight worked examples (Python unless noted)

1. Calls of a specific function, anywhere:
   `requests.get($$$)` -> matches `requests.get(url)`, `requests.get(url, timeout=5)`.

2. Any function definition (capture name + body):
   `def $NAME($$$ARGS): $$$BODY`

3. Method definitions on a class (pin the surrounding `class` to disambiguate):
   `class $C: def $M(self, $$$): $$$`
   If you only want methods of one class, replace `$C` with the literal name.

4. `if x is None` style guards:
   `if $X is None: $$$`
   For the negated form: `if $X is not None: $$$`.

5. Classes inheriting from a base:
   `class $NAME(BaseModel): $$$` -> only direct subclasses of `BaseModel`.
   For multi-inheritance where `BaseModel` is one of several parents, this
   pattern won't match; that's a kind/has-rule case, fall back to `grep`.

6. Imports of a module:
   `from fastapi import $$$` or `import fastapi` (two patterns, run both).

7. New-style decorators with arguments:
   `@$DEC($$$)\ndef $NAME($$$): $$$` -> matches `@app.get("/x")` etc.
   Bare decorators: `@$DEC\ndef $NAME($$$): $$$`.

8. JS/TS: arrow functions assigned to const:
   pattern `const $NAME = ($$$) => $BODY`, language `javascript` or `typescript`.

## Multi-language

`language` accepts `python`, `javascript`, `typescript`, `go`, `rust`, `java`.
Patterns must be valid in that grammar:
- Python is whitespace-sensitive. `def f(): $$$` works; `def f(): pass` only
  matches the literal body `pass`. Use `$$$` for "any body".
- JS/TS need semicolons or newlines as the grammar expects. `console.log($X)`
  matches as expression; `console.log($X);` matches the statement form.
- Go: pointer receivers and types are part of the AST, so
  `func ($R *$T) $M($$$) $$$ { $$$ }` is the shape for a method.

## Pitfalls and what to do when you get zero matches

1. Pattern didn't parse. Try the pattern as a standalone snippet in your head
   - is it valid source? `def $NAME` alone is not a complete Python statement;
   you need `def $NAME($$$): $$$`.
2. Wrong sequence vs single. `foo($X)` requires exactly one argument. Use
   `foo($$$)` for any arity.
3. Same-name aliasing surprised you. `$X.$X` requires both halves identical
   - that's almost never what you want. Switch one to `$_` or `$Y`.
4. Whitespace / decorator coupling. In Python, `@dec\ndef $F(): $$$` matches a
   decorated function as one node; the decorator and `def` are siblings in
   the grammar, not separate top-level matches.
5. Operator precedence. `$A + $B * $C` matches the parsed shape, which is
   `$A + ($B * $C)`. To match `($A + $B) * $C` you need parentheses in the
   pattern.
6. Library-specific names: search for fully-qualified call sites only if your
   codebase actually writes them that way. If imports are aliased, match the
   local name.

When a pattern still returns nothing:
- Re-run with a deliberately broad pattern (e.g. `def $N($$$): $$$`) to
  confirm parsing works for that file at all.
- Drop one constraint at a time until you get hits, then re-tighten.
- If structure genuinely can't be expressed without `kind` / `inside`,
  fall back to `grep` and note the limitation in your finding.

## Quick reference

| Goal                              | Pattern (Python)                          |
| --------------------------------- | ----------------------------------------- |
| Any call to `f`                   | `f($$$)`                                  |
| Call to method `m` on anything    | `$X.m($$$)`                               |
| Any function def                  | `def $N($$$): $$$`                        |
| Async function def                | `async def $N($$$): $$$`                  |
| Class extending `Base`            | `class $N(Base): $$$`                     |
| `is None` check                   | `if $X is None: $$$`                      |
| `try/except` on specific exc      | `try: $$$\nexcept ValueError: $$$`        |
| Decorated route                   | `@$DEC($$$)\ndef $N($$$): $$$`            |

Keep patterns minimal: start broad, add structure only when noise demands it.
