"""Inspecciona un Excel del GPS y devuelve metadata para actualizar.ps1.

Detecta automaticamente la hoja con las columnas esperadas (puede venir como
'Report', 'Hoja3', etc.) y genera un label de periodo desde el rango de fechas.
Imprime JSON a stdout para que PowerShell lo parsee con ConvertFrom-Json.
"""
import json
import sys
import unicodedata

import pandas as pd

EXPECTED_NORM = {"estado", "placa", "comienzo", "fin", "duracion", "conductor"}
MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _norm(text) -> str:
    """Lower + strip tildes + colapsar espacios. Mismo criterio que src/io_loader.py."""
    t = str(text).strip().lower()
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return " ".join(t.split())


def find_data_sheet(path: str) -> str | None:
    """Devuelve el nombre de la hoja con la estructura esperada (la mas grande si hay varias)."""
    xl = pd.ExcelFile(path)
    best = None
    best_rows = 0
    for sheet in xl.sheet_names:
        try:
            head = pd.read_excel(xl, sheet_name=sheet, nrows=0)
        except Exception:
            continue
        cols_norm = {_norm(c) for c in head.columns}
        if EXPECTED_NORM.issubset(cols_norm):
            full = pd.read_excel(xl, sheet_name=sheet)
            if len(full) > best_rows:
                best = sheet
                best_rows = len(full)
    return best


def _col_by_norm(df: pd.DataFrame, target_norm: str) -> str | None:
    for c in df.columns:
        if _norm(c) == target_norm:
            return c
    return None


def build_periodo(df: pd.DataFrame) -> str:
    col_comienzo = _col_by_norm(df, "comienzo")
    if col_comienzo is None:
        return "Dashboard ejecutivo"
    fechas = pd.to_datetime(df[col_comienzo], errors="coerce", dayfirst=True).dropna()
    if fechas.empty:
        return "Dashboard ejecutivo"
    f_min = fechas.min()
    f_max = fechas.max()
    if f_min.month == f_max.month and f_min.year == f_max.year:
        return f"Semana {f_min.day:02d}-{f_max.day:02d} {MESES[f_max.month - 1]} {f_max.year}"
    return (
        f"{f_min.day:02d} {MESES[f_min.month - 1]} - "
        f"{f_max.day:02d} {MESES[f_max.month - 1]} {f_max.year}"
    )


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Falta path al Excel"}, ensure_ascii=False))
        return 1
    path = sys.argv[1]
    try:
        sheet = find_data_sheet(path)
    except Exception as e:
        print(json.dumps({"error": f"No pude abrir el Excel: {e}"}, ensure_ascii=False))
        return 1
    if sheet is None:
        print(json.dumps(
            {"error": "Ninguna hoja tiene las columnas esperadas "
                      "(Estado, Placa, Comienzo, Fin, Duracion, Conductor)"},
            ensure_ascii=False,
        ))
        return 1

    df = pd.read_excel(path, sheet_name=sheet)
    col_estado = _col_by_norm(df, "estado")
    col_conductor = _col_by_norm(df, "conductor")
    movimientos = int((df[col_estado].astype(str).str.lower() == "movimiento").sum()) if col_estado else 0
    conductores = int(df[col_conductor].dropna().nunique()) if col_conductor else 0
    info = {
        "sheet": sheet,
        "periodo": build_periodo(df),
        "filas": int(len(df)),
        "movimientos": movimientos,
        "conductores": conductores,
    }
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
