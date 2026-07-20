from sqlalchemy.orm import Session

from models.invoice_log import InvoiceLog


class InvoiceLogService:

    @staticmethod
    def create(
        db: Session,
        school_id: int,
        event_type: str,
        message: str,
        invoice_id: int | None = None,
        student_id: int | None = None
    ):
        log = InvoiceLog(
            invoice_id=invoice_id,
            school_id=school_id,
            student_id=student_id,
            event_type=event_type,
            message=message
        )

        db.add(log)
        db.commit()
        db.refresh(log)

        return log