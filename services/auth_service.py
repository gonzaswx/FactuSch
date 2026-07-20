import re

from sqlalchemy.orm import Session

from models.user import User
from models.school import School


class AuthService:

    @staticmethod
    def normalize_email(email: str):
        return str(email or "").strip().lower()

    @staticmethod
    def clean_password(password: str):
        return str(password or "").strip()

    @staticmethod
    def validate_password(password: str):
        password = AuthService.clean_password(password)

        if len(password) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")

        if not re.search(r"[!@#$%&*?_\-]", password):
            raise ValueError(
                "La contraseña debe contener al menos un signo: ! @ # $ % & * ? _ -"
            )

        return True

    @staticmethod
    def get_user_by_email(
        db: Session,
        email: str
    ):
        return db.query(User).filter(
            User.email == AuthService.normalize_email(email)
        ).first()

    @staticmethod
    def create_admin_user(
        db: Session,
        email: str,
        password: str,
        full_name: str | None = None
    ):
        email = AuthService.normalize_email(email)
        password = AuthService.clean_password(password)

        AuthService.validate_password(password)

        existing_user = AuthService.get_user_by_email(
            db=db,
            email=email
        )

        if existing_user:
            raise ValueError("Ya existe un usuario con ese email")

        user = User(
            full_name=str(full_name or "").strip() or None,
            email=email,
            password=password,
            role="admin",
            school_id=None,
            is_active=True
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def create_school_user(
        db: Session,
        school_id: int,
        email: str,
        password: str,
        full_name: str | None = None
    ):
        school = db.query(School).filter(
            School.id == school_id
        ).first()

        if not school:
            raise ValueError("Colegio no encontrado")

        email = AuthService.normalize_email(email)
        password = AuthService.clean_password(password)

        AuthService.validate_password(password)

        existing_user = AuthService.get_user_by_email(
            db=db,
            email=email
        )

        if existing_user:
            raise ValueError("Ya existe un usuario con ese email")

        user = User(
            school_id=school.id,
            full_name=str(full_name or "").strip() or None,
            email=email,
            password=password,
            role="school",
            is_active=bool(school.is_active)
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def update_password(
        db: Session,
        user: User,
        password: str
    ):
        password = AuthService.clean_password(password)

        AuthService.validate_password(password)

        user.password = password

        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def authenticate(
        db: Session,
        email: str,
        password: str
    ):
        user = db.query(User).filter(
            User.email == AuthService.normalize_email(email),
            User.password == AuthService.clean_password(password),
            User.is_active == True
        ).first()

        return user