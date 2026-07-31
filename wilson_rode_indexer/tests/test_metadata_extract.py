"""Tests for email-header parsing, date parsing and document classification."""

from __future__ import annotations

from datetime import date

import pytest

from src.metadata_extract import (
    CONF_HIGH,
    CONF_LOW,
    CONF_MEDIUM,
    CONF_UNCERTAIN,
    DOC_UNKNOWN,
    DocumentClassifier,
    EmailParser,
    extract_case_number,
    extract_court,
    extract_custodian,
    extract_invoice_fields,
    find_attachment_references,
    parse_date,
    split_attachments,
    split_recipients,
)


class TestDateParsing:
    """Deterministic date parsing."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Dated 2019-03-04 by the parties", date(2019, 3, 4)),
            ("March 4, 2019", date(2019, 3, 4)),
            ("Mar. 4, 2019", date(2019, 3, 4)),
            ("Sept 15, 2020", date(2020, 9, 15)),
            ("3/4/2019", date(2019, 3, 4)),
            ("12-25-2018", date(2018, 12, 25)),
        ],
    )
    def test_parses_common_formats(self, text, expected):
        assert parse_date(text).value == expected

    def test_iso_format_is_high_confidence(self):
        assert parse_date("2019-03-04").confidence == CONF_HIGH

    def test_slash_format_is_medium_confidence(self):
        """US month/day ordering is an assumption, so confidence is reduced."""
        assert parse_date("3/4/2019").confidence == CONF_MEDIUM

    def test_two_digit_year_is_low_confidence(self):
        result = parse_date("3/4/19")
        assert result.value == date(2019, 3, 4)
        assert result.confidence == CONF_LOW

    def test_rejects_dates_outside_the_window(self):
        assert parse_date("1/2/1850", min_year=1990, max_year=2035).value is None

    def test_empty_text_is_uncertain(self):
        result = parse_date("")
        assert result.value is None and result.confidence == CONF_UNCERTAIN

    def test_does_not_invent_a_date(self):
        assert parse_date("no date at all here, only words").value is None


class TestRecipientSplitting:
    """Recipient list handling."""

    def test_splits_on_semicolons(self):
        assert split_recipients("a@x.com; b@y.com") == ["a@x.com", "b@y.com"]

    def test_splits_on_commas(self):
        assert split_recipients("a@x.com, b@y.com") == ["a@x.com", "b@y.com"]

    def test_keeps_quoted_display_names_intact(self):
        result = split_recipients('"Wilson, John" <jw@x.com>; "Rode, Pat" <pr@y.com>')
        assert len(result) == 2
        assert "Wilson, John" in result[0]

    def test_does_not_split_inside_angle_brackets(self):
        assert len(split_recipients("John <jw@x.com>")) == 1

    def test_drops_outlook_noise(self):
        assert split_recipients("John Wilson (E-mail)") == ["John Wilson"]

    def test_empty_input(self):
        assert split_recipients("") == []
        assert split_recipients("   ") == []


class TestEmailParsing:
    """Outlook-, Gmail- and Vault-style header blocks."""

    def test_parses_a_simple_outlook_header(self):
        parser = EmailParser()
        result = parser.parse(
            "From: John Wilson <jwilson@example.com>\n"
            "Sent: Monday, March 4, 2019 9:15 AM\n"
            "To: Patrick Rode <prode@example.com>\n"
            "Cc: Legal <legal@example.com>\n"
            "Subject: Commission agreement\n\n"
            "Body text follows."
        )
        assert result.top is not None
        assert "John Wilson" in result.top.sender
        assert result.top.subject == "Commission agreement"
        assert len(result.top.to) == 1
        assert len(result.top.cc) == 1
        assert result.top.sent_date == date(2019, 3, 4)
        assert result.confidence == CONF_HIGH

    def test_top_level_header_wins_over_quoted_headers(self):
        """The current message's headers must not be confused with the chain's."""
        parser = EmailParser()
        result = parser.parse(
            "From: Newest Sender <new@example.com>\n"
            "Sent: March 10, 2019\n"
            "To: Someone <someone@example.com>\n"
            "Subject: RE: Original topic\n\n"
            "Latest reply.\n\n"
            "-----Original Message-----\n"
            "From: Older Sender <old@example.com>\n"
            "Sent: March 4, 2019\n"
            "To: Newest Sender <new@example.com>\n"
            "Subject: Original topic\n\n"
            "Older body."
        )
        assert "Newest Sender" in result.top.sender
        assert result.top.sent_date == date(2019, 3, 10)

    def test_counts_embedded_messages(self):
        parser = EmailParser()
        result = parser.parse(
            "From: A <a@x.com>\nSent: March 10, 2019\nTo: B <b@x.com>\n"
            "Subject: Topic\n\nReply.\n\n"
            "-----Original Message-----\n"
            "From: B <b@x.com>\nSent: March 5, 2019\nTo: A <a@x.com>\n"
            "Subject: Topic\n\nFirst.\n\n"
            "-----Original Message-----\n"
            "From: C <c@x.com>\nSent: March 1, 2019\nTo: B <b@x.com>\n"
            "Subject: Topic\n\nOriginal."
        )
        assert result.embedded_count == 2
        assert result.earliest_date == date(2019, 3, 1)
        assert result.latest_date == date(2019, 3, 10)

    def test_parses_gmail_style_date_header(self):
        parser = EmailParser()
        result = parser.parse(
            "From: A <a@x.com>\nDate: March 4, 2019\nTo: B <b@x.com>\n"
            "Subject: Hello\n\nBody."
        )
        assert result.top.sent_date == date(2019, 3, 4)

    def test_parses_attachments_header(self):
        parser = EmailParser()
        result = parser.parse(
            "From: A <a@x.com>\nSent: March 4, 2019\nTo: B <b@x.com>\n"
            "Subject: Docs\nAttachments: Agreement.pdf; Exhibit_37.xlsx\n\nBody."
        )
        assert result.top.attachments == ["Agreement.pdf", "Exhibit_37.xlsx"]

    def test_non_email_text_yields_nothing(self):
        parser = EmailParser()
        result = parser.parse("This is an ordinary paragraph of prose.")
        assert result.top is None
        assert result.embedded_count == 0

    def test_handles_empty_input(self):
        assert EmailParser().parse("").top is None


class TestFieldExtractors:
    """Court, case number, invoice and custodian extraction."""

    def test_extracts_court_name(self):
        court = extract_court(
            "IN THE CIRCUIT COURT FOR THE COUNTY OF WAYNE\nSTATE OF MICHIGAN"
        )
        assert court is not None and "COURT" in court.upper()

    def test_extracts_case_number(self):
        assert extract_case_number("Case No. 2020-123456-CB") == "2020-123456-CB"

    def test_case_number_requires_a_digit(self):
        assert extract_case_number("Case No. ABCDEF") is None

    def test_extracts_invoice_amount(self):
        fields = extract_invoice_fields("INVOICE\nAmount Due: $12,345.67")
        assert fields["invoice_amount"] == "12345.67"

    def test_extracts_vendor_from_letterhead(self):
        fields = extract_invoice_fields(
            "Acme Consulting LLC\n123 Main Street\nINVOICE\nAmount Due: $100.00"
        )
        assert fields["vendor"] == "Acme Consulting LLC"

    def test_custodian_only_when_shown(self):
        name, source = extract_custodian("Custodian: John Wilson")
        assert name == "John Wilson"
        assert source == "observed_on_page"

    def test_custodian_is_never_invented(self):
        """A custodian is never inferred from participants or folder names."""
        assert extract_custodian("From: John Wilson <jw@x.com>") == (None, None)

    def test_finds_attachment_references_in_body(self):
        names = find_attachment_references("Please see Agreement_Draft.pdf attached.")
        assert "Agreement_Draft.pdf" in names

    def test_split_attachments_handles_plain_list(self):
        assert split_attachments("a.pdf; b.docx") == ["a.pdf", "b.docx"]


class TestClassification:
    """Rule-based document-type classification."""

    def test_classifies_an_email(self, config):
        classifier = DocumentClassifier(config)
        doc_type, confidence, _ = classifier.classify(
            "From: a@x.com\nSent: March 4, 2019\nTo: b@x.com\nSubject: Hi\n\nBody."
        )
        assert doc_type in ("email", "email_chain")
        assert confidence > 0

    def test_classifies_a_pleading(self, config):
        classifier = DocumentClassifier(config)
        doc_type, _confidence, _ = classifier.classify(
            "IN THE CIRCUIT COURT FOR THE COUNTY OF WAYNE\n"
            "STATE OF MICHIGAN\nCase No. 2020-1\n"
            "Plaintiff v. Defendant\nANSWER\nAFFIRMATIVE DEFENSE\n"
            "PROOF OF SERVICE"
        )
        assert doc_type in ("court_pleading", "court_order")

    def test_classifies_a_contract(self, config):
        classifier = DocumentClassifier(config)
        doc_type, _confidence, _ = classifier.classify(
            "COMMISSION AGREEMENT\nWHEREAS the parties agree\n"
            "NOW THEREFORE\nIN WITNESS WHEREOF"
        )
        assert doc_type == "contract"

    def test_empty_text_is_blank_not_unknown(self, config):
        classifier = DocumentClassifier(config)
        doc_type, confidence, _ = classifier.classify("")
        assert doc_type == "blank_or_separator"
        assert confidence == 1.0

    def test_unrecognised_text_is_unknown_not_guessed(self, config):
        classifier = DocumentClassifier(config)
        doc_type, _confidence, _ = classifier.classify("qqq zzz wwww")
        assert doc_type == DOC_UNKNOWN
