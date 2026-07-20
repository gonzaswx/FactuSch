from datetime import datetime
from datetime import timezone
from datetime import date

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Form
from fastapi import Request

from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from database import get_db

from models.school import School
from models.student import Student
from models.invoice import Invoice
from models.invoice_log import InvoiceLog
from models.school_settings import SchoolSettings

from services.invoice_query_service import InvoiceQueryService
from services.pdf_service import PDFService
from services.email_service import EmailService
from services.invoice_log_service import InvoiceLogService

from utils.templates import templates

from routers.auth import require_school_access


router = APIRouter(
    prefix="/schools/{school_id}/students/{student_id}/invoices",
    tags=["Student Invoices"]
)


@router.get("/", response_class=HTMLResponse)
async def list_student_invoices(
    school_id: int,
    student_id: int,
    request: Request,
    email_status: str | None = None,
    email_message: str | None = None,
    db: Session = Depends(get_db)
):
    user = require_school_access(
        request=request,
        db=db,
        school_id=school_id
    )

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    school = db.query(School).filter(
        School.id == school_id
    ).first()

    student = db.query(Student).filter(
        Student.id == student_id,
        Student.school_id == school_id
    ).first()

    if not school or not student:
        return RedirectResponse(
            url=f"/schools/{school_id}/students",
            status_code=303
        )

    today = date.today()

    invoices = InvoiceQueryService.get_by_student(
        db=db,
        school_id=school_id,
        student_id=student_id
    )

    invoice_ids = [
        invoice.id
        for invoice in invoices
    ]

    logs_by_invoice = {}

    if invoice_ids:
        logs = (
            db.query(InvoiceLog)
            .filter(
                InvoiceLog.school_id == school_id,
                InvoiceLog.student_id == student_id,
                InvoiceLog.invoice_id.in_(invoice_ids)
            )
            .order_by(
                InvoiceLog.created_at.desc()
            )
            .all()
        )

        for log in logs:
            logs_by_invoice.setdefault(
                log.invoice_id,
                []
            ).append(log)

    total_invoiced = sum(
        float(invoice.amount or 0)
        for invoice in invoices
        if invoice.status == "approved"
    )

    total_paid = sum(
        float(invoice.amount or 0)
        for invoice in invoices
        if invoice.status == "approved" and invoice.is_paid
    )

    total_pending = total_invoiced - total_paid

    overdue_invoices = [
        invoice for invoice in invoices
        if invoice.status == "approved"
        and not invoice.is_paid
        and invoice.due_date
        and invoice.due_date < today
    ]

    total_overdue = sum(
        float(invoice.amount or 0)
        for invoice in overdue_invoices
    )

    paid_count = len([
        invoice for invoice in invoices
        if invoice.status == "approved" and invoice.is_paid
    ])

    pending_count = len([
        invoice for invoice in invoices
        if invoice.status == "approved" and not invoice.is_paid
    ])

    overdue_count = len(overdue_invoices)

    paid_percentage = 0

    if total_invoiced > 0:
        paid_percentage = round(
            (total_paid / total_invoiced) * 100,
            2
        )

    return templates.TemplateResponse(
        "invoices/student_list.html",
        {
            "request": request,
            "school": school,
            "student": student,
            "invoices": invoices,
            "logs_by_invoice": logs_by_invoice,
            "today": today,
            "email_status": email_status,
            "email_message": email_message,
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "total_pending": total_pending,
            "total_overdue": total_overdue,
            "paid_count": paid_count,
            "pending_count": pending_count,
            "overdue_count": overdue_count,
            "paid_percentage": paid_percentage
        }
    )


@router.post("/{invoice_id}/pay")
async def mark_invoice_as_paid(
    school_id: int,
    student_id: int,
    invoice_id: int,
    request: Request,
    payment_method: str = Form("Manual"),
    payment_note: str = Form("Marcada desde cuenta corriente del alumno"),
    db: Session = Depends(get_db)
):
    user = require_school_access(
        request=request,
        db=db,
        school_id=school_id
    )

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.school_id == school_id,
        Invoice.student_id == student_id,
        Invoice.status == "approved"
    ).first()

    if not invoice:
        return RedirectResponse(
            url=f"/schools/{school_id}/students/{student_id}/invoices",
            status_code=303
        )

    if not invoice.is_paid:
        invoice.is_paid = True
        invoice.paid_at = datetime.now(timezone.utc)
        invoice.payment_method = payment_method
        invoice.payment_note = payment_note

        db.commit()

        InvoiceLogService.create(
            db=db,
            school_id=school_id,
            student_id=student_id,
            invoice_id=invoice.id,
            event_type="payment_registered",
            message=f"Pago registrado. Método: {payment_method}. Nota: {payment_note or '-'}"
        )

    return RedirectResponse(
        url=f"/schools/{school_id}/students/{student_id}/invoices",
        status_code=303
    )


@router.post("/{invoice_id}/resend-email")
async def resend_invoice_email(
    school_id: int,
    student_id: int,
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_school_access(
        request=request,
        db=db,
        school_id=school_id
    )

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    school = db.query(School).filter(
        School.id == school_id
    ).first()

    student = db.query(Student).filter(
        Student.id == student_id,
        Student.school_id == school_id
    ).first()

    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.school_id == school_id,
        Invoice.student_id == student_id,
        Invoice.status == "approved"
    ).first()

    settings = db.query(SchoolSettings).filter(
        SchoolSettings.school_id == school_id
    ).first()

    if not school or not student or not invoice:
        return RedirectResponse(
            url=f"/schools/{school_id}/students/{student_id}/invoices?email_status=error&email_message=No se encontró la factura o el alumno",
            status_code=303
        )

    if not settings:
        return RedirectResponse(
            url=f"/schools/{school_id}/students/{student_id}/invoices?email_status=error&email_message=Configuración SMTP no encontrada",
            status_code=303
        )

    pdf_path = PDFService.generate_invoice_pdf(
        invoice=invoice,
        school=school,
        student=student,
        settings=settings
    )

    email_result = EmailService.send_invoice_email(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port or 587,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
        smtp_from=settings.smtp_from,
        to_email=student.email,
        student_name=student.full_name,
        school_name=school.name,
        pdf_path=pdf_path
    )

    if email_result["sent"]:
        invoice.email_status = "sent"
        invoice.email_error = None
        invoice.email_sent_at = datetime.now(timezone.utc)

        db.commit()

        InvoiceLogService.create(
            db=db,
            school_id=school_id,
            student_id=student_id,
            invoice_id=invoice.id,
            event_type="email_resent",
            message=f"Factura reenviada correctamente a {student.email}."
        )

        return RedirectResponse(
            url=f"/schools/{school_id}/students/{student_id}/invoices?email_status=success&email_message=Factura reenviada correctamente",
            status_code=303
        )

    invoice.email_status = "error"
    invoice.email_error = email_result["error"]

    db.commit()

    InvoiceLogService.create(
        db=db,
        school_id=school_id,
        student_id=student_id,
        invoice_id=invoice.id,
        event_type="email_resend_error",
        message=f"Error al reenviar factura: {email_result['error']}"
    )

    return RedirectResponse(
        url=f"/schools/{school_id}/students/{student_id}/invoices?email_status=error&email_message={email_result['error']}",
        status_code=303
    )