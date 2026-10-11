"""ReportLab PDF Certificate Generator.

Generates professional landscape certificates using canvas drawing primitives.
Self-contained with vector graphics, decorative borders, and elegant typography.
"""

import io
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas


def draw_corner_ornament(
    c: canvas.Canvas, x: float, y: float, size: float = 16
) -> None:
    """Draw a small diamond corner ornament."""
    c.saveState()
    c.setFillColor(HexColor("#B8860B"))
    c.setStrokeColor(HexColor("#8B6508"))
    c.setLineWidth(1)
    p = c.beginPath()
    p.moveTo(x, y - size / 2)
    p.lineTo(x + size / 2, y)
    p.lineTo(x, y + size / 2)
    p.lineTo(x - size / 2, y)
    p.close()
    c.drawPath(p, fill=1, stroke=1)
    c.restoreState()


def _render_certificate_content(
    c: canvas.Canvas,
    recipient_name: str,
    title: str,
    organization: str,
    date_of_issue: str,
    width: float,
    height: float,
    signature_image_bytes: bytes | None = None,
) -> None:
    """Draw all graphical and typographic certificate elements onto canvas."""
    # --- Background Canvas ---
    c.setFillColor(HexColor("#FDFAF4"))  # Warm parchment/ivory tone
    c.rect(0, 0, width, height, fill=1, stroke=0)

    # --- Outer Decorative Borders ---
    c.setStrokeColor(HexColor("#B8860B"))  # Dark goldenrod
    c.setLineWidth(3.5)
    c.rect(26, 26, width - 52, height - 52, stroke=1, fill=0)

    c.setStrokeColor(HexColor("#DAA520"))  # Goldenrod inner thin border
    c.setLineWidth(1.0)
    c.rect(34, 34, width - 68, height - 68, stroke=1, fill=0)

    # Corner ornaments
    draw_corner_ornament(c, 34, 34)
    draw_corner_ornament(c, width - 34, 34)
    draw_corner_ornament(c, 34, height - 34)
    draw_corner_ornament(c, width - 34, height - 34)

    # --- Header Section: Organization Name ---
    max_org_width = width - 160
    org_size = 15
    while (
        c.stringWidth(organization.upper(), "Helvetica-Bold", org_size) > max_org_width
        and org_size > 9
    ):
        org_size -= 1
    c.setFillColor(HexColor("#1A1A2E"))  # Deep midnight navy
    c.setFont("Helvetica-Bold", org_size)
    c.drawCentredString(width / 2, height - 90, organization.upper())

    # --- Main Certificate Title ---
    c.setFont("Helvetica-Bold", 34)
    c.setFillColor(HexColor("#B8860B"))
    c.drawCentredString(width / 2, height - 150, "CERTIFICATE")

    c.setFont("Helvetica", 14)
    c.setFillColor(HexColor("#4A4A5A"))
    c.drawCentredString(width / 2, height - 176, "OF ACHIEVEMENT & RECOGNITION")

    # Thin decorative divider line
    c.setStrokeColor(HexColor("#DAA520"))
    c.setLineWidth(1)
    c.line(width / 2 - 120, height - 192, width / 2 + 120, height - 192)

    # --- Certification statement ---
    c.setFont("Helvetica", 13)
    c.setFillColor(HexColor("#333333"))
    c.drawCentredString(
        width / 2, height - 232, "This certificate is proudly presented to"
    )

    # --- Recipient Name (with dynamic font scaling for long names) ---
    max_name_width = width - 140
    name_size = 28
    while (
        c.stringWidth(recipient_name, "Helvetica-Bold", name_size) > max_name_width
        and name_size > 14
    ):
        name_size -= 2
    c.setFont("Helvetica-Bold", name_size)
    c.setFillColor(HexColor("#0F172A"))  # Slate black
    c.drawCentredString(width / 2, height - 280, recipient_name)

    # Dynamic underline beneath recipient name
    name_width = c.stringWidth(recipient_name, "Helvetica-Bold", name_size)
    line_padding = 24
    line_x1 = max(45.0, (width - name_width) / 2 - line_padding)
    line_x2 = min(width - 45.0, (width + name_width) / 2 + line_padding)
    c.setStrokeColor(HexColor("#B8860B"))
    c.setLineWidth(1.8)
    c.line(line_x1, height - 292, line_x2, height - 292)

    # --- Body / Course details ---
    c.setFont("Helvetica", 13)
    c.setFillColor(HexColor("#333333"))
    c.drawCentredString(
        width / 2,
        height - 332,
        "for successfully completing and fulfilling all requirements of",
    )

    max_title_width = width - 140
    title_size = 19
    while (
        c.stringWidth(title, "Helvetica-Bold", title_size) > max_title_width
        and title_size > 11
    ):
        title_size -= 1
    c.setFont("Helvetica-Bold", title_size)
    c.setFillColor(HexColor("#1A1A2E"))
    c.drawCentredString(width / 2, height - 364, title)

    # --- Date and Signatures Footer ---
    footer_y = 100

    # Date column on left
    c.setFont("Helvetica", 11)
    c.setFillColor(HexColor("#555555"))
    c.drawCentredString(width * 0.28, footer_y + 24, f"{date_of_issue}")
    c.setStrokeColor(HexColor("#888888"))
    c.setLineWidth(0.8)
    c.line(width * 0.28 - 70, footer_y + 12, width * 0.28 + 70, footer_y + 12)
    c.setFont("Helvetica", 9)
    c.drawCentredString(width * 0.28, footer_y - 2, "Date of Issuance")

    # Verified seal badge in center
    c.saveState()
    c.setFillColor(HexColor("#FFF7ED"))
    c.setStrokeColor(HexColor("#B8860B"))
    c.setLineWidth(1.5)
    c.circle(width / 2, footer_y + 15, 26, stroke=1, fill=1)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(HexColor("#B8860B"))
    c.drawCentredString(width / 2, footer_y + 18, "OFFICIAL")
    c.setFont("Helvetica", 7)
    c.drawCentredString(width / 2, footer_y + 8, "SEAL")
    c.restoreState()

    # Authorized Signature column on right
    c.setStrokeColor(HexColor("#888888"))
    c.setLineWidth(0.8)
    c.line(width * 0.72 - 70, footer_y + 12, width * 0.72 + 70, footer_y + 12)

    if signature_image_bytes:
        try:
            from reportlab.lib.utils import ImageReader

            img = ImageReader(io.BytesIO(signature_image_bytes))
            sig_w = 110
            sig_h = 36
            c.drawImage(
                img,
                width * 0.72 - (sig_w / 2),
                footer_y + 14,
                width=sig_w,
                height=sig_h,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(HexColor("#1A1A2E"))
            c.drawCentredString(width * 0.72, footer_y + 24, organization)
    else:
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(HexColor("#1A1A2E"))
        c.drawCentredString(width * 0.72, footer_y + 24, organization)

    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#555555"))
    c.drawCentredString(width * 0.72, footer_y - 2, "Authorized Signature")


def generate_certificate_bytes(
    recipient_name: str,
    title: str,
    organization: str,
    date_of_issue: str,
    signature_image_bytes: bytes | None = None,
) -> bytes:
    """Generate a single professional PDF certificate directly as bytes in memory.

    Args:
        recipient_name: Name of the recipient to appear on the certificate.
        title: Title of the course or event.
        organization: Name of the issuing organization.
        date_of_issue: Date string (YYYY-MM-DD format).

    Returns:
        Raw PDF document binary bytes.

    Raises:
        ValueError: If any required parameter is missing or empty.
    """
    if not recipient_name or not recipient_name.strip():
        raise ValueError("Recipient name cannot be empty")
    if not title or not title.strip():
        raise ValueError("Title cannot be empty")
    if not organization or not organization.strip():
        raise ValueError("Organization cannot be empty")
    if not date_of_issue or not date_of_issue.strip():
        raise ValueError("Date of issue cannot be empty")

    clean_name = recipient_name.strip()
    clean_title = title.strip()
    clean_org = organization.strip()
    clean_date = date_of_issue.strip()

    buf = io.BytesIO()
    page_size = landscape(letter)
    width, height = page_size

    c = canvas.Canvas(buf, pagesize=page_size)
    _render_certificate_content(
        c=c,
        recipient_name=clean_name,
        title=clean_title,
        organization=clean_org,
        date_of_issue=clean_date,
        width=width,
        height=height,
        signature_image_bytes=signature_image_bytes,
    )
    c.showPage()
    c.save()

    return buf.getvalue()


def generate_certificate(
    recipient_name: str,
    title: str,
    organization: str,
    date_of_issue: str,
    output_path: str,
    signature_image_bytes: bytes | None = None,
) -> str:
    """Generate a single professional PDF certificate and save it to disk."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    pdf_bytes = generate_certificate_bytes(
        recipient_name=recipient_name,
        title=title,
        organization=organization,
        date_of_issue=date_of_issue,
        signature_image_bytes=signature_image_bytes,
    )
    destination.write_bytes(pdf_bytes)
    return str(destination)
