"""HTML/Folium renderer for the anomalias report.

Pure analytical logic lives in ``src.anomalias.core``. This module is
a thin adapter that wraps that logic with HTML/map rendering.
Re-exports are kept so existing callers (``cli.py``, tests) do not
need to change their imports.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .anomalias.core import (
    HORA_NOCTURNA_FIN,
    HORA_NOCTURNA_INICIO,
    HORARIO_FIN,
    HORARIO_INICIO,
    RADIO_CLUSTER_METROS,
    RADIO_ZONA_CONOCIDA_M,
    UMBRAL_PARADA_LARGA_SEG,
    VISITAS_LUGAR_FRECUENTE,
    ZONAS_CONOCIDAS,
    _alert_tipo_corto,
    _badge_riesgo,
    _clasificar_paradas,
    _cluster_desconocidos,
    _cluster_rows,
    _cluster_unknown_rows,
    _coincidencias_ruta,
    _coordenadas_alerta,
    _detectar_alertas,
    _distancia_m,
    _fmt_horas,
    _group_alertas,
    _heat_color,
    _heatmap_data,
    _metricas_conductor,
    _paradas_largas,
    _productividad_semaforo,
    _resumen_oficinas,
    _ubicacion_repetida_semanal,
    zona_mas_cercana,
    zona_referencia_mas_cercana,
)
from .geo import haversine_metros
from .transform import parse_coordinates, parse_duracion_segundos
from .validation import parse_dates

__all__ = [
    "HORARIO_INICIO",
    "HORARIO_FIN",
    "UMBRAL_PARADA_LARGA_SEG",
    "HORA_NOCTURNA_INICIO",
    "HORA_NOCTURNA_FIN",
    "RADIO_CLUSTER_METROS",
    "RADIO_ZONA_CONOCIDA_M",
    "VISITAS_LUGAR_FRECUENTE",
    "ZONAS_CONOCIDAS",
    "_alert_tipo_corto",
    "_badge_riesgo",
    "_clasificar_paradas",
    "_cluster_desconocidos",
    "_cluster_rows",
    "_cluster_unknown_rows",
    "_coincidencias_ruta",
    "_coordenadas_alerta",
    "_detectar_alertas",
    "_distancia_m",
    "_fmt_horas",
    "_group_alertas",
    "_heat_color",
    "_heatmap_data",
    "_metricas_conductor",
    "_paradas_largas",
    "_productividad_semaforo",
    "_resumen_oficinas",
    "_ubicacion_repetida_semanal",
    "generar_html_anomalias",
    "haversine_metros",
    "parse_coordinates",
    "parse_duracion_segundos",
    "parse_dates",
    "zona_mas_cercana",
    "zona_referencia_mas_cercana",
]


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
