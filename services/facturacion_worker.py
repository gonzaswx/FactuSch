# services/facturacion_worker.py
import logging
import asyncio
from datetime import datetime
from decimal import Decimal
# Importamos tus servicios ya listos
from services.pdf_service import generar_pdf_factura
from services.email_service import enviar_factura_email

logger = logging.getLogger(__name__)

async def procesar_lote_background(lote_id: int, db_session_factory, escuela_data: dict, periodo_str: str):
    """
    Worker que se ejecuta en segundo plano.
    db_session_factory: Función o clase para abrir una conexión limpia a la DB.
    escuela_data: Diccionario con CUIT, Nombre, Domicilio, etc.
    """
    # 1. Abrir sesión de base de datos de forma limpia
    # (Se usa un factory porque al ser un hilo de fondo, necesita su propia conexión)
    db = db_session_factory()
    
    try:
        logger.info(f"Iniciando procesamiento del Lote ID: {lote_id}")
        
        # 2. Buscar los alumnos que entran en este lote (ejemplo: todos los activos)
        # NOTA: Ajustá esta consulta a tus modelos reales de SQLAlchemy.
        # alumnos = db.execute("SELECT * FROM agenda.alumnos WHERE activo = true").fetchall()
        alumnos = [
            {"id": 1, "nombre": "Juan Pérez", "dni": "45678912", "email_tutor": "tutorjuan@gmail.com", "curso": "1° Grado A", "monto": Decimal("15000.00")},
            {"id": 2, "nombre": "Sofía Rodriguez", "dni": "46123456", "email_tutor": "tutosofia@gmail.com", "curso": "3° Año B", "monto": Decimal("18000.00")},
        ]
        
        total_alumnos = len(alumnos)
        if total_alumnos == 0:
            # Actualizar lote a finalizado con 100% si no hay alumnos
            db.execute(
                "UPDATE agenda.lotes_facturacion SET estado = 'FINALIZADO', porcentaje_avance = 100 WHERE id = :id",
                {"id": lote_id}
            )
            db.commit()
            return

        for index, alumno in enumerate(alumnos, start=1):
            try:
                # ── STEP 1: Conexión simulada con ARCA / AFIP ──
                # Acá irá la llamada al webservice de factura electrónica WSFEX / WSASS.
                # Por ahora, simulamos una demora de red de 1.5 segundos.
                await asyncio.sleep(1.5) 
                
                cae_simulado = f"CAE{lote_id:04d}{alumno['id']:06d}99"
                vencimiento_cae = datetime.now() # En la vida real sumará 10 días
                nro_comprobante_simulado = 100 + index # Debería venir de AFIP
                punto_venta = 4
                tipo_cbte = 11 # Factura C
                
                # ── STEP 2: Generar el PDF usando tu pdf_service ──
                # Insertamos un registro previo de la factura para tener el ID único de la tabla
                # factura_id = db.execute("INSERT INTO agenda.facturas ... RETURNING id").scalar()
                factura_id = index # Mock de ID de factura
                
                ruta_pdf = generar_pdf_factura(
                    factura_id=factura_id,
                    nro_comprobante=nro_comprobante_simulado,
                    punto_venta=punto_venta,
                    tipo_cbte=tipo_cbte,
                    cae=cae_simulado,
                    vencimiento_cae=vencimiento_cae,
                    alumno_nombre=alumno["nombre"],
                    alumno_dni=alumno["dni"],
                    email_tutor=alumno["email_tutor"],
                    curso=alumno["curso"],
                    periodo_str=periodo_str,
                    monto=alumno["monto"],
                    escuela_nombre=escuela_data["nombre"],
                    escuela_cuit=escuela_data["cuit"],
                    escuela_domicilio=escuela_data["domicilio"],
                    fecha_emision=datetime.now()
                )
                
                # ── STEP 3: Enviar el correo usando tu email_service ──
                mail_enviado = enviar_factura_email(
                    email_destino=alumno["email_tutor"],
                    nombre_alumno=alumno["nombre"],
                    periodo_str=periodo_str,
                    monto=float(alumno["monto"]),
                    pdf_path=ruta_pdf,
                    escuela_nombre=escuela_data["nombre"]
                )
                
                # ── STEP 4: Guardar éxito en la base de datos ──
                # db.execute("INSERT INTO agenda.facturas (estado, cae, ruta_pdf, mail_enviado) ...")
                logger.info(f"Factura emitida exitosamente para {alumno['nombre']}. Mail: {mail_enviado}")

            except Exception as e:
                logger.error(f"Error procesando alumno {alumno['nombre']}: {e}")
                # Acá registrarías la factura en la DB con estado 'ERROR'
                # db.execute("INSERT INTO agenda.facturas (estado, error_log) VALUES ('ERROR', ...)")

            finally:
                # ── STEP 5: Calcular y actualizar avance del lote ──
                porcentaje = int((index / total_alumnos) * 100)
                
                # Actualizamos la DB para que el JavaScript del Dashboard vea el progreso real
                db.execute(
                    "UPDATE agenda.lotes_facturacion SET porcentaje_avance = :porcentaje WHERE id = :id",
                    {"porcentaje": porcentaje, "id": lote_id}
                )
                db.commit()

        # 6. Al terminar el bucle, pasamos el lote completo a FINALIZADO
        db.execute(
            "UPDATE agenda.lotes_facturacion SET estado = 'FINALIZADO', fecha_fin = :ahora WHERE id = :id",
            {"ahora": datetime.now(), "id": lote_id}
        )
        db.commit()
        logger.info(f"Lote {lote_id} finalizado con éxito.")

    except Exception as master_ex:
        logger.critical(f"Error crítico en el worker del lote {lote_id}: {master_ex}")
        db.execute(
            "UPDATE agenda.lotes_facturacion SET estado = 'ERROR' WHERE id = :id",
            {"id": lote_id}
        )
        db.commit()
    finally:
        db.close()