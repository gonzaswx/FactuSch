from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request

from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from database import get_db

from models.invoice import Invoice
from models.school import School
from models.student import Student

from services.pdf_service import PDFService

from routers.auth import require_school_access


router = APIRouter()


@router.get("/invoices/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id
    ).first()

    if not invoice:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    user = require_school_access(
        request=request,
        db=db,
        school_id=invoice.school_id
    )

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    school = db.query(School).filter(
        School.id == invoice.school_id
    ).first()

    student = db.query(Student).filter(
        Student.id == invoice.student_id,
        Student.school_id == invoice.school_id
    ).first()

    if not school or not student:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    filepath = PDFService.generate_invoice_pdf(
        invoice=invoice,
        school=school,
        student=student
    )

    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filepath.split("/")[-1]
    )