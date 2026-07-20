from fastapi import APIRouter
from fastapi import Depends
from fastapi import Form
from fastapi import Request

from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse

from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from database import get_db

from models.user import User
from models.school import School

from services.auth_service import AuthService


router = APIRouter(tags=["Auth"])

templates = Jinja2Templates(directory="templates")


def get_current_user(
    request: Request,
    db: Session
):
    user_id = request.cookies.get("user_id")

    if not user_id:
        return None

    try:
        user_id = int(user_id)
    except ValueError:
        return None

    user = db.query(User).filter(
        User.id == user_id,
        User.is_active == True
    ).first()

    return user


def require_login(
    request: Request,
    db: Session
):
    user = get_current_user(
        request=request,
        db=db
    )

    if not user:
        return None

    return user


def require_admin(
    request: Request,
    db: Session
):
    user = get_current_user(
        request=request,
        db=db
    )

    if not user:
        return None

    if user.role != "admin":
        return None

    return user


def require_school_access(
    request: Request,
    db: Session,
    school_id: int
):
    user = get_current_user(
        request=request,
        db=db
    )

    if not user:
        return None

    if user.role == "admin":
        return user

    if user.role == "school" and user.school_id == school_id:
        school = db.query(School).filter(
            School.id == school_id,
            School.is_active == True
        ).first()

        if school:
            return user

    return None


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "error": None
        }
    )


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = AuthService.authenticate(
        db=db,
        email=email,
        password=password
    )

    if not user:
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "error": "Email o contraseña incorrectos."
            },
            status_code=400
        )

    if user.role == "school":
        school = db.query(School).filter(
            School.id == user.school_id
        ).first()

        if not school or not school.is_active:
            return templates.TemplateResponse(
                "auth/login.html",
                {
                    "request": request,
                    "error": "La escuela se encuentra bloqueada. Contactá al administrador."
                },
                status_code=403
            )

        redirect_url = f"/schools/{user.school_id}/dashboard"

    else:
        redirect_url = "/admin/dashboard"

    response = RedirectResponse(
        url=redirect_url,
        status_code=303
    )

    response.set_cookie(
        key="user_id",
        value=str(user.id),
        httponly=True
    )

    response.set_cookie(
        key="role",
        value=user.role,
        httponly=True
    )

    if user.school_id:
        response.set_cookie(
            key="school_id",
            value=str(user.school_id),
            httponly=True
        )

    return response

@router.get("/debug-session")
async def debug_session(
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(
        request=request,
        db=db
    )

    return {
        "cookies": {
            "user_id": request.cookies.get("user_id"),
            "role": request.cookies.get("role"),
            "school_id": request.cookies.get("school_id")
        },
        "user": {
            "id": user.id if user else None,
            "email": user.email if user else None,
            "role": user.role if user else None,
            "is_active": user.is_active if user else None,
            "school_id": user.school_id if user else None
        } if user else None
    }

@router.get("/logout")
async def logout():
    response = RedirectResponse(
        url="/login",
        status_code=303
    )

    response.delete_cookie("user_id")
    response.delete_cookie("role")
    response.delete_cookie("school_id")

    return response