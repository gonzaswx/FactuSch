from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request

from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from database import get_db

from models.school import School
from models.invoice_job import InvoiceJob

from routers.auth import require_school_access

from utils.templates import templates


router = APIRouter(
    prefix="/schools/{school_id}/jobs",
    tags=["Invoice Jobs"]
)


@router.get("/", response_class=HTMLResponse)
async def list_jobs(
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
            "/login",
            status_code=303
        )

    school = db.query(School).filter(
        School.id == school_id
    ).first()

    jobs = (
        db.query(InvoiceJob)
        .filter(
            InvoiceJob.school_id == school_id
        )
        .order_by(
            InvoiceJob.created_at.desc()
        )
        .all()
    )

    return templates.TemplateResponse(
        "jobs/list.html",
        {
            "request": request,
            "school": school,
            "jobs": jobs
        }
    )