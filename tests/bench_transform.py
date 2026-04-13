"""Synthetic benchmark for add_derived_columns. Not part of the test suite."""

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.transform import add_derived_columns


def synth(n_rows: int = 10000, n_placas: int = 20) -> pd.DataFrame:
    random.seed(42)
    placas = [f"ABC{i:02d}A" for i in range(n_placas)]
    states = ["Detenido", "Movimiento"]
    rows = []
    for _ in range(n_rows):
        estado = random.choice(states)
        placa = random.choice(placas)
        hour = random.randint(6, 22)
        dur_min = random.randint(1, 120)
        if estado == "Detenido":
            lat = 10.37 + random.uniform(-0.05, 0.05)
            lon = -75.47 + random.uniform(-0.05, 0.05)
            posicion = f"{lat:.6f}, {lon:.6f}"
        else:
            posicion = f"{random.uniform(0.1, 10):.2f} Km"
        rows.append(
            {
                "Estado": estado,
                "Placa": placa,
                "Conductor": placa,
                "Comienzo": f"10-04-2026 {hour:02d}:00:00",
                "Fin": f"10-04-2026 {hour:02d}:30:00",
                "Duracion": f"{dur_min}min 0s",
                "Posicion": posicion,
                "Vel_Max": f"{random.randint(20, 80)} kph",
                "Vel_Media": f"{random.randint(10, 60)} kph",
            }
        )
    return pd.DataFrame(rows)


def main():
    for n in (1000, 5000, 10000):
        df = synth(n)
        t0 = time.perf_counter()
        add_derived_columns(df)
        dt = time.perf_counter() - t0
        print(f"n_rows={n:>6}  time={dt*1000:>8.1f} ms")


if __name__ == "__main__":
    main()
