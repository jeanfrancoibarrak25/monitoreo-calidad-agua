"""Estándares de Calidad Ambiental (ECA) para Agua — D.S. N.° 004-2017-MINAM (Perú).

Valores tomados del Anexo del D.S. N.° 004-2017-MINAM para los parámetros que registra el
sistema. Verifique siempre contra la publicación oficial en El Peruano antes de emitir un informe.

Convenciones
- Cada parámetro: (mínimo, máximo). None = sin límite en ese sentido.
- "temperatura": ("delta", 3) → variación máxima de ±3 °C respecto al promedio mensual multianual
  del área evaluada (se necesita ingresar ese promedio para evaluar).
- Parámetros ausentes = el ECA no establece valor para esa categoría ("No regulado").
- Sólidos totales y sulfito no figuran en el ECA-Agua: se reportan de forma referencial.
"""
from __future__ import annotations

import numpy as np

ECA = {
    "Cat. 1-A1 · Aguas que pueden ser potabilizadas con desinfección": {
        "ph": (6.5, 8.5), "conductividad": (None, 1500), "temperatura": ("delta", 3), "sdt": (None, 1000),
    },
    "Cat. 1-A2 · Aguas que pueden ser potabilizadas con tratamiento convencional": {
        "ph": (5.5, 9.0), "conductividad": (None, 1600), "temperatura": ("delta", 3), "sdt": (None, 1000),
    },
    "Cat. 1-A3 · Aguas que pueden ser potabilizadas con tratamiento avanzado": {
        "ph": (5.5, 9.0), "sdt": (None, 1500),
    },
    "Cat. 1-B1 · Contacto primario": {"ph": (6.0, 9.0)},
    "Cat. 2-C1 · Extracción y cultivo de moluscos, equinodermos y tunicados": {
        "ph": (7.0, 8.5), "temperatura": ("delta", 3), "sst": (None, 80),
    },
    "Cat. 2-C2 · Extracción y cultivo de otras especies hidrobiológicas": {
        "ph": (6.8, 8.5), "temperatura": ("delta", 3), "sst": (None, 60),
    },
    "Cat. 2-C3 · Actividades marino portuarias, industriales o de saneamiento": {
        "ph": (6.8, 8.5), "temperatura": ("delta", 3), "sst": (None, 70),
    },
    "Cat. 2-C4 · Extracción y cultivo de especies hidrobiológicas en lagos o lagunas": {
        "ph": (6.0, 9.0), "temperatura": ("delta", 3),
    },
    "Cat. 3-D1 · Riego de vegetales": {
        "ph": (6.5, 8.5), "conductividad": (None, 2500), "temperatura": ("delta", 3),
    },
    "Cat. 3-D2 · Bebida de animales": {
        "ph": (6.5, 8.4), "conductividad": (None, 5000), "temperatura": ("delta", 3),
    },
    "Cat. 4-E1 · Lagunas y lagos": {
        "ph": (6.5, 9.0), "conductividad": (None, 1000), "temperatura": ("delta", 3), "sst": (None, 25),
    },
    "Cat. 4-E2 · Ríos de costa y sierra": {
        "ph": (6.5, 9.0), "conductividad": (None, 1000), "temperatura": ("delta", 3), "sst": (None, 100),
    },
    "Cat. 4-E2 · Ríos de selva": {
        "ph": (6.5, 9.0), "conductividad": (None, 1000), "temperatura": ("delta", 3), "sst": (None, 400),
    },
    "Cat. 4-E3 · Estuarios": {"ph": (6.8, 8.5), "temperatura": ("delta", 2), "sst": (None, 100)},
    "Cat. 4-E3 · Marinos": {"ph": (6.8, 8.5), "temperatura": ("delta", 2), "sst": (None, 30)},
}

MARCO_LEGAL = [
    ("Constitución Política del Perú (1993), art. 2, inc. 22",
     "Reconoce el derecho fundamental a gozar de un ambiente equilibrado y adecuado al desarrollo de la vida."),
    ("Ley N.° 28611, Ley General del Ambiente (arts. 31 y 33)",
     "Define el Estándar de Calidad Ambiental (ECA) como la medida de la concentración de elementos o "
     "parámetros en el ambiente que no representa riesgo significativo para la salud ni el ambiente, "
     "y lo establece como referente obligatorio."),
    ("Ley N.° 29338, Ley de Recursos Hídricos, y su Reglamento (D.S. N.° 001-2010-AG)",
     "Regulan el uso y la gestión de los recursos hídricos y asignan a la Autoridad Nacional del Agua (ANA) "
     "la vigilancia y el monitoreo de su calidad."),
    ("D.S. N.° 004-2017-MINAM, Estándares de Calidad Ambiental (ECA) para Agua",
     "Aprueba los ECA para Agua y sus categorías; norma de comparación de los resultados de este informe."),
    ("R.J. N.° 010-2016-ANA, Protocolo Nacional para el Monitoreo de la Calidad de los Recursos Hídricos "
     "Superficiales",
     "Establece los procedimientos de ubicación de puntos, toma, preservación, conservación y transporte de "
     "muestras, y el registro de datos de campo."),
    ("R.J. N.° 056-2018-ANA, Clasificación de los cuerpos de agua continentales superficiales",
     "Asigna la categoría ECA a los cuerpos de agua; cuando un cuerpo no está clasificado se aplica la "
     "categoría del recurso hídrico al que tributa."),
]


def limite_texto(lim, t_ref: float | None = None) -> str:
    if lim is None:
        return "No regulado"
    lo, hi = lim
    if lo == "delta":
        if t_ref is None:
            return f"Δ{hi} °C"
        return f"{t_ref - hi:.1f} – {t_ref + hi:.1f} (Δ{hi})".replace(".", ",")
    f = lambda v: (f"{v:g}").replace(".", ",")
    if lo is not None and hi is not None:
        return f"{f(lo)} – {f(hi)}"
    if hi is not None:
        return f"≤ {f(hi)}"
    return f"≥ {f(lo)}"


def rango_efectivo(lim, t_ref: float | None = None):
    """Devuelve (mín, máx) numéricos o None si no se puede evaluar."""
    if lim is None:
        return None
    lo, hi = lim
    if lo == "delta":
        if t_ref is None:
            return None
        return (t_ref - hi, t_ref + hi)
    return (lo, hi)


def cumple(valor, lim, t_ref: float | None = None):
    """True / False / None (sin dato o sin ECA)."""
    r = rango_efectivo(lim, t_ref)
    if r is None or valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    lo, hi = r
    if lo is not None and valor < lo:
        return False
    if hi is not None and valor > hi:
        return False
    return True
