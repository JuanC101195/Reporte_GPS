"""Reporte ejecutivo de inteligencia operativa (anomalias GPS)."""

from __future__ import annotations

import json
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import pandas as pd

from .transform import parse_coordinates, parse_duracion_segundos
from .validation import parse_dates

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
_ZONAS_JSON_PATH = Path(__file__).resolve().parent.parent / "zonas.json"

ZONAS_CONOCIDAS = []
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


def haversine_metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * r * asin(sqrt(a))


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

        # Toda parada en zona desconocida cuenta para revisión (especialmente para encontrar lugares frecuentes)
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


def _detectar_alertas(df_anomalias: pd.DataFrame) -> list[dict]:
    alerts = []

    for _, r in df_anomalias.iterrows():
        dur = int(r.get("duracion_seg", 0) or 0)
        horas = dur / 3600.0
        base = {
            "conductor": r.get("Conductor", "-"),
            "placa": r.get("Placa", "-"),
            "fecha": r.get("Comienzo", "-"),
            "duracion_seg": dur,
            "posicion": r.get("Posicion", "-"),
            "lat": r.get("lat"),
            "lon": r.get("lon"),
            "zona_ref_nombre": r.get("zona_ref_nombre", "-"),
            "zona_ref_dist_m": r.get("zona_ref_dist_m", "-"),
            "imagen_url": r.get("imagen_url", "-"),
        }

        if bool(r.get("es_nocturna", False)):
            sev = "CRITICA" if horas > 2 else ("ALTA" if dur > 30 * 60 else "MEDIA")
            alerts.append({**base, "tipo": "PARADA NOCTURNA en zona desconocida", "icono": "🌙", "severidad": sev})

        if bool(r.get("larga_horario", False)):
            sev = "CRITICA" if horas > 4 else ("ALTA" if horas >= 1 else "MEDIA")
            alerts.append({**base, "tipo": "PARADA LARGA EN HORARIO LABORAL en zona desconocida", "icono": "⏱", "severidad": sev})

        if bool(r.get("fuera_horario", False)) and dur > 30 * 60:
            sev = "ALTA" if horas > 2 else "MEDIA"
            alerts.append({**base, "tipo": "PARADA FUERA DE HORARIO LABORAL en zona desconocida", "icono": "🌅", "severidad": sev})

    for conductor in sorted(df_anomalias["Conductor"].dropna().unique()):
        cdf = df_anomalias[df_anomalias["Conductor"] == conductor].copy()
        clusters = _cluster_desconocidos(cdf, conductor)
        for cl in clusters:
            if cl["visitas"] >= VISITAS_LUGAR_FRECUENTE:
                alerts.append(
                    {
                        "tipo": "LUGAR FRECUENTE DESCONOCIDO",
                        "icono": "📍",
                        "conductor": conductor,
                        "placa": cl.get("placa", "-"),
                        "fecha": cl["ultima_visita"],
                        "duracion_seg": cl["tiempo_total_seg"],
                        "posicion": cl["coord"],
                        "severidad": "ALTA",
                        "zona_ref_nombre": cl.get("zona_ref_nombre", "-"),
                        "zona_ref_dist_m": cl.get("zona_ref_dist_m", "-"),
                        "imagen_url": cl.get("imagen_url", "-"),
                    }
                )

    sev_rank = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2}
    alerts.sort(key=lambda a: (sev_rank.get(a["severidad"], 9), -int(a.get("duracion_seg", 0))))
    return alerts


def _metricas_conductor(df_cond: pd.DataFrame, placa: str, df_anomalias_cond: pd.DataFrame) -> dict:
    largas = df_anomalias_cond[df_anomalias_cond["larga_horario"]]
    fuera = df_anomalias_cond[df_anomalias_cond["fuera_horario"]]
    noct = df_anomalias_cond[df_anomalias_cond["es_nocturna"]]

    paradas_largas = len(largas)
    horas_largas = int(largas["duracion_seg"].sum())
    paradas_fuera = len(fuera)
    horas_fuera = int(fuera["duracion_seg"].sum())
    paradas_noct = len(noct)
    horas_noct = int(noct["duracion_seg"].sum())

    crit_unica = bool((largas["duracion_seg"] > 4 * 3600).any())

    if paradas_noct > 0 or crit_unica:
        riesgo = "CRITICO"
    elif paradas_largas > 15 or paradas_fuera > 20:
        riesgo = "ALTO"
    else:
        riesgo = "NORMAL"

    return {
        "conductor": df_cond["Conductor"].iloc[0] if not df_cond.empty else "-",
        "placa": placa,
        "paradas_largas": paradas_largas,
        "horas_largas": horas_largas,
        "paradas_fuera": paradas_fuera,
        "horas_fuera": horas_fuera,
        "paradas_noct": paradas_noct,
        "horas_noct": horas_noct,
        "riesgo": riesgo,
    }


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

        # Tratar de obtener la imagen del sub set original si existe
        imagen_url = "-"
        if "imagen_url" in sub.columns:
            # Tomar la primera imagen que no sea nula/vacia
            imagenes = sub["imagen_url"].dropna()
            imagenes = imagenes[imagenes != ""]
            if not imagenes.empty:
                imagen_url = str(imagenes.iloc[0])

        result.append(
            {
                "conductor": conductor,
                "placa": sub["Placa"].mode().iloc[0] if not sub["Placa"].mode().empty else "-",
                "coord": coord,
                "visitas": len(sub),
                "visitas_fuera_horario": int(sub["fuera_horario"].sum()),
                "tiempo_total_seg": int(sub["duracion_seg"].sum()),
                "primera_visita": sub["inicio_dt"].min().strftime("%d-%m-%Y %H:%M") if sub["inicio_dt"].notna().any() else "-",
                "ultima_visita": sub["inicio_dt"].max().strftime("%d-%m-%Y %H:%M") if sub["inicio_dt"].notna().any() else "-",
                "zona_ref_nombre": zona["nombre"] if zona else "-",
                "zona_ref_dist_m": dist if dist is not None else "-",
                "imagen_url": imagen_url,
            }
        )

    result.sort(key=lambda x: (-x["visitas"], -x["tiempo_total_seg"]))
    return result


def _heatmap_data(
    df_anomalias: pd.DataFrame,
) -> tuple[list[str], list[str], dict[str, dict[str, int]], dict[str, dict[str, dict]], dict[str, int], dict[str, int]]:
    base = df_anomalias[(df_anomalias["es_nocturna"]) | (df_anomalias["fuera_horario"]) | (df_anomalias["larga_horario"])].copy()
    if not base.empty:
        base = base[base["zona_ref_dist_m"].apply(_distancia_m).fillna(float("inf")) > 200].copy()
    base["inicio_dt"] = parse_dates(base["Comienzo"])
    base = base[base["inicio_dt"].notna()].copy()
    base["dia"] = base["inicio_dt"].dt.strftime("%d-%m-%Y")

    dias = sorted(base["dia"].unique())
    conductores = sorted(base["Conductor"].dropna().unique())

    matrix = {d: {c: 0 for c in conductores} for d in dias}
    tipo_counts = {d: {c: {"larga": 0, "fuera": 0, "noct": 0} for c in conductores} for d in dias}

    if not base.empty:
        grp = base.groupby(["dia", "Conductor"]).size().reset_index(name="n")
        for _, r in grp.iterrows():
            matrix[r["dia"]][r["Conductor"]] = int(r["n"])

        for _, r in base.iterrows():
            d = r["dia"]
            c = r["Conductor"]
            if d not in tipo_counts or c not in tipo_counts[d]:
                continue
            if bool(r.get("larga_horario")):
                tipo_counts[d][c]["larga"] += 1
            if bool(r.get("fuera_horario")):
                tipo_counts[d][c]["fuera"] += 1
            if bool(r.get("es_nocturna")):
                tipo_counts[d][c]["noct"] += 1

    total_por_conductor = {c: sum(matrix[d][c] for d in dias) for c in conductores}
    total_por_dia = {d: sum(matrix[d][c] for c in conductores) for d in dias}
    conductores_sorted = sorted(conductores, key=lambda c: total_por_conductor.get(c, 0), reverse=True)

    return dias, conductores_sorted, matrix, tipo_counts, total_por_conductor, total_por_dia


def _fmt_horas(seg: int) -> str:
    """Convierte segundos a formato 'Xh Ym'."""
    total = int(seg) if seg else 0
    horas = total // 3600
    minutos = (total % 3600) // 60
    return f"{horas}h {minutos}m"


def _badge_riesgo(riesgo: str) -> str:
    if riesgo == "CRITICO":
        return "<span class='badge-crit'>🔴 CRITICO</span>"
    if riesgo == "ALTO":
        return "<span class='badge-alto'>🟡 ALTO</span>"
    return "<span class='badge-normal'>🟢 NORMAL</span>"


def _heat_color(n: int) -> str:
    if n == 0:
        return "#f9fafb"
    if 1 <= n <= 3:
        return "#bbf7d0"
    if 4 <= n <= 6:
        return "#fde68a"
    if 7 <= n <= 9:
        return "#f97316"
    return "#dc2626"


def _alert_tipo_corto(alerta: dict) -> str:
    tipo = str(alerta.get("tipo", "")).upper()
    if "NOCTURNA" in tipo:
        return f"{alerta.get('icono', '🌙')} Nocturna"
    if "LARGA" in tipo:
        return f"{alerta.get('icono', '⏱')} Larga"
    if "FUERA" in tipo:
        return f"{alerta.get('icono', '🌅')} Fuera horario"
    if "FRECUENTE" in tipo:
        return f"{alerta.get('icono', '📍')} Frecuente"
    return f"{alerta.get('icono', '⚠️')} Alerta"


def _coordenadas_alerta(alerta: dict) -> tuple[float | None, float | None]:
    lat = alerta.get("lat")
    lon = alerta.get("lon")
    if pd.notna(lat) and pd.notna(lon):
        return float(lat), float(lon)
    pos = alerta.get("posicion", "")
    lat_p, lon_p = parse_coordinates(pos)
    if lat_p is None or lon_p is None:
        return None, None
    return float(lat_p), float(lon_p)


def _group_alertas(alertas: list[dict], max_dist_m: float = 50.0) -> list[dict]:
    """Agrupa alertas por conductor/placa/tipo cuando estan muy cerca (<50m)."""
    grupos: list[dict] = []
    for alerta in alertas:
        lat, lon = _coordenadas_alerta(alerta)
        if lat is None or lon is None:
            grupos.append({**alerta, "n_veces": 1, "fecha_rango": alerta.get("fecha", "-")})
            continue

        key = (
            alerta.get("conductor", "-"),
            alerta.get("placa", "-"),
            alerta.get("tipo", "-"),
        )

        match = None
        for g in grupos:
            if g.get("group_key") != key:
                continue
            if g.get("lat") is None or g.get("lon") is None:
                continue
            if haversine_metros(lat, lon, g["lat"], g["lon"]) <= max_dist_m:
                match = g
                break

        if not match:
            fecha = alerta.get("fecha", "-")
            fecha_dt = parse_dates(pd.Series([fecha])).iloc[0]
            grupos.append(
                {
                    **alerta,
                    "lat": lat,
                    "lon": lon,
                    "n_veces": 1,
                    "fecha_min": fecha_dt,
                    "fecha_max": fecha_dt,
                    "fecha_rango": fecha,
                    "duracion_total_seg": int(alerta.get("duracion_seg", 0)),
                    "group_key": key,
                }
            )
            continue

        match["n_veces"] += 1
        match["duracion_total_seg"] = int(match.get("duracion_total_seg", 0)) + int(alerta.get("duracion_seg", 0))
        fecha = alerta.get("fecha", "-")
        fecha_dt = parse_dates(pd.Series([fecha])).iloc[0]
        if pd.notna(fecha_dt):
            if match.get("fecha_min") is None or fecha_dt < match.get("fecha_min"):
                match["fecha_min"] = fecha_dt
            if match.get("fecha_max") is None or fecha_dt > match.get("fecha_max"):
                match["fecha_max"] = fecha_dt
        if match.get("fecha_min") is not None and match.get("fecha_max") is not None:
            fmin = match["fecha_min"].strftime("%d-%m-%Y %H:%M")
            fmax = match["fecha_max"].strftime("%d-%m-%Y %H:%M")
            match["fecha_rango"] = f"{fmin} → {fmax}"
        elif match.get("fecha"):
            match["fecha_rango"] = match["fecha"]

    for g in grupos:
        if g.get("n_veces", 1) <= 1:
            g["duracion_total_seg"] = int(g.get("duracion_seg", 0))
            g["fecha_rango"] = g.get("fecha", "-")
    return grupos


def _distancia_m(dist) -> float | None:
    if dist is None:
        return None
    if isinstance(dist, (int, float)):
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


def _productividad_semaforo(det_c: pd.DataFrame) -> list[dict]:
    rows = []
    if det_c.empty:
        return rows

    total_prom = float(det_c["duracion_seg"].mean()) if "duracion_seg" in det_c.columns else 0.0
    total_unknown = float(det_c["es_anomalia"].mean()) if "es_anomalia" in det_c.columns else 0.0
    total_det_by_conductor = (
        det_c.groupby("Conductor")["duracion_seg"].sum() if "duracion_seg" in det_c.columns else pd.Series()
    )
    total_det_prom = float(total_det_by_conductor.mean()) if not total_det_by_conductor.empty else 0.0

    for conductor in sorted(det_c["Conductor"].dropna().unique()):
        sub = det_c[det_c["Conductor"] == conductor].copy()
        if sub.empty:
            continue
        placa = sub["Placa"].mode().iloc[0] if not sub["Placa"].mode().empty else "-"
        avg_det = float(sub["duracion_seg"].mean()) if "duracion_seg" in sub.columns else 0.0
        total_det = float(sub["duracion_seg"].sum()) if "duracion_seg" in sub.columns else 0.0
        unknown_ratio = float(sub["es_anomalia"].mean()) if "es_anomalia" in sub.columns else 0.0
        avg_min = avg_det / 60.0
        unknown_pct = unknown_ratio * 100.0

        if (
            avg_det <= total_prom * 1.1
            and unknown_ratio <= total_unknown * 1.1
            and total_det <= total_det_prom * 1.1
        ):
            nivel = "VERDE"
        elif (
            avg_det <= total_prom * 1.3
            and unknown_ratio <= total_unknown * 1.3
            and total_det <= total_det_prom * 1.3
        ):
            nivel = "AMARILLO"
        else:
            nivel = "ROJO"

        rows.append(
            {
                "conductor": conductor,
                "placa": placa,
                "avg_min": avg_min,
                "unknown_pct": unknown_pct,
                "nivel": nivel,
            }
        )

    return rows


def _paradas_largas(det_c: pd.DataFrame, umbral_seg: int) -> list[dict]:
    if det_c.empty:
        return []

    # Filtramos CUALQUIER parada que supere los 30 min (tanto autorizadas como anomalías)
    sub = det_c[det_c["duracion_seg"] >= umbral_seg].copy()
    if sub.empty:
        return []
    sub["inicio_dt"] = parse_dates(sub["Comienzo"])
    sub = sub[sub["inicio_dt"].notna()].copy()

    rows = []
    for _, r in sub.iterrows():
        hora = r["inicio_dt"].strftime("%H:%M")
        fecha = r["inicio_dt"].strftime("%d-%m-%Y")
        rows.append(
            {
                "conductor": r.get("Conductor", "-"),
                "placa": r.get("Placa", "-"),
                "fecha": fecha,
                "hora": hora,
                "duracion_seg": int(r.get("duracion_seg", 0)),
                "coord": r.get("Posicion", "-"),
                "zona": r.get("zona_nombre", "-"),
            }
        )
    # Ordenamos primero ALFABÉTICAMENTE por trabajador (conductor), y luego por la parada más larga de ese conductor
    rows.sort(key=lambda r: (r["conductor"], -r["duracion_seg"]))
    return rows


def _coincidencias_ruta(det_c: pd.DataFrame) -> list[dict]:
    if det_c.empty:
        return []

    # Se agrupan paradas
    mov = det_c.copy()
    if "inicio_dt" not in mov.columns:
        mov["inicio_dt"] = parse_dates(mov["Comienzo"])

    mov = mov[mov["inicio_dt"].notna()].copy()

    # det_c already has lat and lon from transform, but if not:
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


def generar_html_anomalias(df: pd.DataFrame, zonas: list[dict], output_path: Path, periodo_label: str | None = None) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = df.copy()
    if "Conductor" in df.columns:
        df["Conductor"] = df["Conductor"].astype(str).str.strip()
    if "Placa" in df.columns:
        df["Placa"] = df["Placa"].astype(str).str.strip()
    # Omit GPS records between 20:00 and 08:00 before building the report.
    inicio_dt = parse_dates(df["Comienzo"])
    df = df[inicio_dt.notna()].copy()
    df = df[inicio_dt.dt.hour.between(8, 19)].copy()
    det = df[df["Estado"] == "Detenido"].copy()
    if det.empty:
        output_path.write_text("<html><body><h2>Sin paradas para analizar.</h2></body></html>", encoding="utf-8")
        return output_path

    det_c = _clasificar_paradas(det, zonas)
    anom = det_c[det_c["es_anomalia"]].copy()

    resumen_rows = []
    for placa in sorted(df["Placa"].dropna().unique()):
        dcond = df[df["Placa"] == placa]
        acond = anom[anom["Placa"] == placa]
        m = _metricas_conductor(dcond, placa, acond)
        resumen_rows.append(m)

    alerts = _detectar_alertas(anom)[:40]

    clusters_por_conductor = {}
    for conductor in sorted(anom["Conductor"].dropna().unique()):
        clusters = _cluster_desconocidos(anom, conductor)
        clusters_por_conductor[conductor] = [c for c in clusters if c["visitas"] >= 2][:5]

    dias, conductores, heat, heat_tipos, total_cond, total_dia = _heatmap_data(anom)

    ubicacion_rep = _ubicacion_repetida_semanal(det_c)
    oficinas_rows = _resumen_oficinas(det_c)
    productividad_rows = _productividad_semaforo(det_c)
    paradas_largas = _paradas_largas(det_c, UMBRAL_PARADA_LARGA_SEG)
    coincidencias = _coincidencias_ruta(det_c)

    periodo = periodo_label or (
        f"{det_c['Comienzo'].min()} a {det_c['Comienzo'].max()}" if not det_c.empty else "-"
    )

    resumen_html = []
    for r in resumen_rows:
        resumen_html.append(
            "<tr>"
            f"<td>{r['conductor']}</td>"
            f"<td>{r['placa']}</td>"
            f"<td>{r['paradas_largas']}</td>"
            f"<td>{_fmt_horas(r['horas_largas'])}</td>"
            f"<td>{r['paradas_fuera']}</td>"
            f"<td>{_fmt_horas(r['horas_fuera'])}</td>"
            f"<td>{r['paradas_noct']}</td>"
            f"<td>{_fmt_horas(r['horas_noct'])}</td>"
            f"<td>{_badge_riesgo(r['riesgo'])}</td>"
            "</tr>"
        )

    alertas_filtradas = []
    for a in alerts:
        dist = _distancia_m(a.get("zona_ref_dist_m"))
        if dist is None or dist > 200:
            alertas_filtradas.append(a)

    alertas_grouped = _group_alertas(alertas_filtradas, max_dist_m=50.0)
    sev_rank = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2}
    alertas_grouped.sort(
        key=lambda a: (
            sev_rank.get(a.get("severidad"), 9),
            -int(a.get("duracion_total_seg", a.get("duracion_seg", 0))),
        )
    )
    rows_alertas = []
    for a in alertas_grouped:
        cls = "row-media"
        if a.get("severidad") == "CRITICA":
            cls = "row-crit"
        elif a.get("severidad") == "ALTA":
            cls = "row-alta"

        duracion = _fmt_horas(int(a.get("duracion_total_seg", a.get("duracion_seg", 0))))
        veces = int(a.get("n_veces", 1))
        veces_txt = f" · {veces} veces" if veces > 1 else ""
        fecha_txt = a.get("fecha_rango", a.get("fecha", "-"))
        tipo_corto = _alert_tipo_corto(a)
        ubicacion = a.get("posicion", "-")
        distancia = f"a {a.get('zona_ref_dist_m','-')}m de {a.get('zona_ref_nombre','-')}"

        rows_alertas.append(
            "<tr class='" + cls + "'>"
            f"<td class='alert-type'>{tipo_corto}<span class='sev-tag'>{a.get('severidad','')}</span></td>"
            f"<td>{a.get('conductor','-')}<br><span class='muted'>{a.get('placa','-')}</span></td>"
            f"<td>{fecha_txt}</td>"
            f"<td>{duracion}{veces_txt}</td>"
            f"<td>{ubicacion}</td>"
            f"<td>{distancia}</td>"
            "</tr>"
        )

    clusters_html = []
    for conductor, clusters in clusters_por_conductor.items():
        if not clusters:
            continue
        clusters = [c for c in clusters if _distancia_m(c.get("zona_ref_dist_m")) is None or _distancia_m(c.get("zona_ref_dist_m")) > 200]
        if not clusters:
            continue
        clusters = sorted(clusters, key=lambda c: int(c.get("tiempo_total_seg", 0)), reverse=True)
        rows = []
        for c in clusters:
            img_html = "-"
            img_url = c.get("imagen_url")
            if img_url and img_url != "-":
                # Check if it exists in reportes/img
                img_path = Path("reportes/img") / f"{img_url}.jpeg"
                if img_path.exists():
                    img_html = f"<a href='img/{img_url}.jpeg' target='_blank'><img src='img/{img_url}.jpeg' style='max-height:30px;border-radius:4px;'></a>"
                else:
                    img_html = f"Sin imagen ({img_url})"

            rows.append(
                "<tr>"
                f"<td>{c['coord']}</td>"
                f"<td>{c['visitas']}</td>"
                f"<td>{c['visitas_fuera_horario']}</td>"
                f"<td>{_fmt_horas(c['tiempo_total_seg'])}</td>"
                f"<td>{c['zona_ref_dist_m']}m de {c['zona_ref_nombre']}</td>"
                f"<td>{c['primera_visita']}</td>"
                f"<td>{c['ultima_visita']}</td>"
                f"<td>{img_html}</td>"
                "</tr>"
            )
        clusters_html.append(
            "<div class='cond-block' id='cond-" + conductor.replace(" ", "_") + "'>"
            f"<div class='cond-name'>👤 {conductor}</div>"
            "<div class='tbl-wrap'>"
            "<table><thead><tr><th>Coordenada</th><th>Visitas</th><th>Fuera horario</th><th>Tiempo acum.</th><th>Zona ref.</th><th>Primera</th><th>Ultima</th><th>Imagen</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
            "</div>"
            "</div>"
        )

    heat_rows = []
    for d in dias:
        row_total = total_dia.get(d, 0)
        cols = [f"<td class='heat-day'>{d}</td>"]
        for c in conductores:
            n = int(heat[d][c])
            tipos = heat_tipos.get(d, {}).get(c, {"larga": 0, "fuera": 0, "noct": 0})
            detalle = f"⏱️ Largas: {tipos['larga']} | 🌅 Fuera: {tipos['fuera']} | 🌙 Nocturnas: {tipos['noct']}"
            tooltip = f"🔴 {n} anomalías" if n >= 10 else (f"🟠 {n} anomalías" if n >= 7 else (f"🟡 {n} anomalías" if n >= 4 else (f"🟢 {n} anomalías" if n >= 1 else "⚪ 0 anomalías")))
            tooltip = f"{tooltip} | {detalle}"
            crit = " ⚠️" if n >= 10 else ""
            outline = "outline: 1px solid #b91c1c;" if n >= 10 else ""
            cols.append(
                f"<td class='heat-cell' style='background:{_heat_color(n)}; text-align:center; {outline}' title='{tooltip}'>{n}{crit}</td>"
            )
        cols.append(f"<td class='heat-total'>{row_total}</td>")
        heat_rows.append(f"<tr>{''.join(cols)}</tr>")

    total_cols = ["<td class='heat-total'>Total</td>"]
    for c in conductores:
        total_cols.append(f"<td class='heat-total'>{total_cond.get(c, 0)}</td>")
    total_cols.append(f"<td class='heat-total'>{sum(total_dia.values())}</td>")
    heat_rows.append(f"<tr class='heat-total-row'>{''.join(total_cols)}</tr>")

    fecha_gen = datetime.now().strftime("%d-%m-%Y %H:%M")

    productividad_html = []
    for r in productividad_rows:
        nivel = r["nivel"]
        badge_cls = "badge-verde" if nivel == "VERDE" else ("badge-amarillo" if nivel == "AMARILLO" else "badge-rojo")
        productividad_html.append(
            "<tr>"
            f"<td>{r['conductor']}</td>"
            f"<td>{r['placa']}</td>"
            f"<td>{r['avg_min']:.1f} min</td>"
            f"<td>{r['unknown_pct']:.0f}%</td>"
            f"<td><span class='{badge_cls}'>{nivel}</span></td>"
            "</tr>"
        )

    repetidas_html = []
    for r in ubicacion_rep:
        repetidas_html.append(
            "<tr>"
            f"<td>{r['conductor']}</td>"
            f"<td>{r['placa']}</td>"
            f"<td>{r['coord']}</td>"
            f"<td>{r['visitas']}</td>"
            f"<td>{_fmt_horas(r['tiempo_total_seg'])}</td>"
            "</tr>"
        )

    oficinas_html = []
    for r in oficinas_rows:
        oficinas_html.append(
            "<tr>"
            f"<td>{r['conductor']}</td>"
            f"<td>{r['placa']}</td>"
            f"<td>{r['visitas']}</td>"
            f"<td>{_fmt_horas(r['tiempo_total_seg'])}</td>"
            "</tr>"
        )

    paradas_largas_html = []
    for r in paradas_largas:
        paradas_largas_html.append(
            "<tr>"
            f"<td>{r['conductor']}</td>"
            f"<td>{r['placa']}</td>"
            f"<td>{r['fecha']}</td>"
            f"<td>{r['hora']}</td>"
            f"<td>{_fmt_horas(r['duracion_seg'])}</td>"
            f"<td>{r['coord']}</td>"
            f"<td>{r['zona']}</td>"
            "</tr>"
        )

    coincidencias_html = []
    for r in coincidencias[:80]:
        coincidencias_html.append(
            "<tr>"
            f"<td>{r['hora']}</td>"
            f"<td>{r['coord']}</td>"
            f"<td>{r['placas']}</td>"
            f"<td>{r['conductores']}</td>"
            f"<td>{r['n_placas']}</td>"
            "</tr>"
        )

    total_det_por_conductor = {}
    if not det_c.empty:
        total_det_por_conductor = det_c.groupby("Conductor")["duracion_seg"].sum().to_dict()

    nivel_rank = {"ROJO": 0, "AMARILLO": 1, "VERDE": 2}
    semaforo_cards = []
    for r in sorted(productividad_rows, key=lambda x: (nivel_rank.get(x["nivel"], 9), -total_det_por_conductor.get(x["conductor"], 0))):
        nivel = r["nivel"]
        cls = "rojo" if nivel == "ROJO" else ("amarillo" if nivel == "AMARILLO" else "verde")
        total_det = int(total_det_por_conductor.get(r["conductor"], 0))
        stat_txt = f"{_fmt_horas(total_det)} detenido · {r['avg_min']:.0f} min/parada"
        semaforo_cards.append(
            "<div class=\"cond-card " + cls + "\">"
            f"<div class=\"cond-name\"><span class=\"cond-dot\"></span>{r['conductor']}</div>"
            f"<div class=\"cond-placa\">{r['placa']}</div>"
            f"<div class=\"cond-stat\">{stat_txt}</div>"
            "</div>"
        )

    alertas_criticas = [a for a in alertas_grouped if a.get("severidad") == "CRITICA"]
    alertas_criticas_html = []
    for a in alertas_criticas:
        fecha_txt = a.get("fecha_rango", a.get("fecha", "-"))
        veces = int(a.get("n_veces", 1))
        veces_txt = f" · {veces} veces" if veces > 1 else ""
        duracion = _fmt_horas(int(a.get("duracion_total_seg", a.get("duracion_seg", 0))))
        dist = a.get("zona_ref_dist_m", "-")
        zona = a.get("zona_ref_nombre", "-")
        dist_txt = f"{dist}m de {zona}" if dist not in (None, "-") else "-"
        lat, lon = _coordenadas_alerta(a)
        coord_txt = f"{lat:.6f}, {lon:.6f}" if lat is not None and lon is not None else "-"
        detalle = f"{a.get('tipo','Alerta')} · {fecha_txt}{veces_txt} · {dist_txt} · Coord: {coord_txt}"
        alertas_criticas_html.append(
            "<div class=\"alert-item\">"
            "<div>"
            f"<div class=\"alert-who\">{a.get('conductor','-')} <span class=\"alert-placa\">· {a.get('placa','-')}</span></div>"
            f"<div class=\"alert-detail\">{detalle}</div>"
            "</div>"
            f"<div class=\"alert-dur\">{duracion}</div>"
            "</div>"
        )
    if not alertas_criticas_html:
        alertas_criticas_html.append(
            "<div class=\"alert-item\"><div><div class=\"alert-who\">Sin alertas criticas</div>"
            "<div class=\"alert-detail\">No se detectaron alertas criticas en el periodo.</div></div>"
            "<div class=\"alert-dur\">-</div></div>"
        )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard Ejecutivo GPS · Rentaya · {periodo}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {{
    --bg: #f1f5f9;
    --white: #ffffff;
    --navy: #0f172a;
    --navy2: #1e293b;
    --slate: #475569;
    --border: #e2e8f0;
    --red: #dc2626;
    --red-light: #fef2f2;
    --red-border: #fecaca;
    --amber: #d97706;
    --amber-light: #fffbeb;
    --amber-border: #fde68a;
    --green: #16a34a;
    --green-light: #f0fdf4;
    --green-border: #bbf7d0;
    --blue: #2563eb;
    --blue-light: #eff6ff;
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ scroll-behavior: smooth; }}
body {{
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--navy);
    font-size: 13.5px;
    line-height: 1.5;
}}

/* ── HEADER ── */
.header {{
    background: var(--navy);
    padding: 18px 28px;
    display: flex; align-items: center; justify-content: space-between;
    position: sticky; top: 0; z-index: 50;
}}
.header-brand {{ color: white; font-size: 15px; font-weight: 700; letter-spacing: -.2px; }}
.header-brand span {{ color: #38bdf8; }}
.header-meta {{ color: #94a3b8; font-size: 12px; }}

/* ── MAIN ── */
.main {{ max-width: 1300px; margin: 0 auto; padding: 24px 20px 48px; }}

/* ── KPI CARDS ── */
.kpi-row {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; margin-bottom: 20px; }}
.kpi {{
    background: var(--white); border-radius: 10px;
    border: 1px solid var(--border); padding: 18px 20px;
    display: flex; flex-direction: column; gap: 6px;
}}
.kpi-label {{ font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: .8px; color: var(--slate); }}
.kpi-value {{ font-size: 32px; font-weight: 800; line-height: 1; }}
.kpi-value.red {{ color: var(--red); }}
.kpi-value.amber {{ color: var(--amber); }}
.kpi-value.green {{ color: var(--green); }}
.kpi-value.blue {{ color: var(--blue); }}
.kpi-sub {{ font-size: 11.5px; color: var(--slate); }}

/* ── GRID LAYOUT ── */
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
.grid-1 {{ margin-bottom: 16px; }}

/* ── PANELS ── */
.panel {{
    background: var(--white); border: 1px solid var(--border);
    border-radius: 10px; overflow: hidden;
}}
.panel-head {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 13px 18px; border-bottom: 1px solid var(--border);
    background: #f8fafc;
}}
.panel-title {{ font-size: 13px; font-weight: 700; color: var(--navy); }}
.panel-badge {{
    font-size: 10.5px; font-weight: 600; padding: 2px 8px;
    border-radius: 999px; border: 1px solid;
}}
.panel-badge.red {{ background: var(--red-light); color: var(--red); border-color: var(--red-border); }}
.panel-badge.amber {{ background: var(--amber-light); color: var(--amber); border-color: var(--amber-border); }}

/* ── SEMAFORO GRID ── */
.semaforo-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px,1fr)); gap: 10px; padding: 14px; }}
.cond-card {{
    border-radius: 8px; border: 1px solid; padding: 12px 14px;
    display: flex; flex-direction: column; gap: 5px;
}}
.cond-card.verde {{ background: var(--green-light); border-color: var(--green-border); }}
.cond-card.amarillo {{ background: var(--amber-light); border-color: var(--amber-border); }}
.cond-card.rojo {{ background: var(--red-light); border-color: var(--red-border); }}
.cond-name {{ font-weight: 700; font-size: 12.5px; }}
.cond-card.verde .cond-name {{ color: var(--green); }}
.cond-card.amarillo .cond-name {{ color: var(--amber); }}
.cond-card.rojo .cond-name {{ color: var(--red); }}
.cond-placa {{ font-size: 10.5px; color: var(--slate); font-weight: 500; }}
.cond-stat {{ font-size: 11px; color: var(--slate); margin-top: 4px; }}
.cond-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }}
.verde .cond-dot {{ background: var(--green); }}
.amarillo .cond-dot {{ background: var(--amber); }}
.rojo .cond-dot {{ background: var(--red); }}

/* ── ALERTAS CRITICAS ── */
.alert-list {{ padding: 10px 14px; display: flex; flex-direction: column; gap: 8px; }}
.alert-item {{
    border-radius: 8px; padding: 11px 14px;
    border-left: 4px solid var(--red); background: var(--red-light);
    display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: start;
}}
.alert-who {{ font-weight: 700; font-size: 12.5px; color: var(--navy); }}
.alert-placa {{ font-size: 11px; color: var(--slate); }}
.alert-detail {{ font-size: 11.5px; color: #374151; margin-top: 3px; }}
.alert-dur {{
    font-size: 12px; font-weight: 700; color: var(--red);
    background: white; border: 1px solid var(--red-border);
    border-radius: 6px; padding: 3px 8px; white-space: nowrap;
}}

/* ── RESUMEN TABLE ── */
.tbl-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
thead th {{
    background: #f8fafc; color: var(--slate); padding: 9px 12px;
    text-align: left; font-size: 10.5px; font-weight: 600;
    text-transform: uppercase; letter-spacing: .6px;
    border-bottom: 1px solid var(--border); white-space: nowrap;
}}
tbody td {{ padding: 8px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }}
tbody tr:last-child td {{ border-bottom: none; }}
tbody tr:hover td {{ background: #f8fafc; }}
.badge-crit {{
    background: var(--red-light); color: var(--red); border: 1px solid var(--red-border);
    border-radius: 999px; padding: 2px 9px; font-size: 10.5px; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}}
.badge-alto {{
    background: var(--amber-light); color: var(--amber); border: 1px solid var(--amber-border);
    border-radius: 999px; padding: 2px 9px; font-size: 10.5px; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}}
.badge-normal {{
    background: var(--green-light); color: var(--green); border: 1px solid var(--green-border);
    border-radius: 999px; padding: 2px 9px; font-size: 10.5px; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}}
.badge-verde {{
    background: var(--green-light); color: var(--green); border: 1px solid var(--green-border);
    border-radius: 999px; padding: 2px 9px; font-size: 10.5px; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}}
.badge-amarillo {{
    background: var(--amber-light); color: var(--amber); border: 1px solid var(--amber-border);
    border-radius: 999px; padding: 2px 9px; font-size: 10.5px; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}}
.badge-rojo {{
    background: var(--red-light); color: var(--red); border: 1px solid var(--red-border);
    border-radius: 999px; padding: 2px 9px; font-size: 10.5px; font-weight: 700;
    display: inline-flex; align-items: center; gap: 4px;
}}
.muted {{ color: var(--slate); font-size: 11px; }}
.alert-type {{ font-weight: 600; font-size: 12px; }}
.sev-tag {{
    display: inline-block; font-size: 9px; font-weight: 700;
    text-transform: uppercase; padding: 1px 5px; border-radius: 4px;
    background: #f8fafc; color: var(--slate); margin-left: 6px;
    letter-spacing: .5px;
}}
.row-crit td {{ border-left: 3px solid var(--red); }}
.row-alta td {{ border-left: 3px solid var(--amber); }}
.row-media td {{ border-left: 3px solid var(--blue); }}
.row-crit td:first-child {{ padding-left: 11px; }}
.row-alta td:first-child {{ padding-left: 11px; }}

/* ── HEATMAP ── */
.heat-legend {{ display: flex; gap: 8px; flex-wrap: wrap; padding: 12px 14px 0; }}
.swatch {{ padding: 3px 9px; border-radius: 5px; font-size: 10.5px; font-weight: 600; }}
.s0 {{ background: #f1f5f9; color: var(--slate); }}
.s1 {{ background: #bbf7d0; color: #166534; }}
.s2 {{ background: #fde68a; color: #92400e; }}
.s3 {{ background: #f97316; color: white; }}
.s4 {{ background: #dc2626; color: white; }}
.heat-day {{ font-size: 11px; color: var(--slate); white-space: nowrap; font-weight: 500; }}
.heat-cell {{ text-align: center; font-size: 11.5px; font-weight: 600; min-width: 40px; }}
.heat-total {{ font-weight: 800; font-size: 12px; }}
.heat-total-row td {{ border-top: 2px solid var(--border) !important; }}
.heat-note {{ font-size: 10.5px; color: var(--slate); padding: 8px 14px 12px; }}

/* ── DETALLE COLAPSABLE ── */
details summary {{
    cursor: pointer; padding: 12px 18px;
    font-size: 12.5px; font-weight: 600; color: var(--blue);
    list-style: none; display: flex; align-items: center; gap: 8px;
    border-top: 1px solid var(--border); background: #f8fafc;
}}
details summary::before {{ content: '▶'; font-size: 9px; transition: transform .2s; }}
details[open] summary::before {{ transform: rotate(90deg); }}
details summary::-webkit-details-marker {{ display: none; }}

/* ── INSIGHT BOX ── */
.insight {{
    background: #eff6ff; border: 1px solid #bfdbfe;
    border-radius: 8px; padding: 10px 14px;
    font-size: 12px; color: #1e40af; margin: 12px 14px;
}}

/* RESPONSIVE */
@media (max-width: 900px) {{
    .kpi-row {{ grid-template-columns: repeat(2,1fr); }}
    .grid-2 {{ grid-template-columns: 1fr; }}
}}
@media (max-width: 500px) {{
    .kpi-row {{ grid-template-columns: repeat(2,1fr); }}
    .kpi-value {{ font-size: 24px; }}
}}
</style>
</head>
<body>

<header class="header">
    <div class="header-brand">🚗 Rentaya <span>· GPS Operativo</span></div>
    <div class="header-meta">{periodo} · Generado {fecha_gen}</div>
</header>

<main class="main">

<div class="panel grid-1">
    <div class="panel-head">
        <span class="panel-title">📋 Tablas solicitadas</span>
    </div>

    <details open>
        <summary>Ubicacion repetida semanal por trabajador</summary>
        <div class="tbl-wrap">
            <table>
                <thead><tr>
                    <th>Conductor</th><th>Placa</th>
                    <th>Coordenada</th><th>Visitas</th>
                    <th>Tiempo total</th>
                </tr></thead>
                <tbody>{''.join(repetidas_html) if repetidas_html else '<tr><td colspan="5">Sin ubicaciones repetidas (>=2 visitas).</td></tr>'}</tbody>
            </table>
        </div>
    </details>

    <details>
        <summary>Tiempo y visitas en oficina</summary>
        <div class="tbl-wrap">
            <table>
                <thead><tr>
                    <th>Conductor</th><th>Placa</th>
                    <th>Visitas</th><th>Tiempo total</th>
                </tr></thead>
                <tbody>{''.join(oficinas_html) if oficinas_html else '<tr><td colspan="4">Sin paradas en oficinas registradas.</td></tr>'}</tbody>
            </table>
        </div>
    </details>

    <details>
        <summary>Coincidencias de ruta (mismo lugar y hora)</summary>
        <div class="tbl-wrap">
            <table>
                <thead><tr>
                    <th>Hora</th><th>Coordenada</th>
                    <th>Placas</th><th>Conductores</th><th># Placas</th>
                </tr></thead>
                <tbody>{''.join(coincidencias_html) if coincidencias_html else '<tr><td colspan="5">Sin coincidencias detectadas.</td></tr>'}</tbody>
            </table>
        </div>
    </details>

    <details>
        <summary>Lugares frecuentes desconocidos por conductor</summary>
        <div>
            {''.join(clusters_html) if clusters_html else '<div class="panel"><div style="padding:12px 14px;">No se encontraron lugares desconocidos con al menos 2 visitas.</div></div>'}
        </div>
    </details>

    <details>
        <summary>Paradas mayores a 30 minutos (hora del dia)</summary>
        <div class="tbl-wrap">
            <table>
                <thead><tr>
                    <th>Conductor</th><th>Placa</th>
                    <th>Fecha</th><th>Hora</th>
                    <th>Duracion</th><th>Coordenada</th><th>Zona</th>
                </tr></thead>
                <tbody>{''.join(paradas_largas_html) if paradas_largas_html else '<tr><td colspan="7">Sin paradas mayores a 30 minutos.</td></tr>'}</tbody>
            </table>
        </div>
    </details>

</div>

</main>

</body>
</html>
"""

    output_path.write_text(html, encoding="utf-8")
    return output_path
