"""One-shot smoke test for maps preview integration.

Not part of the pytest suite. Meant to be invoked manually with a real
``GOOGLE_MAPS_API_KEY`` in the environment to validate the end-to-end
rendering path.
"""

import io
import re
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.maps_preview import get_api_key  # noqa: E402
from src.report_anomalias import ZONAS_CONOCIDAS, generar_html_anomalias  # noqa: E402
from src.transform import add_derived_columns  # noqa: E402
from tests.bench_transform import synth  # noqa: E402


def main() -> int:
    key = get_api_key()
    print(f"API key detectada: {'SI (longitud ' + str(len(key)) + ')' if key else 'NO'}")

    df = synth(500)
    df = add_derived_columns(df)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as tmp:
        out = Path(tmp.name)

    generar_html_anomalias(df, ZONAS_CONOCIDAS, out, periodo_label="Smoke maps preview")
    content = out.read_text(encoding="utf-8")
    print(f"HTML generado: {len(content)} bytes")

    sv_count = content.count("maps/api/streetview")
    sm_count = content.count("maps/api/staticmap")
    gmaps_count = content.count("google.com/maps?q=")
    print(f"Street View URLs: {sv_count}")
    print(f"Static Map URLs: {sm_count}")
    print(f"google.com/maps deep links: {gmaps_count}")

    if key:
        key_count = content.count(key)
        expected = sv_count + sm_count
        print(f"API key aparece {key_count} veces (esperado {expected})")
        assert key_count == expected, "Key leakage!"
        print("OK: key solo aparece dentro de las URLs de API")

    sample = re.search(r"https://maps\.googleapis\.com/maps/api/streetview\?[^\"']+", content)
    if sample:
        redacted = re.sub(r"key=[^&]+", "key=<REDACTED>", sample.group(0))
        print(f"\nSample SV URL: {redacted}")

    sample_sm = re.search(r"https://maps\.googleapis\.com/maps/api/staticmap\?[^\"']+", content)
    if sample_sm:
        redacted = re.sub(r"key=[^&]+", "key=<REDACTED>", sample_sm.group(0))
        print(f"Sample SM URL: {redacted}")

    out.unlink()
    print("\nSmoke test OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
