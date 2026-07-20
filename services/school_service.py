from sqlalchemy.orm import Session

from models.school import School
from models.school_settings import SchoolSettings


class SchoolService:

    @staticmethod
    def get_all(db: Session):
        return (
            db.query(School)
            .order_by(School.id.desc())
            .all()
        )

    @staticmethod
    def get_by_id(
        db: Session,
        school_id: int
    ):
        return (
            db.query(School)
            .filter(School.id == school_id)
            .first()
        )

    @staticmethod
    def create(
        db: Session,
        name: str,
        cuit: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        address: str | None = None
    ):
        school = School(
            name=name,
            cuit=cuit,
            email=email,
            phone=phone,
            address=address
        )

        db.add(school)
        db.commit()
        db.refresh(school)

        settings = SchoolSettings(
            school_id=school.id
        )

        db.add(settings)
        db.commit()

        return school

    @staticmethod
    def update(
        db: Session,
        school_id: int,
        name: str,
        cuit: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        address: str | None = None
    ):
        school = SchoolService.get_by_id(
            db=db,
            school_id=school_id
        )

        if not school:
            raise ValueError("Colegio no encontrado.")

        school.name = name
        school.cuit = cuit
        school.email = email
        school.phone = phone
        school.address = address

        db.commit()
        db.refresh(school)

        return school