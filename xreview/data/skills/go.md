# Go lens

Go-specific defects to look for, beyond general correctness:

- **`nil` and zero values** — a `nil` map read is fine but a write panics; a
  `nil` slice appends fine; an interface holding a `nil` concrete pointer is
  `!= nil`. Watch protobuf/JSON zero-value semantics: `0`/`""`/`false` are
  indistinguishable from "unset" and silently change behavior for old clients.
- **Error handling** — unchecked `err`; errors logged but not returned;
  `errors.Is`/`errors.As` vs `==`; wrapping with `%w` vs swallowing context;
  returning a typed-nil error.
- **Goroutines & channels** — leaked goroutines (no exit path / blocked on a
  channel no one closes); writing to a closed channel; missing `context`
  cancellation; `sync.WaitGroup` `Add` after `Wait`; data races on shared maps
  (use `sync.Map` or a mutex; `map` is not concurrency-safe).
- **Loop variable capture** — closures/goroutines capturing the loop variable
  (pre-Go 1.22 semantics, or any code that must run on older toolchains).
- **defer pitfalls** — `defer` in a loop accumulating until function return;
  deferred `Close()` whose error is dropped; arguments evaluated at `defer` time.
- **Slices & aliasing** — `append` mutating a shared backing array; reslicing
  that retains a large array and leaks memory; off-by-one in `s[i:j]`.
- **Concurrency primitives** — see also the `concurrency` skill pack for
  TOCTOU/lock-semantics issues, which are common in Go services.

Cite the exact `file:line` and the failure scenario for each finding.
