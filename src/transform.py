"""Cleaning and enrichment helpers for GPS pipeline."""

import re
from pathlib import Path

import pandas as pd

KNOWN_OFFICES = {
    "Casa Blanca": {"lat": 10.382486, "lon": -75.475173},
    "Renta Ya": {"lat": 10.380147, "lon": -75.474889},
}


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


def identify_office(lat, lon, tolerance=0.0018):
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return None
    for name, coords in KNOWN_OFFICES.items():
        if abs(lat - coords["lat"]) <= tolerance and abs(lon - coords["lon"]) <= tolerance:
            return name
    return None


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

def identify_photo(lat, lon, photos_db, tolerance=0.0018):
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return None
    for p in photos_db:
        if abs(lat - p["lat"]) <= tolerance and abs(lon - p["lon"]) <= tolerance:
            return p["name"]
    return None

def identify_worker_home(lat, lon, placa, homes_by_placa, tolerance=0.0018):
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return None
    placa_norm = _normalize_placa_text(placa)
    if not placa_norm or placa_norm not in homes_by_placa:
        return None
    for home in homes_by_placa[placa_norm]:
        if abs(lat - home["lat"]) <= tolerance and abs(lon - home["lon"]) <= tolerance:
            return home["label"]
    return None


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
        coords = df.loc[stop_mask, "Posicion"].apply(parse_coordinates)
        df.loc[stop_mask, "latitud"] = coords.apply(lambda x: x[0])
        df.loc[stop_mask, "longitud"] = coords.apply(lambda x: x[1])

        homes_by_placa = load_worker_homes(homes_file)
        photos_db = load_photos_db(photos_file)
        for idx in df[stop_mask].index:
            lat = df.at[idx, "latitud"]
            lon = df.at[idx, "longitud"]

            # 1. Foto / Imagen
            photo = identify_photo(lat, lon, photos_db)
            if photo:
                df.at[idx, "imagen_url"] = photo

            # 2. Ubicaciones conocidas
            office = identify_office(lat, lon)
            if not office:
                office = identify_worker_home(lat, lon, df.at[idx, "Placa"], homes_by_placa)
            if office:
                df.at[idx, "ubicacion_conocida"] = office

    return df
