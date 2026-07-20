from sqlalchemy.orm import Session

from models.invoice import Invoice


class InvoiceQueryService:

    @staticmethod
    def get_by_student(
        db: Session,
        school_id: int,
        student_id: int
    ):
        return (
            db.query(Invoice)
            .filter(
                Invoice.school_id == school_id,
                Invoice.student_id == student_id
            )
            .order_by(Invoice.id.desc())
            .all()
        )