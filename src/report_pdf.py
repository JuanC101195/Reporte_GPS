# -*- coding: utf-8 -*-
"""Convert HTML to PDF with wkhtmltopdf/browser fallback."""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_BROWSER_PATHS = [
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
]


def _find_browser():
    for p in _BROWSER_PATHS:
        if Path(p).exists():
            return p
    return None


def _wkhtmltopdf(html_path, pdf_path):
    try:
        import pdfkit

        pdfkit.from_file(str(html_path), str(pdf_path))
        return True
    except Exception as exc:
        logger.warning("wkhtmltopdf failed: %s", exc)
        return False


def _browser_pdf(html_path, pdf_path):
    browser = _find_browser()
    if not browser:
        logger.error("No Edge or Chrome found.")
        return False

    html_path = Path(html_path).resolve()
    pdf_path = Path(pdf_path).resolve()
    url = f"file:///{html_path.as_posix()}"
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path.as_posix()}",
        url,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
            return True
        if result.returncode == 0:
            logger.error("Browser returned success but PDF was not created: %s", pdf_path)
            return False
        logger.error("Browser pdf error [%s]: %s", result.returncode, result.stderr.decode(errors="replace"))
        return False
    except Exception as exc:
        logger.error("Error running browser for PDF: %s", exc)
        return False


def html_to_pdf(html_path, pdf_path):
    html_path = Path(html_path)
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    if shutil.which("wkhtmltopdf"):
        if _wkhtmltopdf(html_path, pdf_path):
            return True
        logger.warning("Falling back to browser headless mode.")

    return _browser_pdf(html_path, pdf_path)
