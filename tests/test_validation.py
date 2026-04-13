"""Unit tests for src.validation."""

import pandas as pd
import pytest

from src.validation import generate_quality_report, parse_dates, validate_schema


class TestParseDates:
    def test_dash_format(self):
        s = pd.Series(["10-04-2026 09:00:00", "11-04-2026 10:30:00"])
        out = parse_dates(s)
        assert out.iloc[0].year == 2026
        assert out.iloc[0].month == 4
        assert out.iloc[0].hour == 9

    def test_slash_format(self):
        s = pd.Series(["10/04/2026 09:00:00"])
        out = parse_dates(s)
        assert out.iloc[0].day == 10

    def test_iso_format(self):
        s = pd.Series(["2026-04-10 09:00:00"])
        out = parse_dates(s)
        assert out.iloc[0].year == 2026

    def test_invalid_returns_nat(self):
        s = pd.Series(["not a date", ""])
        out = parse_dates(s)
        assert out.isna().all()


class TestValidateSchema:
    def test_all_required_columns(self):
        df = pd.DataFrame(columns=["Estado", "Placa", "Comienzo", "Fin", "Duracion"])
        assert validate_schema(df) is True

    def test_missing_column_raises(self):
        df = pd.DataFrame(columns=["Estado", "Placa"])
        with pytest.raises(ValueError, match="Missing required columns"):
            validate_schema(df)


class TestGenerateQualityReport:
    def test_writes_files(self, tmp_path):
        df = pd.DataFrame(
            [
                {
                    "Estado": "Detenido", "Placa": "ABC12A",
                    "Comienzo": "10-04-2026 09:00:00", "Fin": "10-04-2026 09:30:00",
                    "Duracion": "30min 0s", "Conductor": "Juan",
                    "Posicion": "10.37, -75.47", "Vel_Max": "", "Vel_Media": "",
                },
            ]
        )
        stats, errors = generate_quality_report(df, tmp_path)
        assert (tmp_path / "data_quality_stats.csv").exists()
        assert (tmp_path / "data_quality_errors.csv").exists()
        assert "columna" in stats.columns

    def test_detects_bad_state(self, tmp_path):
        df = pd.DataFrame(
            [
                {
                    "Estado": "Volando",  # invalid
                    "Placa": "ABC12A",
                    "Comienzo": "10-04-2026 09:00:00",
                    "Fin": "10-04-2026 09:30:00",
                    "Duracion": "30min 0s",
                    "Conductor": "Juan",
                    "Posicion": "10.37, -75.47",
                    "Vel_Max": "", "Vel_Media": "",
                },
            ]
        )
        _, errors = generate_quality_report(df, tmp_path)
        assert not errors.empty
        assert any(errors["campo"] == "Estado")

    def test_detects_invalid_coord_for_stop(self, tmp_path):
        df = pd.DataFrame(
            [
                {
                    "Estado": "Detenido", "Placa": "ABC12A",
                    "Comienzo": "10-04-2026 09:00:00", "Fin": "10-04-2026 09:30:00",
                    "Duracion": "30min 0s", "Conductor": "Juan",
                    "Posicion": "not a coord", "Vel_Max": "", "Vel_Media": "",
                },
            ]
        )
        _, errors = generate_quality_report(df, tmp_path)
        assert any(errors["campo"] == "Posicion")
