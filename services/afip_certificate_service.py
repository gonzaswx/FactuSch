import os
import re
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


class AFIPCertificateService:

    @staticmethod
    def build_hostname(business_name: str):
        value = business_name.lower().strip()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = value.strip("-")

        if not value:
            value = "facturacion-escolar"

        return value[:60]

    @staticmethod
    def get_school_cert_dir(school_id: int):
        cert_dir = os.path.join(
            "storage",
            "certs",
            f"school_{school_id}"
        )

        os.makedirs(cert_dir, exist_ok=True)

        return cert_dir

    @staticmethod
    def generate_key_and_csr(
        school_id: int,
        cuit: str,
        business_name: str
    ):
        cert_dir = AFIPCertificateService.get_school_cert_dir(school_id)

        hostname = AFIPCertificateService.build_hostname(business_name)

        key_path = os.path.join(cert_dir, "private.key")
        csr_path = os.path.join(cert_dir, "request.csr")

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )

        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, business_name),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit}")
        ])

        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(subject)
            .sign(private_key, hashes.SHA256())
        )

        with open(key_path, "wb") as key_file:
            key_file.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                )
            )

        with open(csr_path, "wb") as csr_file:
            csr_file.write(
                csr.public_bytes(serialization.Encoding.PEM)
            )

        return {
            "hostname": hostname,
            "key_path": key_path,
            "csr_path": csr_path
        }