import base64
import json
import os
import ssl

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from decimal import Decimal
from typing import Any

from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes

from requests import Session
from requests.adapters import HTTPAdapter

from zeep import Client
from zeep.transports import Transport


class LegacyTLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = context

        return super().init_poolmanager(*args, **kwargs)


class ARCARealClient:

    WSAA_HOMO = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl"
    WSAA_PROD = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"

    WSFE_HOMO = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
    WSFE_PROD = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"

    def __init__(self, settings):
        self.settings = settings
        self.environment = settings.afip_environment
        self.cuit = int(str(settings.afip_cuit).replace("-", "").strip())
        self.point_of_sale = int(settings.afip_point_of_sale or 1)
        self.cert_path = settings.afip_cert_path
        self.key_path = settings.afip_key_path

    def get_wsaa_url(self):
        if self.environment == "prod":
            return self.WSAA_PROD

        return self.WSAA_HOMO

    def get_wsfe_url(self):
        if self.environment == "prod":
            return self.WSFE_PROD

        return self.WSFE_HOMO

    def create_session(self):
        session = Session()
        session.mount("https://", LegacyTLSAdapter())
        return session

    def get_ta_cache_path(self):
        school_id = getattr(self.settings, "school_id", "default")

        cache_dir = os.path.join(
            "storage",
            "afip_ta",
            f"school_{school_id}"
        )

        os.makedirs(cache_dir, exist_ok=True)

        return os.path.join(
            cache_dir,
            f"ta_{self.environment}_wsfe.json"
        )

    def get_cached_login(self):
        cache_path = self.get_ta_cache_path()

        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            expiration = data.get("expiration")

            if not expiration:
                return None

            expiration_dt = datetime.fromisoformat(
                expiration.replace("Z", "+00:00")
            )

            if expiration_dt.tzinfo is None:
                expiration_dt = expiration_dt.replace(
                    tzinfo=timezone.utc
                )

            if datetime.now(timezone.utc) < expiration_dt:
                return data

        except Exception:
            return None

        return None

    def save_cached_login(self, login):
        cache_path = self.get_ta_cache_path()

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(login, f, indent=4)

    def create_login_ticket_request(self, service: str = "wsfe"):
        now = datetime.now(timezone.utc)
        unique_id = int(now.timestamp())

        generation_time = (
            now - timedelta(minutes=10)
        ).strftime("%Y-%m-%dT%H:%M:%S%z")

        expiration_time = (
            now + timedelta(hours=12)
        ).strftime("%Y-%m-%dT%H:%M:%S%z")

        generation_time = generation_time[:-2] + ":" + generation_time[-2:]
        expiration_time = expiration_time[:-2] + ":" + expiration_time[-2:]

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
    <header>
        <uniqueId>{unique_id}</uniqueId>
        <generationTime>{generation_time}</generationTime>
        <expirationTime>{expiration_time}</expirationTime>
    </header>
    <service>{service}</service>
</loginTicketRequest>"""

    def sign_login_ticket_request(self, xml: str):
        with open(self.cert_path, "rb") as cert_file:
            cert_data = cert_file.read()

        with open(self.key_path, "rb") as key_file:
            key_data = key_file.read()

        cert = load_pem_x509_certificate(cert_data)

        private_key = serialization.load_pem_private_key(
            key_data,
            password=None
        )

        builder = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(xml.encode("utf-8"))
            .add_signer(cert, private_key, hashes.SHA256())
        )

        signed_data = builder.sign(
            Encoding.DER,
            [pkcs7.PKCS7Options.Binary]
        )

        return base64.b64encode(signed_data).decode("utf-8")

    def login_wsaa(self):
        xml = self.create_login_ticket_request("wsfe")
        cms = self.sign_login_ticket_request(xml)

        session = self.create_session()

        transport = Transport(
            session=session,
            timeout=30
        )

        client = Client(
            wsdl=self.get_wsaa_url(),
            transport=transport
        )

        response = client.service.loginCms(cms)

        token = self._extract_between(response, "<token>", "</token>")
        sign = self._extract_between(response, "<sign>", "</sign>")
        expiration_time = self._extract_between(
            response,
            "<expirationTime>",
            "</expirationTime>"
        )

        if not token or not sign:
            raise ValueError(
                "ARCA no devolvió token/sign válidos."
            )

        return {
            "token": token,
            "sign": sign,
            "expiration": expiration_time
        }

    def get_auth(self):
        login = self.get_cached_login()

        if not login:
            login = self.login_wsaa()
            self.save_cached_login(login)

        return {
            "Token": login["token"],
            "Sign": login["sign"],
            "Cuit": self.cuit
        }

    def get_wsfe_client(self):
        session = self.create_session()

        transport = Transport(
            session=session,
            timeout=30
        )

        return Client(
            wsdl=self.get_wsfe_url(),
            transport=transport
        )

    def ultimo_comprobante(
        self,
        punto_venta: int | None = None,
        tipo_cbte: int = 6
    ):
        auth = self.get_auth()
        client = self.get_wsfe_client()

        point_of_sale = punto_venta or self.point_of_sale

        response = client.service.FECompUltimoAutorizado(
            Auth=auth,
            PtoVta=point_of_sale,
            CbteTipo=tipo_cbte
        )

        return int(response.CbteNro or 0)

    def crear_factura(
        self,
        importe: float,
        punto_venta: int | None = None,
        doc_tipo: int = 99,
        doc_nro: int = 0,
        condicion_iva: int = 5
    ):
        auth = self.get_auth()
        client = self.get_wsfe_client()

        point_of_sale = punto_venta or self.point_of_sale
        cbte_tipo = int(getattr(self.settings, "invoice_type", None) or 11)

        last_number = self.ultimo_comprobante(
            punto_venta=point_of_sale,
            tipo_cbte=cbte_tipo
        )

        next_number = last_number + 1
        today = datetime.now().strftime("%Y%m%d")

        importe_decimal = Decimal(str(importe)).quantize(
            Decimal("0.01")
        )

        request = {
            "FeCabReq": {
                "CantReg": 1,
                "PtoVta": point_of_sale,
                "CbteTipo": cbte_tipo
            },
            "FeDetReq": {
                "FECAEDetRequest": [
                    {
                        "Concepto": 2,
                        "DocTipo": doc_tipo,
                        "DocNro": doc_nro,
                        "CbteDesde": next_number,
                        "CbteHasta": next_number,
                        "CbteFch": today,
                        "ImpTotal": float(importe_decimal),
                        "ImpTotConc": 0,
                        "ImpNeto": float(importe_decimal),
                        "ImpOpEx": 0,
                        "ImpIVA": 0,
                        "ImpTrib": 0,
                        "FchServDesde": today,
                        "FchServHasta": today,
                        "FchVtoPago": today,
                        "MonId": "PES",
                        "MonCotiz": 1,
                        "CondicionIVAReceptorId": condicion_iva
                    }
                ]
            }
        }

        response = client.service.FECAESolicitar(
            Auth=auth,
            FeCAEReq=request
        )

        cabecera = getattr(response, "FeCabResp", None)
        detalle = None

        if getattr(response, "FeDetResp", None):
            detalle_response = getattr(response.FeDetResp, "FECAEDetResponse", None)

            if isinstance(detalle_response, list):
                detalle = detalle_response[0] if detalle_response else None
            else:
                detalle = detalle_response

        if not cabecera:
            raise ValueError(
                f"ARCA no devolvió cabecera de comprobante. "
                f"Errores: {self._format_errors(response)}"
            )

        if not detalle:
            raise ValueError(
                f"ARCA no devolvió detalle de comprobante. "
                f"Errores: {self._format_errors(response)}"
            )

        observaciones = self._merge_errors_and_observations(
            response=response,
            detalle=detalle
        )

        return {
            "FeCabResp": {
                "PtoVta": getattr(cabecera, "PtoVta", point_of_sale),
                "CbteTipo": getattr(cabecera, "CbteTipo", cbte_tipo)
            },
            "FeDetResp": {
                "FECAEDetResponse": [
                    {
                        "CbteDesde": getattr(detalle, "CbteDesde", next_number),
                        "CbteHasta": getattr(detalle, "CbteHasta", next_number),
                        "Resultado": getattr(detalle, "Resultado", "R"),
                        "CAE": getattr(detalle, "CAE", None),
                        "CAEFchVto": getattr(detalle, "CAEFchVto", None),
                        "Observaciones": observaciones
                    }
                ]
            }
        }

    def test_connection(self):
        auth = self.get_auth()
        client = self.get_wsfe_client()

        response = client.service.FEDummy()

        return {
            "ok": True,
            "message": (
                f"Conexión ARCA OK. "
                f"AppServer: {response.AppServer}, "
                f"DbServer: {response.DbServer}, "
                f"AuthServer: {response.AuthServer}"
            ),
            "auth": bool(auth)
        }

    def _parse_errors(self, response: Any):
        errors = getattr(response, "Errors", None)

        if not errors:
            return None

        err_items = getattr(errors, "Err", None)

        if not err_items:
            return None

        if not isinstance(err_items, list):
            err_items = [err_items]

        return {
            "Err": [
                {
                    "Code": getattr(item, "Code", None),
                    "Msg": getattr(item, "Msg", None)
                }
                for item in err_items
            ]
        }

    def _parse_observaciones(self, detalle: Any):
        observaciones = getattr(detalle, "Observaciones", None)

        if not observaciones:
            return None

        obs = getattr(observaciones, "Obs", None)

        if not obs:
            return None

        if not isinstance(obs, list):
            obs = [obs]

        return {
            "Obs": [
                {
                    "Code": getattr(item, "Code", None),
                    "Msg": getattr(item, "Msg", None)
                }
                for item in obs
            ]
        }

    def _merge_errors_and_observations(self, response: Any, detalle: Any):
        result = {}

        errors = self._parse_errors(response)

        if errors:
            result["Errors"] = errors.get("Err", [])

        observations = self._parse_observaciones(detalle)

        if observations:
            result["Obs"] = observations.get("Obs", [])

        if not result:
            return None

        return result

    def _format_errors(self, response: Any):
        errors = self._parse_errors(response)

        if not errors:
            return "Sin errores informados."

        messages = []

        for item in errors.get("Err", []):
            messages.append(
                f"{item.get('Code')}: {item.get('Msg')}"
            )

        return " | ".join(messages)

    def _extract_between(
        self,
        text: str,
        start: str,
        end: str
    ):
        if not text:
            return None

        start_index = text.find(start)

        if start_index == -1:
            return None

        start_index += len(start)
        end_index = text.find(end, start_index)

        if end_index == -1:
            return None

        return text[start_index:end_index]