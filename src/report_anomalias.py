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
    _clasificar_paradas,
    _cluster_desconocidos,
    _cluster_rows,
    _cluster_unknown_rows,
    _coincidencias_ruta,
    _distancia_m,
    _fmt_horas,
    _paradas_largas,
    _resumen_oficinas,
    _ubicacion_repetida_semanal,
    ranking_conductores,
    zona_mas_cercana,
    zona_referencia_mas_cercana,
)
from .geo import haversine_metros
from .maps_preview import preview_cell_html
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
    "_clasificar_paradas",
    "_cluster_desconocidos",
    "_cluster_rows",
    "_cluster_unknown_rows",
    "_coincidencias_ruta",
    "_distancia_m",
    "_fmt_horas",
    "_paradas_largas",
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

    clusters_por_conductor = {}
    for conductor in sorted(anom["Conductor"].dropna().unique()):
        clusters = _cluster_desconocidos(anom, conductor)
        clusters_por_conductor[conductor] = [c for c in clusters if c["visitas"] >= 2][:5]

    ubicacion_rep = _ubicacion_repetida_semanal(det_c)
    oficinas_rows = _resumen_oficinas(det_c)
    paradas_largas = _paradas_largas(det_c, UMBRAL_PARADA_LARGA_SEG, only_anomalas=True)
    coincidencias = _coincidencias_ruta(det_c)
    ranking = ranking_conductores(det_c, anom, clusters_por_conductor)

    # Executive-level KPIs aggregated from the ranking.
    total_conductores = len(ranking)
    total_en_rojo = sum(1 for r in ranking if r["nivel"] == "ROJO")
    total_alertas_crit = sum(r["paradas_anomalas"] for r in ranking)
    total_horas_desc = sum(r["horas_desconocidas"] for r in ranking)

    periodo = periodo_label or (
        f"{det_c['Comienzo'].min()} a {det_c['Comienzo'].max()}" if not det_c.empty else "-"
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
            preview = preview_cell_html(c.get("lat"), c.get("lon"))
            # Severity by visits + accumulated time in unknown place.
            visitas = int(c.get("visitas", 0))
            tiempo_seg = int(c.get("tiempo_total_seg", 0))
            if visitas >= 5 or tiempo_seg > 4 * 3600:
                row_cls = "row-crit"
            elif visitas >= 3 or tiempo_seg > 2 * 3600:
                row_cls = "row-alta"
            else:
                row_cls = "row-media"
            rows.append(
                f"<tr class='{row_cls}'>"
                f"<td>{c['coord']}</td>"
                f"<td>{visitas}</td>"
                f"<td>{c['visitas_fuera_horario']}</td>"
                f"<td>{_fmt_horas(tiempo_seg)}</td>"
                f"<td>{c['zona_ref_dist_m']}m de {c['zona_ref_nombre']}</td>"
                f"<td>{c['primera_visita']}</td>"
                f"<td>{c['ultima_visita']}</td>"
                f"<td>{preview}</td>"
                "</tr>"
            )
        clusters_html.append(
            "<div class='cond-block' id='cond-" + conductor.replace(" ", "_") + "'>"
            f"<div class='cond-name'>👤 {conductor}</div>"
            "<div class='tbl-wrap'>"
            "<table><thead><tr><th>Coordenada</th><th>Visitas</th><th>Fuera horario</th><th>Tiempo acum.</th><th>Zona ref.</th><th>Primera</th><th>Ultima</th><th>Vista previa</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
            "</div>"
            "</div>"
        )

    fecha_gen = datetime.now().strftime("%d-%m-%Y %H:%M")

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
        duracion_seg = int(r["duracion_seg"])
        n_veces = int(r.get("n_veces", 1))
        if r.get("es_nocturna") or duracion_seg > 4 * 3600 or n_veces >= 5:
            row_cls = "row-crit"
        elif r.get("fuera_horario") or duracion_seg > 2 * 3600 or n_veces >= 3:
            row_cls = "row-alta"
        else:
            row_cls = "row-media"
        rango_horario = f"{r['hora']} → {r.get('hora_fin', '-')}"
        veces_html = (
            f"<span class='badge-crit'>{n_veces}x</span>"
            if n_veces >= 5
            else (f"<span class='badge-alto'>{n_veces}x</span>" if n_veces >= 3 else f"{n_veces}x")
        )
        preview = preview_cell_html(r.get("lat"), r.get("lon"))
        paradas_largas_html.append(
            f"<tr class='{row_cls}'>"
            f"<td>{r['conductor']}</td>"
            f"<td>{r['placa']}</td>"
            f"<td>{r['fecha']}</td>"
            f"<td>{rango_horario}</td>"
            f"<td>{_fmt_horas(duracion_seg)}</td>"
            f"<td>{veces_html}</td>"
            f"<td>{preview}</td>"
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

    # KPI bar: 4 numeros que el dueno lee en 5 segundos.
    kpi_crit_color = "red" if total_alertas_crit > 0 else "green"
    kpi_horas_color = "red" if total_horas_desc > 20 else ("amber" if total_horas_desc > 5 else "green")
    kpi_rojos_color = "red" if total_en_rojo > 0 else "green"
    kpi_bar_html = (
        "<div class='kpi-row'>"
        "<div class='kpi'>"
        "<div class='kpi-label'>Alertas criticas</div>"
        f"<div class='kpi-value {kpi_crit_color}'>{total_alertas_crit}</div>"
        "<div class='kpi-sub'>paradas largas en zona desconocida</div>"
        "</div>"
        "<div class='kpi'>"
        "<div class='kpi-label'>Horas en zonas desconocidas</div>"
        f"<div class='kpi-value {kpi_horas_color}'>{total_horas_desc:.0f}h</div>"
        "<div class='kpi-sub'>tiempo acumulado de la flota</div>"
        "</div>"
        "<div class='kpi'>"
        "<div class='kpi-label'>Conductores monitoreados</div>"
        f"<div class='kpi-value blue'>{total_conductores}</div>"
        "<div class='kpi-sub'>flota activa en el periodo</div>"
        "</div>"
        "<div class='kpi'>"
        "<div class='kpi-label'>En alerta (rojo)</div>"
        f"<div class='kpi-value {kpi_rojos_color}'>{total_en_rojo}</div>"
        "<div class='kpi-sub'>revisar con prioridad</div>"
        "</div>"
        "</div>"
    )

    # Top ofensores: tarjetas de los 5 peores conductores.
    top_n = [r for r in ranking if r["nivel"] != "VERDE"][:5]
    if not top_n:
        top_ofensores_html = (
            "<div class='panel'>"
            "<div class='panel-head'><span class='panel-title'>🔥 Top conductores para revisar</span></div>"
            "<div style='padding:18px 20px;color:#16a34a;font-weight:600;'>✓ Sin conductores en alerta esta semana. Flota operando dentro de rangos normales.</div>"
            "</div>"
        )
    else:
        ofensor_cards = []
        for r in top_n:
            nivel = r["nivel"]
            cls = "ofensor-rojo" if nivel == "ROJO" else "ofensor-amarillo"
            peor = r.get("peor_cluster") or {}
            thumb = preview_cell_html(peor.get("lat"), peor.get("lon")) if peor else "-"
            anchor = r["conductor"].replace(" ", "_")
            detalle = (
                f"{r['horas_desconocidas']:.1f}h desconocidas · "
                f"{r['paradas_anomalas']} paradas >30min · "
                f"{r['lugares_frecuentes']} lugares frecuentes · "
                f"{r['horas_fuera_horario']:.1f}h fuera horario"
            )
            ofensor_cards.append(
                f"<a class='ofensor {cls}' href='#cond-{anchor}'>"
                f"<div class='ofensor-thumb'>{thumb}</div>"
                "<div class='ofensor-info'>"
                f"<div class='ofensor-name'>{r['conductor']} <span class='ofensor-placa'>· {r['placa']}</span></div>"
                f"<div class='ofensor-score'>Score: <strong>{r['score']}</strong> · <span class='ofensor-nivel'>{nivel}</span></div>"
                f"<div class='ofensor-detail'>{detalle}</div>"
                "</div>"
                "</a>"
            )
        top_ofensores_html = (
            "<div class='panel'>"
            "<div class='panel-head'><span class='panel-title'>🔥 Top conductores para revisar</span>"
            f"<span class='panel-badge red'>{len(top_n)} en alerta</span>"
            "</div>"
            "<div class='ofensor-list'>"
            + "".join(ofensor_cards)
            + "</div>"
            "</div>"
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

/* ── TOP OFENSORES ── */
.ofensor-list {{ display: flex; flex-direction: column; gap: 10px; padding: 14px; }}
.ofensor {{
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 14px;
    padding: 12px 14px;
    border-radius: 8px;
    border: 1px solid;
    text-decoration: none;
    color: inherit;
    transition: transform .15s, box-shadow .15s;
}}
.ofensor:hover {{ transform: translateY(-1px); box-shadow: 0 4px 10px rgba(15,23,42,.08); }}
.ofensor-rojo {{ background: var(--red-light); border-color: var(--red-border); border-left: 4px solid var(--red); }}
.ofensor-amarillo {{ background: var(--amber-light); border-color: var(--amber-border); border-left: 4px solid var(--amber); }}
.ofensor-thumb {{ display: flex; align-items: center; }}
.ofensor-info {{ display: flex; flex-direction: column; gap: 3px; min-width: 0; }}
.ofensor-name {{ font-weight: 700; font-size: 13.5px; color: var(--navy); }}
.ofensor-placa {{ font-size: 11.5px; color: var(--slate); font-weight: 500; }}
.ofensor-score {{ font-size: 12px; color: var(--slate); }}
.ofensor-rojo .ofensor-nivel {{ color: var(--red); font-weight: 700; }}
.ofensor-amarillo .ofensor-nivel {{ color: var(--amber); font-weight: 700; }}
.ofensor-detail {{ font-size: 11px; color: #475569; }}
@media (max-width: 640px) {{
    .ofensor {{ grid-template-columns: 1fr; }}
    .ofensor-thumb {{ justify-content: flex-start; }}
}}

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

{kpi_bar_html}

{top_ofensores_html}

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
        <summary>Paradas mayores a 30 minutos en zonas desconocidas</summary>
        <div class="tbl-wrap">
            <table>
                <thead><tr>
                    <th>Conductor</th><th>Placa</th>
                    <th>Fecha</th><th>Inicio → Fin</th>
                    <th>Duracion</th><th>Veces</th>
                    <th>Vista previa</th><th>Zona</th>
                </tr></thead>
                <tbody>{''.join(paradas_largas_html) if paradas_largas_html else '<tr><td colspan="8">Sin paradas mayores a 30 minutos en zona desconocida.</td></tr>'}</tbody>
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
