from datetime import datetime

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

from services.bulk_billing_service import BulkBillingService
from utils.templates import templates

from routers.auth import require_school_access


router = APIRouter(
    prefix="/schools/{school_id}/billing",
    tags=["Billing"]
)


def get_active_students(db: Session, school_id: int):
    return (
        db.query(Student)
        .filter(
            Student.school_id == school_id,
            Student.is_active == True
        )
        .all()
    )


def render_billing_page(
    request: Request,
    school,
    students,
    current_month,
    current_year,
    current_due_day,
    result=None,
    error=None
):
    return templates.TemplateResponse(
        "billing/index.html",
        {
            "request": request,
            "school": school,
            "students_count": len(students),
            "total_amount": sum(
                float(student.monthly_fee or 0)
                for student in students
            ),
            "current_month": current_month,
            "current_year": current_year,
            "current_due_day": current_due_day,
            "result": result,
            "error": error
        }
    )


@router.get("/", response_class=HTMLResponse)
async def billing_page(
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

    students = get_active_students(
        db=db,
        school_id=school_id
    )

    now = datetime.now()

    return render_billing_page(
        request=request,
        school=school,
        students=students,
        current_month=now.month,
        current_year=now.year,
        current_due_day=10,
        result=None,
        error=None
    )


@router.post("/run", response_class=HTMLResponse)
async def run_billing(
    school_id: int,
    request: Request,
    job_name: str = Form(...),
    period_month: int = Form(...),
    period_year: int = Form(...),
    due_day: int = Form(10),
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

    students = get_active_students(
        db=db,
        school_id=school_id
    )

    try:
        result = BulkBillingService.run_for_school(
            db=db,
            school_id=school_id,
            job_name=job_name,
            period_month=period_month,
            period_year=period_year,
            due_day=due_day
        )

    except Exception as e:
        return render_billing_page(
            request=request,
            school=school,
            students=students,
            current_month=period_month,
            current_year=period_year,
            current_due_day=due_day,
            result=None,
            error=str(e)
        )

    return render_billing_page(
        request=request,
        school=school,
        students=students,
        current_month=period_month,
        current_year=period_year,
        current_due_day=due_day,
        result=result,
        error=None
    )