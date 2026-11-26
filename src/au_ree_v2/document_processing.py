"""Shared, hash-bound document readers for observational research."""

from collections import Counter, OrderedDict
from pathlib import Path
import re

import pymupdf
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .pdf_extract import DOCUMENT_VERSION, _native_tables, extract_page, readable
from .store import filehash


VERSION = "pdf-document-processing-v1"
SHA256 = re.compile(r"[0-9a-f]{64}")


class DocumentUnavailable(ValueError):
    """The supplied document could not be read as the pinned PDF edition."""


class PdfDocument:
    """Cache the parser views of a single verified PDF for its open lifetime."""

    def __init__(self, path, sha256, counts):
        self.path = path
        self.sha256 = sha256
        self.backend_version = pymupdf.VersionBind
        self._counts = counts
        self._views = {}
        self._native = None
        self._pdf = pymupdf.open(path)

    def __len__(self):
        return len(self._pdf)

    def close(self):
        self._pdf.close()

    def _view(self, page, kind, read):
        if type(page) is not int or not 1 <= page <= len(self):
            raise ValueError("Physical page out of range")
        key = (page, kind)
        if key not in self._views:
            self._counts[kind if isinstance(kind, str) else kind[0]] += 1
            self._views[key] = read(self._pdf[page - 1])
        else:
            self._counts["cached_views"] += 1
        return self._views[key]

    def text(self, page, *, positioned=False):
        mode = "positioned_text" if positioned else "content_order_text"
        return self._view(page, mode, lambda obj: obj.get_text(sort=positioned))

    def blocks(self, page):
        return self._view(page, "text_blocks", lambda obj: tuple(obj.get_text("blocks")))

    def words(self, page):
        return self._view(page, "words", lambda obj: tuple(obj.get_text("words")))

    def bounds(self, page):
        return self._view(page, "page_bounds", lambda obj: tuple(obj.rect))

    def tables(self, page):
        """Native grid, column headers and cell coordinates from the existing parser."""
        result = self._view(page, "native_tables", lambda _: self._read_tables(page))
        return result["tables"], result["error"]

    def _read_tables(self, page):
        try:
            return {"tables": _native_tables(self._pdf, page, None, True, DOCUMENT_VERSION), "error": None}
        except (ValueError, RuntimeError) as exc:
            return {"tables": [], "error": type(exc).__name__}

    def native_text(self, page):
        """The independent Pypdf text view used in evidence verification."""
        return self._view(page, "pypdf_text", lambda _: self._read_native(page))

    def _read_native(self, page):
        try:
            if self._native is None:
                self._native = PdfReader(self.path)
            return self._native.pages[page - 1].extract_text() or "", None
        except (OSError, ValueError, IndexError, PdfReadError) as exc:
            return "", type(exc).__name__

    def evidence(self, page, *, tessdata=None):
        """Expose alternate text and optionally use the existing selective OCR fallback."""
        native, native_error = self.native_text(page)
        positioned = self.text(page, positioned=True)
        alternatives = {"PYPDF_NATIVE": native, "MUPDF_POSITIONED": positioned}
        selected = "PYPDF_NATIVE" if readable(native) else "MUPDF_POSITIONED"
        model_sha = None
        if not readable(alternatives[selected]) and tessdata is not None:
            tessdata = Path(tessdata).resolve()
            ocr = self._view(page, ("ocr", tessdata),
                             lambda _: extract_page(self.path, page, tessdata))
            selected = ocr["method"]
            alternatives[selected] = ocr["text"]
            model_sha = ocr["model_sha256"]
        text = alternatives[selected]
        differs = len({" ".join(view.split()) for view in alternatives.values() if view}) > 1
        status = "UNREADABLE"
        if readable(text):
            status = "PARSER_DISAGREEMENT_REQUIRES_REVIEW" if differs else "EXTRACTED_REQUIRES_SCOPE_VALIDATION"
        return {
            "source_sha256": self.sha256, "physical_page": page, "version": VERSION,
            "backend_version": self.backend_version, "table_parser_version": DOCUMENT_VERSION,
            "text": text, "method": selected, "status": status, "model_sha256": model_sha,
            "text_views": alternatives, "native_error": native_error,
        }


class PdfDocumentCache:
    """Bounded cache of opened PDFs and derived views for one extraction run."""

    def __init__(self, assets, *, max_documents=8):
        if type(max_documents) is not int or max_documents < 1:
            raise ValueError("max_documents must be a positive integer")
        self.assets = Path(assets)
        self.max_documents = max_documents
        self._documents = OrderedDict()
        self.counts = Counter()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        for document in self._documents.values():
            document.close()
        self._documents.clear()

    def open(self, sha256):
        if not isinstance(sha256, str) or not SHA256.fullmatch(sha256):
            raise DocumentUnavailable("INVALID_SOURCE_SHA256")
        if sha256 in self._documents:
            self.counts["cached_documents"] += 1
            self._documents.move_to_end(sha256)
            return self._documents[sha256]
        path = self.assets / sha256
        if not path.is_file():
            path = path.with_suffix(".pdf")
        try:
            if not path.is_file():
                raise DocumentUnavailable("PDF_BYTES_UNAVAILABLE")
            self.counts["verified_hashes"] += 1
            if filehash(path) != sha256:
                raise DocumentUnavailable("SOURCE_HASH_MISMATCH")
            document = PdfDocument(path, sha256, self.counts)
        except (OSError, pymupdf.FileDataError) as exc:
            raise DocumentUnavailable("PDF_BYTES_UNREADABLE") from exc
        self.counts["opened_documents"] += 1
        self._documents[sha256] = document
        if len(self._documents) > self.max_documents:
            _, evicted = self._documents.popitem(last=False)
            evicted.close()
        return document
