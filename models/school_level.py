from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Numeric
from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey

from datetime import datetime

from database import Base


class SchoolLevel(Base):

    __tablename__ = "school_levels"

    id = Column(Integer, primary_key=True, index=True)

    school_id = Column(
        Integer,
        ForeignKey("schools.id"),
        nullable=False
    )

    name = Column(String(100), nullable=False)

    alias = Column(String(50), nullable=True)

    monthly_fee = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    point_of_sale = Column(
        Integer,
        nullable=True
    )

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)