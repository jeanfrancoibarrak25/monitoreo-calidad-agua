import numpy as np
import pandas as pd
import pytest

from calidad_agua import estadistica as est
from calidad_agua.db import BaseDatos
from calidad_agua.informe import conclusiones_auto, generar_informe
from calidad_agua.normativa import ECA, cumple, rango_efectivo

CAT = "Cat. 3-D1 · Riego de vegetales"


@pytest.fixture
def df():
    db = BaseDatos(":memory:")
    n, err = db.importar(pd.read_csv("datos_ejemplo.csv"))
    assert n == 9 and not err
    return db.todas()


def test_descriptiva_basica():
    d = est.descriptiva(pd.Series([1, 2, 3, 4, 5]))
    assert d["n"] == 5 and d["media"] == 3 and d["mediana"] == 3
    assert d["ic95_inf"] < 3 < d["ic95_sup"]


def test_codigo_unico():
    db = BaseDatos(":memory:")
    db.agregar(codigo="M1", punto="P1", fecha="2026-01-01", ph=7)
    with pytest.raises(ValueError):
        db.agregar(codigo="M1", punto="P1", fecha="2026-01-02", ph=7)


def test_fecha_dia_mes():
    db = BaseDatos(":memory:")
    db.agregar(codigo="M1", punto="P1", fecha="05/03/2026", ph=7)
    assert str(db.todas()["fecha"][0]) == "2026-03-05"


def test_cumple_rangos_y_delta():
    assert cumple(7.0, (6.5, 8.5)) is True
    assert cumple(9.0, (6.5, 8.5)) is False
    assert cumple(20.0, ("delta", 3), t_ref=18) is True
    assert cumple(22.0, ("delta", 3), t_ref=18) is False
    assert cumple(22.0, ("delta", 3)) is None
    assert cumple(5.0, None) is None


def test_evaluar_eca():
    ev = est.evaluar_eca(pd.Series([3000, 3100, 2900, 3050, 3200]), (None, 2500))
    assert ev["veredicto"] == "incumple" and ev["n_incumple"] == 5
    ev = est.evaluar_eca(pd.Series([7.2, 7.3, 7.1, 7.4, 7.25]), (6.5, 8.5))
    assert ev["veredicto"] == "cumple"


def test_comparacion_puntos(df):
    r = est.comparar_grupos(df, "conductividad", "punto")
    assert r["significativo"]


def test_informe(df):
    concl = conclusiones_auto(df, CAT, 18.0)
    assert any("Conductividad" in c for c in concl)
    buf = generar_informe(df, {"categoria": CAT, "t_ref": 18.0, "encargado": "Ing. X"}, concl, grupo="punto")
    assert buf.getbuffer().nbytes > 50_000
