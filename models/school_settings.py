from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Boolean
from sqlalchemy import ForeignKey
from sqlalchemy import DateTime

from datetime import datetime

from database import Base


class SchoolSettings(Base):

    __tablename__ = "school_settings"

    id = Column(Integer, primary_key=True, index=True)

    school_id = Column(
        Integer,
        ForeignKey("schools.id"),
        nullable=False,
        unique=True
    )

    # SMTP
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True, default=587)
    smtp_user = Column(String(255), nullable=True)
    smtp_password = Column(String(255), nullable=True)
    smtp_from = Column(String(255), nullable=True)
    smtp_use_tls = Column(Boolean, default=True)

    # AFIP / ARCA
    afip_business_name = Column(String(255), nullable=True)
    afip_server_hostname = Column(String(255), nullable=True)
    afip_cuit = Column(String(20), nullable=True)
    afip_point_of_sale = Column(Integer, nullable=True, default=1)
    afip_environment = Column(String(20), nullable=True, default="homo")
    invoice_type = Column(Integer, nullable=True, default=11)

    afip_cert_path = Column(String(500), nullable=True)
    afip_key_path = Column(String(500), nullable=True)

    # Personalización de factura PDF
    invoice_logo_path = Column(String(500), nullable=True)
    invoice_primary_color = Column(String(20), nullable=True)
    invoice_footer_text = Column(String(1000), nullable=True)
    invoice_legal_text = Column(String(1000), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)