"""Entry point that exposes the ASGI app at module level.

The package directory is named ``social-media-apis-3268`` which contains
characters that are not valid in a Python identifier. We register it under
the importable alias ``social_media_apis_3268`` so the rest of the codebase
can use normal import statements.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PKG_DIR = Path(__file__).parent / "social-media-apis-3268"
_ALIAS = "social_media_apis_3268"


def _install_alias() -> None:
    if _ALIAS in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        _ALIAS,
        _PKG_DIR / "__init__.py",
        submodule_search_locations=[str(_PKG_DIR)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load package from {_PKG_DIR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_ALIAS] = module
    spec.loader.exec_module(module)


_install_alias()

from social_media_apis_3268.main import app  # noqa: E402,F401

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
