# utils/csv_importer.py
# Validación e importación de alumnos desde CSV (Filtrado por Escuela).

import io
import logging
from dataclasses import dataclass, field
from typing import List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Columnas requeridas en el CSV (case-insensitive)
COLUMNAS_REQUERIDAS = {"nombre", "apellido", "dni", "email_tutor", "cuota_base"}
COLUMNAS_OPCIONALES = {"curso"}


@dataclass
class ResultadoImportacion:
    importados:  int = 0
    omitidos:    int = 0    # DNI ya existente en ESTA escuela
    errores:     int = 0
    mensajes:    List[str] = field(default_factory=list)


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza los nombres de columnas: minúsculas y sin espacios."""
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )
    return df


def validar_fila(fila: pd.Series, idx: int) -> Tuple[bool, str]:
    """Valida una fila del CSV. Retorna (ok, mensaje_error)."""
    if not str(fila.get("dni", "")).strip():
        return False, f"Fila {idx}: DNI vacío"
    if not str(fila.get("nombre", "")).strip():
        return False, f"Fila {idx}: Nombre vacío"
    if not str(fila.get("apellido", "")).strip():
        return False, f"Fila {idx}: Apellido vacío"
    if not str(fila.get("email_tutor", "")).strip():
        return False, f"Fila {idx}: Email tutor vacío"
    try:
        cuota = float(str(fila.get("cuota_base", "0")).replace(",", "."))
        if cuota <= 0:
            return False, f"Fila {idx}: cuota_base debe ser mayor a 0"
    except ValueError:
        return False, f"Fila {idx}: cuota_base no es un número válido"
    return True, ""


def importar_alumnos_desde_csv(
    contenido_csv: bytes,
    escuela_id:    int,
    db,            # Session de SQLAlchemy
) -> ResultadoImportacion:
    """
    Procesan un archivo CSV y carga los alumnos en la BD.
    Omite filas con DNI ya existente en la misma escuela.
    """
    # Corregimos el import apuntando a tu módulo real
    from models.models import Alumno

    resultado = ResultadoImportacion()

    # ── 1. Leer CSV ───────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(io.BytesIO(contenido_csv), dtype=str, keep_default_na=False)
        df = normalizar_columnas(df)
    except Exception as exc:
        resultado.errores += 1
        resultado.mensajes.append(f"Error al leer el CSV: {exc}")
        return resultado

    # ── 2. Verificar columnas ─────────────────────────────────────────────────
    columnas_presentes = set(df.columns)
    faltantes = COLUMNAS_REQUERIDAS - columnas_presentes
    if faltantes:
        resultado.mensajes.append(
            f"Columnas faltantes en el CSV: {', '.join(sorted(faltantes))}. "
            f"Requeridas: {', '.join(sorted(COLUMNAS_REQUERIDAS))}"
        )
        resultado.errores = len(df)
        return resultado

    # ── 3. CORRECCIÓN: Obtener DNIs existentes SOLO de esta escuela ───────────
    dnis_existentes = {
        row.dni
        for row in db.query(Alumno.dni).filter(Alumno.escuela_id == escuela_id).all()
    }

    # ── 4. Procesar fila por fila ─────────────────────────────────────────────
    for idx, fila in df.iterrows():
        fila_num = idx + 2   # +2 por índice 0 y fila de encabezado

        ok, error_msg = validar_fila(fila, fila_num)
        if not ok:
            resultado.errores += 1
            resultado.mensajes.append(error_msg)
            continue

        dni = str(fila["dni"]).strip()

        if i := dni in dnis_existentes:
            resultado.omitidos += 1
            resultado.mensajes.append(f"Fila {fila_num}: El alumno con DNI {dni} ya se encuentra registrado.")
            continue

        alumno = Alumno(
            escuela_id  = escuela_id,
            nombre      = str(fila["nombre"]).strip().title(),
            apellido    = str(fila["apellido"]).strip().title(),
            dni         = dni,
            email_tutor = str(fila["email_tutor"]).strip().lower(),
            cuota_base  = float(str(fila["cuota_base"]).replace(",", ".")),
            curso       = str(fila.get("curso", "")).strip() or None,
            activo      = True
        )
        db.add(alumno)
        dnis_existentes.add(dni)   # Evita duplicados si el DNI se repite dentro del mismo CSV
        resultado.importados += 1

    # ── 5. Confirmar en Base de Datos ─────────────────────────────────────────
    if resultado.importados > 0:
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            resultado.errores += resultado.importados
            resultado.importados = 0
            resultado.mensajes.append(f"Error crítico de consistencia al guardar en la base de datos: {exc}")
            logger.exception("Error guardando alumnos del CSV: %s", exc)

    return resultado