from sqlalchemy.orm import Session

from models.student import Student
from models.school_level import SchoolLevel


class StudentService:

    @staticmethod
    def clean_text(value):
        if value is None:
            return None

        value = str(value).strip()

        if value.endswith(".0"):
            value = value[:-2]

        return value or None

    @staticmethod
    def clean_dni(value):
        value = str(value or "").strip()

        if value.endswith(".0"):
            value = value[:-2]

        return value

    @staticmethod
    def validate_dni(value, field_name="DNI"):
        value = StudentService.clean_dni(value)

        if not value:
            raise ValueError(f"{field_name} es obligatorio.")

        if not value.isdigit():
            raise ValueError(f"{field_name} debe contener solo números.")

        if len(value) < 7 or len(value) > 11:
            raise ValueError(f"{field_name} debe tener entre 7 y 11 dígitos.")

        return value

    @staticmethod
    def get_by_school(db: Session, school_id: int):
        return (
            db.query(Student)
            .filter(Student.school_id == school_id)
            .order_by(Student.is_active.desc(), Student.id.desc())
            .all()
        )

    @staticmethod
    def get_by_id(
        db: Session,
        school_id: int,
        student_id: int
    ):
        return (
            db.query(Student)
            .filter(
                Student.id == student_id,
                Student.school_id == school_id
            )
            .first()
        )

    @staticmethod
    def get_existing_by_dni(
        db: Session,
        school_id: int,
        dni: str,
        exclude_student_id: int | None = None
    ):
        query = db.query(Student).filter(
            Student.school_id == school_id,
            Student.dni == dni
        )

        if exclude_student_id:
            query = query.filter(
                Student.id != exclude_student_id
            )

        return query.first()

    @staticmethod
    def resolve_monthly_fee(
        db: Session,
        school_id: int,
        level_id: int | None,
        monthly_fee: float | None
    ):
        final_monthly_fee = monthly_fee or 0

        if level_id and final_monthly_fee == 0:
            level = (
                db.query(SchoolLevel)
                .filter(
                    SchoolLevel.id == level_id,
                    SchoolLevel.school_id == school_id,
                    SchoolLevel.is_active == True
                )
                .first()
            )

            if level:
                final_monthly_fee = float(level.monthly_fee or 0)

        return final_monthly_fee

    @staticmethod
    def create(
        db: Session,
        school_id: int,
        full_name: str,
        dni: str,
        email: str | None = None,
        course: str | None = None,
        division: str | None = None,
        guardian_name: str | None = None,
        guardian_dni: str | None = None,
        level_id: int | None = None,
        monthly_fee: float | None = None
    ):
        clean_student_dni = StudentService.validate_dni(
            dni,
            "DNI del alumno"
        )

        clean_guardian_dni = None

        if guardian_dni:
            clean_guardian_dni = StudentService.validate_dni(
                guardian_dni,
                "DNI del tutor"
            )

            if clean_guardian_dni == clean_student_dni:
                raise ValueError(
                    "El DNI del tutor no puede ser igual al DNI del alumno."
                )

        existing_student = StudentService.get_existing_by_dni(
            db=db,
            school_id=school_id,
            dni=clean_student_dni
        )

        if existing_student:
            raise ValueError(
                "Ya existe un alumno con ese DNI en esta escuela."
            )

        final_monthly_fee = StudentService.resolve_monthly_fee(
            db=db,
            school_id=school_id,
            level_id=level_id,
            monthly_fee=monthly_fee
        )

        student = Student(
            school_id=school_id,
            level_id=level_id,
            full_name=StudentService.clean_text(full_name),
            dni=clean_student_dni,
            email=StudentService.clean_text(email),
            course=StudentService.clean_text(course),
            division=StudentService.clean_text(division),
            guardian_name=StudentService.clean_text(guardian_name),
            guardian_dni=clean_guardian_dni,
            monthly_fee=final_monthly_fee,
            is_active=True
        )

        db.add(student)
        db.commit()
        db.refresh(student)

        return student

    @staticmethod
    def update(
        db: Session,
        school_id: int,
        student_id: int,
        full_name: str,
        dni: str,
        email: str | None = None,
        course: str | None = None,
        division: str | None = None,
        guardian_name: str | None = None,
        guardian_dni: str | None = None,
        level_id: int | None = None,
        monthly_fee: float | None = None
    ):
        student = StudentService.get_by_id(
            db=db,
            school_id=school_id,
            student_id=student_id
        )

        if not student:
            raise ValueError("Alumno no encontrado.")

        clean_student_dni = StudentService.validate_dni(
            dni,
            "DNI del alumno"
        )

        clean_guardian_dni = None

        if guardian_dni:
            clean_guardian_dni = StudentService.validate_dni(
                guardian_dni,
                "DNI del tutor"
            )

            if clean_guardian_dni == clean_student_dni:
                raise ValueError(
                    "El DNI del tutor no puede ser igual al DNI del alumno."
                )

        existing_student = StudentService.get_existing_by_dni(
            db=db,
            school_id=school_id,
            dni=clean_student_dni,
            exclude_student_id=student_id
        )

        if existing_student:
            raise ValueError(
                "Ya existe otro alumno con ese DNI en esta escuela."
            )

        final_monthly_fee = StudentService.resolve_monthly_fee(
            db=db,
            school_id=school_id,
            level_id=level_id,
            monthly_fee=monthly_fee
        )

        student.level_id = level_id
        student.full_name = StudentService.clean_text(full_name)
        student.dni = clean_student_dni
        student.email = StudentService.clean_text(email)
        student.course = StudentService.clean_text(course)
        student.division = StudentService.clean_text(division)
        student.guardian_name = StudentService.clean_text(guardian_name)
        student.guardian_dni = clean_guardian_dni
        student.monthly_fee = final_monthly_fee

        db.commit()
        db.refresh(student)

        return student  