"""Almacenamiento de muestras en SQLite (una fila por muestra)."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

from .parametros import PARAMETROS

CAMPOS_META = ["codigo", "punto", "fecha", "hora", "utm_este", "utm_norte", "zona_utm",
               "altitud", "reactivos", "observaciones"]
COLUMNAS = ["id"] + CAMPOS_META + list(PARAMETROS)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS muestras (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo        TEXT NOT NULL UNIQUE,
    punto         TEXT NOT NULL,
    fecha         TEXT NOT NULL,
    hora          TEXT,
    utm_este      REAL,
    utm_norte     REAL,
    zona_utm      TEXT,
    altitud       REAL,
    reactivos     TEXT,
    observaciones TEXT,
    ph            REAL CHECK (ph IS NULL OR (ph >= 0 AND ph <= 14)),
    conductividad REAL CHECK (conductividad IS NULL OR conductividad >= 0),
    temperatura   REAL,
    sst           REAL CHECK (sst IS NULL OR sst >= 0),
    sdt           REAL CHECK (sdt IS NULL OR sdt >= 0),
    st            REAL CHECK (st IS NULL OR st >= 0),
    sulfito       REAL CHECK (sulfito IS NULL OR sulfito >= 0)
);
"""


def _num(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, str):
        v = v.strip().replace(",", ".")
        if v in {"", "-", "—"} or v.startswith("<"):
            return None
    return float(v)


def _txt(v) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v).strip()


class BaseDatos:
    def __init__(self, ruta: str | Path = "data/calidad_agua.db"):
        if str(ruta) != ":memory:":
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(ruta), check_same_thread=False)
        self.con.execute(ESQUEMA)
        self.con.commit()

    # ------------------------------------------------------------------ #
    def agregar(self, **datos) -> int:
        fila = {c: None for c in COLUMNAS if c != "id"}
        for c in CAMPOS_META:
            if c in ("utm_este", "utm_norte", "altitud"):
                fila[c] = _num(datos.get(c))
            else:
                fila[c] = _txt(datos.get(c))
        for p in PARAMETROS:
            fila[p] = _num(datos.get(p))
        if not fila["codigo"]:
            raise ValueError("El código de muestra es obligatorio.")
        if not fila["punto"]:
            raise ValueError("El punto de monitoreo es obligatorio.")
        if not fila["fecha"]:
            raise ValueError("La fecha es obligatoria.")
        f = str(fila["fecha"]).strip()
        iso = re.match(r"^\d{4}-\d{2}-\d{2}", f) is not None
        fila["fecha"] = str(pd.to_datetime(f[:10] if iso else f, dayfirst=not iso).date())
        cols = ", ".join(fila)
        marcas = ", ".join("?" * len(fila))
        try:
            cur = self.con.execute(f"INSERT INTO muestras ({cols}) VALUES ({marcas})", tuple(fila.values()))
        except sqlite3.IntegrityError as e:
            if "UNIQUE" in str(e):
                raise ValueError(f"Ya existe una muestra con el código «{fila['codigo']}».") from e
            raise ValueError(f"Dato fuera de rango: {e}") from e
        self.con.commit()
        return cur.lastrowid

    def actualizar(self, df: pd.DataFrame) -> None:
        """Reemplaza el contenido por el DataFrame editado (mismas columnas)."""
        self.con.execute("DELETE FROM muestras")
        self.con.commit()
        for _, r in df.iterrows():
            d = r.to_dict()
            d.pop("id", None)
            self.agregar(**d)

    def eliminar(self, ids) -> None:
        self.con.executemany("DELETE FROM muestras WHERE id = ?", [(int(i),) for i in ids])
        self.con.commit()

    def vaciar(self) -> None:
        self.con.execute("DELETE FROM muestras")
        self.con.commit()

    def todas(self) -> pd.DataFrame:
        df = pd.read_sql_query("SELECT * FROM muestras ORDER BY fecha, hora, codigo", self.con)
        if not df.empty:
            df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
        return df

    def importar(self, df: pd.DataFrame) -> tuple[int, list[str]]:
        """Importa filas; devuelve (n_importadas, errores)."""
        df = df.rename(columns=lambda c: str(c).strip().lower())
        faltan = {"codigo", "punto", "fecha"} - set(df.columns)
        if faltan:
            raise ValueError(f"Faltan columnas obligatorias: {', '.join(sorted(faltan))}")
        n, errores = 0, []
        for i, r in df.iterrows():
            try:
                self.agregar(**r.to_dict())
                n += 1
            except ValueError as e:
                errores.append(f"Fila {i + 2}: {e}")
        return n, errores
