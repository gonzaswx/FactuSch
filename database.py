# database.py
# Configuración de la conexión a PostgreSQL usando SQLAlchemy.
# El schema "agenda" se aplica globalmente a todos los modelos.

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.schema import MetaData
from dotenv import load_dotenv

load_dotenv()

# ── Construcción de la URL de conexión ────────────────────────────────────────
DB_USER = os.getenv("DB_USER", "usragenda")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "db_agenda")

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ── Engine ─────────────────────────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,          # Verifica la conexión antes de usarla
    pool_recycle=3600,           # Recicla conexiones cada hora
    connect_args={
        "options": "-csearch_path=agenda"   # Establece el schema por defecto
    },
)

# ── Sesión ─────────────────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ── Metadata con schema "agenda" ───────────────────────────────────────────────
# Todos los modelos que hereden de Base usarán el schema "agenda"
SCHEMA = "agenda"
metadata = MetaData(schema=SCHEMA)


class Base(DeclarativeBase):
    metadata = metadata


# ── Dependency para FastAPI ────────────────────────────────────────────────────
def get_db():
    """
    Generador que provee una sesión de BD y garantiza su cierre al finalizar.
    Usar como dependencia en las rutas de FastAPI:
        db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_schema_if_not_exists():
    """Crea el schema 'agenda' si no existe. Llamar al iniciar la app."""
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        conn.commit()
