#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Command line interface for GPS analysis pipeline."""

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

run_pipeline = importlib.import_module("src.pipeline").run_pipeline


def _run(args):
    run_pipeline(
        input_file=args.input,
        output_dir=args.out_dir,
        sheet_name=args.sheet,
        validate_only=args.validate_only,
        skip_pdf=args.skip_pdf,
        homes_file=getattr(args, "homes_file", None),
        photos_file=getattr(args, "photos_file", None),
    )


def _validate(args):
    run_pipeline(
        input_file=args.input,
        output_dir=args.out_dir,
        sheet_name=args.sheet,
        validate_only=True,
        skip_pdf=True,
        homes_file=getattr(args, "homes_file", None),
        photos_file=getattr(args, "photos_file", None),
    )


def _pdf(args):
    html_to_pdf = importlib.import_module("src.report_pdf").html_to_pdf

    html_dir = Path(args.html_dir)
    pdf_dir = Path(args.pdf_dir) if args.pdf_dir else html_dir / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for html_file in sorted(html_dir.glob("*.html")):
        if html_to_pdf(html_file, pdf_dir / f"{html_file.stem}.pdf"):
            ok += 1

    print(f"PDF generated: {ok} in {pdf_dir}")


def _anomalias(args):
    load_excel = importlib.import_module("src.io_loader").load_excel
    load_csv = importlib.import_module("src.io_loader").load_csv
    add_derived_columns = importlib.import_module("src.transform").add_derived_columns
    anom_mod = importlib.import_module("src.report_anomalias")
    generar_html_anomalias = anom_mod.generar_html_anomalias
    zonas_conocidas = anom_mod.ZONAS_CONOCIDAS

    p = Path(args.input)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    df = load_excel(p, sheet_name=args.sheet) if p.suffix.lower() in (".xlsx", ".xls") else load_csv(p)
    df = add_derived_columns(df)

    output_file = out / "reporte_anomalias.html"
def _anomalias(args):
    # Usar pipeline para leer el df limpio
    from src import pipeline
    from src.report_anomalias import generar_html_anomalias, ZONAS_CONOCIDAS

    from src import io_loader, transform
    df = io_loader.load_excel(Path(args.input), sheet_name=args.sheet)
    df = transform.add_derived_columns(df, photos_file=getattr(args, "photos_file", None))

    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "reporte_anomalias.html"
    
    generar_html_anomalias(df, ZONAS_CONOCIDAS, output_file, periodo_label=args.periodo)
    print(f"Reporte generado: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="GPS vehicle analysis pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Full pipeline: load -> validate -> html -> pdf")
    p_run.add_argument("--input", required=True, help="Path to Excel or CSV file")
    p_run.add_argument("--sheet", default=None, help="Excel sheet name")
    p_run.add_argument("--out-dir", default="reportes", help="Output folder")
    p_run.add_argument("--validate-only", action="store_true", help="Only validate data")
    p_run.add_argument("--skip-pdf", action="store_true", help="Skip PDF generation")
    p_run.add_argument("--homes-file", default=None, help="Excel with worker home coordinates")
    p_run.add_argument("--photos-file", default=None, help="Excel with photo GPS mappings (e.g. UBICACION.xlsx)")
    p_run.set_defaults(func=_run)

    p_val = sub.add_parser("validate", help="Validation-only mode")
    p_val.add_argument("--input", required=True)
    p_val.add_argument("--sheet", default=None)
    p_val.add_argument("--out-dir", default="reportes")
    p_val.add_argument("--homes-file", default=None, help="Excel with worker home coordinates")
    p_val.add_argument("--photos-file", default=None, help="Excel with photo GPS mappings")
    p_val.set_defaults(func=_validate)

    p_pdf = sub.add_parser("pdf", help="Convert existing HTML files to PDF")
    p_pdf.add_argument("--html-dir", required=True)
    p_pdf.add_argument("--pdf-dir", default=None)
    p_pdf.set_defaults(func=_pdf)

    p_anom = sub.add_parser("anomalias", help="Reporte ejecutivo de anomalias GPS")
    p_anom.add_argument("--input", required=True)
    p_anom.add_argument("--sheet", default=None)
    p_anom.add_argument("--out-dir", default="reportes")
    p_anom.add_argument("--periodo", default=None, help="Ej: Semana 9-16 Marzo 2026")
    p_anom.add_argument("--photos-file", default=None, help="Excel with photo GPS mappings")
    p_anom.set_defaults(func=_anomalias)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
