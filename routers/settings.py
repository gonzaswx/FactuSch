import os
import shutil
import json

from datetime import datetime
from datetime import timezone

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import Request
from fastapi import UploadFile

from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from database import get_db

from models.school import School
from models.school_settings import SchoolSettings
from models.invoice import Invoice

from services.afip.afip_service import AFIPService
from services.afip_certificate_service import AFIPCertificateService
from utils.templates import templates


router = APIRouter(
    prefix="/schools",
    tags=["Settings"]
)


def require_admin_user(request: Request):
    return request.cookies.get("role") == "admin"


def get_school(db: Session, school_id: int):
    return db.query(School).filter(
        School.id == school_id
    ).first()


def get_or_create_settings(db: Session, school_id: int):
    settings = db.query(SchoolSettings).filter(
        SchoolSettings.school_id == school_id
    ).first()

    if not settings:
        settings = SchoolSettings(school_id=school_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return settings


def update_settings_from_form(
    settings: SchoolSettings,
    smtp_host: str | None,
    smtp_port: int,
    smtp_user: str | None,
    smtp_password: str | None,
    smtp_from: str | None,
    afip_cuit: str | None,
    afip_business_name: str | None,
    afip_point_of_sale: int,
    afip_environment: str,
    invoice_primary_color: str | None,
    invoice_footer_text: str | None,
    invoice_legal_text: str | None
):
    settings.smtp_host = smtp_host
    settings.smtp_port = smtp_port
    settings.smtp_user = smtp_user
    settings.smtp_password = smtp_password
    settings.smtp_from = smtp_from

    settings.afip_cuit = str(afip_cuit or "").strip() or None
    settings.afip_business_name = str(afip_business_name or "").strip() or None
    settings.afip_point_of_sale = afip_point_of_sale
    settings.afip_environment = afip_environment

    settings.invoice_primary_color = str(invoice_primary_color or "").strip() or None
    settings.invoice_footer_text = str(invoice_footer_text or "").strip() or None
    settings.invoice_legal_text = str(invoice_legal_text or "").strip() or None

    if settings.afip_business_name:
        settings.afip_server_hostname = AFIPCertificateService.build_hostname(
            settings.afip_business_name
        )


def save_uploaded_files(
    settings: SchoolSettings,
    school_id: int,
    afip_cert_file: UploadFile | None = None,
    afip_key_file: UploadFile | None = None,
    afip_csr_file: UploadFile | None = None,
    invoice_logo_file: UploadFile | None = None
):
    cert_dir = os.path.join(
        "storage",
        "certs",
        f"school_{school_id}"
    )

    os.makedirs(cert_dir, exist_ok=True)

    if afip_cert_file and afip_cert_file.filename:
        cert_path = os.path.join(cert_dir, "cert.crt")

        with open(cert_path, "wb") as buffer:
            shutil.copyfileobj(afip_cert_file.file, buffer)

        settings.afip_cert_path = cert_path

    if afip_key_file and afip_key_file.filename:
        key_path = os.path.join(cert_dir, "private.key")

        with open(key_path, "wb") as buffer:
            shutil.copyfileobj(afip_key_file.file, buffer)

        settings.afip_key_path = key_path

    if afip_csr_file and afip_csr_file.filename:
        csr_path = os.path.join(cert_dir, "request.csr")

        with open(csr_path, "wb") as buffer:
            shutil.copyfileobj(afip_csr_file.file, buffer)

    logo_dir = os.path.join(
        "storage",
        "logos",
        f"school_{school_id}"
    )

    os.makedirs(logo_dir, exist_ok=True)

    if invoice_logo_file and invoice_logo_file.filename:
        extension = os.path.splitext(invoice_logo_file.filename)[1] or ".png"
        extension = extension.lower()

        if extension not in [".png", ".jpg", ".jpeg"]:
            extension = ".png"

        logo_path = os.path.join(logo_dir, f"logo{extension}")

        with open(logo_path, "wb") as buffer:
            shutil.copyfileobj(invoice_logo_file.file, buffer)

        settings.invoice_logo_path = logo_path


def render_settings(
    request: Request,
    school: School,
    settings: SchoolSettings,
    arca_test_result=None,
    arca_invoice_result=None
):
    return templates.TemplateResponse(
        "settings/form.html",
        {
            "request": request,
            "school": school,
            "settings": settings,
            "arca_test_result": arca_test_result,
            "arca_invoice_result": arca_invoice_result
        }
    )


@router.get("/{school_id}/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    school_id: int,
    db: Session = Depends(get_db)
):
    if not require_admin_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)

    school = get_school(db=db, school_id=school_id)

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    settings = get_or_create_settings(db=db, school_id=school_id)

    return render_settings(
        request=request,
        school=school,
        settings=settings
    )


@router.post("/{school_id}/settings")
async def save_settings(
    request: Request,
    school_id: int,

    smtp_host: str = Form(None),
    smtp_port: int = Form(587),
    smtp_user: str = Form(None),
    smtp_password: str = Form(None),
    smtp_from: str = Form(None),

    afip_cuit: str = Form(None),
    afip_business_name: str = Form(None),
    afip_point_of_sale: int = Form(1),
    afip_environment: str = Form("mock"),

    invoice_primary_color: str = Form(None),
    invoice_footer_text: str = Form(None),
    invoice_legal_text: str = Form(None),

    afip_cert_file: UploadFile | None = File(None),
    afip_key_file: UploadFile | None = File(None),
    afip_csr_file: UploadFile | None = File(None),
    invoice_logo_file: UploadFile | None = File(None),

    db: Session = Depends(get_db)
):
    if not require_admin_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)

    school = get_school(db=db, school_id=school_id)

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    settings = get_or_create_settings(db=db, school_id=school_id)

    update_settings_from_form(
        settings=settings,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        smtp_from=smtp_from,
        afip_cuit=afip_cuit,
        afip_business_name=afip_business_name,
        afip_point_of_sale=afip_point_of_sale,
        afip_environment=afip_environment,
        invoice_primary_color=invoice_primary_color,
        invoice_footer_text=invoice_footer_text,
        invoice_legal_text=invoice_legal_text
    )

    save_uploaded_files(
        settings=settings,
        school_id=school_id,
        afip_cert_file=afip_cert_file,
        afip_key_file=afip_key_file,
        afip_csr_file=afip_csr_file,
        invoice_logo_file=invoice_logo_file
    )

    db.commit()

    return RedirectResponse(
        url=f"/schools/{school_id}/settings",
        status_code=303
    )


@router.post("/{school_id}/settings/afip/test", response_class=HTMLResponse)
async def test_afip_settings(
    request: Request,
    school_id: int,

    smtp_host: str = Form(None),
    smtp_port: int = Form(587),
    smtp_user: str = Form(None),
    smtp_password: str = Form(None),
    smtp_from: str = Form(None),

    afip_cuit: str = Form(None),
    afip_business_name: str = Form(None),
    afip_point_of_sale: int = Form(1),
    afip_environment: str = Form("mock"),

    invoice_primary_color: str = Form(None),
    invoice_footer_text: str = Form(None),
    invoice_legal_text: str = Form(None),

    afip_cert_file: UploadFile | None = File(None),
    afip_key_file: UploadFile | None = File(None),
    afip_csr_file: UploadFile | None = File(None),
    invoice_logo_file: UploadFile | None = File(None),

    db: Session = Depends(get_db)
):
    if not require_admin_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)

    school = get_school(db=db, school_id=school_id)

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    settings = get_or_create_settings(db=db, school_id=school_id)

    update_settings_from_form(
        settings=settings,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        smtp_from=smtp_from,
        afip_cuit=afip_cuit,
        afip_business_name=afip_business_name,
        afip_point_of_sale=afip_point_of_sale,
        afip_environment=afip_environment,
        invoice_primary_color=invoice_primary_color,
        invoice_footer_text=invoice_footer_text,
        invoice_legal_text=invoice_legal_text
    )

    save_uploaded_files(
        settings=settings,
        school_id=school_id,
        afip_cert_file=afip_cert_file,
        afip_key_file=afip_key_file,
        afip_csr_file=afip_csr_file,
        invoice_logo_file=invoice_logo_file
    )

    db.commit()
    db.refresh(settings)

    afip = AFIPService(settings=settings)

    return render_settings(
        request=request,
        school=school,
        settings=settings,
        arca_test_result=afip.test_configuration()
    )


@router.post("/{school_id}/settings/afip/test-invoice", response_class=HTMLResponse)
async def test_afip_invoice(
    request: Request,
    school_id: int,

    smtp_host: str = Form(None),
    smtp_port: int = Form(587),
    smtp_user: str = Form(None),
    smtp_password: str = Form(None),
    smtp_from: str = Form(None),

    afip_cuit: str = Form(None),
    afip_business_name: str = Form(None),
    afip_point_of_sale: int = Form(1),
    afip_environment: str = Form("mock"),

    invoice_primary_color: str = Form(None),
    invoice_footer_text: str = Form(None),
    invoice_legal_text: str = Form(None),

    afip_cert_file: UploadFile | None = File(None),
    afip_key_file: UploadFile | None = File(None),
    afip_csr_file: UploadFile | None = File(None),
    invoice_logo_file: UploadFile | None = File(None),

    db: Session = Depends(get_db)
):
    if not require_admin_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)

    school = get_school(db=db, school_id=school_id)

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    settings = get_or_create_settings(db=db, school_id=school_id)

    update_settings_from_form(
        settings=settings,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        smtp_from=smtp_from,
        afip_cuit=afip_cuit,
        afip_business_name=afip_business_name,
        afip_point_of_sale=afip_point_of_sale,
        afip_environment=afip_environment,
        invoice_primary_color=invoice_primary_color,
        invoice_footer_text=invoice_footer_text,
        invoice_legal_text=invoice_legal_text
    )

    save_uploaded_files(
        settings=settings,
        school_id=school_id,
        afip_cert_file=afip_cert_file,
        afip_key_file=afip_key_file,
        afip_csr_file=afip_csr_file,
        invoice_logo_file=invoice_logo_file
    )

    db.commit()
    db.refresh(settings)

    afip = AFIPService(settings=settings)

    try:
        response = afip.crear_factura(
            importe=100,
            doc_tipo=99,
            doc_nro=0,
            condicion_iva=5
        )

        cabecera = response["FeCabResp"]
        detalle = response["FeDetResp"]["FECAEDetResponse"][0]

        result = {
            "ok": detalle["Resultado"] == "A",
            "message": "Factura de prueba emitida correctamente.",
            "data": {
                "punto_venta": cabecera["PtoVta"],
                "tipo_comprobante": cabecera["CbteTipo"],
                "numero": detalle["CbteDesde"],
                "resultado": detalle["Resultado"],
                "cae": detalle["CAE"],
                "cae_vto": detalle["CAEFchVto"]
            }
        }

    except Exception as e:
        result = {
            "ok": False,
            "message": "No se pudo emitir la factura de prueba.",
            "errors": [str(e)]
        }

    return render_settings(
        request=request,
        school=school,
        settings=settings,
        arca_invoice_result=result
    )


@router.post("/{school_id}/settings/afip/generate-csr")
async def generate_afip_csr(
    request: Request,
    school_id: int,
    cuit: str = Form(...),
    business_name: str = Form(...),
    db: Session = Depends(get_db)
):
    if not require_admin_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)

    school = get_school(db=db, school_id=school_id)

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    settings = get_or_create_settings(db=db, school_id=school_id)

    result = AFIPCertificateService.generate_key_and_csr(
        school_id=school_id,
        cuit=cuit,
        business_name=business_name
    )

    settings.afip_cuit = str(cuit or "").strip()
    settings.afip_business_name = str(business_name or "").strip()
    settings.afip_server_hostname = result["hostname"]
    settings.afip_key_path = result["key_path"]

    db.commit()

    return RedirectResponse(
        url=f"/schools/{school_id}/settings",
        status_code=303
    )


@router.get("/{school_id}/settings/afip/download-csr")
async def download_afip_csr(
    request: Request,
    school_id: int,
    db: Session = Depends(get_db)
):
    if not require_admin_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)

    school = get_school(db=db, school_id=school_id)

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    csr_path = os.path.join(
        "storage",
        "certs",
        f"school_{school_id}",
        "request.csr"
    )

    if not os.path.exists(csr_path):
        return RedirectResponse(
            url=f"/schools/{school_id}/settings",
            status_code=303
        )

    return FileResponse(
        csr_path,
        media_type="application/octet-stream",
        filename=f"school_{school_id}_afip_request.csr"
    )


@router.get("/{school_id}/settings/afip/diagnostic", response_class=HTMLResponse)
async def afip_diagnostic(
    request: Request,
    school_id: int,
    db: Session = Depends(get_db)
):
    if not require_admin_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)

    school = get_school(db=db, school_id=school_id)

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    settings = get_or_create_settings(
        db=db,
        school_id=school_id
    )

    cert_exists = bool(
        settings.afip_cert_path
        and os.path.exists(settings.afip_cert_path)
    )

    key_exists = bool(
        settings.afip_key_path
        and os.path.exists(settings.afip_key_path)
    )

    csr_path = os.path.join(
        "storage",
        "certs",
        f"school_{school_id}",
        "request.csr"
    )

    csr_exists = os.path.exists(csr_path)

    logo_exists = bool(
        settings.invoice_logo_path
        and os.path.exists(settings.invoice_logo_path)
    )

    smtp_ok = bool(
        settings.smtp_host
        and settings.smtp_user
        and settings.smtp_password
        and settings.smtp_from
    )

    arca_local_ok = bool(
        settings.afip_cuit
        and settings.afip_business_name
        and settings.afip_point_of_sale
        and settings.afip_environment
        and (
            settings.afip_environment == "mock"
            or (cert_exists and key_exists)
        )
    )

    ta_info = {
        "exists": False,
        "valid": False,
        "path": None,
        "expiration": None
    }

    ta_path = os.path.join(
        "storage",
        "afip_ta",
        f"school_{school_id}",
        f"ta_{settings.afip_environment}_wsfe.json"
    )

    if os.path.exists(ta_path):
        ta_info["exists"] = True
        ta_info["path"] = ta_path

        try:
            with open(ta_path, "r", encoding="utf-8") as f:
                ta_data = json.load(f)

            expiration = ta_data.get("expiration")
            ta_info["expiration"] = expiration

            if expiration:
                expiration_dt = datetime.fromisoformat(
                    expiration.replace("Z", "+00:00")
                )

                if expiration_dt.tzinfo is None:
                    expiration_dt = expiration_dt.replace(
                        tzinfo=timezone.utc
                    )

                ta_info["valid"] = datetime.now(timezone.utc) < expiration_dt

        except Exception as e:
            ta_info["error"] = str(e)

    connection_result = None

    if arca_local_ok:
        try:
            afip = AFIPService(settings=settings)
            connection_result = afip.test_configuration()
        except Exception as e:
            connection_result = {
                "ok": False,
                "message": "No se pudo conectar con ARCA.",
                "errors": [str(e)]
            }

    last_invoice = (
        db.query(Invoice)
        .filter(Invoice.school_id == school_id)
        .order_by(Invoice.id.desc())
        .first()
    )

    ready_to_bill = bool(
        smtp_ok
        and arca_local_ok
        and (
            settings.afip_environment == "mock"
            or (connection_result and connection_result.get("ok"))
        )
    )

    diagnostic = {
        "smtp_ok": smtp_ok,
        "arca_local_ok": arca_local_ok,
        "cert_exists": cert_exists,
        "key_exists": key_exists,
        "csr_exists": csr_exists,
        "logo_exists": logo_exists,
        "csr_path": csr_path,
        "ta_info": ta_info,
        "connection_result": connection_result,
        "last_invoice": last_invoice,
        "ready_to_bill": ready_to_bill
    }

    return templates.TemplateResponse(
        "settings/afip_diagnostic.html",
        {
            "request": request,
            "school": school,
            "settings": settings,
            "diagnostic": diagnostic
        }
    )