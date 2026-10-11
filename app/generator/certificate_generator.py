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


def _render_classic_certificate(
    c: canvas.Canvas,
    recipient_name: str,
    title: str,
    organization: str,
    date_of_issue: str,
    width: float,
    height: float,
    signature_image_bytes: bytes | None = None,
) -> None:
    """Draw classic gold-ornamented certificate elements onto canvas."""
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


def _render_modern_certificate(
    c: canvas.Canvas,
    recipient_name: str,
    title: str,
    organization: str,
    date_of_issue: str,
    width: float,
    height: float,
    signature_image_bytes: bytes | None = None,
) -> None:
    """Draw modern minimalist slate/sky-accented certificate elements onto canvas."""
    # --- Background ---
    c.setFillColor(HexColor("#F8FAFC"))  # Crisp slate-50 background
    c.rect(0, 0, width, height, fill=1, stroke=0)

    # --- Modern Structural Borders ---
    c.setStrokeColor(HexColor("#E2E8F0"))  # Slate-200 outer border
    c.setLineWidth(1.5)
    c.roundRect(24, 24, width - 48, height - 48, radius=4, stroke=1, fill=0)

    # Left vertical accent pillars
    c.setFillColor(HexColor("#0284C7"))  # Sky-600 primary accent
    c.rect(34, 34, 6, height - 68, fill=1, stroke=0)
    c.setFillColor(HexColor("#38BDF8"))  # Sky-400 subtle secondary stripe
    c.rect(42, 34, 2, height - 68, fill=1, stroke=0)

    # Top right accent bar
    c.setFillColor(HexColor("#0284C7"))
    c.rect(width - 160, height - 34, 126, 3, fill=1, stroke=0)

    # --- Header Section: Organization & Badge ---
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(HexColor("#0284C7"))
    c.drawString(64, height - 64, "ACCREDITED PROFESSIONAL CREDENTIAL")

    max_org_width = width - 240
    org_size = 15
    while (
        c.stringWidth(organization.upper(), "Helvetica-Bold", org_size) > max_org_width
        and org_size > 9
    ):
        org_size -= 1
    c.setFont("Helvetica-Bold", org_size)
    c.setFillColor(HexColor("#0F172A"))  # Slate-900
    c.drawString(64, height - 86, organization.upper())

    # Thin separator line under org
    c.setStrokeColor(HexColor("#CBD5E1"))
    c.setLineWidth(0.8)
    c.line(64, height - 98, width - 64, height - 98)

    # --- Main Title ---
    c.setFont("Helvetica-Bold", 32)
    c.setFillColor(HexColor("#0F172A"))
    c.drawCentredString(width / 2, height - 156, "CERTIFICATE OF EXCELLENCE")

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(HexColor("#64748B"))
    c.drawCentredString(width / 2, height - 180, "THIS DISTINCTION IS PRESENTED TO")

    # --- Recipient Name ---
    max_name_width = width - 150
    name_size = 28
    while (
        c.stringWidth(recipient_name, "Helvetica-Bold", name_size) > max_name_width
        and name_size > 14
    ):
        name_size -= 2
    c.setFont("Helvetica-Bold", name_size)
    c.setFillColor(HexColor("#0284C7"))  # Modern vibrant sky tone
    c.drawCentredString(width / 2, height - 238, recipient_name)

    # Modern accent underline with square endpoint accents
    name_width = c.stringWidth(recipient_name, "Helvetica-Bold", name_size)
    line_padding = 24
    line_x1 = max(64.0, (width - name_width) / 2 - line_padding)
    line_x2 = min(width - 64.0, (width + name_width) / 2 + line_padding)
    c.setStrokeColor(HexColor("#0284C7"))
    c.setLineWidth(2.0)
    c.line(line_x1, height - 250, line_x2, height - 250)

    # Endpoint accent dots
    c.setFillColor(HexColor("#0284C7"))
    c.circle(line_x1, height - 250, 2.5, fill=1, stroke=0)
    c.circle(line_x2, height - 250, 2.5, fill=1, stroke=0)

    # --- Body / Course details ---
    c.setFont("Helvetica", 12)
    c.setFillColor(HexColor("#475569"))
    c.drawCentredString(
        width / 2,
        height - 290,
        "for successfully demonstrating proficiency and fulfilling all criteria in",
    )

    max_title_width = width - 150
    title_size = 19
    while (
        c.stringWidth(title, "Helvetica-Bold", title_size) > max_title_width
        and title_size > 11
    ):
        title_size -= 1
    c.setFont("Helvetica-Bold", title_size)
    c.setFillColor(HexColor("#0F172A"))
    c.drawCentredString(width / 2, height - 322, title)

    # --- Footer Section ---
    footer_y = 96

    # Date on left
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(HexColor("#64748B"))
    c.drawString(64, footer_y + 30, "DATE OF ISSUANCE")
    c.setFont("Helvetica", 12)
    c.setFillColor(HexColor("#0F172A"))
    c.drawString(64, footer_y + 12, f"{date_of_issue}")
    c.setStrokeColor(HexColor("#CBD5E1"))
    c.setLineWidth(0.8)
    c.line(64, footer_y + 2, 200, footer_y + 2)

    # Modern Verified Credential Shield in center
    c.saveState()
    c.setFillColor(HexColor("#F0F9FF"))
    c.setStrokeColor(HexColor("#0284C7"))
    c.setLineWidth(1.5)
    c.circle(width / 2, footer_y + 16, 24, stroke=1, fill=1)
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(HexColor("#0284C7"))
    c.drawCentredString(width / 2, footer_y + 19, "VERIFIED")
    c.setFont("Helvetica-Bold", 6)
    c.setFillColor(HexColor("#64748B"))
    c.drawCentredString(width / 2, footer_y + 10, "CREDENTIAL")
    c.restoreState()

    # Signature on right
    c.setStrokeColor(HexColor("#CBD5E1"))
    c.setLineWidth(0.8)
    c.line(width - 200, footer_y + 2, width - 64, footer_y + 2)

    if signature_image_bytes:
        try:
            from reportlab.lib.utils import ImageReader

            img = ImageReader(io.BytesIO(signature_image_bytes))
            sig_w = 110
            sig_h = 36
            c.drawImage(
                img,
                (width - 132) - (sig_w / 2),
                footer_y + 8,
                width=sig_w,
                height=sig_h,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(HexColor("#0F172A"))
            c.drawCentredString(width - 132, footer_y + 12, organization)
    else:
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(HexColor("#0F172A"))
        c.drawCentredString(width - 132, footer_y + 12, organization)

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(HexColor("#64748B"))
    c.drawCentredString(width - 132, footer_y - 10, "AUTHORIZED SIGNATORY")


def generate_certificate_bytes(
    recipient_name: str,
    title: str,
    organization: str,
    date_of_issue: str,
    signature_image_bytes: bytes | None = None,
    template: str = "classic",
) -> bytes:
    """Generate a single professional PDF certificate directly as bytes in memory.

    Args:
        recipient_name: Name of the recipient to appear on the certificate.
        title: Title of the course or event.
        organization: Name of the issuing organization.
        date_of_issue: Date string (YYYY-MM-DD format).
        signature_image_bytes: Optional binary bytes of signature image.
        template: Design template to use ('classic' or 'modern').

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
    chosen_template = (template or "classic").strip().lower()

    buf = io.BytesIO()
    page_size = landscape(letter)
    width, height = page_size

    c = canvas.Canvas(buf, pagesize=page_size)

    if chosen_template == "modern":
        _render_modern_certificate(
            c=c,
            recipient_name=clean_name,
            title=clean_title,
            organization=clean_org,
            date_of_issue=clean_date,
            width=width,
            height=height,
            signature_image_bytes=signature_image_bytes,
        )
    else:
        _render_classic_certificate(
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
    template: str = "classic",
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
        template=template,
    )
    destination.write_bytes(pdf_bytes)
    return str(destination)
