# Python lens

- Mutable default arguments; shared class-level mutable state.
- Broad `except:` / `except Exception:` that swallow errors silently.
- Truthiness traps: `if x:` when `x` can be `0`, `""`, or empty collection but
  those are valid values; prefer `is None`.
- Resource handling without context managers; files/sockets left open.
- `==` vs `is`; integer/identity caching surprises.
- f-string / format injection into SQL, shell, or paths.
