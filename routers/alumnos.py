# routers/alumnos.py
# Rutas para gestión de alumnos: listado, búsqueda y carga por CSV.

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Alumno, Factura
from routers.auth import get_escuela_actual
from utils.csv_importer import importar_alumnos_desde_csv
from utils.templates import templates

router    = APIRouter(prefix="/alumnos", tags=["alumnos"])



@router.get("", response_class=HTMLResponse)
async def lista_alumnos(
    request:  Request,
    busqueda: str = "",
    pagina:   int = 1,
    db:       Session = Depends(get_db),
    escuela   = Depends(get_escuela_actual),
):
    POR_PAGINA = 20
    query = db.query(Alumno).filter(
        Alumno.escuela_id == escuela.id,
        Alumno.activo     == True,
    )

    if busqueda.strip():
        termino = f"%{busqueda.strip()}%"
        query = query.filter(
            (Alumno.dni.ilike(termino))
            | (Alumno.nombre.ilike(termino))
            | (Alumno.apellido.ilike(termino))
        )

    total     = query.count()
    alumnos   = (
        query
        .order_by(Alumno.apellido, Alumno.nombre)
        .offset((pagina - 1) * POR_PAGINA)
        .limit(POR_PAGINA)
        .all()
    )
    total_paginas = (total + POR_PAGINA - 1) // POR_PAGINA

    return templates.TemplateResponse("alumnos.html", {
        "request":       request,
        "escuela":       escuela,
        "alumnos":       alumnos,
        "busqueda":      busqueda,
        "pagina":        pagina,
        "total":         total,
        "total_paginas": total_paginas,
    })


@router.post("/upload-csv", response_class=HTMLResponse)
async def subir_csv(
    request: Request,
    archivo: UploadFile = File(...),
    db:      Session = Depends(get_db),
    escuela  = Depends(get_escuela_actual),
):
    contenido = await archivo.read()
    resultado = importar_alumnos_desde_csv(contenido, escuela.id, db)

    return templates.TemplateResponse("alumnos.html", {
        "request":    request,
        "escuela":    escuela,
        "alumnos":    db.query(Alumno).filter_by(escuela_id=escuela.id, activo=True)
                        .order_by(Alumno.apellido).limit(20).all(),
        "busqueda":   "",
        "pagina":     1,
        "total":      db.query(Alumno).filter_by(escuela_id=escuela.id).count(),
        "total_paginas": 1,
        "resultado_csv": resultado,
    })


@router.get("/{alumno_id}/facturas", response_class=HTMLResponse)
async def historial_alumno(
    request:   Request,
    alumno_id: int,
    db:        Session = Depends(get_db),
    escuela    = Depends(get_escuela_actual),
):
    alumno = db.query(Alumno).filter(
        Alumno.id         == alumno_id,
        Alumno.escuela_id == escuela.id,
    ).first()

    if not alumno:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/alumnos")

    facturas = (
        db.query(Factura)
        .filter(Factura.alumno_id == alumno_id)
        .order_by(Factura.periodo_anio.desc(), Factura.periodo_mes.desc())
        .all()
    )

    return templates.TemplateResponse("historial_alumno.html", {
        "request":  request,
        "escuela":  escuela,
        "alumno":   alumno,
        "facturas": facturas,
    })