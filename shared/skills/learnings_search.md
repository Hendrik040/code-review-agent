# search_learnings — query formulation

Use this skill when you need to dig deeper than the auto-injected
`<past_learnings>` block. The block surfaces the top-K (5) maintainer
corrections matched to the diff at cosine ≥ 0.78. If you suspect a
relevant learning didn't surface, call `search_learnings(query)`.

## When to call

- A finding's category or pattern feels like something maintainers have
  taught before, but the auto-injected block didn't include a hit.
- You're uncertain whether a finding is real and want to check whether
  past corrections have addressed similar code.

## How to phrase the query

Pick the form that matches the *match shape* you want:

- **Exact code pattern** — paste the snippet (e.g. `Reflect.apply(fn, this, args)`).
  Best for syntactic similarities.
- **Natural-language description** — describe the concept (e.g.
  "OAuth state CSRF check missing"). Best for cross-language patterns
  and security/architectural concerns where syntactic match is brittle.
- **Hybrid** — short NL preamble followed by representative code.

## What you get back

An `<results>` block with the same `<item>` shape as the auto-injected
section: score, file, lines, author, learning text, code anchor. Treat
items the same way: priors, not rules.

## Don't

- Don't call this tool repeatedly with the same query.
- Don't search for things already in the auto-injected `<past_learnings>` block.
