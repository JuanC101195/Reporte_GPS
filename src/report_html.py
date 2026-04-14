"""Generate HTML reports by placa."""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_TMPL = """<!DOCTYPE html>
<html lang=\"es\">
<head>
<meta charset=\"UTF-8\">
<title>Reporte GPS - {placa}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; color: #333; }}
  .header {{ background: #1a3c5e; color: white; padding: 24px 32px; }}
  .header h1 {{ font-size: 22px; font-weight: 600; }}
  .header p  {{ font-size: 13px; opacity: .9; margin-top: 4px; }}
  .container {{ padding: 24px 32px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 28px; }}
  .kpi {{ background: white; border-radius: 8px; padding: 16px 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  .kpi .label {{ font-size: 11px; text-transform: uppercase; color: #888; letter-spacing: .5px; }}
  .kpi .value {{ font-size: 24px; font-weight: 700; color: #1a3c5e; margin-top: 4px; }}
  .kpi .unit  {{ font-size: 12px; color: #999; }}
  .section-title {{ font-size: 15px; font-weight: 600; color: #1a3c5e; margin-bottom: 12px; border-left: 4px solid #1a3c5e; padding-left: 10px; }}
  .table-wrap {{ overflow-x: auto; background: white; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 28px; max-height: 70vh; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  thead th {{ background: #1a3c5e; color: white; padding: 10px 12px; text-align: left; white-space: nowrap; position: sticky; top: 0; }}
  tbody tr:nth-child(even) {{ background: #f9fafb; }}
  tbody tr:hover {{ background: #eef3f8; }}
  tbody td {{ padding: 8px 12px; border-bottom: 1px solid #eee; white-space: nowrap; }}
  .badge {{ display: inline-block; border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}
  .badge-det {{ background: #fef3cd; color: #856404; }}
  .badge-mov {{ background: #d1e7dd; color: #0a5c36; }}
  .footer {{ text-align: center; font-size: 11px; color: #aaa; padding: 20px; border-top: 1px solid #eee; margin-top: 12px; }}
</style>
</head>
<body>
<div class=\"header\">
  <h1>Reporte GPS - Vehiculo {placa}</h1>
  <p>Conductor: {conductor} | Periodo: {fecha_inicio} -> {fecha_fin} | Generado: {fecha_gen}</p>
</div>
<div class=\"container\">
  <div class=\"kpi-grid\">
    <div class=\"kpi\"><div class=\"label\">Total eventos</div><div class=\"value\">{total_eventos}</div></div>
    <div class=\"kpi\"><div class=\"label\">Tiempo detenido</div><div class=\"value\">{tiempo_det_h}<span class=\"unit\">h</span> {tiempo_det_m}<span class=\"unit\">min</span></div></div>
    <div class=\"kpi\"><div class=\"label\">Distancia total</div><div class=\"value\">{distancia_total}<span class=\"unit\"> km</span></div></div>
    <div class=\"kpi\"><div class=\"label\">Vel maxima</div><div class=\"value\">{vel_max}<span class=\"unit\"> kph</span></div></div>
    <div class=\"kpi\"><div class=\"label\">Vel media prom</div><div class=\"value\">{vel_media}<span class=\"unit\"> kph</span></div></div>
    <div class=\"kpi\"><div class=\"label\">Dias activo</div><div class=\"value\">{dias_activos}</div></div>
    <div class=\"kpi\"><div class=\"label\">Paradas en ubic. conocidas</div><div class=\"value\">{paradas_conocidas}</div></div>
  </div>

  <div class=\"section-title\">Detalle de todos los eventos ({total_eventos})</div>
  <div class=\"table-wrap\">
    <table>
      <thead>
        <tr>
          <th>#</th><th>Estado</th><th>Inicio</th><th>Fin</th><th>Duracion</th><th>Posicion / Distancia</th><th>Ubicacion conocida</th><th>Vel Max</th><th>Vel Media</th>
        </tr>
      </thead>
      <tbody>
{filas}
      </tbody>
    </table>
  </div>
</div>
<div class=\"footer\">Sistema GPS - {fecha_gen}</div>
</body>
</html>
"""

_ROW_TMPL = (
    "<tr>"
    "<td>{n}</td>"
    "<td><span class='badge {badge_cls}'>{estado}</span></td>"
    "<td>{comienzo}</td>"
    "<td>{fin}</td>"
    "<td>{duracion}</td>"
    "<td>{posicion}</td>"
    "<td>{ubicacion}</td>"
    "<td>{vel_max}</td>"
    "<td>{vel_media}</td>"
    "</tr>"
)


def _fmt_segundos(seg):
    h = int(seg) // 3600
    m = (int(seg) % 3600) // 60
    return h, m


def generate_single_html(df_placa, placa, output_dir):
    df = df_placa.copy()

    comienzo_dates = pd.to_datetime(df["Comienzo"], format="%d-%m-%Y %H:%M:%S", errors="coerce")
    fin_dates = pd.to_datetime(df["Fin"], format="%d-%m-%Y %H:%M:%S", errors="coerce")

    fecha_inicio = comienzo_dates.min().strftime("%d/%m/%Y %H:%M") if comienzo_dates.notna().any() else "-"
    fecha_fin = fin_dates.max().strftime("%d/%m/%Y %H:%M") if fin_dates.notna().any() else "-"

    conductor = df["Conductor"].dropna().mode()
    conductor = conductor.iloc[0] if len(conductor) else placa

    det = df[df["Estado"] == "Detenido"]
    mov = df[df["Estado"] == "Movimiento"]

    seg_detenido = int(det["duracion_seg"].sum()) if "duracion_seg" in df.columns else 0
    h_det, m_det = _fmt_segundos(seg_detenido)

    distancia_total = round(mov["distancia_km"].dropna().sum(), 2) if "distancia_km" in mov.columns else 0
    vel_max_global = mov["vel_max_kph"].max() if "vel_max_kph" in mov.columns and mov["vel_max_kph"].notna().any() else 0
    vel_media_prom = round(mov["vel_media_kph"].mean(), 1) if "vel_media_kph" in mov.columns and mov["vel_media_kph"].notna().any() else 0

    dias_activos = comienzo_dates.dt.date.nunique() if comienzo_dates.notna().any() else 0
    paradas_conocidas = int(det["ubicacion_conocida"].notna().sum()) if "ubicacion_conocida" in det.columns else 0

    filas_html = []
    for i, (_, row) in enumerate(df.iterrows(), 1):
        estado = str(row.get("Estado", ""))
        badge = "badge-det" if estado == "Detenido" else "badge-mov"

        filas_html.append(
            _ROW_TMPL.format(
                n=i,
                badge_cls=badge,
                estado=estado,
                comienzo=str(row.get("Comienzo", "")),
                fin=str(row.get("Fin", "")),
                duracion=str(row.get("Duracion", "")),
                posicion=str(row.get("Posicion", "")),
                ubicacion=(str(row.get("ubicacion_conocida", "")) or "-"),
                vel_max=(str(row.get("Vel_Max", "")) or "-"),
                vel_media=(str(row.get("Vel_Media", "")) or "-"),
            )
        )

    html = _TMPL.format(
        placa=placa,
        conductor=conductor,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        fecha_gen=datetime.now().strftime("%d/%m/%Y %H:%M"),
        total_eventos=len(df),
        tiempo_det_h=h_det,
        tiempo_det_m=m_det,
        distancia_total=distancia_total,
        vel_max=int(vel_max_global) if vel_max_global else 0,
        vel_media=vel_media_prom,
        dias_activos=dias_activos,
        paradas_conocidas=paradas_conocidas,
        filas="\n".join(filas_html),
    )

    out_file = Path(output_dir) / f"reporte_{placa.replace(' ', '_')}.html"
    out_file.write_text(html, encoding="utf-8")
    logger.info("  HTML: %s", out_file.name)
    return out_file


def generate_html_report(df, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if "Placa" not in df.columns:
        raise ValueError("Column 'Placa' not found in dataframe.")

    placas = df["Placa"].dropna().unique()
    generated = []
    for placa in sorted(placas):
        df_p = df[df["Placa"] == placa].copy()
        generated.append(generate_single_html(df_p, placa, output_dir))

    logger.info("Total HTML generated: %s", len(generated))
    return len(generated)
