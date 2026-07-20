import os
import smtplib

from email.message import EmailMessage


class EmailService:

    @staticmethod
    def send_invoice_email(
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        smtp_from: str,
        to_email: str,
        student_name: str,
        school_name: str,
        pdf_path: str
    ):

        if not to_email:
            return {
                "sent": False,
                "error": "El alumno no tiene email cargado"
            }

        if not smtp_host or not smtp_user or not smtp_password:
            return {
                "sent": False,
                "error": "SMTP no configurado para la escuela"
            }

        msg = EmailMessage()

        msg["Subject"] = f"Factura emitida - {school_name}"
        msg["From"] = smtp_from or smtp_user
        msg["To"] = to_email

        msg.set_content(
            f"""Hola {student_name},

Te adjuntamos la factura correspondiente emitida por {school_name}.

Saludos.
"""
        )

        filename = os.path.basename(pdf_path)

        with open(pdf_path, "rb") as f:
            pdf_data = f.read()

        msg.add_attachment(
            pdf_data,
            maintype="application",
            subtype="pdf",
            filename=filename
        )

        try:
            with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            return {
                "sent": True,
                "error": None
            }

        except Exception as e:
            return {
                "sent": False,
                "error": str(e)
            }

    @staticmethod
    def send_payment_reminder_email(
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        smtp_from: str,
        to_email: str,
        student_name: str,
        school_name: str,
        period: str,
        amount: float,
        due_date: str,
        invoice_number: str,
        is_overdue: bool
    ):

        if not to_email:
            return {
                "sent": False,
                "error": "El alumno no tiene email cargado"
            }

        if not smtp_host or not smtp_user or not smtp_password:
            return {
                "sent": False,
                "error": "SMTP no configurado para la escuela"
            }

        msg = EmailMessage()

        subject_status = "vencida" if is_overdue else "pendiente"

        msg["Subject"] = f"Recordatorio de cuota {subject_status} - {school_name}"
        msg["From"] = smtp_from or smtp_user
        msg["To"] = to_email

        estado_texto = "se encuentra vencida" if is_overdue else "se encuentra pendiente de pago"

        msg.set_content(
            f"""Hola,

Te contactamos desde {school_name} para recordarte que la cuota correspondiente a {student_name} {estado_texto}.

Detalle:
Alumno: {student_name}
Período: {period}
Factura: {invoice_number}
Importe: $ {amount:.2f}
Fecha de vencimiento: {due_date or "-"}

Por favor, regularizar el pago a la brevedad o comunicarse con la administración del colegio.

Saludos.
{school_name}
"""
        )

        try:
            with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            return {
                "sent": True,
                "error": None
            }

        except Exception as e:
            return {
                "sent": False,
                "error": str(e)
            }