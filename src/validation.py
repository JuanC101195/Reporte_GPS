"""Data validation and quality reports for GPS pipeline."""

import re
from pathlib import Path

import pandas as pd

from .schema import CANONICAL_COLUMNS, DATE_FORMATS, VALID_STATES


def parse_dates(series):
    result = pd.Series([pd.NaT] * len(series), index=series.index)
    for fmt in DATE_FORMATS:
        mask = result.isna() & series.notna() & (series != "")
        if not mask.any():
            break
        parsed = pd.to_datetime(series[mask], format=fmt, errors="coerce")
        result[mask] = parsed
    return result


def validate_schema(df):
    required = {"Estado", "Placa", "Comienzo", "Fin", "Duracion"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    return True


def _collect_errors(df):
    errors = []

    invalid_state = ~df["Estado"].isin(VALID_STATES)
    for idx in df.index[invalid_state]:
        errors.append(
            {
                "fila": idx,
                "campo": "Estado",
                "valor": df.at[idx, "Estado"],
                "error": f"Invalid state. Expected: {sorted(VALID_STATES)}",
            }
        )

    start = parse_dates(df["Comienzo"])
    end = parse_dates(df["Fin"])

    for idx in df.index[start.isna()]:
        errors.append({"fila": idx, "campo": "Comienzo", "valor": df.at[idx, "Comienzo"], "error": "Unparseable date"})
    for idx in df.index[end.isna()]:
        errors.append({"fila": idx, "campo": "Fin", "valor": df.at[idx, "Fin"], "error": "Unparseable date"})

    bad_order = start.notna() & end.notna() & (start > end)
    for idx in df.index[bad_order]:
        errors.append(
            {
                "fila": idx,
                "campo": "Comienzo/Fin",
                "valor": f"{df.at[idx, 'Comienzo']} > {df.at[idx, 'Fin']}",
                "error": "Start date after end date",
            }
        )

    coord_re = re.compile(r"^-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?$")
    dist_re = re.compile(r"^\d+(\.\d+)?\s*[Kk][Mm]$")

    for idx, row in df.iterrows():
        val = str(row.get("Posicion", "")).strip()
        if not val or val.lower() == "nan":
            continue
        estado = row.get("Estado", "")
        if estado == "Detenido" and not coord_re.match(val):
            errors.append({"fila": idx, "campo": "Posicion", "valor": val, "error": "Invalid coordinate format (lat,lon)"})
        elif estado == "Movimiento" and not dist_re.match(val):
            errors.append({"fila": idx, "campo": "Posicion", "valor": val, "error": "Invalid distance format (number Km)"})

    return errors


def generate_quality_report(df, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    errors = _collect_errors(df)
    errors_df = pd.DataFrame(errors) if errors else pd.DataFrame(columns=["fila", "campo", "valor", "error"])

    cols = [c for c in CANONICAL_COLUMNS if c in df.columns]
    null_counts = df[cols].replace("", None).isnull().sum()
    stats_df = pd.DataFrame(
        {
            "columna": null_counts.index,
            "nulos": null_counts.values,
            "pct_nulos": (null_counts.values / len(df) * 100).round(2),
        }
    )

    stats_df.to_csv(output_dir / "data_quality_stats.csv", index=False, encoding="utf-8-sig")
    errors_df.to_csv(output_dir / "data_quality_errors.csv", index=False, encoding="utf-8-sig")

    return stats_df, errors_df
