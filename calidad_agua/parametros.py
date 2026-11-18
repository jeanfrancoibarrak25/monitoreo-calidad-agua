"""Definición de los parámetros fisicoquímicos que registra el sistema."""

PARAMETROS = {
    "ph": {"nombre": "pH", "unidad": "unid. pH", "decimales": 2},
    "conductividad": {"nombre": "Conductividad eléctrica", "unidad": "µS/cm", "decimales": 1},
    "temperatura": {"nombre": "Temperatura", "unidad": "°C", "decimales": 1},
    "sst": {"nombre": "Sólidos suspendidos totales (SST)", "unidad": "mg/L", "decimales": 1},
    "sdt": {"nombre": "Sólidos disueltos totales (SDT)", "unidad": "mg/L", "decimales": 1},
    "st": {"nombre": "Sólidos totales (ST)", "unidad": "mg/L", "decimales": 1},
    "sulfito": {"nombre": "Sulfito (SO₃²⁻)", "unidad": "mg/L", "decimales": 2},
}

CORTO = {
    "ph": "pH", "conductividad": "CE", "temperatura": "T", "sst": "SST",
    "sdt": "SDT", "st": "ST", "sulfito": "SO₃²⁻",
}


def etiqueta(clave: str) -> str:
    p = PARAMETROS.get(clave)
    return f"{p['nombre']} ({p['unidad']})" if p else clave


def formato(clave: str, valor) -> str:
    if valor is None or valor != valor:  # NaN
        return "—"
    dec = PARAMETROS.get(clave, {}).get("decimales", 2)
    return f"{valor:,.{dec}f}".replace(",", " ").replace(".", ",")
