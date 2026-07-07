"""
Extract plain text from an uploaded resume / cover letter.

The matcher only needs words, so we pull readable text out of PDF, Word (.docx),
or plain-text files. We never store more than the bytes the user gave us, and the
caller decides whether to keep the original file.
"""

from __future__ import annotations

import io
import logging
import re

logger = logging.getLogger("jobbot.resume")

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md", ".text")


def tidy_text(text: str) -> str:
    """Clean up PDF-extraction artifacts so the text reads like the document.

    pypdf often emits a newline-space-newline between every word and doubled
    spaces everywhere ("hardware  and  \\nsoftware,\\n \\nworking\\n ..."),
    which makes the stored resume hard for the AI (and humans) to read.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    # the word-per-line artifact: newline + spaces + newline mid-sentence
    text = re.sub(r"\n[ \t]+\n", " ", text)
    # doubled spaces/tabs -> one space; spaces before a newline -> newline
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    # never more than one blank line in a row
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(filename: str, data: bytes) -> str:
    """Return plain text from the uploaded file's bytes (best effort)."""
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf"):
            return tidy_text(_from_pdf(data))
        if name.endswith(".docx"):
            return tidy_text(_from_docx(data))
        # .txt / .md / unknown: treat as text
        return tidy_text(data.decode("utf-8", errors="ignore"))
    except Exception as exc:  # noqa: BLE001 — never let a bad file crash the app
        logger.warning("could not parse %s: %s", filename, exc)
        return ""


def _from_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(parts).strip()


def _from_docx(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs).strip()
