from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Numeric

from datetime import datetime

from database import Base


class Student(Base):

    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)

    school_id = Column(
        Integer,
        ForeignKey("schools.id"),
        nullable=False
    )

    level_id = Column(
        Integer,
        ForeignKey("school_levels.id"),
        nullable=True
    )

    full_name = Column(
        String(255),
        nullable=False
    )

    dni = Column(
        String(20),
        nullable=False
    )

    email = Column(
        String(255),
        nullable=True
    )

    course = Column(
        String(100),
        nullable=True
    )

    division = Column(
        String(50),
        nullable=True
    )

    guardian_name = Column(
        String(255),
        nullable=True
    )

    guardian_dni = Column(
        String(20), 
        nullable=True
    )

    monthly_fee = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    is_active = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    