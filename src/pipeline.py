# -*- coding: utf-8 -*-
"""Orchestrator for end-to-end GPS pipeline."""

import logging
import sys
from datetime import datetime
from pathlib import Path

from . import io_loader, report_html, report_pdf, transform, validation


def _setup_logging(log_dir="logs"):
    Path(log_dir).mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(log_dir) / f"run_{ts}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("pipeline")


def run_pipeline(
    input_file,
    output_dir="reportes",
    sheet_name=None,
    validate_only=False,
    skip_pdf=False,
    log_dir="logs",
    homes_file=None,
    photos_file=None,
):
    log = _setup_logging(log_dir)
    input_file = Path(input_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("PIPELINE START")
    log.info("Input : %s", input_file)
    log.info("Output: %s", output_dir)
    if homes_file:
        log.info("Homes : %s", homes_file)
    if photos_file:
        log.info("Photos: %s", photos_file)
    log.info("=" * 60)

    try:
        ext = input_file.suffix.lower()
        if ext in (".xlsx", ".xls"):
            df = io_loader.load_excel(input_file, sheet_name=sheet_name)
        elif ext == ".csv":
            df = io_loader.load_csv(input_file)
        else:
            raise ValueError(f"Unsupported extension: {ext}")
    except Exception as exc:
        log.error("Load error: %s", exc)
        return False

    log.info("Rows loaded: %s | Columns: %s", len(df), list(df.columns))

    quality_dir = output_dir / "quality"
    try:
        validation.validate_schema(df)
        _, errors = validation.generate_quality_report(df, quality_dir)
        log.info("Quality check: %s errors -> %s", len(errors), quality_dir)
        if not errors.empty:
            log.warning("Review: %s", quality_dir / "data_quality_errors.csv")
    except Exception as exc:
        log.error("Validation error: %s", exc)
        return False

    if validate_only:
        log.info("validate-only mode. Stop pipeline.")
        return True

    try:
        df = transform.add_derived_columns(df, homes_file=homes_file, photos_file=photos_file)
        log.info("Transform complete (durations, week, speed, distance).")
    except Exception as exc:
        log.error("Transform error: %s", exc)
        return False

    html_dir = output_dir / "html"
    try:
        n_html = report_html.generate_html_report(df, html_dir)
        log.info("HTML generated: %s -> %s", n_html, html_dir)
    except Exception as exc:
        log.error("HTML generation error: %s", exc)
        return False

    if not skip_pdf:
        pdf_dir = output_dir / "pdf"
        pdf_dir.mkdir(exist_ok=True)
        html_files = sorted(html_dir.glob("*.html"))
        ok = err = 0
        for html_file in html_files:
            pdf_file = pdf_dir / f"{html_file.stem}.pdf"
            if report_pdf.html_to_pdf(html_file, pdf_file):
                ok += 1
            else:
                err += 1
                log.error("PDF failed: %s", html_file.name)
        log.info("PDF generated: %s/%s -> %s", ok, ok + err, pdf_dir)

    log.info("=" * 60)
    log.info("PIPELINE COMPLETE")
    log.info("=" * 60)
    return True
