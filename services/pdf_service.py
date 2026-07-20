import base64
import json
import os
from datetime import datetime
from urllib.parse import quote

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF


PDF_DIR = "storage/pdfs"


class PDFService:

    @staticmethod
    def money(value):
        return f"$ {float(value or 0):,.2f}"

    @staticmethod
    def get_primary_color(settings):
        default_color = "#111827"

        if not settings or not settings.invoice_primary_color:
            return default_color

        color = settings.invoice_primary_color.strip()

        if not color.startswith("#"):
            color = "#" + color

        if len(color) != 7:
            return default_color

        return color

    @staticmethod
    def get_period_text(invoice):
        if invoice.period_month and invoice.period_year:
            return f"{invoice.period_month:02d}/{invoice.period_year}"

        return "-"

    @staticmethod
    def format_full_invoice_number(invoice):
        if invoice.full_invoice_number:
            return invoice.full_invoice_number

        point_of_sale = int(invoice.point_of_sale or 0)
        invoice_number = int(invoice.invoice_number or 0)

        return f"{point_of_sale:04d}-{invoice_number:08d}"

    @staticmethod
    def get_invoice_date(invoice):
        if invoice.created_at:
            return invoice.created_at.strftime("%Y-%m-%d")

        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def build_arca_qr_url(invoice, school, student, settings=None):
        cuit = None

        if settings and settings.afip_cuit:
            cuit = settings.afip_cuit
        elif getattr(school, "cuit", None):
            cuit = school.cuit

        if not cuit or not invoice.cae:
            return None

        clean_cuit = str(cuit).replace("-", "").replace(" ", "").strip()

        if not clean_cuit.isdigit():
            return None

        cae = str(invoice.cae).strip()

        qr_data = {
            "ver": 1,
            "fecha": PDFService.get_invoice_date(invoice),
            "cuit": int(clean_cuit),
            "ptoVta": int(invoice.point_of_sale),
            "tipoCmp": int(invoice.invoice_type or 6),
            "nroCmp": int(invoice.invoice_number),
            "importe": float(invoice.amount or 0),
            "moneda": "PES",
            "ctz": 1,
            "tipoDocRec": 99,
            "nroDocRec": 0,
            "tipoCodAut": "E",
            "codAut": int(cae) if cae.isdigit() else cae
        }

        json_data = json.dumps(
            qr_data,
            separators=(",", ":"),
            ensure_ascii=False
        )

        encoded = base64.b64encode(
            json_data.encode("utf-8")
        ).decode("utf-8")

        return "https://www.arca.gob.ar/fe/qr/?p=" + quote(encoded, safe="")

    @staticmethod
    def draw_qr(c, qr_url, x, y, size=95):
        if not qr_url:
            return

        qr_code = qr.QrCodeWidget(qr_url)
        bounds = qr_code.getBounds()

        qr_width = bounds[2] - bounds[0]
        qr_height = bounds[3] - bounds[1]

        drawing = Drawing(
            size,
            size,
            transform=[
                size / qr_width,
                0,
                0,
                size / qr_height,
                0,
                0
            ]
        )

        drawing.add(qr_code)
        renderPDF.draw(drawing, c, x, y)

    @staticmethod
    def draw_logo(c, settings, x, y, width=95, height=45):
        if not settings or not settings.invoice_logo_path:
            return False

        logo_path = settings.invoice_logo_path

        if not os.path.exists(logo_path):
            return False

        try:
            c.drawImage(
                logo_path,
                x,
                y,
                width=width,
                height=height,
                preserveAspectRatio=True,
                mask="auto"
            )
            return True

        except Exception:
            return False

    @staticmethod
    def generate_invoice_pdf(invoice, school, student, settings=None):

        os.makedirs(PDF_DIR, exist_ok=True)

        full_number = PDFService.format_full_invoice_number(invoice)

        filename = f"factura_{full_number.replace('-', '_')}.pdf"
        filepath = os.path.join(PDF_DIR, filename)

        c = canvas.Canvas(filepath, pagesize=A4)
        width, height = A4

        period_text = PDFService.get_period_text(invoice)
        primary_color = PDFService.get_primary_color(settings)

        qr_url = PDFService.build_arca_qr_url(
            invoice=invoice,
            school=school,
            student=student,
            settings=settings
        )

        c.setFillColor(colors.HexColor(primary_color))
        c.rect(0, height - 90, width, 90, fill=True, stroke=False)

        logo_drawn = PDFService.draw_logo(
            c=c,
            settings=settings,
            x=40,
            y=height - 72,
            width=110,
            height=50
        )

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 22)

        invoice_type_text = PDFService.get_invoice_type_text(invoice)

        if logo_drawn:
            c.drawString(165, height - 45, invoice_type_text)
        else:
            c.drawString(40, height - 45, invoice_type_text)

        c.setFont("Helvetica", 10)
        c.drawRightString(width - 40, height - 40, f"Punto de venta: {invoice.point_of_sale}")
        c.drawRightString(width - 40, height - 58, f"Comprobante N°: {full_number}")
        c.drawRightString(width - 40, height - 76, f"Período: {period_text}")

        y = height - 130

        c.setFillColor(colors.HexColor(primary_color))
        c.setFont("Helvetica-Bold", 13)
        c.drawString(40, y, "Datos del colegio")

        business_name = school.name

        if settings and settings.afip_business_name:
            business_name = settings.afip_business_name

        cuit = school.cuit or "-"

        if settings and settings.afip_cuit:
            cuit = settings.afip_cuit

        y -= 22
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#111827"))
        c.drawString(40, y, f"Nombre / Razón social: {business_name}")
        y -= 16
        c.drawString(40, y, f"CUIT: {cuit}")
        y -= 16
        c.drawString(40, y, f"Dirección: {school.address or '-'}")

        y -= 38
        c.setFillColor(colors.HexColor(primary_color))
        c.setFont("Helvetica-Bold", 13)
        c.drawString(40, y, "Datos del alumno")

        y -= 22
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#111827"))
        c.drawString(40, y, f"Alumno: {student.full_name}")
        y -= 16
        c.drawString(40, y, f"DNI: {student.dni}")
        y -= 16
        c.drawString(40, y, f"Curso: {student.course or '-'} {student.division or ''}")

        y -= 34
        c.setFillColor(colors.HexColor(primary_color))
        c.setFont("Helvetica-Bold", 13)
        c.drawString(40, y, "Datos de facturación")

        y -= 22
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#111827"))
        c.drawString(40, y, f"Período facturado: {period_text}")
        y -= 16
        c.drawString(40, y, f"Fecha de vencimiento: {invoice.due_date or '-'}")

        y -= 40

        c.setFillColor(colors.HexColor("#e5e7eb"))
        c.rect(40, y, width - 80, 28, fill=True, stroke=False)

        c.setFillColor(colors.HexColor("#111827"))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(55, y + 9, "Descripción")
        c.drawRightString(width - 55, y + 9, "Importe")

        y -= 28
        c.setFont("Helvetica", 10)
        c.drawString(55, y + 9, f"Cuota / servicio educativo - Período {period_text}")
        c.drawRightString(width - 55, y + 9, PDFService.money(invoice.amount))

        y -= 55

        c.setFont("Helvetica", 10)
        c.drawRightString(width - 55, y, f"Neto: {PDFService.money(invoice.net_amount)}")
        y -= 18
        c.drawRightString(width - 55, y, f"IVA: {PDFService.money(invoice.iva_amount)}")
        y -= 24

        c.setFont("Helvetica-Bold", 14)
        c.drawRightString(width - 55, y, f"TOTAL: {PDFService.money(invoice.amount)}")

        y -= 95

        c.setFillColor(colors.HexColor("#f3f4f6"))
        c.rect(40, y - 15, width - 80, 105, fill=True, stroke=False)

        c.setFillColor(colors.HexColor("#111827"))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(55, y + 48, f"CAE: {invoice.cae}")
        c.drawString(55, y + 28, f"Vencimiento CAE: {invoice.cae_expiration}")
        c.drawString(55, y + 8, f"Comprobante: {full_number}")

        PDFService.draw_qr(
            c=c,
            qr_url=qr_url,
            x=width - 145,
            y=y + 2,
            size=80
        )

        footer_text = "Comprobante generado electrónicamente mediante servicios ARCA/AFIP."

        if settings and settings.invoice_footer_text:
            footer_text = settings.invoice_footer_text

        legal_text = None

        if settings and settings.invoice_legal_text:
            legal_text = settings.invoice_legal_text

        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#6b7280"))

        if legal_text:
            c.drawString(40, 62, legal_text[:140])

        c.drawString(
            40,
            45,
            footer_text[:150]
        )

        c.save()

        return filepath
    
    @staticmethod
    def get_invoice_type_text(invoice):
        invoice_types = {
            1: "FACTURA A",
            6: "FACTURA B",
            11: "FACTURA C"
        }

        return invoice_types.get(
            int(invoice.invoice_type or 0),
            "FACTURA"
        )