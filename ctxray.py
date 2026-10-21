#!/usr/bin/env python3
"""Single-command entrypoint for ctxray (python ctxray.py ...)."""

from ctxray.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
