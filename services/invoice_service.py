from decimal import Decimal
from sqlalchemy.orm import Session

from models.invoice import Invoice
from models.student import Student
from models.school import School
from services.afip.afip_service import AFIPService


class InvoiceService:

    @staticmethod
    def issue_for_student(
        db: Session,
        school_id: int,
        student_id: int,
        amount: float
    ):

        school = db.query(School).filter(School.id == school_id).first()
        student = db.query(Student).filter(
            Student.id == student_id,
            Student.school_id == school_id
        ).first()

        if not school:
            raise ValueError("Colegio no encontrado")

        if not student:
            raise ValueError("Alumno no encontrado")

        afip = AFIPService()

        response = afip.crear_factura(
            importe=amount,
            punto_venta=1,
            doc_tipo=99,
            doc_nro=0,
            condicion_iva=5
        )

        cab = response["FeCabResp"]
        det = response["FeDetResp"]["FECAEDetResponse"][0]

        status = "approved" if det["Resultado"] == "A" else "rejected"

        observation = None
        if det.get("Observaciones"):
            obs = det["Observaciones"].get("Obs", [])
            if obs:
                observation = " | ".join(
                    f'{o.get("Code")}: {o.get("Msg")}' for o in obs
                )

        invoice = Invoice(
            school_id=school.id,
            student_id=student.id,
            invoice_number=det["CbteDesde"],
            point_of_sale=cab["PtoVta"],
            invoice_type=cab["CbteTipo"],
            amount=Decimal(str(amount)),
            net_amount=Decimal(str(round(amount / 1.21, 2))),
            iva_amount=Decimal(str(round(amount - (amount / 1.21), 2))),
            cae=det.get("CAE"),
            cae_expiration=det.get("CAEFchVto"),
            status=status,
            afip_result=det["Resultado"],
            afip_observation=observation
        )

        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        return invoice