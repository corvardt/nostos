"""`python -m nostos`, for when the console script is not on PATH."""

from .cli import main

raise SystemExit(main())
