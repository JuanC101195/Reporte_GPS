"""Unit tests for the executive-level ranking and scoring in anomalias.core."""

import pandas as pd
import pytest

from src.anomalias.core import (
    SCORE_THRESHOLD_AMARILLO,
    SCORE_THRESHOLD_ROJO,
    WEIGHT_HORAS_DESC,
    WEIGHT_HORAS_FUERA,
    WEIGHT_LUGARES_FREC,
    WEIGHT_PARADAS_ANOM,
    _clasificar_paradas,
    _cluster_desconocidos,
    _nivel_score,
    ranking_conductores,
)


class TestNivelScore:
    def test_verde_below_amber(self):
        assert _nivel_score(0) == "VERDE"
        assert _nivel_score(SCORE_THRESHOLD_AMARILLO - 0.1) == "VERDE"

    def test_amarillo_between(self):
        assert _nivel_score(SCORE_THRESHOLD_AMARILLO) == "AMARILLO"
        assert _nivel_score(SCORE_THRESHOLD_ROJO - 0.1) == "AMARILLO"

    def test_rojo_above(self):
        assert _nivel_score(SCORE_THRESHOLD_ROJO) == "ROJO"
        assert _nivel_score(999) == "ROJO"


@pytest.fixture
def zonas():
    return [
        {"nombre": "Oficina Base", "tipo": "oficina", "lat": 10.0, "lon": -75.0, "radio_m": 200},
    ]


@pytest.fixture
def det_clasificado(zonas):
    # Cond_MALO: 3 paradas largas en zona desconocida (una nocturna),
    # suficientes para superar el threshold ROJO.
    # Cond_BUENO: 2 paradas cortas en la oficina base (todas dentro de radio).
    rows = [
        {
            "Estado": "Detenido", "Placa": "MAL123", "Conductor": "Juan Malo",
            "Comienzo": "05-04-2026 10:00:00", "Duracion": "5h 0min 0s",
            "Posicion": "10.5, -75.5", "duracion_seg": 5 * 3600, "lat": 10.5, "lon": -75.5,
        },
        {
            "Estado": "Detenido", "Placa": "MAL123", "Conductor": "Juan Malo",
            "Comienzo": "06-04-2026 15:00:00", "Duracion": "4h 0min 0s",
            "Posicion": "10.5, -75.5", "duracion_seg": 4 * 3600, "lat": 10.5, "lon": -75.5,
        },
        {
            "Estado": "Detenido", "Placa": "MAL123", "Conductor": "Juan Malo",
            "Comienzo": "07-04-2026 23:30:00", "Duracion": "2h 0min 0s",
            "Posicion": "10.5, -75.5", "duracion_seg": 2 * 3600, "lat": 10.5, "lon": -75.5,
        },
        {
            "Estado": "Detenido", "Placa": "BUE456", "Conductor": "Pedro Bueno",
            "Comienzo": "05-04-2026 10:00:00", "Duracion": "15min 0s",
            "Posicion": "10.0, -75.0", "duracion_seg": 15 * 60, "lat": 10.0, "lon": -75.0,
        },
        {
            "Estado": "Detenido", "Placa": "BUE456", "Conductor": "Pedro Bueno",
            "Comienzo": "05-04-2026 15:00:00", "Duracion": "10min 0s",
            "Posicion": "10.0, -75.0", "duracion_seg": 10 * 60, "lat": 10.0, "lon": -75.0,
        },
    ]
    df = pd.DataFrame(rows)
    return _clasificar_paradas(df, zonas)


class TestRankingConductores:
    def test_empty_df(self):
        assert ranking_conductores(pd.DataFrame(), pd.DataFrame()) == []

    def test_malo_scores_higher_than_bueno(self, det_clasificado):
        anom = det_clasificado[det_clasificado["es_anomalia"]].copy()
        clusters = {
            "Juan Malo": _cluster_desconocidos(anom, "Juan Malo"),
            "Pedro Bueno": _cluster_desconocidos(anom, "Pedro Bueno"),
        }
        ranking = ranking_conductores(det_clasificado, anom, clusters)

        assert len(ranking) == 2
        # El malo debe aparecer primero
        assert ranking[0]["conductor"] == "Juan Malo"
        assert ranking[1]["conductor"] == "Pedro Bueno"
        assert ranking[0]["score"] > ranking[1]["score"]

    def test_malo_is_rojo(self, det_clasificado):
        anom = det_clasificado[det_clasificado["es_anomalia"]].copy()
        clusters = {"Juan Malo": _cluster_desconocidos(anom, "Juan Malo")}
        ranking = ranking_conductores(det_clasificado, anom, clusters)
        malo = next(r for r in ranking if r["conductor"] == "Juan Malo")
        assert malo["nivel"] == "ROJO"
        assert malo["paradas_anomalas"] == 3  # 5h, 4h, 2h todas califican
        assert malo["horas_desconocidas"] == pytest.approx(11.0, abs=0.01)
        assert malo["peor_cluster"] is not None

    def test_bueno_is_verde(self, det_clasificado):
        anom = det_clasificado[det_clasificado["es_anomalia"]].copy()
        ranking = ranking_conductores(det_clasificado, anom, {})
        bueno = next(r for r in ranking if r["conductor"] == "Pedro Bueno")
        assert bueno["nivel"] == "VERDE"
        assert bueno["score"] == 0.0
        assert bueno["paradas_anomalas"] == 0
        assert bueno["peor_cluster"] is None

    def test_score_formula_matches(self, det_clasificado):
        anom = det_clasificado[det_clasificado["es_anomalia"]].copy()
        clusters = {"Juan Malo": _cluster_desconocidos(anom, "Juan Malo")}
        ranking = ranking_conductores(det_clasificado, anom, clusters)
        malo = next(r for r in ranking if r["conductor"] == "Juan Malo")
        expected = (
            malo["horas_desconocidas"] * WEIGHT_HORAS_DESC
            + malo["paradas_anomalas"] * WEIGHT_PARADAS_ANOM
            + malo["lugares_frecuentes"] * WEIGHT_LUGARES_FREC
            + malo["horas_fuera_horario"] * WEIGHT_HORAS_FUERA
        )
        assert malo["score"] == pytest.approx(expected, rel=1e-3)
