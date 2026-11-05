"""Read KEY=VALUE lines from .env into the environment (no extra dependency).

Called at the entry points (CLI, API, evals) so keys put in .env (git-ignored) are used.
Variables already set in the environment win; .env never overrides them.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None, environ: dict | None = None) -> list[str]:
    """Load the file; return the names that were set (never their values)."""
    environ = os.environ if environ is None else environ
    if path is None and environ.get("JRA_NO_DOTENV"):  # set by the test suite
        return []
    path = path or ROOT / ".env"
    if not path.exists():
        return []
    loaded = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key and key not in environ and value != "":
            environ[key] = value
            loaded.append(key)
    return loaded
