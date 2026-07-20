# tasks/__init__.py
# Inicialización del módulo de tareas Celery

from .facturacion_tasks import celery_app, procesar_lote_task

# Comentamos temporalmente los módulos que vas a ir agregando más adelante
# from .email_tasks import enviar_email_factura_task, reenviar_emails_fallidos_task
# from .beat_schedule import generar_deuda_mensual_task, limpiar_pdfs_antiguos_task

__all__ = [
    "celery_app",
    "procesar_lote_task",
]