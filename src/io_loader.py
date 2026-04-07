# -*- coding: utf-8 -*-
"""Load and normalize Excel/CSV for GPS data."""

import unicodedata
import pandas as pd
from .schema import ALIAS_MAP, CANONICAL_COLUMNS


def _normalize(text):
    if not isinstance(text, str):
        return ""
    t = text.strip().lower()
    t = "".join(
        c for c in unicodedata.normalize("NFKD", t)
        if not unicodedata.combining(c)
    )
    return " ".join(t.split())


def _rename_columns(df):
    mapping = {}
    for col in df.columns:
        norm = _normalize(str(col))
        if norm in ALIAS_MAP:
            mapping[col] = ALIAS_MAP[norm]
    return df.rename(columns=mapping)


def load_excel(filepath, sheet_name=None):
    """Load Excel with support for double-header format."""
    xls = pd.ExcelFile(filepath)

    if sheet_name is None:
        preferred = ["Report", "Hoja2", "Sheet1"]
        sheet_name = next((s for s in preferred if s in xls.sheet_names), xls.sheet_names[0])

    peek = pd.read_excel(filepath, sheet_name=sheet_name, nrows=3, header=None)
    second_row_vals = [_normalize(str(v)) for v in peek.iloc[1].tolist()]

    has_double_header = any(
        "velocidad" in v or "longitud de ruta" in v
        for v in second_row_vals
    )

    skip = 2 if has_double_header else 1

    df = pd.read_excel(
        filepath,
        sheet_name=sheet_name,
        skiprows=skip,
        header=None,
        dtype=str,
        keep_default_na=False,
    )

    col_names_raw = [str(v) for v in peek.iloc[0].tolist()]

    if has_double_header:
        col_names_level1 = [str(v) for v in peek.iloc[1].tolist()]
        final_names = []
        for n0, n1 in zip(col_names_raw, col_names_level1):
            n1_norm = _normalize(n1)
            if n1_norm and n1_norm != "nan":
                final_names.append(n1)
            else:
                final_names.append(n0)
        if len(final_names) == len(df.columns):
            df.columns = final_names
        else:
            df.columns = col_names_raw[: len(df.columns)]
    elif len(col_names_raw) == len(df.columns):
        df.columns = col_names_raw

    df = _rename_columns(df)

    if "Estado" in df.columns:
        df = df[df["Estado"].isin({"Detenido", "Movimiento"})].copy()

    if "Conductor" not in df.columns or df["Conductor"].replace("", None).isna().all():
        df["Conductor"] = df.get("Placa", pd.Series(dtype=str))

    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[CANONICAL_COLUMNS].reset_index(drop=True)


def load_csv(filepath):
    """Load CSV and normalize columns into canonical schema."""
    df = pd.read_csv(filepath, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df = _rename_columns(df)
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[CANONICAL_COLUMNS].reset_index(drop=True)
