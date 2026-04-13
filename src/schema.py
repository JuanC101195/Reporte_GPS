"""Canonical schema for GPS pipeline."""

CANONICAL_COLUMNS = [
    "Estado",
    "Placa",
    "Comienzo",
    "Fin",
    "Duracion",
    "Conductor",
    "Posicion",
    "Vel_Max",
    "Vel_Media",
]

ALIAS_MAP = {
    "estado": "Estado",
    "placa": "Placa",
    "comienzo": "Comienzo",
    "fin": "Fin",
    "duracion": "Duracion",
    "conductor": "Conductor",
    "posicion de parada": "Posicion",
    "longitud de ruta / posicion de parada": "Posicion",
    "longitud de ruta": "Posicion",
    "velocidad maxima": "Vel_Max",
    "velocidad media": "Vel_Media",
}

VALID_STATES = {"Detenido", "Movimiento"}

DATE_FORMATS = [
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
]
