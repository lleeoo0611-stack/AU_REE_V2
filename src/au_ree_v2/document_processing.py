"""Shared, hash-bound document readers for observational research."""

from collections import Counter, OrderedDict
from functools import lru_cache
import hashlib
from pathlib import Path
import re

import pymupdf
import pypdf
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .derived_cache import code_fingerprint
from .pdf_extract import DOCUMENT_VERSION, _native_tables, extract_page, readable
from .store import digest


VERSION = "pdf-document-processing-v1"
SHA256 = re.compile(r"[0-9a-f]{64}")


class DocumentUnavailable(ValueError):
    """The supplied document could not be read as the pinned PDF edition."""


def _file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def ocr_model_sha(tessdata):
    """Use the model bytes rather than the installation location as their identity."""
    return _file_sha(Path(tessdata) / "eng.traineddata") if tessdata is not None else None


def _string(value):
    if not isinstance(value, str):
        raise ValueError("Expected PDF text")


def _array(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("Expected PDF geometry")


def _native_view(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or not isinstance(value[0], str):
        raise ValueError("Invalid independent text view")
    if value[1] is not None and not isinstance(value[1], str):
        raise ValueError("Invalid native parser disposition")


def _table_view(value):
    if not isinstance(value, dict) or not isinstance(value.get("tables"), list) or "error" not in value:
        raise ValueError("Invalid PDF table view")


def _page_count(value):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid physical page count")


class PdfDocument:
    """Cache verified PDF views and open the native document on demand."""

    def __init__(self, path, sha256, counts, cache=None):
        self.path = path
        self.sha256 = sha256
        self.backend_version = pymupdf.VersionBind
        self._counts = counts
        self._cache = cache
        self._views = {}
        self._native = None
        self._pdf = None
        if cache is None:
            self._open()
            self._length = len(self._pdf)
        else:
            self._length = self._derive(
                "page_count", None, lambda: len(self._open()), _page_count,
            )

    def _open(self):
        if self._pdf is None:
            try:
                self._pdf = pymupdf.open(self.path)
            except (OSError, pymupdf.FileDataError) as exc:
                raise DocumentUnavailable("PDF_BYTES_UNREADABLE") from exc
            self._counts["opened_documents"] += 1
        return self._pdf

    def __len__(self):
        return self._length

    def close(self):
        if self._pdf is not None:
            self._pdf.close()
            self._pdf = None

    def _derive(self, kind, page, read, validate):
        def build():
            self._counts[kind] += 1
            return read()

        if self._cache is None:
            return build()
        location = f"{self.sha256}:{page if page is not None else 0}:{kind}"
        return self._cache.compute(
            "pdf", location, {"page": page, "operation": kind, **pdf_view_spec(kind)},
            build, upstream={"source_snapshot": self.sha256}, validate=validate,
        )

    def _view(self, page, kind, read, validate, restore=None):
        self._validate_page(page)
        key = page, kind
        if key not in self._views:
            value = self._derive(kind, page, read, validate)
            self._views[key] = restore(value) if restore else value
        else:
            self._counts["cached_views"] += 1
        return self._views[key]

    def _validate_page(self, page):
        if type(page) is not int or not 1 <= page <= len(self):
            raise ValueError("Physical page out of range")

    def text(self, page, *, positioned=False):
        mode = "positioned_text" if positioned else "content_order_text"
        return self._view(page, mode, lambda: self._open()[page - 1].get_text(sort=positioned), _string)

    def blocks(self, page):
        return self._view(page, "text_blocks", lambda: self._open()[page - 1].get_text("blocks"),
                          _array, lambda value: tuple(map(tuple, value)))

    def words(self, page):
        return self._view(page, "words", lambda: self._open()[page - 1].get_text("words"),
                          _array, lambda value: tuple(map(tuple, value)))

    def bounds(self, page):
        return self._view(page, "page_bounds", lambda: tuple(self._open()[page - 1].rect), _array, tuple)

    def tables(self, page):
        """Native grid, column headers and cell coordinates from the existing parser."""
        result = self._view(page, "native_tables", lambda: self._read_tables(page), _table_view)
        if self._cache is not None and result["error"] is not None:
            self._cache.record("pdf", f"{self.sha256}:{page}:native_tables", "PARSER_FAILED",
                               reason=result["error"])
        return result["tables"], result["error"]

    def _read_tables(self, page):
        document = self._open()
        try:
            return {"tables": _native_tables(document, page, None, True, DOCUMENT_VERSION), "error": None}
        except (ValueError, RuntimeError) as exc:
            return {"tables": [], "error": type(exc).__name__}

    def native_text(self, page):
        """The independent Pypdf text view used in evidence verification."""
        return self._view(page, "pypdf_text", lambda: self._read_native(page), _native_view, tuple)

    def _read_native(self, page):
        try:
            if self._native is None:
                self._native = PdfReader(self.path)
                self._counts["opened_native_readers"] += 1
            return self._native.pages[page - 1].extract_text() or "", None
        except (OSError, ValueError, IndexError, PdfReadError) as exc:
            return "", type(exc).__name__

    def _ocr(self, page, tessdata, native, positioned):
        model_sha = ocr_model_sha(tessdata)
        key = page, "ocr", model_sha

        def validate(value):
            if (not isinstance(value, dict) or value.get("source_sha256") != self.sha256
                    or value.get("physical_page") != page or value.get("model_sha256") != model_sha
                    or not isinstance(value.get("text"), str)):
                raise ValueError("OCR output differs from source, page or model contract")

        def build():
            self._counts["ocr"] += 1
            result = extract_page(self.path, page, tessdata)
            validate(result)
            return result

        if key not in self._views:
            if self._cache is None:
                self._views[key] = build()
            else:
                self._views[key] = self._cache.compute(
                    "ocr", f"{self.sha256}:{page}", {"version": "pdf-page-v1", "page": page, "dpi": 200,
                    "clip": None, "language": "eng", "model_sha256": model_sha,
                    "backend": self.backend_version, "pypdf": pypdf.__version__,
                    "code": code_fingerprint(extract_page, readable)},
                    build, upstream={"source_snapshot": self.sha256, "native_text": digest(native),
                                     "positioned_text": digest(positioned)}, validate=validate,
                )
        else:
            self._counts["cached_views"] += 1
        return self._views[key]

    def evidence(self, page, *, tessdata=None):
        """Expose alternate text and optionally use the existing selective OCR fallback."""
        native, native_error = self.native_text(page)
        positioned = self.text(page, positioned=True)
        alternatives = {"PYPDF_NATIVE": native, "MUPDF_POSITIONED": positioned}
        selected = "PYPDF_NATIVE" if readable(native) else "MUPDF_POSITIONED"
        model_sha = None
        if not readable(alternatives[selected]) and tessdata is not None:
            ocr = self._ocr(page, Path(tessdata).resolve(), native, positioned)
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


@lru_cache
def pdf_view_spec(kind):
    """Dependencies for each view, also used by downstream extraction contracts."""
    readers = {
        "page_count": (PdfDocument.__init__, PdfDocument._open),
        "positioned_text": (PdfDocument.text,),
        "content_order_text": (PdfDocument.text,),
        "text_blocks": (PdfDocument.blocks,),
        "words": (PdfDocument.words,),
        "page_bounds": (PdfDocument.bounds,),
        "native_tables": (PdfDocument._read_tables, _native_tables),
        "pypdf_text": (PdfDocument._read_native,),
    }
    specification = {
        "format": VERSION,
        "code": code_fingerprint(PdfDocument._view, PdfDocument._derive, *readers[kind]),
        "backend": pypdf.__version__ if kind == "pypdf_text" else pymupdf.VersionBind,
    }
    if kind == "native_tables":
        specification["table_parser"] = DOCUMENT_VERSION
    return specification


class PdfDocumentCache:
    """Bounded reader cache with optional reusable views across executions."""

    def __init__(self, assets, *, max_documents=8, cache=None):
        if type(max_documents) is not int or max_documents < 1:
            raise ValueError("max_documents must be a positive integer")
        self.assets = Path(assets)
        self.cache = cache
        self.max_documents = max_documents
        self._documents = OrderedDict()
        self._verified_paths = {}
        self._unavailable = {}
        self.counts = Counter()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        for document in self._documents.values():
            document.close()
        self._documents.clear()
        self._verified_paths.clear()
        self._unavailable.clear()

    def verify(self, sha256):
        """Reconcile original bytes in this run even when derived results are present."""
        if not isinstance(sha256, str) or not SHA256.fullmatch(sha256):
            raise DocumentUnavailable("INVALID_SOURCE_SHA256")
        if sha256 in self._unavailable:
            raise DocumentUnavailable(self._unavailable[sha256])
        if sha256 not in self._verified_paths:
            path = self.assets / sha256
            if not path.is_file():
                path = path.with_suffix(".pdf")
            try:
                if not path.is_file():
                    raise DocumentUnavailable("PDF_BYTES_UNAVAILABLE")
                self.counts["verified_hashes"] += 1
                if _file_sha(path) != sha256:
                    raise DocumentUnavailable("SOURCE_HASH_MISMATCH")
                self._verified_paths[sha256] = path
            except DocumentUnavailable as exc:
                self._missing(sha256, str(exc))
                raise
            except OSError as exc:
                reason = "PDF_BYTES_UNREADABLE"
                self._missing(sha256, reason)
                raise DocumentUnavailable(reason) from exc
        return self._verified_paths[sha256]

    def _missing(self, sha256, reason):
        self._unavailable[sha256] = reason
        self.counts["missing_sources"] += 1
        if self.cache is not None:
            self.cache.record("pdf", sha256, "SOURCE_BLOCKED", reason=reason)

    def open(self, sha256):
        if isinstance(sha256, str) and sha256 in self._documents:
            self.counts["cached_documents"] += 1
            self._documents.move_to_end(sha256)
            return self._documents[sha256]
        path = self.verify(sha256)
        document = PdfDocument(path, sha256, self.counts, self.cache)
        self._documents[sha256] = document
        if len(self._documents) > self.max_documents:
            _, evicted = self._documents.popitem(last=False)
            evicted.close()
        return document
