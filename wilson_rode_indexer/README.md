# Wilson-Rode Derived Document Index

A fully local, read-only document indexing and triage tool for a large
Bates-numbered legal document production.

Everything it produces is **derived review metadata**: values calculated or
inferred by software from the produced PDF files themselves. Nothing it
produces is original or native document metadata, and it never claims
otherwise.

---

## Table of contents

1. [What this is, and what it is not](#1-what-this-is-and-what-it-is-not)
2. [Safety guarantees](#2-safety-guarantees)
3. [Installation on macOS](#3-installation-on-macos)
4. [Finding your Google Drive folder](#4-finding-your-google-drive-folder)
5. [Running each phase](#5-running-each-phase)
6. [Resuming a stopped run](#6-resuming-a-stopped-run)
7. [Interpreting each report](#7-interpreting-each-report)
8. [Derived versus native metadata](#8-derived-versus-native-metadata)
9. [Privacy limitations](#9-privacy-limitations)
10. [Changing issue tags](#10-changing-issue-tags)
11. [Re-running only failed files](#11-re-running-only-failed-files)
12. [Updating reports after new files are added](#12-updating-reports-after-new-files-are-added)
13. [Troubleshooting](#13-troubleshooting)
14. [Quality control](#14-quality-control)
15. [Project layout](#15-project-layout)

---

## 1. What this is, and what it is not

**It is** a local triage tool. It inventories a production, audits which pages
actually carry readable text, derives review metadata (dates, senders,
subjects, document types, Bates ranges), detects duplicates, infers possible
email/attachment families, applies configurable keyword screening tags, and
produces Excel workbooks that let a human decide what to read first.

**It is not** a review platform, a privilege log, a relevance determination,
or a substitute for reading the documents. In particular:

- **Issue tags are keyword hits.** `STATUTE_OF_FRAUDS` on a document means the
  phrase appeared in the text. It is not a legal conclusion.
- **Priority scores order work.** A high score means configured screening
  terms clustered in one document. It does not indicate malpractice, breach,
  liability, relevance, or privilege.
- **Family relationships are inferences.** This production has no load file,
  so no authoritative family data exists. Every inferred relationship carries
  the reason it was inferred and a confidence level.
- **No accuracy claim is made.** Accuracy is only knowable once you complete
  the quality-control sample (section 14).

---

## 2. Safety guarantees

These are enforced in code and covered by tests in `tests/test_safety.py`.

| Guarantee | How it is enforced |
| --- | --- |
| The source folder is never renamed, moved, altered, annotated, OCRed in place, combined, or deleted | `assert_read_only()` guards every write path; a test hashes every source file before and after a full Phase 1 run and asserts nothing changed |
| All generated files go to a separate sibling folder | `Config.resolve_output_folder()` refuses any output path inside the source |
| Nothing is uploaded anywhere | No network code exists in this package. All PDF work, OCR, hashing, indexing and classification run locally |
| Document text never reaches the terminal | A `ContentGuard` logging filter is installed on **every** handler and replaces any record that looks like document content with a placeholder |
| Document text never reaches a report | Text is written only to the SQLite `page_text` table and its FTS5 index. No report column is bound to a text field |
| Every operation is auditable | Every phase writes to the `audit_log` table and to a rotating log file |
| Runs are resumable | SQLite is the authoritative state. A file is re-processed only if its size or modification timestamp changed |

Verify them yourself before trusting the tool:

```bash
./scripts/run_tests.sh
```

All tests use synthetic PDFs generated in a temporary directory. No test reads
a real document.

---

## 3. Installation on macOS

### Quick path

```bash
cd wilson_rode_indexer
chmod +x scripts/*.sh
./scripts/setup_mac.sh
```

`setup_mac.sh` creates `.venv`, installs the Python dependencies, reports on
Homebrew / Tesseract / OCRmyPDF availability, and runs the test suite. It
**never installs OCR tooling and never runs OCR**; it only tells you what is
present.

### Manual path

```bash
# Python 3.12 recommended (3.10+ required)
brew install python@3.12

cd wilson_rode_indexer
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -m pytest tests -q
```

### Optional OCR tooling

OCR is **off by default** and is not needed for Phase 1 at all. Phase 2 only
uses it for pages that have no usable text layer *and* do contain meaningful
image content.

```bash
brew install tesseract
brew install ocrmypdf
```

Then either set `ocr.enabled: true` in `config.yaml` or pass `--ocr` on a
Phase 2 run. OCR always writes its derivative to
`Wilson_Rode_Derived_Index/ocr_cache/`; the source PDF is copied to a
temporary file first, so an OCR-engine bug cannot write back into the
production.

### Full Disk Access

macOS blocks access to `~/Library/CloudStorage` unless your terminal has Full
Disk Access. If the tool cannot see the folder:

> System Settings → Privacy & Security → Full Disk Access → add Terminal (or
> iTerm) → **restart the terminal**

### Check the environment

```bash
source .venv/bin/activate
python -m src.cli doctor --check-ocr
```

---

## 4. Finding your Google Drive folder

```bash
python -m src.cli locate
```

This searches `~/Library/CloudStorage`, `~/Google Drive`, `~/Documents`,
`~/Desktop` and `/Volumes` (configurable under `paths.search_roots`) for a
folder named exactly `Wilson-Rode File`, and prints each match with a file
count, PDF count and total size so you can tell a real production from an
empty shortcut. **It modifies nothing.**

Google Drive paths typically look like:

```
/Users/YOU/Library/CloudStorage/GoogleDrive-you@example.com/My Drive/Wilson-Rode File
```

If several folders match, pick one and either pass it with `--source` or set
it in `config.yaml`:

```yaml
paths:
  source_folder: "/Users/YOU/Library/CloudStorage/GoogleDrive-ACCOUNT/My Drive/Wilson-Rode File"
```

### Make the files available offline first

Google Drive's streaming mode leaves stub placeholder files on disk until
something opens them. The tool detects placeholders, retries with backoff, and
logs them **rather than treating them as corrupt** — but it is far faster to
download them up front:

> In Finder, right-click the `Wilson-Rode File` folder → **Make available
> offline** → wait for the download to complete.

---

## 5. Running each phase

### Phase 1 — structural inventory (start here)

```bash
./scripts/run_phase1_mac.sh "/Users/YOU/Library/CloudStorage/GoogleDrive-ACCOUNT/My Drive/Wilson-Rode File"
```

**Quote the path** — it contains spaces and a hyphen.

Phase 1 reads structural facts only: filename, path, size, timestamps,
SHA-256, PDF page count, encryption state, readability. It does **not** read
substantive content, extract text, or run OCR.

The script refuses to run when:

1. the source folder does not exist;
2. the source folder is writable by the application;
3. the source and output folders are the same (or the output is nested inside
   the source);
4. the source folder contains no PDFs.

Check 2 is the strictest. The application never writes to the source, but an
operating-system guarantee beats a promise in code. Make the folder read-only
first:

```bash
chmod -R a-w "/Users/YOU/.../Wilson-Rode File"
# to restore later:
chmod -R u+w "/Users/YOU/.../Wilson-Rode File"
```

Google Drive may reset permissions on re-sync, and some Drive configurations
ignore `chmod` entirely. If you cannot make the folder read-only, re-run with
`--allow-writable-source` to acknowledge that and proceed. That flag only
suppresses the pre-flight check; the in-code read-only guard stays active.

Do **not** run the script with `sudo`. Root bypasses permission bits, so check
2 can never pass for it.

**Phase 1 stops when it finishes.** Read `Phase_1_Summary.md` before going on.

### Phase 2 — text and page-condition audit

Always pilot first:

```bash
./scripts/run_phase2.sh                    # pilot: ~200 stratified documents
```

The pilot samples across low and high Bates ranges, small and large files,
single- and multi-page PDFs, suspected searchable / image-only / blank files,
exact duplicates, and malformed filenames. Any stratum the collection cannot
fill is reported, never silently skipped.

Review `Phase_2_Pilot_Summary.md`, then:

```bash
./scripts/run_phase2.sh --full             # whole production
./scripts/run_phase2.sh --full --ocr       # with local OCR
```

The CLI refuses `--full` until a pilot has been recorded.

### Phase 3 — derived review metadata

```bash
python -m src.cli phase3
```

Derives Bates ranges, dates, email headers, document types, court and case
numbers, invoice fields, duplicates, families, issue tags and priority scores,
then writes workbooks 09–20.

### Everything at once

```bash
./scripts/run_full.sh              # Phase 1 + Phase 2 pilot, then stops
./scripts/run_full.sh --continue   # also Phase 2 full + Phase 3 + QC sample
```

---

## 6. Resuming a stopped run

Just re-run the same command.

SQLite is the authoritative state. Work is committed in batches
(`performance.checkpoint_every`, default 250), so an interruption — Ctrl-C,
a crash, a closed laptop — loses at most one batch. On restart:

- files already inventoried whose size and modification timestamp are
  unchanged are skipped;
- documents already extracted are skipped in Phase 2;
- documents that already have metadata are skipped in Phase 3.

```bash
python -m src.cli status            # what is done, what is left
python -m src.cli status --verbose  # plus per-phase statistics
```

To deliberately redo work, add `--force`.

---

## 7. Interpreting each report

Every workbook has three standard tabs: **Data Dictionary** (what each column
means and whether it is Observed, Calculated or Inferred), **Methodology and
Limitations**, and **Run Statistics**.

### Phase 1

| Report | What it tells you | Watch out for |
| --- | --- | --- |
| `01_File_Inventory.xlsx` / `.csv` | Every file: size, timestamps, hash, page count, flags. Clickable local links | `Created` is a **file-system** timestamp. On a synced Drive folder it usually reflects the sync, not authorship |
| `02_Bates_Structural_Report.xlsx` | Bates parsed from filenames, structural problems, preliminary gaps | Every Bates value here comes from a **filename**, not a page stamp |
| `03_Exact_Duplicate_Report.xlsx` | Byte-identical files grouped by SHA-256 | Reproducible: re-hash any two members to verify |
| `04_Unreadable_or_Corrupt_Files.xlsx` | Encrypted, corrupt and placeholder files | **Placeholders are not corrupt.** They are undownloaded Drive stubs |

**The single most important caveat in Phase 1:** filename-based Bates gaps are
*preliminary*. A five-page PDF named `WILSONRODE000010-null.pdf` occupies
Bates 000010–000014, but only 000010 appears in a filename — so 000011–000014
look like a "gap" while being perfectly present. Check the page-count
distribution: the more multi-page PDFs, the more spurious the gaps.

### Phase 2

| Report | What it tells you |
| --- | --- |
| `05_Page_Condition_Audit.xlsx` | Every page: condition, character/word counts, image coverage, Bates stamp read from the page. Includes a Condition Reference sheet |
| `06_Blank_and_Bates_Only_Candidates.xlsx` | Pages with no meaningful text, categorised as truly-blank / Bates-only / separator / failed-export / uncertain — each a **candidate** needing confirmation |
| `07_OCR_Required.xlsx` | Documents with pages lacking a text layer but holding image content |
| `08_Extraction_Failures.xlsx` | Documents that could not be fully read |

`uncertain` is used deliberately. It means the evidence did not support any
other category — it is not a guess.

### Phase 3

| Report | What it tells you |
| --- | --- |
| `09_Derived_Document_Index.xlsx` / `.csv` | The master index, one row per document, all 37 columns |
| `10_Bates_Gap_and_Overlap_Report.xlsx` | Gaps and overlaps across derived begin/end ranges |
| `11_Blank_and_Extraction_Failure_Report.xlsx` | Document-level roll-up of blank-heavy and failed documents |
| `12_Duplicate_Groups.xlsx` | All three duplicate passes with the relationship type |
| `13_Document_Family_Inferences.xlsx` | Possible parent/attachment links — **every row is an inference**, with its reason |
| `14_Issue_Tag_Index.xlsx` | Every tag hit with term, page and count |
| `15_Priority_Review_Queue.xlsx` | Whole production, priority-ordered |
| `16`–`20_*_Review_Queue.xlsx` | Tag-specific queues (John Wilson, statute of frauds, expert/damages, client file, insurance) |
| `Processing_Errors.xlsx` | Everything that did not complete cleanly |
| `Final_Run_Summary.md` | Aggregate narrative summary |

**Read the confidence columns.** `Bates Confidence` of `confirmed` means a
stamp was read off the page. `possible` usually means it came from the
filename and the end Bates was arithmetic. Those are very different claims.

### Searching

```bash
python -m src.cli search "statute NEAR frauds"
python -m src.cli search "lifetime OR perpetual"
```

Results are **locations only** — filename and page number. Document text is
never printed.

---

## 8. Derived versus native metadata

This distinction matters more than anything else in this tool.

**Native metadata** is what the producing party's system recorded: the actual
sender, the actual sent time, the actual custodian, the actual family
relationships. It normally arrives in a load file (DAT, OPT, CSV) alongside
the images. **This production did not include one.**

**Derived metadata** is what this tool reconstructs by reading the PDFs. When
the index says a document was sent by `John Wilson <jwilson@example.com>` on
`2019-03-04`, it means those strings were parsed out of text printed on the
page — not that the mail server recorded them.

Consequences worth internalising:

- A derived date can be the date printed in a letterhead, a fax banner, a
  quoted prior message, or a court stamp. The `Date Source` and
  `Date Confidence` columns say which.
- A derived `From` is whatever appeared after `From:`. In a forwarded chain
  that can be a quoted sender rather than the actual one — the parser works
  hard to distinguish them, and the embedded-message count tells you when a
  chain was present.
- **Custodian is only populated when a custodian is literally stamped on the
  page.** It is never inferred from a folder name or an email participant.
- Family relationships are inferred from Bates adjacency, attachment lists,
  dates and subjects. Bates adjacency is treated as a necessary condition
  (matching dates alone are far too weak), and each relationship states its
  reason.

Every workbook carries this notice on its Data Dictionary tab. Do not strip it
when circulating the reports.

---

## 9. Privacy limitations

**What the tool guarantees**

- No network calls. No external API, cloud OCR, hosted AI service, or remote
  database. Everything runs on your machine.
- No document text in the terminal (structurally filtered, not just avoided).
- No document text in any workbook or CSV.
- The source production is never modified.

**What it cannot guarantee — read this**

- **The derived index folder contains extracted text.**
  `wilson_rode_index.sqlite` holds full page text and an FTS5 search index.
  Treat that file with exactly the same care as the production itself. It is
  discoverable, it is unencrypted, and it should not be emailed or synced to a
  location the production would not be synced to.
- **The OCR cache contains full document images and text.** Same handling.
- **The log file** records filenames, paths and error messages. Filenames in
  this production are Bates numbers, so the log is low-sensitivity — but it is
  not nothing.
- **The workbooks contain derived metadata** — subjects, senders, dates,
  titles. That is often sensitive even without body text. Issue-tag context
  locators are withheld from Excel by default
  (`issue_tag_options.redact_context_in_excel: true`); turning that off puts
  short snippets of document text into the workbook. Think before you do.
- If the derived-index folder is created inside a synced Drive or Dropbox
  folder, **you will sync the extracted text to the cloud.** The tool cannot
  detect this for you. Put it on local disk.
- The tool does not encrypt anything at rest. Use FileVault.

---

## 10. Changing issue tags

Tags live in `config.yaml` under `issue_tags`. Edit freely:

```yaml
issue_tags:
  MY_NEW_TAG:
    - "some phrase"
    - "another phrase"

  STATUTE_OF_FRAUDS:
    - "statute of frauds"
    - "within one year"
    # ...
```

Matching options are under `issue_tag_options`:

| Option | Effect |
| --- | --- |
| `case_sensitive` | Default `false` |
| `whole_word` | Default `true` — stops `one year` firing inside `one yearbook` |
| `context_chars` | Length of the stored context locator |
| `redact_context_in_excel` | Default `true` — keeps locators out of the workbook |
| `max_hits_per_tag` | Cap on recorded hits per document/tag |

Multi-word terms match across flexible whitespace, so `statute of frauds`
matches text broken across a line.

After editing, re-tag without re-extracting:

```bash
python -m src.cli phase3 --force
```

This re-runs tagging, scoring, duplicates and families against the text
already in the database. It does not re-open a single PDF.

To change scoring, edit `priority.tag_weights`, `priority.keyword_bonus`,
`priority.participant_bonus` or `priority.date_windows`. Every component that
fires is written into the `Priority Score Explanation` column, so a score can
always be reconstructed by hand.

---

## 11. Re-running only failed files

```bash
python -m src.cli retry-failed --phase 2
```

This selects only files whose status is `error` or `cloud_placeholder`, or
whose extraction or OCR failed, and re-processes just those. Use `--phase 1`
to re-inventory them, `--phase 3` to re-derive metadata.

Typical workflow after fixing placeholders:

```bash
# 1. In Finder: right-click the folder -> Make available offline. Wait.
# 2. Re-inventory the stubs:
python -m src.cli retry-failed --phase 1
# 3. Extract the newly available documents:
python -m src.cli phase2 --full
# 4. Refresh the workbooks:
python -m src.cli reports
```

Check what is outstanding first with `Processing_Errors.xlsx` or:

```bash
python -m src.cli status
```

---

## 12. Updating reports after new files are added

The pipeline is incremental. When the producing party sends a supplemental
production into the same folder:

```bash
# 1. Inventory: existing files are skipped, new ones are picked up
./scripts/run_phase1_mac.sh "/Users/YOU/.../Wilson-Rode File"

# 2. Extract only the new documents
python -m src.cli phase2 --full

# 3. Derive metadata for the new documents
python -m src.cli phase3

# 4. Regenerate every workbook from the database
python -m src.cli reports
```

Notes:

- Steps 1–3 skip completed work automatically. Only new or changed files cost
  anything.
- Duplicate detection and family inference are **recomputed across the whole
  corpus** in step 3, because a new document can join an existing duplicate
  group or attach to an existing email. That is correct, and it is why step 3
  is not purely incremental.
- `python -m src.cli reports --phase 1` regenerates a single phase's
  workbooks.
- Re-run the QC sample after a material addition; the old accuracy figure does
  not automatically carry over.

---

## 13. Troubleshooting

**`No folder named 'Wilson-Rode File' was found`**
Google Drive may not be running, or the folder is not synced. Grant Full Disk
Access to your terminal (section 3) and check the path manually in Finder.

**`REFUSING TO RUN: The source folder is writable by this application`**
Expected. Run `chmod -R a-w "<source>"`, or pass `--allow-writable-source` to
acknowledge and proceed. Do not use `sudo` — root always trips this check.

**`REFUSING TO RUN: The source folder contains no PDF files`**
Usually undownloaded Drive placeholders. Make the folder available offline in
Finder, wait for the download, and re-run.

**Many files reported as cloud placeholders**
Same cause. They are logged, retried with backoff, and explicitly *not*
treated as corrupt. Download them and run
`python -m src.cli retry-failed --phase 1`.

**`Operation not permitted` reading `~/Library/CloudStorage`**
Full Disk Access, then restart the terminal.

**`ModuleNotFoundError: No module named 'fitz'`**
The virtual environment is not active, or dependencies are not installed:
```bash
source .venv/bin/activate && pip install -r requirements.txt
```

**`database is locked`**
Two runs are using the same derived-index folder. Stop one. The database uses
WAL with a 60-second busy timeout, so brief contention resolves itself.

**The run is very slow**
Reading tens of thousands of files through Drive's virtual file system is the
bottleneck, not CPU. Make everything available offline first. `workers` is set
conservatively (default 4) precisely because a synced volume punishes
aggressive parallelism — raising it can make things *slower*.

**Excel is slow to open a workbook**
Expected for very large productions. The CSV companion
(`09_Derived_Document_Index.csv`) loads faster and holds the same data.
Hyperlinks are capped at `reports.max_hyperlinks`; beyond that, paths remain
as plain text.

**Out of disk space**
The OCR cache is the usual culprit. Cap it with `ocr.max_cache_gb` (default
20 GiB). It can be deleted safely — it is a cache, and deleting it only means
OCR re-runs for those pages.

**`Phase 2 has not completed. Run ...` when starting Phase 3**
The phase gates are deliberate. Run the earlier phase, or check
`python -m src.cli status` to see where the pipeline actually is.

**A classification looks wrong**
Likely, in some fraction of cases — that is what the QC sample is for. Tune
`classification.rules` and re-run `python -m src.cli phase3 --force`. No PDF
is re-opened.

---

## 14. Quality control

```bash
python -m src.cli qc-sample
```

Generates `QC_Sample.xlsx` with a reproducible stratified sample (seed fixed
in `config.yaml`):

| Stratum | Default size |
| --- | ---: |
| High-priority documents | 50 |
| Low-priority documents | 50 |
| OCR documents | 25 |
| Blank-page candidates | 25 |
| Family inferences | 25 |
| Near-duplicate matches | 25 |

Each row states the specific question it was sampled to answer and leaves two
columns for you: a verdict (Yes / No / Partly) and notes.

**Then compute accuracy per stratum: correct ÷ reviewed.** Report that
measured figure. The tool deliberately makes no accuracy claim on its own, and
you should not make one on its behalf.

The low-priority stratum matters most. A document wrongly buried at low
priority is the costliest failure mode, because nothing else in the workflow
will surface it.

---

## 15. Project layout

```
wilson_rode_indexer/
├── README.md
├── config.yaml               # paths, regexes, thresholds, tags, weights
├── pyproject.toml
├── requirements.txt
├── src/
│   ├── cli.py                # command-line interface and phase gating
│   ├── config.py             # config loading, validation, path resolution
│   ├── database.py           # SQLite state, FTS5 index, audit log
│   ├── logging_setup.py      # structured logging + content guard
│   ├── inventory.py          # Phase 1: walk, hash, probe, read-only guard
│   ├── bates.py              # Bates parsing, ranges, gaps, overlaps
│   ├── pdf_extract.py        # Phase 2: text extraction, page conditions, OCR
│   ├── metadata_extract.py   # Phase 3: emails, dates, types, fields
│   ├── duplicates.py         # SHA-256, normalised text, SimHash + LSH
│   ├── issue_tags.py         # configurable keyword screening
│   ├── document_family.py    # parent/attachment inference
│   ├── priority.py           # transparent priority scoring
│   ├── pipeline.py           # Phase 2 and Phase 3 drivers
│   ├── reports.py            # workbook writer and house conventions
│   ├── phase1_reports.py     # reports 01-04 + Phase_1_Summary.md
│   ├── phase2_reports.py     # reports 05-08 + Phase_2_Pilot_Summary.md
│   ├── phase3_reports.py     # reports 09-20 + Final_Run_Summary.md
│   ├── qc.py                 # quality-control sampling
│   └── version.py
├── tests/                    # 174 tests, synthetic fixtures only
│   ├── conftest.py
│   ├── test_bates.py
│   ├── test_duplicates.py
│   ├── test_issue_tags.py
│   ├── test_metadata_extract.py
│   ├── test_pipeline.py
│   └── test_safety.py
├── scripts/
│   ├── setup_mac.sh          # venv + deps + dependency checks + tests
│   ├── run_phase1_mac.sh     # Phase 1 with pre-flight safety checks
│   ├── run_phase1.sh
│   ├── run_phase2.sh
│   ├── run_full.sh
│   └── run_tests.sh
└── logs/
```

Output, written to `Wilson_Rode_Derived_Index/` beside the source:

```
Wilson_Rode_Derived_Index/
├── 01_File_Inventory.xlsx / .csv
├── 02_Bates_Structural_Report.xlsx
├── 03_Exact_Duplicate_Report.xlsx
├── 04_Unreadable_or_Corrupt_Files.xlsx
├── 05_Page_Condition_Audit.xlsx
├── 06_Blank_and_Bates_Only_Candidates.xlsx
├── 07_OCR_Required.xlsx
├── 08_Extraction_Failures.xlsx
├── 09_Derived_Document_Index.xlsx / .csv
├── 10_Bates_Gap_and_Overlap_Report.xlsx
├── 11_Blank_and_Extraction_Failure_Report.xlsx
├── 12_Duplicate_Groups.xlsx
├── 13_Document_Family_Inferences.xlsx
├── 14_Issue_Tag_Index.xlsx
├── 15_Priority_Review_Queue.xlsx
├── 16_John_Wilson_Review_Queue.xlsx
├── 17_Statute_of_Frauds_Review_Queue.xlsx
├── 18_Expert_and_Damages_Review_Queue.xlsx
├── 19_Client_File_Review_Queue.xlsx
├── 20_Insurance_Review_Queue.xlsx
├── Phase_1_Summary.md
├── Phase_2_Pilot_Summary.md
├── Final_Run_Summary.md
├── Processing_Errors.xlsx
├── QC_Sample.xlsx
├── wilson_rode_index.sqlite    # CONTAINS EXTRACTED TEXT - handle carefully
├── ocr_cache/                  # CONTAINS DOCUMENT IMAGES - handle carefully
└── logs/
```

---

## Version

`wilson_rode_indexer` 1.0.0. The application version is written into every
database row, so records produced by different releases stay distinguishable.
