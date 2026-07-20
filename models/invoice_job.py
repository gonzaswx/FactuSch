from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String

from database import Base


class InvoiceJob(Base):

    __tablename__ = "invoice_jobs"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    school_id = Column(
        Integer,
        ForeignKey("schools.id"),
        nullable=False
    )

    job_name = Column(
        String(255),
        nullable=False
    )

    period_month = Column(
        Integer,
        nullable=True
    )

    period_year = Column(
        Integer,
        nullable=True
    )

    due_day = Column(
        Integer,
        nullable=True
    )

    total_records = Column(
        Integer,
        default=0
    )

    processed_records = Column(
        Integer,
        default=0
    )

    skipped_records = Column(
        Integer,
        default=0
    )

    failed_records = Column(
        Integer,
        default=0
    )

    sent_emails = Column(
        Integer,
        default=0
    )

    email_errors = Column(
        Integer,
        default=0
    )

    status = Column(
        String(50),
        default="pending"
    )

    error_message = Column(
        String(1000),
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    finished_at = Column(
        DateTime,
        nullable=True
    )