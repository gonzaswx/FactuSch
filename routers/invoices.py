from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request

from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from database import get_db
from routers.auth import require_school_access


router = APIRouter()


@router.post(
    "/schools/{school_id}/students/{student_id}/invoices/issue"
)
def issue_invoice_disabled(
    school_id: int,
    student_id: int,
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

    return RedirectResponse(
        url=f"/schools/{school_id}/students/{student_id}/invoices",
        status_code=303
    )