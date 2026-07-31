"""Application version constants.

The version string is written into every database row so that reports can
distinguish records produced by different releases of the indexer.
"""

from __future__ import annotations

APP_NAME = "wilson_rode_indexer"
APP_VERSION = "1.0.0"

#: Schema version of the SQLite processing database.  Bumping this value
#: forces :func:`src.database.connect` to refuse an older database rather than
#: silently mixing incompatible rows.
SCHEMA_VERSION = 1
