# Concurrency lens

Look specifically for:

- **TOCTOU / check-then-act** gaps — a value read under one lock (or RLock) and
  acted on after the lock is released or re-acquired; another goroutine/thread
  can mutate state in between.
- **Non-atomic compound operations** on "thread-safe" containers — e.g.
  `emplace()` then `find()`, or `contains()` then `get()`. Individual ops being
  safe does NOT make the pair atomic.
- **Lock semantics mismatches** — read vs write lock used inconsistently across
  functions that touch the same state; missing lock on one path.
- **Concurrent writes to distinct indices** of a shared buffer without
  synchronization, assuming the memory model guarantees safety (it usually
  does not).
- **Data published before fully initialized** — a pointer/handle made visible
  to other threads before the object it points to is complete.

Name the two interleaving execution paths and the shared state for every race.
