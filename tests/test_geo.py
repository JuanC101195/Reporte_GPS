"""Unit tests for src.geo."""

import numpy as np
import pytest

from src.geo import EARTH_RADIUS_M, haversine_matrix, haversine_metros


class TestHaversineMetros:
    def test_same_point_is_zero(self):
        assert haversine_metros(10.0, -75.0, 10.0, -75.0) == pytest.approx(0.0, abs=1e-6)

    def test_one_degree_latitude_is_about_111km(self):
        d = haversine_metros(0.0, 0.0, 1.0, 0.0)
        assert d == pytest.approx(111_195, rel=0.001)

    def test_cartagena_to_bogota_approx_700km(self):
        cartagena = (10.3910, -75.4794)
        bogota = (4.7110, -74.0721)
        d = haversine_metros(*cartagena, *bogota)
        assert 630_000 < d < 720_000

    def test_symmetric(self):
        d1 = haversine_metros(10.38, -75.47, 10.39, -75.48)
        d2 = haversine_metros(10.39, -75.48, 10.38, -75.47)
        assert d1 == pytest.approx(d2, rel=1e-9)


class TestHaversineMatrix:
    def test_shape(self):
        a_lat = [10.0, 10.1, 10.2]
        a_lon = [-75.0, -75.1, -75.2]
        b_lat = [10.0, 10.5]
        b_lon = [-75.0, -75.5]
        m = haversine_matrix(a_lat, a_lon, b_lat, b_lon)
        assert m.shape == (3, 2)

    def test_diagonal_zero_when_same_points(self):
        lats = [10.0, 10.1, 10.2]
        lons = [-75.0, -75.1, -75.2]
        m = haversine_matrix(lats, lons, lats, lons)
        assert np.allclose(np.diag(m), 0.0, atol=1e-6)

    def test_matches_scalar_for_one_pair(self):
        d_scalar = haversine_metros(10.0, -75.0, 10.5, -75.5)
        m = haversine_matrix([10.0], [-75.0], [10.5], [-75.5])
        assert m[0, 0] == pytest.approx(d_scalar, rel=1e-9)

    def test_earth_radius_constant(self):
        assert EARTH_RADIUS_M == 6_371_000.0
