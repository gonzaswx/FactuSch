from datetime import datetime, timedelta
import os
import random

from services.afip.arca_real_client import ARCARealClient


class AFIPService:

    def __init__(self, settings=None):
        self.settings = settings
        self.mock_mode = self._should_use_mock()

    def _should_use_mock(self):
        if not self.settings:
            return True

        if self.settings.afip_environment == "mock":
            return True

        required_values = [
            self.settings.afip_cuit,
            self.settings.afip_point_of_sale,
            self.settings.afip_environment,
            self.settings.afip_cert_path,
            self.settings.afip_key_path
        ]

        if any(not value for value in required_values):
            return True

        if not os.path.exists(self.settings.afip_cert_path):
            return True

        if not os.path.exists(self.settings.afip_key_path):
            return True

        return False

    def test_configuration(self):
        errors = []

        if not self.settings:
            errors.append("No existe configuración ARCA para esta escuela.")
            return {
                "ok": False,
                "message": "Configuración ARCA incompleta.",
                "errors": errors
            }

        cuit = str(self.settings.afip_cuit or "").strip()

        if not cuit:
            errors.append("Falta cargar el CUIT.")
        elif not cuit.isdigit():
            errors.append("El CUIT debe contener solo números.")
        elif len(cuit) != 11:
            errors.append("El CUIT debe tener 11 dígitos.")

        if not self.settings.afip_business_name:
            errors.append("Falta cargar la razón social.")

        if not self.settings.afip_point_of_sale:
            errors.append("Falta cargar el punto de venta.")

        if self.settings.afip_environment not in ["mock", "homo", "prod"]:
            errors.append("El entorno debe ser mock, homo o prod.")

        if self.settings.afip_environment in ["homo", "prod"]:
            if not self.settings.afip_key_path:
                errors.append("Falta generar o cargar la clave privada.")
            elif not os.path.exists(self.settings.afip_key_path):
                errors.append("La clave privada no existe en el servidor.")

            if not self.settings.afip_cert_path:
                errors.append("Falta cargar el certificado CRT.")
            elif not os.path.exists(self.settings.afip_cert_path):
                errors.append("El certificado CRT no existe en el servidor.")

        if errors:
            return {
                "ok": False,
                "message": "La configuración ARCA tiene errores.",
                "errors": errors
            }

        if self.mock_mode:
            return {
                "ok": True,
                "message": "Configuración local válida. El sistema está trabajando en modo mock.",
                "errors": []
            }

        try:
            client = ARCARealClient(settings=self.settings)
            return client.test_connection()

        except Exception as e:
            return {
                "ok": False,
                "message": "No se pudo conectar con ARCA.",
                "errors": [str(e)]
            }

    def crear_factura(
        self,
        importe: float,
        punto_venta: int | None = None,
        doc_tipo: int = 99,
        doc_nro: int = 0,
        condicion_iva: int = 5
    ):
        if self.mock_mode:
            return self._crear_factura_mock(
                importe=importe,
                punto_venta=punto_venta
            )

        return self._crear_factura_real(
            importe=importe,
            punto_venta=punto_venta,
            doc_tipo=doc_tipo,
            doc_nro=doc_nro,
            condicion_iva=condicion_iva
        )

    def _crear_factura_mock(
        self,
        importe: float,
        punto_venta: int | None = None
    ):
        comprobante = random.randint(1000, 999999)
        cae = str(random.randint(10000000000000, 99999999999999))
        cae_vto = (datetime.now() + timedelta(days=10)).strftime("%Y%m%d")

        punto_venta_final = punto_venta or 1

        if self.settings and self.settings.afip_point_of_sale:
            punto_venta_final = self.settings.afip_point_of_sale

        return {
            "FeCabResp": {
                "PtoVta": punto_venta_final,
                "CbteTipo": int(getattr(self.settings, "invoice_type", None) or 11)
            },
            "FeDetResp": {
                "FECAEDetResponse": [
                    {
                        "CbteDesde": comprobante,
                        "CbteHasta": comprobante,
                        "Resultado": "A",
                        "CAE": cae,
                        "CAEFchVto": cae_vto,
                        "Observaciones": None
                    }
                ]
            }
        }

    def _crear_factura_real(
        self,
        importe: float,
        punto_venta: int | None = None,
        doc_tipo: int = 99,
        doc_nro: int = 0,
        condicion_iva: int = 5
    ):
        client = ARCARealClient(settings=self.settings)

        return client.crear_factura(
            importe=importe,
            punto_venta=punto_venta,
            doc_tipo=doc_tipo,
            doc_nro=doc_nro,
            condicion_iva=condicion_iva
        )

    def ultimo_comprobante(
        self,
        punto_venta: int | None = None,
        tipo_cbte: int = 6
    ):
        if self.mock_mode:
            return random.randint(1000, 999999)

        client = ARCARealClient(settings=self.settings)

        return client.ultimo_comprobante(
            punto_venta=punto_venta,
            tipo_cbte=tipo_cbte
        )