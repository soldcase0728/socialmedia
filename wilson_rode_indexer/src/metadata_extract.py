"""Phase 3 -- derived review metadata from extracted text.

Everything here is deterministic: regular expressions and rule-based parsing.
No external language model, no network call, no hosted service.

The values produced are **derived review metadata**.  They are not native
metadata, not a load file, and not a substitute for one.  Each value carries a
confidence and, where meaningful, a source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .config import Config
from .logging_setup import get_logger

log = get_logger("metadata")

# ---------------------------------------------------------------------------
# confidence vocabulary
# ---------------------------------------------------------------------------
CONF_HIGH = "high"
CONF_MEDIUM = "medium"
CONF_LOW = "low"
CONF_UNCERTAIN = "uncertain"

DOC_UNKNOWN = "unknown"
DOC_BLANK = "blank_or_separator"

_EMAIL_ADDRESS_RE = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+")
_ANGLE_ADDRESS_RE = re.compile(r"<([^>]+)>")

_CASE_NUMBER_RE = re.compile(
    r"\b(?:Case|Cause|Civil Action|Docket|File)\s*(?:No\.?|Number|#)\s*[:.]?\s*"
    r"([A-Z0-9][A-Z0-9\-/. ]{3,28}[A-Z0-9])",
    re.IGNORECASE,
)
_COURT_RE = re.compile(
    r"((?:IN THE\s+)?(?:UNITED STATES\s+)?(?:[A-Z][A-Za-z.'`-]+\s+){0,6}"
    r"(?:DISTRICT|CIRCUIT|SUPERIOR|SUPREME|APPEALS?|APPELLATE|PROBATE|BANKRUPTCY|"
    r"COUNTY)\s+COURT(?:\s+(?:OF|FOR)\s+(?:THE\s+)?[A-Z][A-Za-z.'`-]+"
    r"(?:\s+[A-Z][A-Za-z.'`-]+){0,4})?)",
    re.IGNORECASE,
)
_INVOICE_NUMBER_RE = re.compile(
    r"\bInvoice\s*(?:No\.?|Number|#)\s*[:.]?\s*([A-Za-z0-9\-/]{2,24})", re.IGNORECASE
)
_AMOUNT_RE = re.compile(
    r"(?:Total(?:\s+Due)?|Amount\s+Due|Balance\s+Due|Please\s+Remit)\s*[:.]?\s*"
    r"\$?\s*([0-9][0-9,]*(?:\.[0-9]{2})?)",
    re.IGNORECASE,
)
_FILE_EXTENSIONS = (
    r"pdf|docx?|xlsx?|pptx?|msg|eml|txt|csv|rtf|jpe?g|png|tiff?|zip"
)
#: Strict form: no spaces.  Used on body text, where a filename sits inside a
#: sentence and a space-tolerant pattern would swallow the preceding words.
_ATTACHMENT_NAME_RE = re.compile(
    rf"(?<![\w.\-])([\w][\w\-().,&'+]{{0,80}}\.(?:{_FILE_EXTENSIONS}))\b",
    re.IGNORECASE,
)
#: Space-tolerant form.  Used only on an ``Attachments:`` header value, where
#: the whole field is a filename list and spaces belong to the names.
_ATTACHMENT_HEADER_RE = re.compile(
    rf"(?<![\w.\-])([\w][\w \-().,&'+]{{0,80}}\.(?:{_FILE_EXTENSIONS}))\b",
    re.IGNORECASE,
)
_FILING_PARTY_RE = re.compile(
    r"\b(Plaintiff(?:s|'s|s')?|Defendant(?:s|'s|s')?|Appellant(?:s|'s|s')?|"
    r"Appellee(?:s|'s|s')?|Petitioner(?:s|'s|s')?|Respondent(?:s|'s|s')?)\b",
    re.IGNORECASE,
)

# Date patterns, ordered from most to least specific.
_DATE_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (
        re.compile(
            r"\b(January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
            re.IGNORECASE,
        ),
        "mdy_name",
    ),
    (
        re.compile(
            r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+"
            r"(\d{1,2}),?\s+(\d{4})\b",
            re.IGNORECASE,
        ),
        "mdy_abbr",
    ),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "mdy_slash"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b"), "mdy_slash2"),
    (re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b"), "mdy_dash"),
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------
@dataclass
class ParsedDate:
    """A date parsed from text, with its provenance."""

    value: Optional[date]
    raw: Optional[str]
    confidence: str = CONF_UNCERTAIN
    source: Optional[str] = None

    @property
    def iso(self) -> Optional[str]:
        """ISO-8601 form, or ``None`` if nothing was parsed."""
        return self.value.isoformat() if self.value else None


def parse_date(
    text: str, *, min_year: int = 1990, max_year: int = 2035
) -> ParsedDate:
    """Parse the first plausible date from ``text``.

    Ambiguous two-digit years and out-of-window values are rejected rather
    than guessed, because a wrong date in a review index is worse than a
    missing one.  Slash-format dates are read as US month/day/year, which is
    the convention throughout this production; the result is reported as
    ``medium`` confidence to record that the assumption was made.
    """
    if not text:
        return ParsedDate(None, None, CONF_UNCERTAIN)

    for pattern, kind in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group(0)
        try:
            parsed, confidence = _interpret(match, kind)
        except (ValueError, KeyError):
            continue
        if parsed is None:
            continue
        if not (min_year <= parsed.year <= max_year):
            continue
        return ParsedDate(parsed, raw, confidence, kind)

    # Last resort: dateutil, which is permissive.  Anything it returns is
    # reported as low confidence.
    try:
        from dateutil import parser as dateutil_parser

        candidate = dateutil_parser.parse(text[:200], fuzzy=True, default=datetime(2000, 1, 1))
        if min_year <= candidate.year <= max_year:
            return ParsedDate(candidate.date(), text[:60].strip(), CONF_LOW, "dateutil")
    except Exception:
        pass
    return ParsedDate(None, None, CONF_UNCERTAIN)


def _interpret(match: re.Match, kind: str) -> Tuple[Optional[date], str]:
    """Convert a regex match into a ``date`` plus a confidence level."""
    groups = match.groups()
    if kind == "ymd":
        return date(int(groups[0]), int(groups[1]), int(groups[2])), CONF_HIGH
    if kind in ("mdy_name", "mdy_abbr"):
        month = _MONTHS[groups[0].lower().rstrip(".")]
        return date(int(groups[2]), month, int(groups[1])), CONF_HIGH
    if kind == "mdy_slash":
        return date(int(groups[2]), int(groups[0]), int(groups[1])), CONF_MEDIUM
    if kind == "mdy_dash":
        return date(int(groups[2]), int(groups[0]), int(groups[1])), CONF_MEDIUM
    if kind == "mdy_slash2":
        year = int(groups[2])
        year += 2000 if year < 50 else 1900
        return date(year, int(groups[0]), int(groups[1])), CONF_LOW
    return None, CONF_UNCERTAIN


# ---------------------------------------------------------------------------
# email parsing
# ---------------------------------------------------------------------------
@dataclass
class EmailMessage:
    """One message's headers within a document."""

    sender: Optional[str] = None
    sent: Optional[str] = None
    sent_date: Optional[date] = None
    to: List[str] = field(default_factory=list)
    cc: List[str] = field(default_factory=list)
    bcc: List[str] = field(default_factory=list)
    subject: Optional[str] = None
    attachments: List[str] = field(default_factory=list)
    start_offset: int = 0

    @property
    def is_populated(self) -> bool:
        """Whether enough headers were found to call this a message."""
        return bool(self.sender or self.to or self.subject or self.sent)


@dataclass
class EmailParseResult:
    """Top-level message plus the chain beneath it."""

    top: Optional[EmailMessage] = None
    embedded_count: int = 0
    earliest_date: Optional[date] = None
    latest_date: Optional[date] = None
    all_messages: List[EmailMessage] = field(default_factory=list)
    confidence: str = CONF_UNCERTAIN


class EmailParser:
    """Recognises Outlook-, Gmail- and Google Vault-style header blocks.

    The parser distinguishes the *current* message's header block from headers
    quoted inside a chain.  The rule is positional: the first header block in
    reading order is the top-level message; every subsequent block belongs to
    a prior, quoted message.  Blocks introduced by an explicit separator
    (``----- Original Message -----``, ``On ... wrote:``) are always treated as
    quoted.
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        labels = (config.get("email", "header_labels") if config else None) or {}
        self.labels = {
            "from": labels.get("from", ["From", "Sender"]),
            "sent": labels.get("sent", ["Sent", "Date"]),
            "to": labels.get("to", ["To"]),
            "cc": labels.get("cc", ["Cc", "CC"]),
            "bcc": labels.get("bcc", ["Bcc", "BCC"]),
            "subject": labels.get("subject", ["Subject", "Subj"]),
            "attachments": labels.get("attachments", ["Attachments", "Attachment"]),
        }
        self.delimiter = (
            config.get("email", "recipient_delimiter", default="; ") if config else "; "
        )
        self.max_messages = int(
            config.get("email", "max_chain_messages", default=60) if config else 60
        )
        separators = (config.get("email", "chain_separators") if config else None) or [
            r"^-{2,}\s*Original Message\s*-{2,}",
            r"^_{5,}\s*$",
            r"^On .{5,120} wrote:\s*$",
            r"^-{2,}\s*Forwarded message\s*-{2,}",
        ]
        self._separator_res = [
            re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in separators
            if not pattern.startswith("^From:")
        ]
        self._min_year = int(config.get("dates", "min_year", default=1990) if config else 1990)
        self._max_year = int(config.get("dates", "max_year", default=2035) if config else 2035)
        self._field_res = {
            field_name: re.compile(
                r"^[ \t>]*(?:" + "|".join(re.escape(l) for l in label_list) + r")\s*:\s*(.*)$",
                re.IGNORECASE,
            )
            for field_name, label_list in self.labels.items()
        }

    # ------------------------------------------------------------------
    def parse(self, text: str) -> EmailParseResult:
        """Parse ``text`` into a top-level message plus embedded messages."""
        result = EmailParseResult()
        if not text:
            return result

        lines = text.splitlines()
        blocks = self._find_header_blocks(lines)
        if not blocks:
            return result

        separator_offsets = self._separator_offsets(text, lines)

        messages: List[EmailMessage] = []
        for block in blocks[: self.max_messages]:
            message = self._parse_block(lines, block)
            if message.is_populated:
                messages.append(message)

        if not messages:
            return result

        result.all_messages = messages
        # The top-level message is the first header block that is not preceded
        # by a chain separator.
        top_index = 0
        for index, message in enumerate(messages):
            if not any(offset < message.start_offset for offset in separator_offsets):
                top_index = index
                break
        else:
            top_index = 0
        result.top = messages[top_index]
        result.embedded_count = max(0, len(messages) - 1)

        dates = [m.sent_date for m in messages if m.sent_date]
        if dates:
            result.earliest_date = min(dates)
            result.latest_date = max(dates)

        populated = sum(
            1 for value in (result.top.sender, result.top.to, result.top.subject,
                            result.top.sent) if value
        )
        result.confidence = (
            CONF_HIGH if populated >= 3 else CONF_MEDIUM if populated == 2 else CONF_LOW
        )
        return result

    # ------------------------------------------------------------------
    def _find_header_blocks(self, lines: Sequence[str]) -> List[Tuple[int, int]]:
        """Locate contiguous header blocks as ``(start_line, end_line)`` pairs."""
        blocks: List[Tuple[int, int]] = []
        index = 0
        while index < len(lines):
            if self._is_header_line(lines[index], ("from", "sent", "to", "subject")):
                start = index
                end = index
                blanks = 0
                probe = index
                while probe < len(lines):
                    line = lines[probe]
                    if self._is_header_line(line, tuple(self.labels)):
                        end = probe
                        blanks = 0
                    elif not line.strip():
                        blanks += 1
                        if blanks >= 2:
                            break
                    elif probe > end + 1:
                        break
                    probe += 1
                blocks.append((start, end))
                index = end + 1
            else:
                index += 1
        return blocks

    def _is_header_line(self, line: str, fields: Sequence[str]) -> bool:
        """Whether ``line`` starts one of the given header fields."""
        return any(self._field_res[name].match(line) for name in fields)

    def _separator_offsets(self, text: str, lines: Sequence[str]) -> List[int]:
        """Line indices at which an explicit chain separator appears."""
        offsets: List[int] = []
        for index, line in enumerate(lines):
            if any(pattern.match(line) for pattern in self._separator_res):
                offsets.append(index)
        return offsets

    def _parse_block(self, lines: Sequence[str], block: Tuple[int, int]) -> EmailMessage:
        """Parse one header block into an :class:`EmailMessage`."""
        start, end = block
        message = EmailMessage(start_offset=start)
        current_field: Optional[str] = None
        buffer: Dict[str, List[str]] = {}

        for index in range(start, min(end + 1, len(lines))):
            line = lines[index]
            matched = False
            for name, pattern in self._field_res.items():
                match = pattern.match(line)
                if match:
                    current_field = name
                    buffer.setdefault(name, []).append(match.group(1).strip())
                    matched = True
                    break
            if not matched and current_field and line.strip() and not line[:1].isupper():
                # Continuation of a wrapped recipient list.
                buffer.setdefault(current_field, []).append(line.strip())

        message.sender = _first_value(buffer.get("from"))
        message.sent = _first_value(buffer.get("sent"))
        if message.sent:
            parsed = parse_date(message.sent, min_year=self._min_year,
                                max_year=self._max_year)
            message.sent_date = parsed.value
        message.subject = _first_value(buffer.get("subject"))
        message.to = split_recipients(" ".join(buffer.get("to", [])))
        message.cc = split_recipients(" ".join(buffer.get("cc", [])))
        message.bcc = split_recipients(" ".join(buffer.get("bcc", [])))
        message.attachments = split_attachments(" ".join(buffer.get("attachments", [])))
        return message

    def join(self, values: Sequence[str]) -> Optional[str]:
        """Join recipients with the configured delimiter."""
        return self.delimiter.join(values) if values else None


def _first_value(values: Optional[Sequence[str]]) -> Optional[str]:
    """Return the first non-empty entry from ``values``."""
    for value in values or []:
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return None


def split_recipients(value: str) -> List[str]:
    """Split a recipient string into individual recipients.

    Handles the common forms: comma- and semicolon-separated lists, quoted
    display names containing commas, and ``Name <addr@example.com>``.
    """
    if not value or not value.strip():
        return []
    parts: List[str] = []
    current: List[str] = []
    in_quotes = False
    in_angle = False
    for char in value:
        if char == '"':
            in_quotes = not in_quotes
        elif char == "<":
            in_angle = True
        elif char == ">":
            in_angle = False
        if char in ";," and not in_quotes and not in_angle:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))

    cleaned: List[str] = []
    for part in parts:
        text = part.strip().strip('"').strip()
        if not text:
            continue
        # Drop trailing Outlook noise such as "(E-mail)".
        text = re.sub(r"\s*\((?:E-?mail|SMTP)\)\s*$", "", text, flags=re.IGNORECASE)
        if text and text.lower() not in {"none", "n/a", "-"}:
            cleaned.append(text)
    return cleaned


def split_attachments(value: str) -> List[str]:
    """Extract attachment filenames from an ``Attachments:`` header value."""
    if not value:
        return []
    # A header value is entirely filenames, so spaces inside a name are safe.
    names = [m.group(1).strip() for m in _ATTACHMENT_HEADER_RE.finditer(value)]
    if names:
        return _dedupe(names)
    return _dedupe([p.strip() for p in re.split(r"[;,]", value) if p.strip()])


def find_attachment_references(text: str, limit: int = 40) -> List[str]:
    """Find filenames referenced anywhere in the document text.

    Uses the strict, space-free pattern: in running prose a space-tolerant
    match would absorb the words preceding the filename.
    """
    return _dedupe(
        [m.group(1).strip() for m in _ATTACHMENT_NAME_RE.finditer(text or "")]
    )[:limit]


def _dedupe(values: Iterable[str]) -> List[str]:
    """Order-preserving de-duplication, case-insensitive."""
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def extract_addresses(text: str) -> List[str]:
    """Return e-mail addresses appearing in ``text``."""
    return _dedupe(_EMAIL_ADDRESS_RE.findall(text or ""))


# ---------------------------------------------------------------------------
# document-type classification
# ---------------------------------------------------------------------------
class DocumentClassifier:
    """Rule-based document-type classifier.

    Each configured type owns a weight and a list of regular expressions.  A
    type's raw score is ``weight * (matched_patterns / total_patterns)``; the
    winner is reported with a normalised confidence in ``[0, 1]``.  Because
    the rules live in ``config.yaml``, a reviewer can inspect exactly why a
    document was classified the way it was.
    """

    def __init__(self, config: Config) -> None:
        rules = config.get("classification", "rules") or {}
        self.rules: Dict[str, Tuple[float, List[re.Pattern]]] = {}
        for name, spec in rules.items():
            patterns = [
                re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                for pattern in (spec or {}).get("patterns", [])
            ]
            if patterns:
                self.rules[name] = (float((spec or {}).get("weight", 1.0)), patterns)
        self.min_confidence = float(
            config.get("classification", "min_confidence", default=0.25)
        )

    def classify(self, text: str) -> Tuple[str, float, List[str]]:
        """Classify ``text``.

        Returns
        -------
        tuple
            ``(document_type, confidence, matched_rule_names)``.  When no rule
            reaches ``min_confidence`` the type is ``unknown`` -- the
            classifier never guesses to fill a cell.
        """
        if not text or not text.strip():
            return DOC_BLANK, 1.0, ["empty text"]

        scores: Dict[str, float] = {}
        matches: Dict[str, int] = {}
        for name, (weight, patterns) in self.rules.items():
            hit = sum(1 for pattern in patterns if pattern.search(text))
            if hit:
                scores[name] = weight * (hit / len(patterns))
                matches[name] = hit

        if not scores:
            return DOC_UNKNOWN, 0.0, []

        best = max(scores, key=lambda k: scores[k])
        total = sum(scores.values()) or 1.0
        confidence = round(scores[best] / total, 3)

        # An email chain is a specialisation of an email; prefer the chain
        # label when both fired.
        if "email_chain" in scores and best == "email" and scores["email_chain"] > 0:
            best = "email_chain"
            confidence = round(scores["email_chain"] / total, 3)

        if confidence < self.min_confidence:
            return DOC_UNKNOWN, confidence, sorted(matches, key=lambda k: -scores[k])[:3]
        return best, confidence, sorted(matches, key=lambda k: -scores[k])[:3]


# ---------------------------------------------------------------------------
# field extractors
# ---------------------------------------------------------------------------
def extract_court(text: str) -> Optional[str]:
    """Return the court name appearing in ``text``, if any."""
    match = _COURT_RE.search(text or "")
    if not match:
        return None
    court = re.sub(r"\s+", " ", match.group(1)).strip(" ,.")
    court = re.sub(r"^IN THE\s+", "", court, flags=re.IGNORECASE)
    return court[:160] if len(court) > 8 else None


def extract_case_number(text: str) -> Optional[str]:
    """Return the case/docket number appearing in ``text``, if any."""
    match = _CASE_NUMBER_RE.search(text or "")
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip(" .,;")
    return value if any(ch.isdigit() for ch in value) else None


def extract_filing_party(text: str) -> Optional[str]:
    """Return the apparent filing party, based on the first party word used."""
    match = _FILING_PARTY_RE.search(text or "")
    return match.group(1).title() if match else None


def extract_invoice_fields(text: str) -> Dict[str, Optional[str]]:
    """Return invoice number, amount and vendor when the text looks like one."""
    out: Dict[str, Optional[str]] = {
        "invoice_number": None, "invoice_amount": None, "vendor": None
    }
    if not text:
        return out
    number = _INVOICE_NUMBER_RE.search(text)
    if number:
        out["invoice_number"] = number.group(1).strip()
    amount = _AMOUNT_RE.search(text)
    if amount:
        out["invoice_amount"] = amount.group(1).replace(",", "")
    out["vendor"] = _guess_vendor(text)
    return out


def _guess_vendor(text: str) -> Optional[str]:
    """Guess a vendor from the first line that looks like a company name.

    Only the first few lines are considered, and the result is deliberately
    conservative: an invoice's letterhead is normally the first non-empty
    line.  A wrong vendor is worse than a blank cell, so anything ambiguous
    returns ``None``.
    """
    for line in (text or "").splitlines()[:6]:
        candidate = line.strip()
        if not (4 <= len(candidate) <= 80):
            continue
        if _EMAIL_ADDRESS_RE.search(candidate) or candidate.lower().startswith("invoice"):
            continue
        if re.search(r"\b(?:LLC|L\.L\.C\.|Inc\.?|Corp\.?|Company|Co\.|PLLC|PC|LLP|"
                     r"Associates|Group|Partners)\b", candidate, re.IGNORECASE):
            return candidate
    return None


def extract_title(text: str, document_type: str) -> Optional[str]:
    """Derive a document title from the first substantive line.

    For pleadings this is normally the caption line; for other types it is the
    first line long enough to be meaningful.  The value is a *derived* title,
    not a native document property.
    """
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    if document_type in ("court_pleading", "court_order", "expert_report", "contract"):
        for line in lines[:60]:
            upper_ratio = sum(1 for ch in line if ch.isupper()) / max(1, len(line))
            if 8 <= len(line) <= 120 and upper_ratio > 0.6 and any(
                ch.isalpha() for ch in line
            ):
                return line[:200]
    for line in lines[:12]:
        if 8 <= len(line) <= 200 and not _EMAIL_ADDRESS_RE.search(line):
            return line[:200]
    return lines[0][:200]


def extract_custodian(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(custodian, source)`` only when a custodian is actually shown.

    Production sets sometimes stamp ``Custodian: <name>`` on the page.  When no
    such marking exists this returns ``(None, None)``: a custodian is never
    inferred from a folder name, an email participant, or anything else.
    """
    match = re.search(
        r"\bCustodian\s*[:\-]\s*([A-Za-z][A-Za-z.,'` \-]{2,60})", text or "",
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(" .,"), "observed_on_page"
    return None, None


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------
@dataclass
class DerivedMetadata:
    """The full derived-metadata record for one document."""

    document_type: str = DOC_UNKNOWN
    doc_type_confidence: float = 0.0
    document_date: Optional[str] = None
    date_confidence: str = CONF_UNCERTAIN
    date_source: Optional[str] = None
    email_sent_date: Optional[str] = None
    email_from: Optional[str] = None
    email_to: Optional[str] = None
    email_cc: Optional[str] = None
    email_bcc: Optional[str] = None
    email_subject: Optional[str] = None
    embedded_message_count: int = 0
    earliest_message_date: Optional[str] = None
    latest_message_date: Optional[str] = None
    author: Optional[str] = None
    title: Optional[str] = None
    court_name: Optional[str] = None
    case_number: Optional[str] = None
    filing_date: Optional[str] = None
    filing_party: Optional[str] = None
    invoice_date: Optional[str] = None
    vendor: Optional[str] = None
    invoice_amount: Optional[str] = None
    attachment_names: Optional[str] = None
    custodian: Optional[str] = None
    custodian_source: Optional[str] = None
    extraction_confidence: str = CONF_UNCERTAIN
    manual_review_required: bool = False
    processing_notes: List[str] = field(default_factory=list)

    def notes_string(self) -> Optional[str]:
        """Join processing notes into a single cell value."""
        return "; ".join(self.processing_notes) if self.processing_notes else None


def derive_metadata(
    text: str,
    *,
    config: Config,
    classifier: DocumentClassifier,
    email_parser: EmailParser,
    page_count: Optional[int] = None,
) -> DerivedMetadata:
    """Derive review metadata from a document's sampled text.

    Parameters
    ----------
    text:
        Concatenated text of the sampled pages (normally the first three pages
        and the last page).
    config, classifier, email_parser:
        Configuration and the deterministic parsers.
    page_count:
        Total pages, used only for the manual-review heuristics.

    Returns
    -------
    DerivedMetadata
        Fields the parsers could actually support.  Anything unsupported is
        left ``None`` and the record is flagged for manual review; no value is
        ever invented to fill a column.
    """
    metadata = DerivedMetadata()
    min_year = int(config.get("dates", "min_year", default=1990))
    max_year = int(config.get("dates", "max_year", default=2035))

    if not text or not text.strip():
        metadata.document_type = DOC_BLANK
        metadata.doc_type_confidence = 1.0
        metadata.extraction_confidence = CONF_LOW
        metadata.manual_review_required = True
        metadata.processing_notes.append(
            "no extractable text; classification based on absence of text only"
        )
        return metadata

    doc_type, confidence, matched = classifier.classify(text)
    metadata.document_type = doc_type
    metadata.doc_type_confidence = confidence
    if matched:
        metadata.processing_notes.append("type rules matched: " + ", ".join(matched))

    email_result = email_parser.parse(text)
    if email_result.top is not None:
        top = email_result.top
        metadata.email_from = top.sender
        metadata.email_to = email_parser.join(top.to)
        metadata.email_cc = email_parser.join(top.cc)
        metadata.email_bcc = email_parser.join(top.bcc)
        metadata.email_subject = top.subject
        metadata.email_sent_date = top.sent_date.isoformat() if top.sent_date else None
        metadata.embedded_message_count = email_result.embedded_count
        metadata.earliest_message_date = (
            email_result.earliest_date.isoformat() if email_result.earliest_date else None
        )
        metadata.latest_message_date = (
            email_result.latest_date.isoformat() if email_result.latest_date else None
        )
        metadata.author = top.sender
        if top.attachments:
            metadata.attachment_names = "; ".join(top.attachments)
        if email_result.embedded_count > 0 and metadata.document_type == "email":
            metadata.document_type = "email_chain"
            metadata.processing_notes.append(
                f"{email_result.embedded_count} embedded prior message(s) detected"
            )

    if not metadata.attachment_names:
        referenced = find_attachment_references(text)
        if referenced:
            metadata.attachment_names = "; ".join(referenced[:20])
            metadata.processing_notes.append(
                "attachment names taken from filenames referenced in text (inferred)"
            )

    metadata.title = extract_title(text, metadata.document_type)
    metadata.court_name = extract_court(text)
    metadata.case_number = extract_case_number(text)
    if metadata.court_name or metadata.case_number:
        metadata.filing_party = extract_filing_party(text)

    if metadata.document_type in ("invoice", "financial_record"):
        invoice = extract_invoice_fields(text)
        metadata.vendor = invoice["vendor"]
        metadata.invoice_amount = invoice["invoice_amount"]

    metadata.custodian, metadata.custodian_source = extract_custodian(text)

    # Document date: prefer the email sent date, else the first parsed date.
    if metadata.email_sent_date:
        metadata.document_date = metadata.email_sent_date
        metadata.date_confidence = CONF_HIGH
        metadata.date_source = "email Sent header"
    else:
        parsed = parse_date(text[:4000], min_year=min_year, max_year=max_year)
        metadata.document_date = parsed.iso
        metadata.date_confidence = parsed.confidence
        metadata.date_source = f"text pattern ({parsed.source})" if parsed.source else None

    if metadata.document_type in ("court_pleading", "court_order"):
        metadata.filing_date = metadata.document_date
    if metadata.document_type == "invoice":
        metadata.invoice_date = metadata.document_date

    metadata.extraction_confidence = _score_extraction(metadata, len(text))
    metadata.manual_review_required = _needs_manual_review(metadata, page_count, len(text))
    return metadata


def _score_extraction(metadata: DerivedMetadata, text_length: int) -> str:
    """Grade how much of the record the parsers could actually support."""
    populated = sum(
        1
        for value in (
            metadata.document_date, metadata.email_from, metadata.email_subject,
            metadata.title, metadata.court_name, metadata.case_number,
        )
        if value
    )
    if metadata.doc_type_confidence >= 0.5 and populated >= 3 and text_length > 400:
        return CONF_HIGH
    if metadata.doc_type_confidence >= 0.3 and populated >= 2:
        return CONF_MEDIUM
    if populated >= 1:
        return CONF_LOW
    return CONF_UNCERTAIN


def _needs_manual_review(
    metadata: DerivedMetadata, page_count: Optional[int], text_length: int
) -> bool:
    """Flag records a human should look at before relying on them."""
    if metadata.document_type == DOC_UNKNOWN:
        return True
    if metadata.extraction_confidence in (CONF_LOW, CONF_UNCERTAIN):
        return True
    if metadata.doc_type_confidence < 0.35:
        return True
    if page_count and page_count > 25 and text_length < 500:
        return True
    if not metadata.document_date:
        return True
    return False
