"""Unit tests for src.io_loader (Excel/CSV loading with alias normalization)."""

import pandas as pd
import pytest

from src.io_loader import load_csv, load_excel
from src.schema import CANONICAL_COLUMNS


@pytest.fixture
def single_header_excel(tmp_path):
    path = tmp_path / "single.xlsx"
    df = pd.DataFrame(
        [
            ["Detenido", "ABC12A", "10-04-2026 09:00:00", "10-04-2026 09:30:00",
             "30min 0s", "Juan", "10.37, -75.47", "60 kph", "30 kph"],
            ["Movimiento", "ABC12A", "10-04-2026 09:30:00", "10-04-2026 10:00:00",
             "30min 0s", "Juan", "5.2 Km", "80 kph", "55 kph"],
        ],
        columns=[
            "Estado", "Placa", "Comienzo", "Fin", "Duracion",
            "Conductor", "Posicion de parada", "Velocidad maxima", "Velocidad media",
        ],
    )
    df.to_excel(path, sheet_name="Sheet1", index=False)
    return path


@pytest.fixture
def aliased_csv(tmp_path):
    path = tmp_path / "data.csv"
    df = pd.DataFrame(
        [
            ["Detenido", "ABC12A", "10-04-2026 09:00:00", "10-04-2026 09:30:00",
             "30min 0s", "Juan", "10.37, -75.47", "60 kph", "30 kph"],
        ],
        columns=[
            "estado", "placa", "comienzo", "fin", "duracion",
            "conductor", "posicion de parada", "velocidad maxima", "velocidad media",
        ],
    )
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


class TestLoadExcel:
    def test_canonical_columns_present(self, single_header_excel):
        df = load_excel(single_header_excel)
        assert list(df.columns) == CANONICAL_COLUMNS

    def test_rows_loaded(self, single_header_excel):
        df = load_excel(single_header_excel)
        assert len(df) == 2
        assert df.iloc[0]["Placa"] == "ABC12A"

    def test_filters_valid_states(self, single_header_excel):
        df = load_excel(single_header_excel)
        assert set(df["Estado"]).issubset({"Detenido", "Movimiento"})

    def test_fallback_conductor_to_placa_when_blank(self, tmp_path):
        path = tmp_path / "no_conductor.xlsx"
        df_in = pd.DataFrame(
            [["Detenido", "XYZ99Z", "10-04-2026 09:00:00", "10-04-2026 09:30:00",
              "30min 0s", "", "10.37, -75.47", "60 kph", "30 kph"]],
            columns=[
                "Estado", "Placa", "Comienzo", "Fin", "Duracion",
                "Conductor", "Posicion", "Vel_Max", "Vel_Media",
            ],
        )
        df_in.to_excel(path, index=False)
        df = load_excel(path)
        assert df.iloc[0]["Conductor"] == "XYZ99Z"


class TestLoadCsv:
    def test_aliases_normalized(self, aliased_csv):
        df = load_csv(aliased_csv)
        assert list(df.columns) == CANONICAL_COLUMNS
        assert df.iloc[0]["Vel_Max"] == "60 kph"
        assert df.iloc[0]["Posicion"] == "10.37, -75.47"
