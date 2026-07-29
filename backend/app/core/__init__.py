"""Cross-cutting backend concerns owned by W7.

This package holds everything the API layer needs that is not itself an HTTP
route: configuration (:mod:`app.core.config`), secret loading
(:mod:`app.core.secrets`), structured logging (:mod:`app.core.logging`), the
in-memory read index (:mod:`app.core.index`) and the small pure helpers the
routers compose (serialisation, timing, rate limiting).

Nothing here imports FastAPI, so it can be unit-tested in isolation and reused by
the daily job (W8) without dragging the web framework in.
"""

from __future__ import annotations
