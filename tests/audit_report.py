"""Audit the generated report — counts items per section + top offenders."""

import re
from pathlib import Path

path = Path("reportes/reporte_anomalias.html")
content = path.read_text(encoding="utf-8")

print("=" * 70)
print("AUDIT DEL REPORTE ACTUAL")
print("=" * 70)

# KPI row
kpi_values = re.findall(r"<div class='kpi-value [^']+'>([^<]+)</div>", content)
kpi_labels = re.findall(r"<div class='kpi-label'>([^<]+)</div>", content)
print("\n[KPI BAR]")
for label, value in zip(kpi_labels, kpi_values, strict=False):
    safe = "".join(ch if ord(ch) < 128 else "?" for ch in label.strip())
    print(f"  {safe}: {value}")

# Top ofensores: extract each card
card_pattern = re.compile(
    r"<a class='ofensor (ofensor-\w+)'[^>]*>.*?"
    r"<div class='ofensor-name'>([^<]+)<span class='ofensor-placa'>([^<]+)</span></div>.*?"
    r"Score: <strong>([^<]+)</strong>.*?"
    r"<span class='ofensor-nivel'>(\w+)</span>.*?"
    r"<div class='ofensor-detail'>([^<]+)</div>",
    re.DOTALL,
)
cards = card_pattern.findall(content)
print(f"\n[TOP OFENSORES] {len(cards)} cards")
for _cls, name, _placa, score, nivel, detail in cards:
    safe_name = "".join(ch if ord(ch) < 128 else "?" for ch in name.strip())
    safe_detail = "".join(ch if ord(ch) < 128 else "?" for ch in detail.strip())
    print(f"  [{nivel:8}] {safe_name:25} score {score:>6}  {safe_detail}")

# Sections
sections = re.findall(
    r"<details[^>]*>.*?<summary>([^<]+)</summary>(.*?)</details>",
    content,
    re.DOTALL,
)
print("\n[TABLAS SOLICITADAS]")
for title, body in sections:
    safe = "".join(ch if ord(ch) < 128 else "?" for ch in title.strip())
    tbody = re.search(r"<tbody>(.*?)</tbody>", body, re.DOTALL)
    if tbody:
        rows = tbody.group(1).count("<tr")
    else:
        rows = body.count("<tr")
    print(f"  {safe}: {rows} filas")

# Row coloring (subtract CSS rules ~ 5 per class)
crit = content.count("class='row-crit'")
alta = content.count("class='row-alta'")
media = content.count("class='row-media'")
print("\n[COLOREADO DE FILAS]")
print(f"  row-crit:  {crit}")
print(f"  row-alta:  {alta}")
print(f"  row-media: {media}")

cond_blocks = re.findall(r"id='cond-([^']+)'", content)
print(f"\n[BLOQUES CLUSTERS] {len(cond_blocks)} conductores")

# Size
print(f"\n[TAMANO]: {len(content) / 1024:.1f} KB")
