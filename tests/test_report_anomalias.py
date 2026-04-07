import unittest
import pandas as pd
from datetime import datetime
import sys
from pathlib import Path

# Añadimos la raíz del proyecto para importar src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.report_anomalias import (
    _clasificar_paradas,
    _paradas_largas,
    _coincidencias_ruta,
    _ubicacion_repetida_semanal,
    UMBRAL_PARADA_LARGA_SEG
)

class TestReportAnomalias(unittest.TestCase):
    def setUp(self):
        # Mapeo similar a las ZONAS_CONOCIDAS
        self.zonas = [
            {"nombre": "Base_1", "tipo": "oficina", "lat": 10.0, "lon": -75.0, "radio_m": 200},
            {"nombre": "Casa_X", "tipo": "casa", "conductor": "Cond_A", "lat": 10.1, "lon": -75.1, "radio_m": 200}
        ]
        
        # Simulamos datos provenientes de la estructura procesada del pipeline
        data = [
            # 0. Parada larga en lugar desconocido (Anomalía)
            {"Estado": "Detenido", "Placa": "AAA111", "Conductor": "Cond_A", "Comienzo": "05-04-2026 10:00:00", "Duracion": "1h 0min 0s", "Posicion": "10.2, -75.2", "duracion_seg": 3600, "lat": 10.2, "lon": -75.2},
            
            # 1. Parada corta en lugar desconocido (Normal/No anomalía)
            {"Estado": "Detenido", "Placa": "AAA111", "Conductor": "Cond_A", "Comienzo": "05-04-2026 11:30:00", "Duracion": "5min 0s", "Posicion": "10.3, -75.3", "duracion_seg": 300, "lat": 10.3, "lon": -75.3},
            
            # 2. Parada larga en casa del conductor (No es anomalía porque es su casa)
            {"Estado": "Detenido", "Placa": "AAA111", "Conductor": "Cond_A", "Comienzo": "05-04-2026 12:00:00", "Duracion": "2h 0min 0s", "Posicion": "10.1, -75.1", "duracion_seg": 7200, "lat": 10.1, "lon": -75.1},
            
            # 3. Movimiento (Para simular ruido en df, aunque clasificamos paradas)
            {"Estado": "Movimiento", "Placa": "AAA111", "Conductor": "Cond_A", "Comienzo": "05-04-2026 14:00:00", "Duracion": "30min 0s", "Posicion": "10.15, -75.15", "duracion_seg": 1800, "lat": 10.15, "lon": -75.15},
            
            # 4 y 5. Coincidencias de ruta (2 vehículos distintos en el mismo lugar/radio, misma hora)
            {"Estado": "Detenido", "Placa": "BBB222", "Conductor": "Cond_B", "Comienzo": "05-04-2026 15:10:00", "Duracion": "40min 0s", "Posicion": "10.4, -75.4", "duracion_seg": 2400, "lat": 10.4, "lon": -75.4},
            {"Estado": "Detenido", "Placa": "CCC333", "Conductor": "Cond_C", "Comienzo": "05-04-2026 15:15:00", "Duracion": "35min 0s", "Posicion": "10.4001, -75.4001", "duracion_seg": 2100, "lat": 10.4001, "lon": -75.4001},
            
            # 6 y 7. Lugar repetido semanal (Mismo origen en días diferentes del Cond_D)
            {"Estado": "Detenido", "Placa": "DDD444", "Conductor": "Cond_D", "Comienzo": "05-04-2026 16:00:00", "Duracion": "10min 0s", "Posicion": "10.5, -75.5", "duracion_seg": 600, "lat": 10.5, "lon": -75.5},
            {"Estado": "Detenido", "Placa": "DDD444", "Conductor": "Cond_D", "Comienzo": "06-04-2026 16:00:00", "Duracion": "10min 0s", "Posicion": "10.5001, -75.5001", "duracion_seg": 600, "lat": 10.5001, "lon": -75.5001}
        ]
        self.df = pd.DataFrame(data)

    def test_01_clasificar_paradas_detecta_anomalias(self):
        """Verifica que las paradas mayores a 30m en zonas desconocidas sean Anomalías"""
        det = self.df[self.df["Estado"] == "Detenido"].copy()
        res = _clasificar_paradas(det, self.zonas)
        
        # Filtramos resultados del Conductor A
        cond_a = res[res["Conductor"] == "Cond_A"]
        
        # Index 0 correspondía a una parada desconocida de 1h -> Anomalía Larga
        self.assertTrue(cond_a.iloc[0]["es_anomalia"])
        self.assertTrue(cond_a.iloc[0]["larga_horario"])
        
        # Index 1 correspondía a 5 mins desconocida -> SÍ es anomalía para los reportes de repetidas, pero NO larga
        self.assertTrue(cond_a.iloc[1]["es_anomalia"])
        self.assertFalse(cond_a.iloc[1]["larga_horario"])
        
        # Index 2 correspondía a 2 horas pero en Casa_X (zona autorizada) -> No es anomalía
        self.assertFalse(cond_a.iloc[2]["es_anomalia"])
        self.assertEqual(cond_a.iloc[2]["zona_ref_nombre"], "Casa_X")

    def test_02_paradas_largas_coherencia(self):
        """Verifica que la función _paradas_largas retorna correctamente las paradas mayores a 30 min"""
        det = self.df[self.df["Estado"] == "Detenido"].copy()
        res = _clasificar_paradas(det, self.zonas)
        largas = _paradas_largas(res, UMBRAL_PARADA_LARGA_SEG)
        
        # Cond_A tiene 2 paradas largas en los datos (Index 0 y Index 2)
        largas_cond_a = [r for r in largas if r["conductor"] == "Cond_A"]
        self.assertEqual(len(largas_cond_a), 2)
        
        # Las paradas cortas (5 min, 10 min) de Cond_D no deben estar aquí
        largas_cond_d = [r for r in largas if r["conductor"] == "Cond_D"]
        self.assertEqual(len(largas_cond_d), 0)

    def test_03_coincidencias_ruta(self):
        """Verifica que al cruzarse 2 autos en el mismo radio a la misma hora, genere la advertencia"""
        det = self.df[self.df["Estado"] == "Detenido"].copy()
        res = _clasificar_paradas(det, self.zonas)
        coincidencias = _coincidencias_ruta(res)
        
        # Solo hubo coincidencia entre Cond_B y Cond_C alrededor de las 15:00
        self.assertEqual(len(coincidencias), 1)
        self.assertEqual(coincidencias[0]["n_placas"], 2)
        
        self.assertIn("BBB222", coincidencias[0]["placas"])
        self.assertIn("CCC333", coincidencias[0]["placas"])
        self.assertIn("05-04-2026 15:00", coincidencias[0]["hora"])

    def test_04_ubicacion_repetida_semanal(self):
        """Valida que los registros que se repiten múltiples veces en la semana se detecten correctamente"""
        det = self.df[self.df["Estado"] == "Detenido"].copy()
        res_clasif = _clasificar_paradas(det, self.zonas)
        repetidas = _ubicacion_repetida_semanal(res_clasif)
        
        # Cond_A solo visita 1 vez cada lugar, no debe aparecer en repetidas con visitas >= 2
        rep_cond_a = [r for r in repetidas if r["conductor"] == "Cond_A"]
        self.assertEqual(len(rep_cond_a), 0)
        
        # Cond_D visita las coordenadas 10.5, -75.5 en dos días diferentes
        rep_cond_d = [r for r in repetidas if r["conductor"] == "Cond_D"]
        self.assertEqual(len(rep_cond_d), 1)
        self.assertEqual(rep_cond_d[0]["visitas"], 2)


if __name__ == '__main__':
    unittest.main()