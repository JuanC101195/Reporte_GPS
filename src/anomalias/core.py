"""Pure analytical logic for GPS anomalias.

All functions in this module are free of HTML/Folium rendering and
can be reused from a CLI, a notebook, or a web microservice.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..geo import haversine_matrix, haversine_metros
from ..transform import parse_coordinates, parse_duracion_segundos
from ..validation import parse_dates

# Constantes horarias operativas
HORARIO_INICIO = 8
HORARIO_FIN = 20
UMBRAL_PARADA_LARGA_SEG = 30 * 60
HORA_NOCTURNA_INICIO = 22
HORA_NOCTURNA_FIN = 6
RADIO_CLUSTER_METROS = 150
RADIO_ZONA_CONOCIDA_M = 200
VISITAS_LUGAR_FRECUENTE = 3

# Zonas conocidas cargadas desde json (con fallback en duro por si se borra)
_ZONAS_JSON_PATH = Path(__file__).resolve().parent.parent.parent / "zonas.json"

ZONAS_CONOCIDAS: list[dict] = []
try:
    with open(_ZONAS_JSON_PATH, encoding="utf-8") as f:
        ZONAS_CONOCIDAS = json.load(f)
except Exception:
    ZONAS_CONOCIDAS = [
        {"nombre": "Casa Blanca", "tipo": "oficina", "lat": 10.382486, "lon": -75.475173, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Renta Ya", "tipo": "oficina", "lat": 10.380147, "lon": -75.474889, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "La Consolata", "tipo": "oficina", "lat": 10.372929, "lon": -75.472837, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Casa Jaime - Carlitos", "tipo": "casa", "conductor": "Jaime - Carlitos", "lat": 10.372592, "lon": -75.474683, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Casa Jhonatan Gomez", "tipo": "casa", "conductor": "Jhonatan Gomez", "lat": 10.372700, "lon": -75.475891, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Casa Victor Grau", "tipo": "casa", "conductor": "Victor Grau", "lat": 10.373054, "lon": -75.472928, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Casa Julio Bello", "tipo": "casa", "conductor": "Julio Bello", "lat": 10.377404, "lon": -75.486535, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Casa Yilmer Sierra", "tipo": "casa", "conductor": "Yilmer Sierra", "lat": 10.373169, "lon": -75.472924, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Casa Julian Bello", "tipo": "casa", "conductor": "Julian Bello", "lat": 10.424527, "lon": -75.461526, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Casa Yanior", "tipo": "casa", "conductor": "Yanior", "lat": 10.385875, "lon": -75.459067, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Casa Wilder", "tipo": "casa", "conductor": "Wilder", "lat": 10.379178, "lon": -75.489432, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Casa Misael", "tipo": "casa", "conductor": "Misael", "lat": 10.372133, "lon": -75.480468, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Casa Luis Rafael", "tipo": "casa", "conductor": "Luis Rafael", "lat": 10.396344, "lon": -75.474550, "radio_m": RADIO_ZONA_CONOCIDA_M},
        {"nombre": "Casa Hugo", "tipo": "casa", "conductor": "Hugo", "lat": 10.374511, "lon": -75.474478, "radio_m": RADIO_ZONA_CONOCIDA_M},
    ]


def zona_mas_cercana(lat: float, lon: float, zonas: list[dict], conductor: str | None = None) -> tuple[dict | None, float | None]:
    """Retorna la zona válida dentro de radio más cercana."""
    mejor = None
    mejor_dist = float("inf")
    for z in zonas:
        if z.get("lat") is None or z.get("lon") is None:
            continue
        d = haversine_metros(lat, lon, float(z["lat"]), float(z["lon"]))
        if d <= float(z.get("radio_m", RADIO_ZONA_CONOCIDA_M)) and d < mejor_dist:
            if z.get("tipo") == "casa" and conductor and z.get("conductor") != conductor:
                continue
            mejor = z
            mejor_dist = d
    return mejor, (mejor_dist if mejor else None)


def zona_referencia_mas_cercana(lat: float, lon: float, zonas: list[dict]) -> tuple[dict | None, float | None]:
    """Zona más cercana sin validar radio para mostrar referencia."""
    candidatos = [z for z in zonas if z.get("lat") is not None and z.get("lon") is not None]
    if not candidatos:
        return None, None
    mejor = min(candidatos, key=lambda z: haversine_metros(lat, lon, float(z["lat"]), float(z["lon"])))
    dist = haversine_metros(lat, lon, float(mejor["lat"]), float(mejor["lon"]))
    return mejor, round(dist)


def _clasificar_paradas(df_det: pd.DataFrame, zonas: list[dict]) -> pd.DataFrame:
    out = df_det.copy()
    out["inicio_dt"] = parse_dates(out["Comienzo"])
    out["hora"] = out["inicio_dt"].dt.hour
    if "duracion_seg" not in out.columns:
        out["duracion_seg"] = parse_duracion_segundos(out["Duracion"])

    lat_lon = out["Posicion"].apply(parse_coordinates)
    out["lat"] = lat_lon.apply(lambda x: x[0])
    out["lon"] = lat_lon.apply(lambda x: x[1])

    zona_nombre = []
    tipo_zona = []
    es_anom = []
    es_nocturna = []
    fuera_horario = []
    larga_horario = []
    ref_nombre = []
    ref_dist = []

    for _, row in out.iterrows():
        lat = row["lat"]
        lon = row["lon"]
        conductor = row.get("Conductor")
        hora = int(row["hora"]) if pd.notna(row["hora"]) else -1
        dur_seg = int(row.get("duracion_seg", 0) or 0)

        if lat is None or lon is None:
            zona_nombre.append("Sin coordenada")
            tipo_zona.append(None)
            es_anom.append(False)
            es_nocturna.append(False)
            fuera_horario.append(False)
            larga_horario.append(False)
            ref_nombre.append(None)
            ref_dist.append(None)
            continue

        zm, _ = zona_mas_cercana(lat, lon, zonas, conductor=conductor)
        zr, dr = zona_referencia_mas_cercana(lat, lon, zonas)
        ref_nombre.append(zr.get("nombre") if zr else None)
        ref_dist.append(dr)

        if zm:
            zona_nombre.append(zm["nombre"])
            tipo_zona.append(zm.get("tipo"))
            es_anom.append(False)
            es_nocturna.append(False)
            fuera_horario.append(False)
            larga_horario.append(False)
            continue

        zona_nombre.append("Zona desconocida")
        tipo_zona.append(None)

        noct = hora >= HORA_NOCTURNA_INICIO or hora < HORA_NOCTURNA_FIN
        fuera = hora < HORARIO_INICIO or hora >= HORARIO_FIN
        larga = (HORARIO_INICIO <= hora < HORARIO_FIN) and dur_seg > UMBRAL_PARADA_LARGA_SEG

        es_anom.append(True)
        es_nocturna.append(noct)
        fuera_horario.append(fuera)
        larga_horario.append(larga)

    out["zona_nombre"] = zona_nombre
    out["tipo_zona"] = tipo_zona
    out["es_anomalia"] = es_anom
    out["es_nocturna"] = es_nocturna
    out["fuera_horario"] = fuera_horario
    out["larga_horario"] = larga_horario
    out["zona_ref_nombre"] = ref_nombre
    out["zona_ref_dist_m"] = ref_dist
    return out


def _cluster_unknown_rows(df_in: pd.DataFrame) -> list[dict]:
    clusters: list[dict] = []
    if df_in.empty:
        return clusters

    for idx, row in df_in.iterrows():
        lat, lon = row["lat"], row["lon"]
        if pd.isna(lat) or pd.isna(lon):
            continue
        assigned = False
        for c in clusters:
            d = haversine_metros(lat, lon, c["centroid_lat"], c["centroid_lon"])
            if d <= RADIO_CLUSTER_METROS:
                c["indices"].append(idx)
                n = len(c["indices"])
                c["centroid_lat"] = ((c["centroid_lat"] * (n - 1)) + lat) / n
                c["centroid_lon"] = ((c["centroid_lon"] * (n - 1)) + lon) / n
                assigned = True
                break
        if not assigned:
            clusters.append({"indices": [idx], "centroid_lat": float(lat), "centroid_lon": float(lon)})

    return clusters


def _cluster_rows(df_in: pd.DataFrame, radio_m: float) -> list[dict]:
    clusters: list[dict] = []
    if df_in.empty:
        return clusters

    for idx, row in df_in.iterrows():
        lat, lon = row.get("lat"), row.get("lon")
        if pd.isna(lat) or pd.isna(lon):
            continue
        assigned = False
        for c in clusters:
            d = haversine_metros(lat, lon, c["centroid_lat"], c["centroid_lon"])
            if d <= radio_m:
                c["indices"].append(idx)
                n = len(c["indices"])
                c["centroid_lat"] = ((c["centroid_lat"] * (n - 1)) + lat) / n
                c["centroid_lon"] = ((c["centroid_lon"] * (n - 1)) + lon) / n
                assigned = True
                break
        if not assigned:
            clusters.append({"indices": [idx], "centroid_lat": float(lat), "centroid_lon": float(lon)})

    return clusters


def _cluster_desconocidos(df_anomalias: pd.DataFrame, conductor: str) -> list[dict]:
    data = df_anomalias[(df_anomalias["Conductor"] == conductor) & (df_anomalias["es_anomalia"])].copy()
    if data.empty:
        return []

    clusters_raw = _cluster_unknown_rows(data)
    result = []

    for c in clusters_raw:
        sub = data.loc[c["indices"]].copy()
        sub["inicio_dt"] = parse_dates(sub["Comienzo"])
        coord = f"{c['centroid_lat']:.6f}, {c['centroid_lon']:.6f}"
        zona, dist = zona_referencia_mas_cercana(c["centroid_lat"], c["centroid_lon"], ZONAS_CONOCIDAS)

        result.append(
            {
                "conductor": conductor,
                "placa": sub["Placa"].mode().iloc[0] if not sub["Placa"].mode().empty else "-",
                "coord": coord,
                "lat": float(c["centroid_lat"]),
                "lon": float(c["centroid_lon"]),
                "visitas": len(sub),
                "visitas_fuera_horario": int(sub["fuera_horario"].sum()),
                "tiempo_total_seg": int(sub["duracion_seg"].sum()),
                "primera_visita": sub["inicio_dt"].min().strftime("%d-%m-%Y %H:%M") if sub["inicio_dt"].notna().any() else "-",
                "ultima_visita": sub["inicio_dt"].max().strftime("%d-%m-%Y %H:%M") if sub["inicio_dt"].notna().any() else "-",
                "zona_ref_nombre": zona["nombre"] if zona else "-",
                "zona_ref_dist_m": dist if dist is not None else "-",
            }
        )

    result.sort(key=lambda x: (-x["visitas"], -x["tiempo_total_seg"]))
    return result


def _fmt_horas(seg: int) -> str:
    """Convierte segundos a formato 'Xh Ym'."""
    total = int(seg) if seg else 0
    horas = total // 3600
    minutos = (total % 3600) // 60
    return f"{horas}h {minutos}m"


def _distancia_m(dist) -> float | None:
    if dist is None:
        return None
    if isinstance(dist, int | float):
        return float(dist)
    try:
        return float(str(dist).replace("m", "").strip())
    except ValueError:
        return None


def _ubicacion_repetida_semanal(det_c: pd.DataFrame) -> list[dict]:
    resumen = []
    if det_c.empty:
        return resumen

    det_c = det_c.copy()
    if "inicio_dt" not in det_c.columns:
        det_c["inicio_dt"] = parse_dates(det_c["Comienzo"])

    for conductor in sorted(det_c["Conductor"].dropna().unique()):
        sub = det_c[det_c["Conductor"] == conductor].copy()
        if sub.empty:
            continue
        clusters = _cluster_rows(sub, RADIO_CLUSTER_METROS)
        for c in clusters:
            subc = sub.loc[c["indices"]].copy()
            if len(subc) < 2:
                continue
            dur_total = int(subc["duracion_seg"].sum()) if "duracion_seg" in subc.columns else 0
            horas = subc["inicio_dt"].dt.hour.dropna().astype(int)
            hora_top = None
            hora_top_n = 0
            if not horas.empty:
                vc = horas.value_counts()
                hora_top = int(vc.index[0])
                hora_top_n = int(vc.iloc[0])
            item = {
                "conductor": conductor,
                "placa": subc["Placa"].mode().iloc[0] if not subc["Placa"].mode().empty else "-",
                "coord": f"{c['centroid_lat']:.6f}, {c['centroid_lon']:.6f}",
                "visitas": len(subc),
                "tiempo_total_seg": dur_total,
                "hora_top": f"{hora_top:02d}:00" if hora_top is not None else "-",
                "hora_top_n": hora_top_n,
            }
            resumen.append(item)

    return resumen


def _resumen_oficinas(det_c: pd.DataFrame) -> list[dict]:
    oficinas = det_c[det_c["tipo_zona"] == "oficina"].copy()
    if oficinas.empty:
        return []

    rows = []
    grp = oficinas.groupby(["Conductor", "Placa"], dropna=False)
    for (conductor, placa), g in grp:
        rows.append(
            {
                "conductor": conductor or "-",
                "placa": placa or "-",
                "visitas": len(g),
                "tiempo_total_seg": int(g["duracion_seg"].sum()) if "duracion_seg" in g.columns else 0,
            }
        )
    rows.sort(key=lambda r: (-r["visitas"], -r["tiempo_total_seg"]))
    return rows


RECURRENCE_RADIO_M = 50.0

# Mapeo de los dias que devuelve pandas (ingles, default) al nombre
# en espanol con tilde. Evita depender de locale del sistema (que en
# Windows y Linux se configura distinto y rompe en CI).
_DIAS_ES = {
    "Monday": "Lunes",
    "Tuesday": "Martes",
    "Wednesday": "Miércoles",
    "Thursday": "Jueves",
    "Friday": "Viernes",
    "Saturday": "Sábado",
    "Sunday": "Domingo",
}


def _paradas_largas(
    det_c: pd.DataFrame,
    umbral_seg: int,
    only_anomalas: bool = True,
) -> list[dict]:
    """Return stops longer than ``umbral_seg`` seconds.

    When ``only_anomalas`` is True (default), stops that match a known
    office or worker home are filtered out — the boss only cares about
    long stops in unknown places. Pass ``only_anomalas=False`` to audit
    all long stops regardless of zone.

    Each returned row is enriched with everything a director needs to
    judge the stop in one glance:

    - ``lat``/``lon``: raw floats so the renderer can embed a preview.
    - ``hora`` / ``hora_fin``: start and end of the stop (HH:MM).
    - ``n_veces``: how many times the SAME conductor has been within
      ``RECURRENCE_RADIO_M`` of this exact spot across the whole
      dataset (not just long stops). Tells "patron vs unique".
    """
    if det_c.empty:
        return []

    sub = det_c[det_c["duracion_seg"] >= umbral_seg].copy()
    if sub.empty:
        return []
    if only_anomalas and "tipo_zona" in sub.columns:
        sub = sub[sub["tipo_zona"].isna()].copy()
        if sub.empty:
            return []
    sub["inicio_dt"] = parse_dates(sub["Comienzo"])
    sub = sub[sub["inicio_dt"].notna()].copy()

    # Preload all stops with valid coords for the recurrence count.
    # Grouped by conductor so the per-row lookup is cheap.
    all_by_cond: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if {"lat", "lon", "Conductor"}.issubset(det_c.columns):
        valid = det_c[det_c["lat"].notna() & det_c["lon"].notna()]
        for conductor, grp in valid.groupby("Conductor"):
            all_by_cond[str(conductor)] = (
                grp["lat"].to_numpy(dtype=float),
                grp["lon"].to_numpy(dtype=float),
            )

    rows = []
    for _, r in sub.iterrows():
        inicio_dt = r["inicio_dt"]
        hora_int = int(inicio_dt.hour)
        dur_seg = int(r.get("duracion_seg", 0))
        fin_dt = inicio_dt + pd.Timedelta(seconds=dur_seg)

        lat_val = r.get("lat")
        lon_val = r.get("lon")
        lat_f = float(lat_val) if pd.notna(lat_val) else None
        lon_f = float(lon_val) if pd.notna(lon_val) else None

        # Recurrence count: same conductor within RECURRENCE_RADIO_M.
        n_veces = 1
        conductor_key = str(r.get("Conductor", ""))
        if lat_f is not None and lon_f is not None and conductor_key in all_by_cond:
            cand_lats, cand_lons = all_by_cond[conductor_key]
            if cand_lats.size > 0:
                dists = haversine_matrix([lat_f], [lon_f], cand_lats, cand_lons)[0]
                n_veces = int((dists <= RECURRENCE_RADIO_M).sum())

        rows.append(
            {
                "conductor": r.get("Conductor", "-"),
                "placa": r.get("Placa", "-"),
                "fecha": inicio_dt.strftime("%d-%m-%Y"),
                "dia_semana": _DIAS_ES.get(inicio_dt.day_name(), inicio_dt.day_name()),
                "hora": inicio_dt.strftime("%H:%M"),
                "hora_fin": fin_dt.strftime("%H:%M"),
                "hora_int": hora_int,
                "duracion_seg": dur_seg,
                "coord": r.get("Posicion", "-"),
                "lat": lat_f,
                "lon": lon_f,
                "zona": r.get("zona_nombre", "-"),
                "fuera_horario": hora_int < HORARIO_INICIO or hora_int >= HORARIO_FIN,
                "es_nocturna": hora_int >= HORA_NOCTURNA_INICIO or hora_int < HORA_NOCTURNA_FIN,
                "n_veces": n_veces,
            }
        )
    rows.sort(key=lambda r: (r["conductor"], -r["duracion_seg"]))
    return rows


# Thresholds for the executive-level suspicion score. Calibrated for a
# delivery fleet in Cartagena where drivers normally spend most of their
# time outside known bases — the strong signal is *frequent* unknown
# places, NOT raw hours in unknowns (that is just their job).
SCORE_THRESHOLD_ROJO = 30.0
SCORE_THRESHOLD_AMARILLO = 12.0

# Weights per factor (tuned with the boss-as-user perspective).
# lugares_frecuentes is the king signal: revisiting the same unknown
# spot 3+ times within a week is what justifies a conversation.
WEIGHT_HORAS_DESC = 0.5
WEIGHT_PARADAS_ANOM = 3.0
WEIGHT_LUGARES_FREC = 15.0
WEIGHT_HORAS_FUERA = 4.0


def _nivel_score(score: float) -> str:
    if score >= SCORE_THRESHOLD_ROJO:
        return "ROJO"
    if score >= SCORE_THRESHOLD_AMARILLO:
        return "AMARILLO"
    return "VERDE"


def ranking_conductores(
    det_c: pd.DataFrame,
    anom: pd.DataFrame,
    clusters_por_conductor: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Return conductors sorted by suspicion score, worst first.

    The score combines four factors weighted by business impact:

        score = horas_desconocidas  * WEIGHT_HORAS_DESC   (0.5)
              + paradas_anomalas    * WEIGHT_PARADAS_ANOM (3)
              + lugares_frecuentes  * WEIGHT_LUGARES_FREC (15)
              + horas_fuera_horario * WEIGHT_HORAS_FUERA  (4)

    Each entry in the result contains ``conductor``, ``placa``, the raw
    inputs, the computed ``score``, a ``nivel`` label (ROJO/AMARILLO/VERDE)
    and the ``peor_cluster`` (worst unknown place the driver visited).
    """
    if det_c.empty:
        return []

    clusters_por_conductor = clusters_por_conductor or {}
    rows: list[dict] = []

    for conductor in sorted(det_c["Conductor"].dropna().unique()):
        cdet = det_c[det_c["Conductor"] == conductor]
        canom = anom[anom["Conductor"] == conductor] if not anom.empty else anom.iloc[0:0]
        placa = cdet["Placa"].mode().iloc[0] if not cdet["Placa"].mode().empty else "-"

        horas_desc = float(canom["duracion_seg"].sum()) / 3600.0 if not canom.empty else 0.0
        paradas_anom = int((canom["duracion_seg"] >= UMBRAL_PARADA_LARGA_SEG).sum()) if not canom.empty else 0

        clusters = clusters_por_conductor.get(conductor, [])
        lugares_frec = sum(1 for cl in clusters if cl.get("visitas", 0) >= VISITAS_LUGAR_FRECUENTE)

        if not canom.empty:
            mask_fuera = canom.get("fuera_horario", pd.Series(False, index=canom.index)).astype(bool)
            mask_noct = canom.get("es_nocturna", pd.Series(False, index=canom.index)).astype(bool)
            horas_fuera = float(canom.loc[mask_fuera | mask_noct, "duracion_seg"].sum()) / 3600.0
        else:
            horas_fuera = 0.0

        score = (
            horas_desc * WEIGHT_HORAS_DESC
            + paradas_anom * WEIGHT_PARADAS_ANOM
            + lugares_frec * WEIGHT_LUGARES_FREC
            + horas_fuera * WEIGHT_HORAS_FUERA
        )
        nivel = _nivel_score(score)

        peor_cluster = None
        if clusters:
            peor_cluster = max(
                clusters,
                key=lambda c: int(c.get("visitas", 0)) * int(c.get("tiempo_total_seg", 0)),
            )

        rows.append(
            {
                "conductor": conductor,
                "placa": placa,
                "horas_desconocidas": round(horas_desc, 2),
                "paradas_anomalas": paradas_anom,
                "lugares_frecuentes": lugares_frec,
                "horas_fuera_horario": round(horas_fuera, 2),
                "score": round(score, 1),
                "nivel": nivel,
                "peor_cluster": peor_cluster,
            }
        )

    rows.sort(key=lambda r: -r["score"])
    return rows


def _coincidencias_ruta(det_c: pd.DataFrame) -> list[dict]:
    if det_c.empty:
        return []

    mov = det_c.copy()
    if "inicio_dt" not in mov.columns:
        mov["inicio_dt"] = parse_dates(mov["Comienzo"])

    mov = mov[mov["inicio_dt"].notna()].copy()

    if "lat" not in mov.columns or "lon" not in mov.columns:
        lat_lon = mov["Posicion"].apply(parse_coordinates)
        mov["lat"] = lat_lon.apply(lambda x: x[0])
        mov["lon"] = lat_lon.apply(lambda x: x[1])

    mov = mov[mov["lat"].notna() & mov["lon"].notna()].copy()
    if mov.empty:
        return []

    mov["hora_key"] = mov["inicio_dt"].dt.strftime("%d-%m-%Y %H:00")
    rows = []
    for hora_key, g in mov.groupby("hora_key"):
        clusters = _cluster_rows(g, RADIO_CLUSTER_METROS)
        for c in clusters:
            subc = g.loc[c["indices"]].copy()
            placas = sorted(subc["Placa"].dropna().unique())
            if len(placas) < 2:
                continue
            conductores = sorted(subc["Conductor"].dropna().unique())
            rows.append(
                {
                    "hora": hora_key,
                    "coord": f"{c['centroid_lat']:.6f}, {c['centroid_lon']:.6f}",
                    "placas": ", ".join(placas),
                    "conductores": ", ".join(conductores) if conductores else "-",
                    "n_placas": len(placas),
                }
            )

    rows.sort(key=lambda r: (-r["n_placas"], r["hora"]))
    return rows
