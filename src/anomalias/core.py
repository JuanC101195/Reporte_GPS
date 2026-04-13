"""Pure analytical logic for GPS anomalias.

All functions in this module are free of HTML/Folium rendering and
can be reused from a CLI, a notebook, or a web microservice.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..geo import haversine_metros
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

        imagen_url = "-"
        if "imagen_url" in sub.columns:
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
    """Agrupa alertas por conductor/placa/tipo cuando están muy cerca (<50m)."""
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
    rows.sort(key=lambda r: (r["conductor"], -r["duracion_seg"]))
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
