"""Wilson-Rode derived document index.

A fully local, read-only document indexing and triage toolkit for a
Bates-numbered legal document production.

Every value this package produces is *derived review metadata*: it is
calculated or inferred from the PDF files themselves.  Nothing in this package
reads, reconstructs, or reports native/original document metadata from a load
file, because the production does not include one.
"""

from __future__ import annotations

from .version import APP_NAME, APP_VERSION, SCHEMA_VERSION

__all__ = ["APP_NAME", "APP_VERSION", "SCHEMA_VERSION"]
