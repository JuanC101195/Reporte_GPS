"""Cleaning and enrichment helpers for GPS pipeline."""

import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import geo

KNOWN_OFFICES = {
    "Casa Blanca": {"lat": 10.382486, "lon": -75.475173},
    "Renta Ya": {"lat": 10.380147, "lon": -75.474889},
}

# Radio de coincidencia para emparejar paradas con oficinas/casas/fotos (metros).
RADIO_MATCH_METROS = 200.0


def _normalize_placa_text(value):
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", "", str(value)).upper().strip()


def parse_coordinates(value):
    """Parse coordinate text like '10.37098, -75.474797' into (lat, lon)."""
    if pd.isna(value):
        return None, None
    parts = re.findall(r"-?\d+\.?\d*", str(value))
    if len(parts) >= 2:
        return float(parts[0]), float(parts[1])
    return None, None


def parse_coordinates_series(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Vectorized parse of a Series of 'lat, lon' strings into two float Series.

    Returns (lat_series, lon_series) with NaN where parsing fails.
    """
    extracted = series.fillna("").astype(str).str.extract(
        r"(-?\d+(?:\.\d+)?)[^-\d]+(-?\d+(?:\.\d+)?)"
    )
    lat = pd.to_numeric(extracted[0], errors="coerce")
    lon = pd.to_numeric(extracted[1], errors="coerce")
    return lat, lon


def load_worker_homes(homes_file=None):
    """Load worker home coordinates keyed by placa from external Excel."""
    if not homes_file:
        return {}

    path = Path(homes_file)
    if not path.exists():
        return {}

    try:
        df = pd.read_excel(path, sheet_name="Hoja1")
    except Exception:
        try:
            df = pd.read_excel(path)
        except Exception:
            return {}

    if df.empty:
        return {}

    columns = list(df.columns)
    col_norm = {col: re.sub(r"\s+", " ", str(col)).strip().lower() for col in columns}

    col_base = next((col for col in columns if col_norm[col] == "casa placa"), None)
    col_placa = next((col for col in columns if "placa" in col_norm[col]), None)
    col_nombre = next(
        (
            col for col in columns
            if col_norm[col] in {"casa", "nombre", "trabajador"} and "placa" not in col_norm[col]
        ),
        None,
    )

    if col_base is not None:
        home_cols = [col for col in columns if "casa" in col_norm[col] and col_norm[col] != "casa placa"]
    else:
        if col_placa is None:
            return {}
        home_cols = [col for col in columns if "casa" in col_norm[col] and col not in {col_nombre, col_base}]

    if not home_cols:
        return {}

    homes_by_placa = {}

    for _, row in df.iterrows():
        if col_base is not None:
            base = str(row.get(col_base, "")).strip()
            if not base or base.lower() == "nan":
                continue
            placa_match = re.search(r"([A-Z]{3}\s*\d{2}[A-Z])\s*$", base.upper())
            if not placa_match:
                continue
            placa_raw = placa_match.group(1)
            nombre = re.sub(r"([A-Z]{3}\s*\d{2}[A-Z])\s*$", "", base, flags=re.IGNORECASE).strip()
            nombre = re.sub(r"\s+", " ", nombre)
            if not nombre:
                nombre = placa_raw
        else:
            placa_raw = str(row.get(col_placa, "")).strip()
            if not placa_raw or placa_raw.lower() == "nan":
                continue
            nombre = str(row.get(col_nombre, "")).strip() if col_nombre else ""
            if not nombre or nombre.lower() == "nan":
                nombre = placa_raw

        placa = _normalize_placa_text(placa_raw)
        if not placa:
            continue

        homes = []
        for i, col in enumerate(home_cols, 1):
            value = row.get(col)
            if pd.isna(value):
                continue
            coords = re.findall(r"-?\d+\.?\d*", str(value))
            if len(coords) < 2:
                continue
            lat = float(coords[0])
            lon = float(coords[1])
            label = f"Casa {nombre}" if i == 1 else f"Casa {nombre} ({i})"
            homes.append({"label": label, "lat": lat, "lon": lon})

        if homes:
            homes_by_placa[placa] = homes

    return homes_by_placa


def load_photos_db(photos_file=None):
    if not photos_file:
        return []
    path = Path(photos_file)
    if not path.exists():
        return []

    try:
        df = pd.read_excel(path)
    except Exception:
        return []

    photos = []
    # Asegurar que las columnas coinciden aunque tengan espacios
    col_img = next((c for c in df.columns if "IMAGEN" in c.upper()), None)
    col_coord = next((c for c in df.columns if "CORDENADA" in c.upper() or "COORDENADA" in c.upper()), None)

    if not col_img or not col_coord:
        return []

    for _, row in df.iterrows():
        img_name = str(row[col_img]).strip()
        coords_str = str(row[col_coord]).strip()
        if not img_name or not coords_str or img_name.lower() == "nan":
            continue

        parts = re.findall(r"-?\d+\.?\d*", coords_str)
        if len(parts) >= 2:
            photos.append({
                "name": img_name,
                "lat": float(parts[0]),
                "lon": float(parts[1])
            })

    return photos

def _match_nearest(
    lat_series: pd.Series,
    lon_series: pd.Series,
    target_lats,
    target_lons,
    target_labels: list[str],
    radius_m: float,
) -> pd.Series:
    """Return a Series of nearest target labels within ``radius_m``, else None.

    Uses broadcasted haversine so the whole column is matched in one shot.
    """
    result = pd.Series([None] * len(lat_series), index=lat_series.index, dtype=object)
    if len(target_lats) == 0 or lat_series.empty:
        return result
    valid = lat_series.notna() & lon_series.notna()
    if not valid.any():
        return result

    lats = lat_series[valid].to_numpy(dtype=float)
    lons = lon_series[valid].to_numpy(dtype=float)
    target_lats = np.asarray(target_lats, dtype=float)
    target_lons = np.asarray(target_lons, dtype=float)

    dist = geo.haversine_matrix(lats, lons, target_lats, target_lons)
    best_idx = dist.argmin(axis=1)
    best_dist = dist[np.arange(len(lats)), best_idx]
    within = best_dist <= radius_m

    matched = np.array(
        [target_labels[best_idx[i]] if within[i] else None for i in range(len(best_idx))],
        dtype=object,
    )
    result.loc[valid] = matched
    return result


def clean_placa(series):
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
    )


def clean_conductor(series):
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )


def parse_duracion_segundos(series):
    def _parse(val):
        if pd.isna(val) or str(val).strip() in ("", "nan"):
            return 0
        s = str(val)
        h = int(m.group(1)) * 3600 if (m := re.search(r"(\d+)\s*h", s)) else 0
        m_ = int(m.group(1)) * 60 if (m := re.search(r"(\d+)\s*min", s)) else 0
        sec = int(m.group(1)) if (m := re.search(r"(\d+)\s*s\b", s)) else 0
        return h + m_ + sec

    return series.apply(_parse).astype(int)


def parse_velocidad_kph(series):
    return (
        series.fillna("")
        .astype(str)
        .str.extract(r"(\d+(?:\.\d+)?)\s*kph", expand=False)
        .astype(float)
    )


def parse_distancia_km(series):
    return (
        series.fillna("")
        .astype(str)
        .str.extract(r"(\d+(?:\.\d+)?)\s*[Kk][Mm]", expand=False)
        .astype(float)
    )


def add_derived_columns(df, homes_file=None, photos_file=None):
    from .validation import parse_dates

    df = df.copy()
    comienzo = parse_dates(df["Comienzo"])

    df["duracion_seg"] = parse_duracion_segundos(df["Duracion"])
    df["semana"] = comienzo.dt.isocalendar().week.astype("Int64")
    df["dia_semana"] = comienzo.dt.day_name()
    df["fecha"] = comienzo.dt.date

    df["vel_max_kph"] = parse_velocidad_kph(df.get("Vel_Max", pd.Series(dtype=str)))
    df["vel_media_kph"] = parse_velocidad_kph(df.get("Vel_Media", pd.Series(dtype=str)))

    df["distancia_km"] = None
    mov_mask = df["Estado"] == "Movimiento"
    df.loc[mov_mask, "distancia_km"] = parse_distancia_km(df.loc[mov_mask, "Posicion"])

    df["Placa"] = clean_placa(df["Placa"])
    df["Conductor"] = clean_conductor(df["Conductor"])

    # Known location tagging (offices + worker homes) for stop events.
    df["latitud"] = None
    df["longitud"] = None
    df["ubicacion_conocida"] = None
    df["imagen_url"] = None

    stop_mask = df["Estado"] == "Detenido"
    if stop_mask.any():
        lat_s, lon_s = parse_coordinates_series(df.loc[stop_mask, "Posicion"])
        df.loc[stop_mask, "latitud"] = lat_s
        df.loc[stop_mask, "longitud"] = lon_s

        # 1. Photos: single shared lookup, matched in one broadcasted pass.
        photos_db = load_photos_db(photos_file)
        if photos_db:
            photo_result = _match_nearest(
                lat_s,
                lon_s,
                [p["lat"] for p in photos_db],
                [p["lon"] for p in photos_db],
                [p["name"] for p in photos_db],
                RADIO_MATCH_METROS,
            )
            df.loc[stop_mask, "imagen_url"] = photo_result

        # 2. Offices: same broadcasting idea.
        office_result = _match_nearest(
            lat_s,
            lon_s,
            [o["lat"] for o in KNOWN_OFFICES.values()],
            [o["lon"] for o in KNOWN_OFFICES.values()],
            list(KNOWN_OFFICES.keys()),
            RADIO_MATCH_METROS,
        )
        df.loc[stop_mask, "ubicacion_conocida"] = office_result

        # 3. Worker homes: per-placa fallback (offices take precedence).
        homes_by_placa = load_worker_homes(homes_file)
        if homes_by_placa:
            stop_placas = df.loc[stop_mask, "Placa"]
            stop_ubic = df.loc[stop_mask, "ubicacion_conocida"]
            for placa, homes in homes_by_placa.items():
                sub = (stop_placas == placa) & stop_ubic.isna()
                if not sub.any():
                    continue
                sub_index = stop_placas[sub].index
                home_result = _match_nearest(
                    lat_s.loc[sub_index],
                    lon_s.loc[sub_index],
                    [h["lat"] for h in homes],
                    [h["lon"] for h in homes],
                    [h["label"] for h in homes],
                    RADIO_MATCH_METROS,
                )
                matched = home_result.dropna()
                if not matched.empty:
                    df.loc[matched.index, "ubicacion_conocida"] = matched

    return df
