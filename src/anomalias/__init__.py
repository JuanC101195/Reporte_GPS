"""Pure analytical core for the anomalias pipeline.

This package contains the business logic (classification, clustering,
alerts, coincidences, frequent places) decoupled from any HTML/Folium
rendering. Importing from here is the recommended entry point for
microservices or notebooks that only need the analytics.
"""

from .core import (
    HORA_NOCTURNA_FIN,
    HORA_NOCTURNA_INICIO,
    HORARIO_FIN,
    HORARIO_INICIO,
    RADIO_CLUSTER_METROS,
    RADIO_ZONA_CONOCIDA_M,
    UMBRAL_PARADA_LARGA_SEG,
    VISITAS_LUGAR_FRECUENTE,
    ZONAS_CONOCIDAS,
    zona_mas_cercana,
    zona_referencia_mas_cercana,
)

__all__ = [
    "HORARIO_INICIO",
    "HORARIO_FIN",
    "UMBRAL_PARADA_LARGA_SEG",
    "HORA_NOCTURNA_INICIO",
    "HORA_NOCTURNA_FIN",
    "RADIO_CLUSTER_METROS",
    "RADIO_ZONA_CONOCIDA_M",
    "VISITAS_LUGAR_FRECUENTE",
    "ZONAS_CONOCIDAS",
    "zona_mas_cercana",
    "zona_referencia_mas_cercana",
]
