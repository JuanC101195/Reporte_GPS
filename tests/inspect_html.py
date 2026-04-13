"""One-shot inspector for the generated HTML — counts previews and sections."""

import os
import re
import sys
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("reportes/reporte_anomalias.html")
content = path.read_text(encoding="utf-8")

key = os.environ.get("GOOGLE_MAPS_API_KEY", "")

size_kb = len(content) / 1024
print(f"Tamano: {size_kb:.1f} KB")

titles = re.findall(r"<summary>([^<]+)</summary>", content)
print(f"\nSecciones colapsables: {len(titles)}")
for t in titles:
    safe = "".join(ch if ord(ch) < 128 else "?" for ch in t.strip())
    print(f"  - {safe}")

sv = content.count("maps/api/streetview")
sm = content.count("maps/api/staticmap")
gm = content.count("google.com/maps?q=")
print(f"\nMiniaturas Street View: {sv}")
print(f"Miniaturas Static Map: {sm}")
print(f"Deep links Google Maps: {gm}")

cond_blocks = re.findall(r"id='cond-([^']+)'", content)
print(f"\nBloques por conductor en clusters: {len(cond_blocks)}")
for c in cond_blocks[:15]:
    safe = "".join(ch if ord(ch) < 128 else "?" for ch in c)
    print(f"  - {safe}")
if len(cond_blocks) > 15:
    print(f"  ... y {len(cond_blocks) - 15} mas")

tr_count = content.count("<tr>")
print(f"\n<tr> totales en el HTML: {tr_count}")

if key:
    kc = content.count(key)
    expected = sv + sm
    print(f"\nAPI key aparece {kc} veces (esperado: {expected})")
    if kc == expected:
        print("OK: no leak")
    else:
        print("WARN: conteo distinto, revisar")
else:
    print("\n(sin API key en el entorno actual)")
