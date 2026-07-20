from sqlalchemy.orm import Session

from models.school_level import SchoolLevel


class SchoolLevelService:

    @staticmethod
    def clean_text(value):
        return str(value or "").strip()

    @staticmethod
    def normalize_alias(value):
        return (
            SchoolLevelService.clean_text(value)
            .upper()
            .replace(" ", "_")
            .replace("-", "_")
        )

    @staticmethod
    def get_by_school(
        db: Session,
        school_id: int,
        include_inactive: bool = True
    ):
        query = db.query(SchoolLevel).filter(
            SchoolLevel.school_id == school_id
        )

        if not include_inactive:
            query = query.filter(
                SchoolLevel.is_active == True
            )

        return (
            query
            .order_by(
                SchoolLevel.is_active.desc(),
                SchoolLevel.name.asc()
            )
            .all()
        )

    @staticmethod
    def get_by_id(
        db: Session,
        school_id: int,
        level_id: int
    ):
        return (
            db.query(SchoolLevel)
            .filter(
                SchoolLevel.id == level_id,
                SchoolLevel.school_id == school_id
            )
            .first()
        )

    @staticmethod
    def validate_unique_alias(
        db: Session,
        school_id: int,
        alias: str,
        level_id: int | None = None
    ):
        query = db.query(SchoolLevel).filter(
            SchoolLevel.school_id == school_id,
            SchoolLevel.alias == alias
        )

        if level_id:
            query = query.filter(
                SchoolLevel.id != level_id
            )

        existing = query.first()

        if existing:
            raise ValueError(
                f"Ya existe un nivel con el alias '{alias}' en esta escuela."
            )

    @staticmethod
    def validate_unique_name(
        db: Session,
        school_id: int,
        name: str,
        level_id: int | None = None
    ):
        query = db.query(SchoolLevel).filter(
            SchoolLevel.school_id == school_id,
            SchoolLevel.name == name
        )

        if level_id:
            query = query.filter(
                SchoolLevel.id != level_id
            )

        existing = query.first()

        if existing:
            raise ValueError(
                f"Ya existe un nivel llamado '{name}' en esta escuela."
            )

    @staticmethod
    def validate_data(
        db: Session,
        school_id: int,
        name: str,
        alias: str,
        monthly_fee: float,
        point_of_sale: int,
        level_id: int | None = None
    ):
        name = SchoolLevelService.clean_text(name)
        alias = SchoolLevelService.normalize_alias(alias)

        if not name:
            raise ValueError("El nombre del nivel es obligatorio.")

        if not alias:
            raise ValueError("El alias del nivel es obligatorio.")

        if monthly_fee is None:
            raise ValueError("La cuota mensual es obligatoria.")

        if float(monthly_fee) < 0:
            raise ValueError("La cuota mensual no puede ser negativa.")

        if not point_of_sale:
            raise ValueError("El punto de venta del nivel es obligatorio.")

        try:
            point_of_sale = int(point_of_sale)
        except Exception:
            raise ValueError("El punto de venta debe ser numérico.")

        if point_of_sale <= 0:
            raise ValueError("El punto de venta debe ser mayor a cero.")

        SchoolLevelService.validate_unique_name(
            db=db,
            school_id=school_id,
            name=name,
            level_id=level_id
        )

        SchoolLevelService.validate_unique_alias(
            db=db,
            school_id=school_id,
            alias=alias,
            level_id=level_id
        )

        return {
            "name": name,
            "alias": alias,
            "monthly_fee": monthly_fee,
            "point_of_sale": point_of_sale
        }

    @staticmethod
    def create(
        db: Session,
        school_id: int,
        name: str,
        alias: str,
        monthly_fee: float,
        point_of_sale: int
    ):
        data = SchoolLevelService.validate_data(
            db=db,
            school_id=school_id,
            name=name,
            alias=alias,
            monthly_fee=monthly_fee,
            point_of_sale=point_of_sale
        )

        level = SchoolLevel(
            school_id=school_id,
            name=data["name"],
            alias=data["alias"],
            monthly_fee=data["monthly_fee"],
            point_of_sale=data["point_of_sale"],
            is_active=True
        )

        db.add(level)
        db.commit()
        db.refresh(level)

        return level

    @staticmethod
    def update(
        db: Session,
        school_id: int,
        level_id: int,
        name: str,
        alias: str,
        monthly_fee: float,
        point_of_sale: int
    ):
        level = SchoolLevelService.get_by_id(
            db=db,
            school_id=school_id,
            level_id=level_id
        )

        if not level:
            raise ValueError("Nivel no encontrado.")

        data = SchoolLevelService.validate_data(
            db=db,
            school_id=school_id,
            level_id=level_id,
            name=name,
            alias=alias,
            monthly_fee=monthly_fee,
            point_of_sale=point_of_sale
        )

        level.name = data["name"]
        level.alias = data["alias"]
        level.monthly_fee = data["monthly_fee"]
        level.point_of_sale = data["point_of_sale"]

        db.commit()
        db.refresh(level)

        return level

    @staticmethod
    def toggle_active(
        db: Session,
        school_id: int,
        level_id: int
    ):
        level = SchoolLevelService.get_by_id(
            db=db,
            school_id=school_id,
            level_id=level_id
        )

        if not level:
            raise ValueError("Nivel no encontrado.")

        level.is_active = not level.is_active

        db.commit()
        db.refresh(level)

        return level