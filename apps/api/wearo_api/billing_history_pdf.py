from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

PAGE_WIDTH = 842
PAGE_HEIGHT = 595
ROWS_PER_PAGE = 25


def _pdf_text(value: object, limit: int = 36) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "replace").decode("ascii")
    compact = " ".join(ascii_text.split())
    shortened = compact if len(compact) <= limit else f"{compact[: limit - 3]}..."
    return shortened.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _date_text(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime("%d %b %Y %H:%M UTC")
    return _pdf_text(value, 24)


def _money_text(currency: object, amount_minor: object) -> str:
    try:
        amount = int(str(amount_minor)) / 100
    except (TypeError, ValueError):
        amount = 0
    return f"{_pdf_text(currency or 'INR', 5)} {amount:,.2f}"


def _text_command(x: int, y: int, text: object, *, size: int = 9, bold: bool = False) -> str:
    font = "F2" if bold else "F1"
    return f"BT /{font} {size} Tf 1 0 0 1 {x} {y} Tm ({_pdf_text(text)}) Tj ET"


def _page_stream(
    rows: list[Mapping[str, object]], page: int, page_count: int, generated_at: datetime
) -> bytes:
    commands = [
        _text_command(36, 558, "Wearo.ai", size=17, bold=True),
        _text_command(36, 538, "Complete billing history", size=12, bold=True),
        _text_command(
            580,
            558,
            f"Generated {generated_at.astimezone(UTC):%d %b %Y %H:%M UTC}",
            size=8,
        ),
        "0.45 G 36 524 m 806 524 l S",
    ]
    columns = (
        (36, "DATE"),
        (166, "PACKAGE"),
        (341, "AMOUNT"),
        (436, "TOKENS"),
        (516, "STATUS"),
        (601, "RECEIPT"),
    )
    for x, label in columns:
        commands.append(_text_command(x, 505, label, size=8, bold=True))
    commands.append("0.75 G 36 496 m 806 496 l S")

    if not rows:
        commands.append(_text_command(36, 466, "No payment records are available."))
    for index, row in enumerate(rows):
        y = 474 - index * 17
        values = (
            (36, _date_text(row.get("paid_at") or row.get("created_at")), 26),
            (166, row.get("package_name") or "Try-on credits", 28),
            (341, _money_text(row.get("currency"), row.get("amount_minor")), 18),
            (436, row.get("tokens") or 0, 12),
            (516, row.get("state") or "PENDING", 14),
            (601, row.get("receipt_number") or "-", 29),
        )
        for x, value, limit in values:
            commands.append(_text_command(x, y, _pdf_text(value, limit), size=8))
        commands.append(f"0.9 G 36 {y - 6} m 806 {y - 6} l S")

    commands.extend(
        [
            _text_command(36, 28, "Amounts include the tax recorded with each payment.", size=7),
            _text_command(750, 28, f"Page {page} of {page_count}", size=7, bold=True),
        ]
    )
    return "\n".join(commands).encode("ascii")


def billing_history_pdf(
    rows: Iterable[Mapping[str, object]], *, generated_at: datetime | None = None
) -> bytes:
    items = list(rows)
    pages = [items[index : index + ROWS_PER_PAGE] for index in range(0, len(items), ROWS_PER_PAGE)]
    if not pages:
        pages = [[]]
    now = generated_at or datetime.now(UTC)

    objects: list[bytes] = [b""]

    def add(value: bytes = b"") -> int:
        objects.append(value)
        return len(objects) - 1

    catalog_id = add()
    pages_id = add()
    regular_font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    bold_font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    page_ids: list[int] = []
    for page_number, rows_on_page in enumerate(pages, start=1):
        stream = _page_stream(rows_on_page, page_number, len(pages), now)
        content_id = add(
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
        page_id = add(
            (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} "
                f"{PAGE_HEIGHT}] /Resources << /Font << /F1 {regular_font_id} 0 R "
                f"/F2 {bold_font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    objects[catalog_id] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()

    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, value in enumerate(objects[1:], start=1):
        offsets.append(len(document))
        document.extend(f"{object_id} 0 obj\n".encode())
        document.extend(value)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects)}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        (
            f"trailer\n<< /Size {len(objects)} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(document)
