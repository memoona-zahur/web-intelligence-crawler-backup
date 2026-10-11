"""Read a pasted list or a CSV and insert new websites (CR-A01, A02, A04, A06-A08, A10, A11).

A row is skipped when:
- it is not a real website address (the reason is stored in import_issues)
- the same website is already in the database
- the same website appears twice in this import
One bad line never stops the import (ISS-04). A 60,000-line list is checked in batches, not one query per line (ISS-17).
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crawler.guard import is_safe_import_target
from app.domains import domain_key
from app.models import ImportIssue, Job, Website
from app.normalize import explain_invalid, normalize_website, redact_credentials

URL_COLUMNS = {"url", "original_url", "website", "website_url", "link"}
ID_COLUMNS = {"id", "record_id", "external_id", "source_id", "source_record_id", "ref", "reference"}
SOURCE_COLUMNS = {"source", "batch", "source_batch", "dataset"}
CHUNK = 500


@dataclass
class ImportResult:
    added: int = 0
    duplicates: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    job_id: int | None = None


def _csv_rows(text: str):
    """Rows of a simple CSV as dicts, or None when the text is a plain list of URLs."""
    first_line = text.splitlines()[0]
    try:
        headers = [part.strip().lower() for part in next(csv.reader([first_line]))]
    except (csv.Error, StopIteration):
        return None, []
    url_column = next((name for name in headers if name in URL_COLUMNS), None)
    if url_column is None:
        return None, headers
    return url_column, headers


def _read(text: str) -> list[tuple[str, str, str]]:
    """[(raw_url, record_id, source)] in file order."""
    text = (text or "").strip()
    if not text:
        return []
    url_column, _headers = _csv_rows(text)
    out: list[tuple[str, str, str]] = []
    if url_column is not None:
        try:
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                lowered = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k is not None}
                value = lowered.get(url_column, "")
                if not value:
                    continue
                record_id = next((lowered[c] for c in ID_COLUMNS if lowered.get(c)), "")
                source = next((lowered[c] for c in SOURCE_COLUMNS if lowered.get(c)), "")
                out.append((value, record_id, source))
            return out
        except csv.Error:
            out = []  # fall through: treat as a plain list
    for line in text.splitlines():
        try:
            cells = next(csv.reader([line.strip()]), [])
            cell = cells[0].strip() if cells else ""   # a blank line gives no cells at all (this used to crash the whole import)
        except csv.Error:
            cell = line.strip()
        if cell:
            out.append((cell, "", ""))
    return out


def extract_urls(text: str) -> list[str]:
    """Pull website addresses out of plain lines or a simple CSV."""
    return [raw for raw, _id, _source in _read(text)]


def _record_meta(text: str) -> list[tuple[str, str]]:
    return [(record_id, source) for _raw, record_id, source in _read(text)]


def excel_to_text(data: bytes) -> str:
    """Turn the first worksheet of an .xlsx file into CSV text for extract_urls."""
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sheet = book.active
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if cell is None else str(cell).strip() for cell in row]
            if any(cells):
                writer.writerow(cells)
        return buffer.getvalue()
    finally:
        book.close()


def _existing(session: Session, normalized: list[str]) -> set[str]:
    found: set[str] = set()
    for start in range(0, len(normalized), CHUNK):
        chunk = normalized[start:start + CHUNK]
        found.update(session.scalars(select(Website.normalized_website).where(Website.normalized_website.in_(chunk))))
    return found


def import_urls(session: Session, text: str, source_batch: str | None = None, source_file: str | None = None) -> ImportResult:
    result = ImportResult()
    raw_urls = extract_urls(text)
    if not raw_urls:
        return result
    meta = _record_meta(text)

    batch_default = source_batch.strip() if source_batch and source_batch.strip() else None
    file_name = source_file.strip() if source_file and source_file.strip() else None
    job = Job(kind="import", status="queued", total=len(raw_urls), source_file=file_name or batch_default)
    session.add(job)
    session.flush()
    result.job_id = job.id

    # Pass 1: per-line decisions. Nothing here can stop the import.
    decided: list[tuple[int, str, str, str, str]] = []  # (line_no, raw, normalized, record_id, source)
    issues: list[ImportIssue] = []
    for index, raw in enumerate(raw_urls):
        record_id, source = meta[index] if index < len(meta) else ("", "")
        try:
            normalized = normalize_website(raw)
            safe = normalized is not None and is_safe_import_target(normalized)
        except Exception as exc:  # noqa: BLE001 - belt and braces: normalize_website itself never raises
            normalized, safe = None, False
            issues.append(ImportIssue(job_id=job.id, line_no=index + 1, raw=str(raw)[:2000], decision="invalid", reason=f"error: {type(exc).__name__}"))
            result.invalid.append(raw)
            continue
        if normalized is None or not safe:
            reason = explain_invalid(raw) if normalized is None else "not a public address"
            issues.append(ImportIssue(job_id=job.id, line_no=index + 1, raw=str(raw)[:2000], decision="invalid", reason=reason[:255]))
            result.invalid.append(raw)
            continue
        decided.append((index + 1, raw, normalized, record_id, source))

    # Pass 2: duplicates (in this import, then in the database - in batches).
    existing = _existing(session, list(dict.fromkeys(item[2] for item in decided)))
    seen: set[str] = set()
    new_rows: list[Website] = []
    for line_no, raw, normalized, record_id, source in decided:
        if normalized in seen or normalized in existing:
            result.duplicates.append(normalized)
            reason = "already in the database" if normalized in existing else "appears twice in this import"
            issues.append(ImportIssue(job_id=job.id, line_no=line_no, raw=str(raw)[:2000], decision="duplicate", reason=reason))
            seen.add(normalized)
            continue
        seen.add(normalized)
        new_rows.append(
            Website(
                original_url=redact_credentials(raw)[:2048],
                normalized_website=normalized,
                status="pending",
                source_batch=(source or batch_default),
                source_file=file_name,
                source_record_id=(record_id or None),
                domain_key=domain_key(normalized),
                job_id=job.id,
            )
        )
        result.added += 1
    for start in range(0, len(new_rows), CHUNK * 4):
        session.add_all(new_rows[start:start + CHUNK * 4])
        session.flush()
    session.add_all(issues)

    job.added = result.added
    job.duplicates = len(result.duplicates)
    job.invalid = len(result.invalid)
    job.status = "queued" if result.added else "completed"
    job.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.commit()
    return result
