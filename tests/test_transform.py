"""Unit tests for src.transform."""

import pandas as pd
import pytest

from src.transform import (
    KNOWN_OFFICES,
    RADIO_MATCH_METROS,
    _match_nearest,
    add_derived_columns,
    clean_conductor,
    clean_placa,
    parse_coordinates,
    parse_coordinates_series,
    parse_distancia_km,
    parse_duracion_segundos,
    parse_velocidad_kph,
)


class TestParseCoordinates:
    def test_basic(self):
        assert parse_coordinates("10.371, -75.474") == (10.371, -75.474)

    def test_nan_returns_none_none(self):
        assert parse_coordinates(None) == (None, None)
        assert parse_coordinates(float("nan")) == (None, None)

    def test_garbage_returns_none_none(self):
        assert parse_coordinates("no hay coordenadas aqui") == (None, None)


class TestParseCoordinatesSeries:
    def test_basic(self):
        s = pd.Series(["10.371, -75.474", "10.382, -75.475", "garbage"])
        lat, lon = parse_coordinates_series(s)
        assert lat.iloc[0] == pytest.approx(10.371)
        assert lon.iloc[1] == pytest.approx(-75.475)
        assert pd.isna(lat.iloc[2])

    def test_empty_series(self):
        lat, lon = parse_coordinates_series(pd.Series([], dtype=str))
        assert lat.empty and lon.empty

    def test_with_na_values(self):
        s = pd.Series([None, "10.0, -75.0", ""])
        lat, lon = parse_coordinates_series(s)
        assert pd.isna(lat.iloc[0])
        assert lat.iloc[1] == pytest.approx(10.0)
        assert pd.isna(lat.iloc[2])


class TestParseDurationSegundos:
    def test_hours_minutes_seconds(self):
        s = pd.Series(["2h 30min 15s", "45min 0s", "10s"])
        out = parse_duracion_segundos(s)
        assert out.iloc[0] == 2 * 3600 + 30 * 60 + 15
        assert out.iloc[1] == 45 * 60
        assert out.iloc[2] == 10

    def test_empty_and_nan(self):
        s = pd.Series(["", None, "nan"])
        out = parse_duracion_segundos(s)
        assert (out == 0).all()


class TestParseVelocidadKph:
    def test_basic(self):
        s = pd.Series(["80 kph", "45.5 kph", "no speed"])
        out = parse_velocidad_kph(s)
        assert out.iloc[0] == pytest.approx(80.0)
        assert out.iloc[1] == pytest.approx(45.5)
        assert pd.isna(out.iloc[2])


class TestParseDistanciaKm:
    def test_basic(self):
        s = pd.Series(["12.5 Km", "3 km", "nothing"])
        out = parse_distancia_km(s)
        assert out.iloc[0] == pytest.approx(12.5)
        assert out.iloc[1] == pytest.approx(3.0)
        assert pd.isna(out.iloc[2])


class TestCleanPlacaConductor:
    def test_clean_placa_uppercases_and_trims(self):
        s = pd.Series(["  abc12a  ", "def34b", None])
        out = clean_placa(s)
        assert out.iloc[0] == "ABC12A"
        assert out.iloc[1] == "DEF34B"
        assert out.iloc[2] == ""

    def test_clean_conductor_collapses_whitespace(self):
        s = pd.Series(["  Juan   Pedro  ", "Maria"])
        out = clean_conductor(s)
        assert out.iloc[0] == "Juan Pedro"
        assert out.iloc[1] == "Maria"


class TestMatchNearest:
    def test_empty_targets_returns_all_none(self):
        lat_s = pd.Series([10.0, 10.1])
        lon_s = pd.Series([-75.0, -75.1])
        out = _match_nearest(lat_s, lon_s, [], [], [], 200.0)
        assert out.isna().all()

    def test_matches_within_radius(self):
        # Target at Casa Blanca, probe points close and far.
        cb = KNOWN_OFFICES["Casa Blanca"]
        lat_s = pd.Series([cb["lat"], cb["lat"] + 0.01])  # ~1.1 km away
        lon_s = pd.Series([cb["lon"], cb["lon"]])
        out = _match_nearest(
            lat_s, lon_s,
            [cb["lat"]], [cb["lon"]], ["Casa Blanca"],
            RADIO_MATCH_METROS,
        )
        assert out.iloc[0] == "Casa Blanca"
        assert out.iloc[1] is None

    def test_nan_lat_lon_yields_none(self):
        lat_s = pd.Series([float("nan"), 10.382486])
        lon_s = pd.Series([-75.0, -75.475173])
        out = _match_nearest(
            lat_s, lon_s,
            [10.382486], [-75.475173], ["Casa Blanca"],
            RADIO_MATCH_METROS,
        )
        assert out.iloc[0] is None
        assert out.iloc[1] == "Casa Blanca"


class TestAddDerivedColumns:
    def _build_df(self):
        # 2 stops (one at Casa Blanca, one elsewhere) + 1 movement.
        cb = KNOWN_OFFICES["Casa Blanca"]
        return pd.DataFrame(
            [
                {
                    "Estado": "Detenido",
                    "Placa": "ABC12A",
                    "Conductor": "Juan",
                    "Comienzo": "10-04-2026 09:00:00",
                    "Fin": "10-04-2026 09:30:00",
                    "Duracion": "30min 0s",
                    "Posicion": f"{cb['lat']}, {cb['lon']}",
                    "Vel_Max": "60 kph",
                    "Vel_Media": "30 kph",
                },
                {
                    "Estado": "Detenido",
                    "Placa": "ABC12A",
                    "Conductor": "Juan",
                    "Comienzo": "10-04-2026 10:00:00",
                    "Fin": "10-04-2026 10:45:00",
                    "Duracion": "45min 0s",
                    "Posicion": "10.500, -75.500",  # unknown place
                    "Vel_Max": "70 kph",
                    "Vel_Media": "40 kph",
                },
                {
                    "Estado": "Movimiento",
                    "Placa": "ABC12A",
                    "Conductor": "Juan",
                    "Comienzo": "10-04-2026 11:00:00",
                    "Fin": "10-04-2026 11:30:00",
                    "Duracion": "30min 0s",
                    "Posicion": "5.2 Km",
                    "Vel_Max": "80 kph",
                    "Vel_Media": "55 kph",
                },
            ]
        )

    def test_columns_added(self):
        df = add_derived_columns(self._build_df())
        expected = {
            "duracion_seg",
            "semana",
            "dia_semana",
            "fecha",
            "vel_max_kph",
            "vel_media_kph",
            "distancia_km",
            "latitud",
            "longitud",
            "ubicacion_conocida",
        }
        assert expected.issubset(set(df.columns))

    def test_known_office_tagged_only_for_stop(self):
        df = add_derived_columns(self._build_df())
        # First row is a stop at Casa Blanca -> tagged
        assert df.loc[0, "ubicacion_conocida"] == "Casa Blanca"
        # Second row is a stop far away -> not tagged
        assert df.loc[1, "ubicacion_conocida"] is None
        # Third row is movement -> not tagged
        assert df.loc[2, "ubicacion_conocida"] is None

    def test_distance_parsed_only_for_movement(self):
        df = add_derived_columns(self._build_df())
        assert df.loc[2, "distancia_km"] == pytest.approx(5.2)
        assert df.loc[0, "distancia_km"] is None
        assert df.loc[1, "distancia_km"] is None
