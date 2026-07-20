from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Numeric
from sqlalchemy import DateTime
from sqlalchemy import Boolean
from sqlalchemy import Date
from sqlalchemy import ForeignKey
from sqlalchemy.sql import func

from database import Base


class Invoice(Base):

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)

    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=True)

    period_month = Column(Integer, nullable=True)
    period_year = Column(Integer, nullable=True)

    due_date = Column(Date, nullable=True)

    invoice_number = Column(Integer, nullable=False)
    point_of_sale = Column(Integer, nullable=False)
    invoice_type = Column(Integer, default=6)
    full_invoice_number = Column(String(30), nullable=True)

    amount = Column(Numeric(12, 2), nullable=False)
    net_amount = Column(Numeric(12, 2), nullable=True)
    iva_amount = Column(Numeric(12, 2), nullable=True)

    cae = Column(String(50), nullable=True)
    cae_expiration = Column(String(20), nullable=True)

    status = Column(String(30), default="pending")
    afip_result = Column(String(10), nullable=True)
    afip_observation = Column(String(500), nullable=True)

    email_status = Column(String(30), default="pending")
    email_error = Column(String(1000), nullable=True)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)

    is_paid = Column(Boolean, default=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    payment_method = Column(String(100), nullable=True)
    payment_note = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())