"""Module entry point for ``python -m verify_compatibility``."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
