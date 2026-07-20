import calendar
import os

from datetime import date
from datetime import datetime
from datetime import timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from models.school import School
from models.student import Student
from models.invoice import Invoice
from models.invoice_job import InvoiceJob
from models.school_settings import SchoolSettings
from models.school_level import SchoolLevel

from services.invoice_log_service import InvoiceLogService
from services.afip.afip_service import AFIPService
from services.pdf_service import PDFService
from services.email_service import EmailService


class BulkBillingService:

    @staticmethod
    def build_due_date(period_month: int, period_year: int, due_day: int):
        last_day = calendar.monthrange(period_year, period_month)[1]
        safe_day = min(due_day, last_day)

        return date(period_year, period_month, safe_day)

    @staticmethod
    def extract_afip_observation(detalle):
        observations = detalle.get("Observaciones")

        if not observations:
            return None

        messages = []

        for item in observations.get("Errors", []):
            code = item.get("Code")
            msg = item.get("Msg")
            messages.append(f"{code}: {msg}")

        for item in observations.get("Obs", []):
            code = item.get("Code")
            msg = item.get("Msg")
            messages.append(f"{code}: {msg}")

        if not messages:
            return None

        return " | ".join(messages)

    @staticmethod
    def validate_before_billing(
        school,
        settings,
        students,
        period_month: int,
        period_year: int,
        due_day: int
    ):
        errors = []

        if not school:
            errors.append("Colegio no encontrado.")

        if not period_month or period_month < 1 or period_month > 12:
            errors.append("El mes a facturar es inválido.")

        if not period_year or period_year < 2020:
            errors.append("El año a facturar es inválido.")

        if not due_day or due_day < 1 or due_day > 31:
            errors.append("El día de vencimiento es inválido.")

        if not students:
            errors.append("No hay alumnos activos para facturar.")

        students_without_fee = [
            student.full_name
            for student in students
            if float(student.monthly_fee or 0) <= 0
        ]

        if students_without_fee:
            errors.append(
                "Hay alumnos activos con cuota en cero: "
                + ", ".join(students_without_fee[:10])
            )

        if not settings:
            errors.append("La escuela no tiene configuración cargada.")
        else:
            if not settings.afip_cuit:
                errors.append("Falta cargar el CUIT de ARCA/AFIP.")

            if not str(settings.afip_cuit or "").isdigit():
                errors.append("El CUIT de ARCA/AFIP debe contener solo números.")

            if not settings.afip_environment:
                errors.append("Falta seleccionar el entorno ARCA/AFIP.")

            if settings.afip_environment not in ["mock", "homo", "prod"]:
                errors.append("El entorno ARCA/AFIP debe ser mock, homo o prod.")

            if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
                errors.append("Falta completar la configuración SMTP.")

            if settings.afip_environment in ["homo", "prod"]:
                if not settings.afip_key_path:
                    errors.append("Falta generar o cargar la clave privada ARCA.")
                elif not os.path.exists(settings.afip_key_path):
                    errors.append("La clave privada ARCA no existe en el servidor.")

                if not settings.afip_cert_path:
                    errors.append("Falta cargar el certificado CRT emitido por ARCA.")
                elif not os.path.exists(settings.afip_cert_path):
                    errors.append("El certificado CRT de ARCA no existe en el servidor.")

        if errors:
            raise ValueError(
                "No se puede facturar el lote: " + " | ".join(errors)
            )

    @staticmethod
    def get_student_level(
        db: Session,
        school_id: int,
        student: Student
    ):
        if not student.level_id:
            return None

        return (
            db.query(SchoolLevel)
            .filter(
                SchoolLevel.id == student.level_id,
                SchoolLevel.school_id == school_id,
                SchoolLevel.is_active == True
            )
            .first()
        )

    @staticmethod
    def run_for_school(
        db: Session,
        school_id: int,
        job_name: str,
        period_month: int,
        period_year: int,
        due_day: int
    ):

        school = db.query(School).filter(
            School.id == school_id
        ).first()

        if not school:
            raise ValueError("Colegio no encontrado")

        settings = db.query(SchoolSettings).filter(
            SchoolSettings.school_id == school_id
        ).first()

        students = (
            db.query(Student)
            .filter(
                Student.school_id == school_id,
                Student.is_active == True
            )
            .all()
        )

        BulkBillingService.validate_before_billing(
            school=school,
            settings=settings,
            students=students,
            period_month=period_month,
            period_year=period_year,
            due_day=due_day
        )

        job = InvoiceJob(
            school_id=school_id,
            job_name=job_name,
            period_month=period_month,
            period_year=period_year,
            due_day=due_day,
            total_records=len(students),
            processed_records=0,
            skipped_records=0,
            failed_records=0,
            sent_emails=0,
            email_errors=0,
            status="running",
            error_message=None
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        afip = AFIPService(settings=settings)

        processed = 0
        failed = 0
        skipped = 0
        sent_emails = 0
        email_errors = 0
        details = []

        due_date = BulkBillingService.build_due_date(
            period_month=period_month,
            period_year=period_year,
            due_day=due_day
        )

        try:
            for student in students:

                try:
                    existing_invoice = (
                        db.query(Invoice)
                        .filter(
                            Invoice.school_id == school_id,
                            Invoice.student_id == student.id,
                            Invoice.period_month == period_month,
                            Invoice.period_year == period_year,
                            Invoice.status == "approved"
                        )
                        .first()
                    )

                    if existing_invoice:
                        skipped += 1
                        details.append({
                            "student": student.full_name,
                            "status": "skipped",
                            "message": "Ya tiene factura aprobada para este período"
                        })
                        continue

                    level = BulkBillingService.get_student_level(
                        db=db,
                        school_id=school_id,
                        student=student
                    )

                    if not level:
                        failed += 1
                        details.append({
                            "student": student.full_name,
                            "status": "error",
                            "message": "El alumno no tiene un nivel activo asignado."
                        })
                        continue

                    point_of_sale = level.point_of_sale or settings.afip_point_of_sale

                    if not point_of_sale:
                        failed += 1
                        details.append({
                            "student": student.full_name,
                            "status": "error",
                            "message": f"El nivel {level.name} no tiene punto de venta configurado."
                        })
                        continue

                    amount = float(student.monthly_fee or 0)

                    if amount <= 0:
                        failed += 1
                        details.append({
                            "student": student.full_name,
                            "status": "error",
                            "message": "Cuota mensual inválida o en cero"
                        })
                        continue

                    response = afip.crear_factura(
                        importe=amount,
                        punto_venta=point_of_sale
                    )

                    cabecera = response["FeCabResp"]
                    detalle = response["FeDetResp"]["FECAEDetResponse"][0]

                    status = "approved" if detalle["Resultado"] == "A" else "rejected"
                    observation = BulkBillingService.extract_afip_observation(detalle)

                    full_invoice_number = (
                        f"{int(cabecera.get('PtoVta')):04d}-"
                        f"{int(detalle.get('CbteDesde')):08d}"
                    )

                    invoice = Invoice(
                        school_id=school.id,
                        student_id=student.id,

                        due_date=due_date,

                        period_month=period_month,
                        period_year=period_year,

                        invoice_number=detalle.get("CbteDesde"),
                        point_of_sale=cabecera.get("PtoVta"),
                        invoice_type=cabecera.get("CbteTipo"),
                        full_invoice_number=full_invoice_number,

                        amount=Decimal(str(amount)),
                        net_amount=Decimal(str(amount)),
                        iva_amount=Decimal("0.00"),

                        cae=detalle.get("CAE"),
                        cae_expiration=detalle.get("CAEFchVto"),

                        status=status,
                        afip_result=detalle.get("Resultado"),
                        afip_observation=observation,

                        email_status="pending",
                        is_paid=False
                    )

                    db.add(invoice)
                    db.commit()
                    db.refresh(invoice)

                    InvoiceLogService.create(
                        db=db,
                        school_id=school.id,
                        student_id=student.id,
                        invoice_id=invoice.id,
                        event_type="invoice_created",
                        message=(
                            f"Factura creada con estado {status}. "
                            f"Comprobante {full_invoice_number}. "
                            f"Nivel: {level.name}. "
                            f"Punto de venta: {point_of_sale}."
                        )
                    )

                    if invoice.status != "approved":
                        failed += 1

                        message = (
                            f"Factura rechazada por ARCA. "
                            f"{observation or 'Sin observación devuelta.'}"
                        )

                        details.append({
                            "student": student.full_name,
                            "status": "error",
                            "message": message
                        })

                        InvoiceLogService.create(
                            db=db,
                            school_id=school.id,
                            student_id=student.id,
                            invoice_id=invoice.id,
                            event_type="arca_rejected",
                            message=message
                        )

                        continue

                    processed += 1

                    pdf_path = PDFService.generate_invoice_pdf(
                        invoice=invoice,
                        school=school,
                        student=student,
                        settings=settings
                    )

                    InvoiceLogService.create(
                        db=db,
                        school_id=school.id,
                        student_id=student.id,
                        invoice_id=invoice.id,
                        event_type="pdf_generated",
                        message=f"PDF generado correctamente: {pdf_path}"
                    )

                    email_result = EmailService.send_invoice_email(
                        smtp_host=settings.smtp_host,
                        smtp_port=settings.smtp_port or 587,
                        smtp_user=settings.smtp_user,
                        smtp_password=settings.smtp_password,
                        smtp_from=settings.smtp_from,
                        to_email=student.email,
                        student_name=student.full_name,
                        school_name=school.name,
                        pdf_path=pdf_path
                    )

                    if email_result["sent"]:
                        invoice.email_status = "sent"
                        invoice.email_error = None
                        invoice.email_sent_at = datetime.now(timezone.utc)
                        sent_emails += 1
                        email_message = "Email enviado"

                        InvoiceLogService.create(
                            db=db,
                            school_id=school.id,
                            student_id=student.id,
                            invoice_id=invoice.id,
                            event_type="email_sent",
                            message=f"Factura enviada por email a {student.email}."
                        )
                    else:
                        invoice.email_status = "error"
                        invoice.email_error = email_result["error"]
                        email_errors += 1
                        email_message = f'Email no enviado: {email_result["error"]}'

                        InvoiceLogService.create(
                            db=db,
                            school_id=school.id,
                            student_id=student.id,
                            invoice_id=invoice.id,
                            event_type="email_error",
                            message=f"Error enviando email: {email_result['error']}"
                        )

                    db.commit()

                    details.append({
                        "student": student.full_name,
                        "status": "ok",
                        "message": (
                            f"Factura {detalle.get('CbteDesde')} emitida. "
                            f"PV: {int(point_of_sale):04d}. "
                            f"Nivel: {level.name}. "
                            f"Período: {period_month:02d}/{period_year}. "
                            f"Vence: {due_date}. {email_message}"
                        )
                    })

                except Exception as e:
                    db.rollback()
                    failed += 1

                    details.append({
                        "student": student.full_name,
                        "status": "error",
                        "message": str(e)
                    })

            job.processed_records = processed
            job.failed_records = failed
            job.skipped_records = skipped
            job.sent_emails = sent_emails
            job.email_errors = email_errors
            job.status = "completed"
            job.finished_at = datetime.utcnow()

            db.commit()
            db.refresh(job)

        except Exception as e:
            db.rollback()

            job.status = "error"
            job.error_message = str(e)
            job.finished_at = datetime.utcnow()

            db.commit()

            raise

        return {
            "job": job,
            "details": details,
            "processed": processed,
            "failed": failed,
            "skipped": skipped,
            "sent_emails": sent_emails,
            "email_errors": email_errors
        }