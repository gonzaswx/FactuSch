# routers/facturacion.py
# Rutas para gestión de facturación: inicio de lote, estado en tiempo real, historial y descarga de PDFs.

from datetime import datetime
from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from utils.templates import templates

from database import get_db
# Importaciones corregidas apuntando al módulo real
from models.models import (
    Alumno, Factura, LoteFacturacion,
    EstadoFactura, EstadoLote,
)
from routers.auth import get_escuela_actual

router    = APIRouter(prefix="/facturacion", tags=["facturacion"])



# ── GET /facturacion ───────────────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def vista_facturacion(
    request: Request,
    db:      Session = Depends(get_db),
    escuela  = Depends(get_escuela_actual),
):
    lotes = (
        db.query(LoteFacturacion)
        .filter(LoteFacturacion.escuela_id == escuela.id)
        .order_by(LoteFacturacion.creado_en.desc())
        .limit(10)
        .all()
    )
    hoy = datetime.now()
    return templates.TemplateResponse("facturacion.html", {
        "request":    request,
        "escuela":    escuela,
        "lotes":      lotes,
        "mes_actual": hoy.month,
        "anio_actual": hoy.year,
    })


# ── POST /facturacion/iniciar ──────────────────────────────────────────────────
@router.post("/iniciar")
async def iniciar_facturacion(
    request: Request,
    mes:     int = Form(...),
    anio:    int = Form(...),
    db:      Session = Depends(get_db),
    escuela  = Depends(get_escuela_actual),
):
    """
    Genera las facturas PENDIENTES de forma masiva en la BD y despierta
    al worker secuencial de Celery de forma asíncrona e inmediata.
    """
    # 1. Validar que no exista ya un lote para el período
    lote_existente = db.query(LoteFacturacion).filter(
        LoteFacturacion.escuela_id  == escuela.id,
        LoteFacturacion.periodo_mes == mes,
        LoteFacturacion.periodo_anio == anio,
    ).first()

    if lote_existente:
        return templates.TemplateResponse("facturacion.html", {
            "request": request,
            "escuela": escuela,
            "lotes":   [lote_existente],
            "error":   f"Ya existe un lote para {lote_existente.periodo_str} ({lote_existente.estado.value}).",
            "mes_actual": mes,
            "anio_actual": anio,
        })

    # 2. Obtener alumnos activos
    alumnos = db.query(Alumno).filter(
        Alumno.escuela_id == escuela.id,
        Alumno.activo     == True,
    ).all()

    if not alumnos:
        return templates.TemplateResponse("facturacion.html", {
            "request": request,
            "escuela": escuela,
            "lotes":   [],
            "error":   "No hay alumnos activos para facturar.",
            "mes_actual": mes,
            "anio_actual": anio,
        })

    # 3. OPTIMIZACIÓN SUPREMA: Traer de un solo golpe quiénes ya fueron facturados este mes
    alumnos_ids = [a.id for a in alumnos]
    facturas_ya_existentes = (
        db.query(Factura.alumno_id)
        .filter(
            Factura.alumno_id.in_(alumnos_ids),
            Factura.periodo_mes == mes,
            Factura.periodo_anio == anio,
        )
        .all()
    )
    # Convertimos a un set de Python para búsquedas instantáneas O(1) en memoria
    ids_ya_facturados = {f.alumno_id for f in facturas_ya_existentes}

    # 4. Crear el encabezado del Lote
    lote = LoteFacturacion(
        escuela_id    = escuela.id,
        periodo_mes   = mes,
        periodo_anio  = anio,
        estado        = EstadoLote.EN_COLA,
        total_facturas= 0, 
    )
    db.add(lote)
    db.flush() # Obtenemos lote.id sin cerrar la transacción fiscal

    facturas_a_insertar = []
    for alumno in alumnos:
        # Si el ID ya está en el set, significa que ya tiene factura: lo salteamos
        if alumno.id in ids_ya_facturados:
            continue

        factura = Factura(
            alumno_id    = alumno.id,
            lote_id      = lote.id,
            periodo_mes  = mes,
            periodo_anio = anio,
            monto        = alumno.cuota_base,
            estado       = EstadoFactura.PENDIENTE,
        )
        facturas_a_insertar.append(factura)

    if not facturas_a_insertar:
        db.rollback()
        return templates.TemplateResponse("facturacion.html", {
            "request": request,
            "escuela": escuela,
            "lotes":   [],
            "error":   "Todas las facturas para este período ya fueron generadas previamente.",
            "mes_actual": mes,
            "anio_actual": anio,
        })

    # Guardamos masivamente en Postgres
    db.add_all(facturas_a_insertar)
    lote.total_facturas = len(facturas_a_insertar)
    db.commit()

    # 5. Despachar a la terminal de Celery de forma ultra veloz
    try:
        from tasks.facturacion_tasks import procesar_lote_task
        task = procesar_lote_task.delay(lote.id, escuela.id) # .delay() es el shorthand limpio de apply_async()
        lote.celery_task_id = task.id
        db.commit()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Memurai/Redis no disponible localmente. Lote %s guardado en Standby: %s", lote.id, exc
        )

    from fastapi.responses import RedirectResponse
    return RedirectResponse(
        url=f"/facturacion/{lote.id}",
        status_code=303,
    )

# ── GET /facturacion/{lote_id} ─────────────────────────────────────────────────
@router.get("/{lote_id}", response_class=HTMLResponse)
async def detalle_lote(
    request: Request,
    lote_id: int,
    db:      Session = Depends(get_db),
    escuela  = Depends(get_escuela_actual),
):
    lote = db.query(LoteFacturacion).filter(
        LoteFacturacion.id         == lote_id,
        LoteFacturacion.escuela_id == escuela.id,
    ).first()

    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    facturas_error = (
        db.query(Factura)
        .filter(Factura.lote_id == lote_id, Factura.estado == EstadoFactura.ERROR)
        .all()
    )

    return templates.TemplateResponse("facturacion_detalle.html", {
        "request":        request,
        "escuela":        escuela,
        "lote":           lote,
        "facturas_error": facturas_error,
    })


# ── GET /facturacion/{lote_id}/estado (API JSON para polling de carga) ─────────
@router.get("/{lote_id}/estado")
async def estado_lote(
    lote_id: int,
    db:      Session = Depends(get_db),
    escuela  = Depends(get_escuela_actual),
):
    lote = db.query(LoteFacturacion).filter(
        LoteFacturacion.id         == lote_id,
        LoteFacturacion.escuela_id == escuela.id,
    ).first()

    if not lote:
        raise HTTPException(status_code=404)

    return JSONResponse({
        "estado":          lote.estado.value,
        "total":           lote.total_facturas,
        "emitidas":        lote.emitidas,
        "con_error":       lote.con_error,
        "porcentaje": int(lote.porcentaje_avance) if lote.porcentaje_avance is not None else 0,
        "completado":      lote.estado in (EstadoLote.COMPLETADO, EstadoLote.CON_ERRORES),
    })


# ── GET /historial ─────────────────────────────────────────────────────────────
@router.get("/historial/all", response_class=HTMLResponse)
async def historial_facturas(
    request: Request,
    mes:     int = 0,
    anio:    int = 0,
    estado:  str = "",
    pagina:  int = 1,
    db:      Session = Depends(get_db),
    escuela  = Depends(get_escuela_actual),
):
    POR_PAGINA = 25
    
    # Optimizamos con joinedload(Factura.alumno) para traer todo en una sola query SQL
    query = (
        db.query(Factura)
        .join(Alumno, Factura.alumno_id == Alumno.id)
        .options(joinedload(Factura.alumno))
        .filter(Alumno.escuela_id == escuela.id)
    )

    if mes:
        query = query.filter(Factura.periodo_mes == mes)
    if anio:
        query = query.filter(Factura.periodo_anio == anio)
    if estado:
        try:
            query = query.filter(Factura.estado == EstadoFactura(estado))
        except ValueError:
            pass

    total    = query.count()
    facturas = (
        query
        .order_by(Factura.creado_en.desc())
        .offset((pagina - 1) * POR_PAGINA)
        .limit(POR_PAGINA)
        .all()
    )

    return templates.TemplateResponse("historial_facturas.html", {
        "request":       request,
        "escuela":       escuela,
        "facturas":      facturas,
        "total":         total,
        "pagina":        pagina,
        "total_paginas": (total + POR_PAGINA - 1) // POR_PAGINA,
        "filtro_mes":    mes,
        "filtro_anio":   anio,
        "filtro_estado": estado,
        "estados":       [e.value for e in EstadoFactura],
    })


# ── GET /factura/{factura_id}/pdf ──────────────────────────────────────────────
@router.get("/factura/{factura_id}/pdf")
async def descargar_pdf(
    factura_id: int,
    db:         Session = Depends(get_db),
    escuela     = Depends(get_escuela_actual),
):
    factura = (
        db.query(Factura)
        .join(Alumno)
        .filter(
            Factura.id         == factura_id,
            Alumno.escuela_id  == escuela.id,
            Factura.url_pdf    != None,
        )
        .first()
    )
    if not factura:
        raise HTTPException(status_code=404, detail="El archivo PDF solicitado no existe o no se ha generado.")

    return FileResponse(
        path        = factura.url_pdf,
        media_type  = "application/pdf",
        filename    = f"Factura_{factura.periodo_str}_{factura.alumno.apellido}.pdf",
    )