from datetime import datetime
from datetime import date

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request

from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from database import get_db

from models.school import School
from models.student import Student
from models.invoice import Invoice

from utils.templates import templates

from routers.auth import require_school_access


router = APIRouter(
    prefix="/schools/{school_id}/dashboard",
    tags=["School Dashboard"]
)


@router.get("/", response_class=HTMLResponse)
async def school_dashboard(
    school_id: int,
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

    if not school:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    now = datetime.now()
    today = date.today()

    total_students = db.query(Student).filter(
        Student.school_id == school_id,
        Student.is_active == True
    ).count()

    inactive_students = db.query(Student).filter(
        Student.school_id == school_id,
        Student.is_active == False
    ).count()

    invoices = db.query(Invoice).filter(
        Invoice.school_id == school_id,
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

    overdue_students_count = len({
        invoice.student_id
        for invoice in overdue_invoices
        if invoice.student_id
    })

    paid_count = len([
        invoice for invoice in invoices
        if invoice.is_paid
    ])

    pending_count = len([
        invoice for invoice in invoices
        if not invoice.is_paid
    ])

    overdue_count = len(overdue_invoices)

    paid_percentage = 0

    if total_invoiced > 0:
        paid_percentage = round(
            (total_paid / total_invoiced) * 100,
            2
        )

    recent_invoices = (
        db.query(Invoice)
        .filter(
            Invoice.school_id == school_id,
            Invoice.status == "approved"
        )
        .order_by(Invoice.created_at.desc())
        .limit(10)
        .all()
    )

    students_by_id = {
        student.id: student
        for student in db.query(Student)
        .filter(Student.school_id == school_id)
        .all()
    }

    return templates.TemplateResponse(
        "school_dashboard/index.html",
        {
            "request": request,
            "school": school,
            "current_month": now.month,
            "current_year": now.year,
            "today": today,

            "total_students": total_students,
            "inactive_students": inactive_students,

            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "total_pending": total_pending,
            "total_overdue": total_overdue,

            "paid_count": paid_count,
            "pending_count": pending_count,
            "overdue_count": overdue_count,
            "overdue_students_count": overdue_students_count,
            "paid_percentage": paid_percentage,

            "recent_invoices": recent_invoices,
            "students_by_id": students_by_id
        }
    )