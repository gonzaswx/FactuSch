from fastapi import APIRouter
from fastapi import Depends
from fastapi import Form
from fastapi import Request

from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from database import get_db

from models.school import School

from services.school_level_service import SchoolLevelService

from utils.templates import templates

from routers.auth import require_school_access


router = APIRouter(
    prefix="/schools/{school_id}/levels",
    tags=["School Levels"]
)


def get_school(
    db: Session,
    school_id: int
):
    return db.query(School).filter(
        School.id == school_id
    ).first()


@router.get("/", response_class=HTMLResponse)
async def list_levels(
    school_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_school_access(
        request=request,
        db=db,
        school_id=school_id
    )

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    school = get_school(
        db=db,
        school_id=school_id
    )

    if not school:
        return RedirectResponse(
            url="/schools",
            status_code=303
        )

    levels = SchoolLevelService.get_by_school(
        db=db,
        school_id=school_id,
        include_inactive=True
    )

    return templates.TemplateResponse(
        "levels/list.html",
        {
            "request": request,
            "school": school,
            "levels": levels
        }
    )


@router.get("/create", response_class=HTMLResponse)
async def create_level_page(
    school_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_school_access(
        request=request,
        db=db,
        school_id=school_id
    )

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    school = get_school(
        db=db,
        school_id=school_id
    )

    if not school:
        return RedirectResponse(
            url="/schools",
            status_code=303
        )

    return templates.TemplateResponse(
        "levels/create.html",
        {
            "request": request,
            "school": school,
            "error": None
        }
    )


@router.post("/create", response_class=HTMLResponse)
async def create_level(
    school_id: int,
    request: Request,
    name: str = Form(...),
    alias: str = Form(...),
    monthly_fee: float = Form(...),
    point_of_sale: int = Form(...),
    db: Session = Depends(get_db)
):
    user = require_school_access(
        request=request,
        db=db,
        school_id=school_id
    )

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    school = get_school(
        db=db,
        school_id=school_id
    )

    if not school:
        return RedirectResponse(
            url="/schools",
            status_code=303
        )

    try:
        SchoolLevelService.create(
            db=db,
            school_id=school_id,
            name=name,
            alias=alias,
            monthly_fee=monthly_fee,
            point_of_sale=point_of_sale
        )

    except Exception as e:
        return templates.TemplateResponse(
            "levels/create.html",
            {
                "request": request,
                "school": school,
                "error": str(e)
            },
            status_code=400
        )

    return RedirectResponse(
        url=f"/schools/{school_id}/levels",
        status_code=303
    )


@router.get("/{level_id}/edit", response_class=HTMLResponse)
async def edit_level_page(
    school_id: int,
    level_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_school_access(
        request=request,
        db=db,
        school_id=school_id
    )

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    school = get_school(
        db=db,
        school_id=school_id
    )

    level = SchoolLevelService.get_by_id(
        db=db,
        school_id=school_id,
        level_id=level_id
    )

    if not school or not level:
        return RedirectResponse(
            url=f"/schools/{school_id}/levels",
            status_code=303
        )

    return templates.TemplateResponse(
        "levels/edit.html",
        {
            "request": request,
            "school": school,
            "level": level,
            "error": None
        }
    )


@router.post("/{level_id}/edit", response_class=HTMLResponse)
async def edit_level(
    school_id: int,
    level_id: int,
    request: Request,
    name: str = Form(...),
    alias: str = Form(...),
    monthly_fee: float = Form(...),
    point_of_sale: int = Form(...),
    db: Session = Depends(get_db)
):
    user = require_school_access(
        request=request,
        db=db,
        school_id=school_id
    )

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    school = get_school(
        db=db,
        school_id=school_id
    )

    level = SchoolLevelService.get_by_id(
        db=db,
        school_id=school_id,
        level_id=level_id
    )

    if not school or not level:
        return RedirectResponse(
            url=f"/schools/{school_id}/levels",
            status_code=303
        )

    try:
        SchoolLevelService.update(
            db=db,
            school_id=school_id,
            level_id=level_id,
            name=name,
            alias=alias,
            monthly_fee=monthly_fee,
            point_of_sale=point_of_sale
        )

    except Exception as e:
        return templates.TemplateResponse(
            "levels/edit.html",
            {
                "request": request,
                "school": school,
                "level": level,
                "error": str(e)
            },
            status_code=400
        )

    return RedirectResponse(
        url=f"/schools/{school_id}/levels",
        status_code=303
    )


@router.post("/{level_id}/toggle-active")
async def toggle_level_active(
    school_id: int,
    level_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = require_school_access(
        request=request,
        db=db,
        school_id=school_id
    )

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    try:
        SchoolLevelService.toggle_active(
            db=db,
            school_id=school_id,
            level_id=level_id
        )

    except Exception:
        pass

    return RedirectResponse(
        url=f"/schools/{school_id}/levels",
        status_code=303
    )