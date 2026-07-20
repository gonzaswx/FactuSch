from datetime import datetime, date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db

from models.school import School
from models.student import Student
from models.invoice import Invoice

from routers.auth import require_admin
from utils.templates import templates


router = APIRouter(
    prefix="/admin",
    tags=["Admin Dashboard"]
)


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    now = datetime.now()
    today = date.today()

    active_schools = db.query(School).filter(
        School.is_active == True
    ).count()

    blocked_schools = db.query(School).filter(
        School.is_active == False
    ).count()

    total_students = db.query(Student).count()

    active_students = db.query(Student).filter(
        Student.is_active == True
    ).count()

    invoices = db.query(Invoice).filter(
        Invoice.period_month == now.month,
        Invoice.period_year == now.year,
        Invoice.status == "approved"
    ).all()

    total_invoiced = sum(
        float(invoice.amount or 0)
        for invoice in invoices
    )

    total_paid = sum(
        float(invoice.amount or 0)
        for invoice in invoices
        if invoice.is_paid
    )

    total_pending = total_invoiced - total_paid

    overdue_invoices = [
        invoice for invoice in invoices
        if not invoice.is_paid
        and invoice.due_date
        and invoice.due_date < today
    ]

    total_overdue = sum(
        float(invoice.amount or 0)
        for invoice in overdue_invoices
    )

    overdue_schools = {
        invoice.school_id
        for invoice in overdue_invoices
    }

    paid_percentage = 0

    if total_invoiced > 0:
        paid_percentage = round(
            (total_paid / total_invoiced) * 100,
            2
        )

    recent_schools = (
        db.query(School)
        .order_by(School.id.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "current_month": now.month,
            "current_year": now.year,
            "active_schools": active_schools,
            "blocked_schools": blocked_schools,
            "total_students": total_students,
            "active_students": active_students,
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "total_pending": total_pending,
            "total_overdue": total_overdue,
            "overdue_schools_count": len(overdue_schools),
            "paid_percentage": paid_percentage,
            "recent_schools": recent_schools
        }
    )