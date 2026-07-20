from fastapi import APIRouter
from fastapi import Depends
from fastapi import Form
from fastapi import Request

from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from database import get_db

from models.school import School
from models.user import User

from services.school_service import SchoolService
from services.auth_service import AuthService

from utils.templates import templates

from routers.auth import require_admin


router = APIRouter(
    prefix="/schools",
    tags=["Schools"]
)


def clean_text(value):
    return str(value or "").strip()


def clean_cuit(value):
    return clean_text(value).replace("-", "").replace(" ", "")


def validate_required_school_data(name, cuit, email, phone, address):
    errors = []

    if not clean_text(name):
        errors.append("El nombre del colegio es obligatorio.")

    cuit = clean_cuit(cuit)

    if not cuit:
        errors.append("El CUIT es obligatorio.")
    elif not cuit.isdigit() or len(cuit) != 11:
        errors.append("El CUIT debe tener 11 números, sin guiones.")

    if not clean_text(email):
        errors.append("El email institucional es obligatorio.")

    if not clean_text(phone):
        errors.append("El teléfono es obligatorio.")

    if not clean_text(address):
        errors.append("La dirección es obligatoria.")

    return errors


def get_school_or_redirect(db: Session, school_id: int):
    return db.query(School).filter(
        School.id == school_id
    ).first()


def get_school_users(db: Session, school_id: int):
    return (
        db.query(User)
        .filter(User.school_id == school_id)
        .order_by(User.id.desc())
        .all()
    )


def render_school_users(
    request: Request,
    school: School,
    users,
    error=None
):
    return templates.TemplateResponse(
        "schools/users.html",
        {
            "request": request,
            "school": school,
            "users": users,
            "error": error
        }
    )


@router.get("/", response_class=HTMLResponse)
async def list_schools(
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    schools = SchoolService.get_all(db)

    return templates.TemplateResponse(
        "schools/list.html",
        {
            "request": request,
            "schools": schools
        }
    )


@router.get("/create", response_class=HTMLResponse)
async def create_school_page(
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(
        "schools/create.html",
        {
            "request": request,
            "error": None,
            "form": None
        }
    )


@router.post("/create", response_class=HTMLResponse)
async def create_school(
    request: Request,
    name: str = Form(...),
    cuit: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(None),
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    form = {
        "name": clean_text(name),
        "cuit": clean_cuit(cuit),
        "email": clean_text(email).lower(),
        "phone": clean_text(phone),
        "address": clean_text(address),
        "full_name": clean_text(full_name)
    }

    errors = validate_required_school_data(
        name=form["name"],
        cuit=form["cuit"],
        email=form["email"],
        phone=form["phone"],
        address=form["address"]
    )

    try:
        AuthService.validate_password(password)
    except ValueError as e:
        errors.append(str(e))

    existing_user = AuthService.get_user_by_email(
        db=db,
        email=form["email"]
    )

    if existing_user:
        errors.append("Ya existe un usuario registrado con ese email.")

    existing_school_cuit = db.query(School).filter(
        School.cuit == form["cuit"]
    ).first()

    if existing_school_cuit:
        errors.append("Ya existe un colegio registrado con ese CUIT.")

    if errors:
        return templates.TemplateResponse(
            "schools/create.html",
            {
                "request": request,
                "error": " | ".join(errors),
                "form": form
            },
            status_code=400
        )

    try:
        school = SchoolService.create(
            db=db,
            name=form["name"],
            cuit=form["cuit"],
            email=form["email"],
            phone=form["phone"],
            address=form["address"]
        )

        AuthService.create_school_user(
            db=db,
            school_id=school.id,
            email=form["email"],
            password=password,
            full_name=form["full_name"] or "Administrador principal"
        )

    except Exception as e:
        db.rollback()

        return templates.TemplateResponse(
            "schools/create.html",
            {
                "request": request,
                "error": str(e),
                "form": form
            },
            status_code=400
        )

    return RedirectResponse(
        url="/schools/",
        status_code=303
    )


@router.get("/{school_id}/edit", response_class=HTMLResponse)
async def edit_school_page(
    school_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    school = SchoolService.get_by_id(
        db=db,
        school_id=school_id
    )

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    return templates.TemplateResponse(
        "schools/edit.html",
        {
            "request": request,
            "school": school,
            "error": None
        }
    )


@router.post("/{school_id}/edit", response_class=HTMLResponse)
async def edit_school(
    school_id: int,
    request: Request,
    name: str = Form(...),
    cuit: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    school = SchoolService.get_by_id(
        db=db,
        school_id=school_id
    )

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    form_cuit = clean_cuit(cuit)

    errors = validate_required_school_data(
        name=name,
        cuit=form_cuit,
        email=email,
        phone=phone,
        address=address
    )

    existing_school_cuit = db.query(School).filter(
        School.cuit == form_cuit,
        School.id != school_id
    ).first()

    if existing_school_cuit:
        errors.append("Ya existe otro colegio registrado con ese CUIT.")

    if errors:
        school.name = clean_text(name)
        school.cuit = form_cuit
        school.email = clean_text(email).lower()
        school.phone = clean_text(phone)
        school.address = clean_text(address)

        return templates.TemplateResponse(
            "schools/edit.html",
            {
                "request": request,
                "school": school,
                "error": " | ".join(errors)
            },
            status_code=400
        )

    try:
        SchoolService.update(
            db=db,
            school_id=school_id,
            name=clean_text(name),
            cuit=form_cuit,
            email=clean_text(email).lower(),
            phone=clean_text(phone),
            address=clean_text(address)
        )

    except Exception as e:
        return templates.TemplateResponse(
            "schools/edit.html",
            {
                "request": request,
                "school": school,
                "error": str(e)
            },
            status_code=400
        )

    return RedirectResponse(
        url="/schools",
        status_code=303
    )


@router.get("/{school_id}/users", response_class=HTMLResponse)
async def list_school_users(
    school_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    school = get_school_or_redirect(db, school_id)

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    users = get_school_users(
        db=db,
        school_id=school_id
    )

    return render_school_users(
        request=request,
        school=school,
        users=users,
        error=None
    )


@router.post("/{school_id}/users/create", response_class=HTMLResponse)
async def create_school_user(
    school_id: int,
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    school = get_school_or_redirect(db, school_id)

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    try:
        AuthService.create_school_user(
            db=db,
            school_id=school_id,
            email=email,
            password=password,
            full_name=full_name
        )

    except Exception as e:
        users = get_school_users(
            db=db,
            school_id=school_id
        )

        return render_school_users(
            request=request,
            school=school,
            users=users,
            error=str(e)
        )

    return RedirectResponse(
        url=f"/schools/{school_id}/users",
        status_code=303
    )


@router.post("/{school_id}/users/{user_id}/toggle-active")
async def toggle_school_user_active(
    school_id: int,
    user_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    admin = require_admin(request, db)

    if not admin:
        return RedirectResponse(url="/login", status_code=303)

    school_user = db.query(User).filter(
        User.id == user_id,
        User.school_id == school_id,
        User.role == "school"
    ).first()

    if not school_user:
        return RedirectResponse(
            url=f"/schools/{school_id}/users",
            status_code=303
        )

    school_user.is_active = not school_user.is_active
    db.commit()

    return RedirectResponse(
        url=f"/schools/{school_id}/users",
        status_code=303
    )


@router.post("/{school_id}/users/{user_id}/reset-password", response_class=HTMLResponse)
async def reset_school_user_password(
    school_id: int,
    user_id: int,
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    admin = require_admin(request, db)

    if not admin:
        return RedirectResponse(url="/login", status_code=303)

    school = get_school_or_redirect(db, school_id)

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    school_user = db.query(User).filter(
        User.id == user_id,
        User.school_id == school_id,
        User.role == "school"
    ).first()

    if not school_user:
        return RedirectResponse(
            url=f"/schools/{school_id}/users",
            status_code=303
        )

    try:
        AuthService.update_password(
            db=db,
            user=school_user,
            password=password
        )

    except Exception as e:
        users = get_school_users(
            db=db,
            school_id=school_id
        )

        return render_school_users(
            request=request,
            school=school,
            users=users,
            error=str(e)
        )

    return RedirectResponse(
        url=f"/schools/{school_id}/users",
        status_code=303
    )


@router.get("/{school_id}/reset-password", response_class=HTMLResponse)
async def reset_school_password_page(
    school_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    return RedirectResponse(
        url=f"/schools/{school_id}/users",
        status_code=303
    )


@router.post("/{school_id}/reset-password", response_class=HTMLResponse)
async def reset_school_password(
    school_id: int,
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    school = get_school_or_redirect(db, school_id)

    if not school:
        return RedirectResponse(url="/schools", status_code=303)

    school_user = db.query(User).filter(
        User.school_id == school_id,
        User.role == "school"
    ).order_by(User.id.asc()).first()

    if not school_user:
        return RedirectResponse(url="/schools", status_code=303)

    try:
        AuthService.update_password(
            db=db,
            user=school_user,
            password=password
        )

    except Exception as e:
        users = get_school_users(
            db=db,
            school_id=school_id
        )

        return render_school_users(
            request=request,
            school=school,
            users=users,
            error=str(e)
        )

    return RedirectResponse(
        url=f"/schools/{school_id}/users",
        status_code=303
    )


@router.post("/{school_id}/toggle-active")
async def toggle_school_active(
    school_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_admin(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    school = db.query(School).filter(
        School.id == school_id
    ).first()

    if not school:
        return RedirectResponse(
            url="/schools",
            status_code=303
        )

    school.is_active = not school.is_active

    users = db.query(User).filter(
        User.school_id == school_id
    ).all()

    for school_user in users:
        school_user.is_active = school.is_active

    db.commit()

    return RedirectResponse(
        url="/schools",
        status_code=303
    )