# General code-review lens

Review for real defects, not style preferences. Prioritize, in order:

1. **Correctness** — logic errors, off-by-one, wrong operators/units, inverted
   conditions, incorrect API/contract usage, broken invariants.
2. **Lifecycle & state** — partially-initialized data, use-after-free, resource
   leaks, ordering bugs (something runs before its prerequisite), stale caches.
3. **Error handling** — swallowed errors, unchecked return values, silent
   fallbacks that hide failures, missing validation/precondition checks.
4. **Compatibility** — behavior changes that break old data, old clients, or
   other backends; zero-value/default semantics; protocol/format changes.
5. **Edge cases** — empty/nil, boundary values, large inputs, concurrency.

For every finding cite the exact file/function/line and explain the concrete
failure scenario. Do not flag things you cannot tie to specific code.
