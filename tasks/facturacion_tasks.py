# tasks/facturacion_tasks.py
# Tareas Celery optimizadas para procesamiento secuencial de ARCA y asíncrono para PDFs/emails.

import logging
import os
from datetime import datetime
from celery import Celery
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv()

logger = logging.getLogger(__name__)

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_URL = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

celery_app = Celery(
    "facturacion_escolar",
    broker=BROKER_URL,
    backend=RESULT_URL,
)

celery_app.conf.update(
    task_serializer             = "json",
    result_serializer           = "json",
    accept_content              = ["json"],
    timezone                    = "America/Argentina/Buenos_Aires",
    enable_utc                  = True,
    task_acks_late              = True,       # Se confirma la tarea solo al finalizar con éxito
    worker_prefetch_multiplier  = 1,          # Evita que un worker acapare tareas de más
)


# ═══════════════════════════════════════════════════════════════════════════════
# TAREA 1: Orquestar el lote completo (Ejecución secuencial de CAE)
# ═══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name="tasks.procesar_lote")
def procesar_lote_task(lote_id: int, escuela_id: int):
    from database import SessionLocal
    from models.models import LoteFacturacion, Factura, Escuela, EstadoLote, EstadoFactura
    from services.arca_client import get_arca_client

    db = SessionLocal()
    try:
        lote = db.query(LoteFacturacion).filter(LoteFacturacion.id == lote_id).first()
        if not lote:
            logger.error("Lote %s no encontrado", lote_id)
            return

        lote.estado = EstadoLote.PROCESANDO
        lote.iniciado_en = datetime.now()
        db.commit()

        escuela = db.query(Escuela).filter(Escuela.id == escuela_id).first()
        arca = get_arca_client(escuela)

        # Buscamos las facturas pendientes
        facturas = (
            db.query(Factura)
            .filter(Factura.lote_id == lote_id, Factura.estado == EstadoFactura.PENDIENTE)
            .order_by(Factura.id.asc())
            .all()
        )

        logger.info("Lote %s: Iniciando procesamiento de %s facturas...", lote_id, len(facturas))

        # Obtenemos el último número autorizado en AFIP una sola vez al inicio del lote
        ultimo_comprobante = arca.obtener_ultimo_comprobante(
            escuela.punto_venta, escuela.tipo_comprobante
        )

        for factura in facturas:
            # Incrementamos el número de forma segura uno a uno en el bucle
            ultimo_comprobante += 1
            factura.intentos += 1
            
            try:
                # 1. Petición estricta a ARCA
                resultado = arca.solicitar_cae(
                    punto_venta      = escuela.punto_venta,
                    tipo_comprobante = escuela.tipo_comprobante,
                    nro_comprobante  = ultimo_comprobante,
                    fecha_emision    = datetime.now(),
                    monto_total      = float(factura.monto),
                    cuit_receptor    = factura.alumno.dni,
                )

                if resultado.exito:
                    # Guardamos la aprobación fiscal de inmediato
                    factura.cae = resultado.cae
                    factura.vencimiento_cae = resultado.vencimiento_cae
                    factura.nro_comprobante = resultado.nro_comprobante
                    factura.estado = EstadoFactura.EMITIDA
                    db.commit()

                    # Despachamos las tareas secundarias (PDF y Mail) en segundo plano total
                    # para que no frenen el bucle fiscal
                    procesar_post_emision_task.delay(factura.id, escuela_id)
                    _incrementar_lote_emitida(db, lote_id)
                else:
                    # Error de validación de negocio devuelto por AFIP
                    factura.estado = EstadoFactura.ERROR
                    factura.mensaje_error = resultado.mensaje_error
                    db.commit()
                    _incrementar_lote_error(db, lote_id)
                    # Si AFIP rechaza el número, decrementamos el contador para que la próxima factura intente con este mismo número
                    ultimo_comprobante -= 1

            except Exception as e:
                # Si se corta internet o se cae el servidor de AFIP a nivel de red, pausamos el lote entero
                db.rollback()
                logger.error("Fallo de red o servicio caótico en ARCA. Frenando lote para reintento. Error: %s", e)
                factura.estado = EstadoFactura.ERROR
                factura.mensaje_error = "Servicio de ARCA temporalmente no disponible (Timeout)."
                db.commit()
                _incrementar_lote_error(db, lote_id)
                ultimo_comprobante -= 1

    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# TAREA 2: Post-Emisión Paralela (Generación de PDF y envío de Email)
# ═══════════════════════════════════════════════════════════════════════════════

@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    name="tasks.procesar_post_emision"
)
def procesar_post_emision_task(self, factura_id: int, escuela_id: int):
    """
    Esta tarea corre 100% en paralelo. Si falla el mail, se reintenta sola, 
    ¡pero sin volver a tocar jamás la API de AFIP! Protege tu negocio.
    """
    from database import SessionLocal
    from models.models import Factura, Escuela
    # CORRECCIÓN: Apuntamos de forma limpia a los nuevos módulos individuales estructurados
    from services.pdf_service import generar_pdf_factura
    from services.email_service import enviar_factura_email

    db = SessionLocal()
    try:
        factura = db.query(Factura).filter(Factura.id == factura_id).first()
        if not factura or not factura.cae:
            return

        escuela = db.query(Escuela).filter(Escuela.id == escuela_id).first()
        alumno = factura.alumno

        # Generar el PDF si no se generó previamente
        if not factura.url_pdf:
            pdf_path = generar_pdf_factura(
                factura_id        = factura.id,
                nro_comprobante   = factura.nro_comprobante,
                punto_venta       = escuela.punto_venta,
                tipo_cbte         = escuela.tipo_comprobante,
                cae               = factura.cae,
                vencimiento_cae   = factura.vencimiento_cae,
                alumno_nombre     = alumno.nombre_completo,
                alumno_dni        = alumno.dni,
                email_tutor       = alumno.email_tutor,
                curso             = alumno.curso or "",
                periodo_str       = factura.periodo_str,
                monto             = factura.monto,
                escuela_nombre    = escuela.nombre,
                escuela_cuit      = escuela.cuit,
                escuela_domicilio = escuela.domicilio or "",
                fecha_emision     = datetime.now(),
            )
            factura.url_pdf = pdf_path
            db.commit()

        # Enviar por Correo Electrónico
        if not factura.email_enviado:
            email_ok = enviar_factura_email(
                email_destino  = alumno.email_tutor,
                nombre_alumno  = alumno.nombre_completo,
                periodo_str    = factura.periodo_str,
                monto          = float(factura.monto),
                pdf_path       = factura.url_pdf,
                escuela_nombre = escuela.nombre,
            )
            factura.email_enviado = email_ok
            db.commit()
            
            # Si el proveedor de mail rebotó, forzamos reintento exclusivo de mail
            if not email_ok:
                raise RuntimeWarning("El servidor SMTP rechazó el envío temporalmente.")

        logger.info("Post-procesamiento completado para Factura ID: %s", factura_id)

    except Exception as exc:
        db.rollback()
        logger.warning("Fallo en post-emisión (PDF/Email) para factura %s. Reintentando... Error: %s", factura_id, exc)
        raise self.retry(exc=exc)
    finally:
        db.close()


# ── Contadores Atómicos Seguros para el Polling ────────────────────────────────

def _incrementar_lote_emitida(db: Session, lote_id: int):
    from models.models import LoteFacturacion
    lote = db.query(LoteFacturacion).filter_by(id=lote_id).first()
    if lote:
        lote.emitidas = LoteFacturacion.emitidas + 1
        db.commit()
        db.refresh(lote)
        _actualizar_porcentaje_y_revisar(db, lote)

def _incrementar_lote_error(db: Session, lote_id: int):
    from models.models import LoteFacturacion
    lote = db.query(LoteFacturacion).filter_by(id=lote_id).first()
    if lote:
        lote.con_error = LoteFacturacion.con_error + 1
        db.commit()
        db.refresh(lote)
        _actualizar_porcentaje_y_revisar(db, lote)

def _actualizar_porcentaje_y_revisar(db: Session, lote):
    from models.models import EstadoLote
    
    procesadas = lote.emitidas + lote.con_error
    
    # OPTIMIZACIÓN: Calculamos y guardamos el porcentaje en cada iteración para que la UI responda en tiempo real
    if lote.total_facturas > 0:
        lote.porcentaje_avance = int((procesadas / lote.total_facturas) * 100)
    else:
        lote.porcentaje_avance = 100

    if procesadas >= lote.total_facturas:
        lote.completado_en = datetime.now()
        lote.estado = (
            EstadoLote.CON_ERRORES if lote.con_error > 0
            else EstadoLote.COMPLETADO
        )
    
    db.commit()