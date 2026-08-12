# video_pipeline — automated short-video editing from a OneDrive folder

Drop raw clips into a OneDrive-synced folder on your computer; edited
shorts appear in another synced folder a few minutes later. The OneDrive
client handles all cloud upload/download — this pipeline just works on
the local folders.

For each new clip it:

1. **Cuts silence / dead space** with [auto-editor](https://github.com/WyattBlue/auto-editor)
2. **Crops to vertical 9:16** (1080x1920, center-crop) for TikTok / Reels / Shorts
3. **Overlays optional caption and watermark text**
4. Writes a clean H.264/AAC `.mp4` to the output folder, which OneDrive syncs back up

Every step is optional and configurable. Everything installs with pip —
no separate ffmpeg install needed.

## Setup (Windows)

1. Install [Python 3.11+](https://www.python.org/downloads/) (check "Add python.exe to PATH").
2. In a terminal, from the repo root:

   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r video_pipeline\requirements.txt
   ```

3. Create the two folders inside OneDrive, e.g. `OneDrive\Videos\Inbox`
   and `OneDrive\Videos\Edited` (these are the defaults; any folders work).

4. Run it:

   ```bat
   py -m video_pipeline --watch-dir "%USERPROFILE%\OneDrive\Videos\Inbox" --output-dir "%USERPROFILE%\OneDrive\Videos\Edited" --watermark "@yourhandle"
   ```

The first run downloads auto-editor's processing binary (one time,
needs internet). Then drop a clip into the Inbox folder — from your
phone's OneDrive app, another synced computer, or by copying it in —
and the edited version lands in `Edited` and syncs everywhere.

macOS/Linux is the same, just `python3 -m venv .venv && source .venv/bin/activate`.

## Modes

| Command | What it does |
| ------- | ------------ |
| `py -m video_pipeline` | Process backlog, then keep watching (Ctrl+C to stop) |
| `py -m video_pipeline --once` | Process the backlog and exit |
| `py -m video_pipeline --dry-run` | List what would be processed |

## Options

Every option is a CLI flag and/or an environment variable (flags win).

| Flag | Env var | Default | Meaning |
| ---- | ------- | ------- | ------- |
| `--watch-dir` | `VP_WATCH_DIR` | `~/OneDrive/Videos/Inbox` | Folder watched for new clips (recursive) |
| `--output-dir` | `VP_OUTPUT_DIR` | `~/OneDrive/Videos/Edited` | Where edited clips are written |
| `--caption` | `VP_CAPTION` | *(none)* | Text overlaid near the top of every clip |
| `--watermark` | `VP_WATERMARK` | *(none)* | Small text in the bottom-right corner |
| `--margin` | `VP_MARGIN` | `0.2sec` | Padding kept around non-silent audio |
| `--no-silence-cut` | `VP_SILENCE_CUT=0` | on | Skip the silence-cutting stage |
| `--no-vertical` | `VP_VERTICAL=0` | on | Keep the original aspect ratio |
| | `VP_WIDTH` / `VP_HEIGHT` | `1080` / `1920` | Output size in vertical mode |
| | `VP_FONT` | auto-detected | Path to a `.ttf` font for the text overlays |
| | `VP_CRF` / `VP_PRESET` | `20` / `veryfast` | x264 quality / speed |
| | `VP_SUFFIX` | `_edited` | Appended to output filenames |
| | `VP_STABLE_SECONDS` | `5` | How long a file must stop changing before processing (guards against half-synced files) |

Recognized inputs: `.mp4 .mov .m4v .avi .mkv .webm .mts .3gp`.

## Run it automatically at login (Windows)

Task Scheduler → Create Task:

- **General**: "Run only when user is logged on" (OneDrive sync runs in your session).
- **Triggers**: New → "At log on".
- **Actions**: New → Program: `C:\path\to\repo\.venv\Scripts\pythonw.exe`,
  Arguments: `-m video_pipeline`, Start in: `C:\path\to\repo`.
  Set folder/caption options via `VP_*` user environment variables, or put
  them in the Arguments field.

## OneDrive notes

- **Files On-Demand**: right-click your Inbox folder in Explorer and
  choose **"Always keep on this device"**, so new clips download fully
  and the pipeline can read them. The pipeline also waits until a file
  has stopped changing (`VP_STABLE_SECONDS`) before touching it, so
  partially-synced files are never processed.
- Progress is tracked in `<output-dir>/.processed.json` — a clip is
  processed once, even across restarts. Re-upload a changed file with
  the same name and it will be processed again.
- Originals are never modified or deleted.

## Troubleshooting

- **Text overlays missing** — no usable font was found; set `VP_FONT`
  to a font file, e.g. `C:\Windows\Fonts\arialbd.ttf`.
- **First run fails downloading auto-editor's binary** — it fetches
  from GitHub once; check your network/proxy and retry.
- **A clip failed** — the error is logged and the pipeline moves on;
  fix the file (or options) and touch/re-copy it to retry.
