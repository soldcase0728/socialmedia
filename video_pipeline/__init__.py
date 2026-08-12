"""Automated short-video pipeline for a OneDrive-synced folder.

Watches a locally-synced folder for new clips, cuts silence with
auto-editor, then crops to vertical 9:16 and overlays optional
caption/watermark text with ffmpeg. Outputs land in another synced
folder so the OneDrive client uploads them back automatically.
"""

__version__ = "0.1.0"
