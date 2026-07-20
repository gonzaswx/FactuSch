import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from models.invoice_log import InvoiceLog

from database import Base, engine, create_schema_if_not_exists

from models.school import School
from models.student import Student
from models.invoice import Invoice
from models.invoice_job import InvoiceJob
from models.user import User
from models.school_settings import SchoolSettings
from models.school_level import SchoolLevel

from routers.students import router as students_router
from routers.invoices import router as invoices_router
from routers.student_invoices import router as student_invoices_router
from routers.pdf_invoices import router as pdf_invoices_router
from routers.auth import router as auth_router
from routers.billing import router as billing_router
from routers.settings import router as settings_router
from routers.school_levels import router as school_levels_router
from routers.payments import router as payments_router
from routers.school_dashboard import router as school_dashboard_router
from routers.admin_dashboard import router as admin_dashboard_router
from routers.invoice_jobs import router as invoice_jobs_router
from routers.schools import router as schools_router


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("facturacion_escolar")


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Iniciando aplicación – verificando base de datos...")

    create_schema_if_not_exists()
    Base.metadata.create_all(bind=engine)

    pdf_dir = Path(os.getenv("PDF_STORAGE_PATH", "./storage/pdfs"))
    pdf_dir.mkdir(parents=True, exist_ok=True)

    cert_dir = Path("./storage/certs")
    cert_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Base de datos y directorios listos.")

    yield

    logger.info("Aplicación detenida.")


app = FastAPI(
    title="Facturación Masiva Escolar",
    description="Sistema de facturación electrónica para colegios integrada con ARCA/AFIP",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)


templates = Jinja2Templates(directory="templates")


def formato_moneda(value):
    try:
        return f"$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "$ 0,00"


templates.env.filters["moneda"] = formato_moneda


app.include_router(auth_router)
app.include_router(admin_dashboard_router)
app.include_router(schools_router)
app.include_router(school_dashboard_router)
app.include_router(students_router)
app.include_router(school_levels_router)
app.include_router(settings_router)
app.include_router(billing_router)
app.include_router(invoice_jobs_router)
app.include_router(payments_router)
app.include_router(student_invoices_router)
app.include_router(invoices_router)
app.include_router(pdf_invoices_router)


@app.get("/", response_class=HTMLResponse)
async def raiz():
    return RedirectResponse(url="/login", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    role = request.cookies.get("role")

    if not role:
        return RedirectResponse(url="/login", status_code=303)

    if role == "admin":
        return RedirectResponse(url="/admin/dashboard", status_code=303)

    school_id = request.cookies.get("school_id")

    if school_id:
        return RedirectResponse(
            url=f"/schools/{school_id}/dashboard",
            status_code=303
        )

    return RedirectResponse(url="/login", status_code=303)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "facturacion-escolar"
    }


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):

    if exc.status_code != 404:
        raise exc

    if request.url.path.startswith("/api"):
        return RedirectResponse(url="/api/docs", status_code=303)

    if request.cookies.get("user_id"):
        return RedirectResponse(url="/dashboard", status_code=303)

    return RedirectResponse(url="/login", status_code=303)