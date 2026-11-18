"""Estadística descriptiva e inferencial para parámetros de calidad de agua."""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

ALFA = 0.05


# --------------------------------------------------------------------------- #
# Descriptiva
# --------------------------------------------------------------------------- #
def descriptiva(serie: pd.Series) -> dict:
    x = pd.to_numeric(serie, errors="coerce").dropna().to_numpy(dtype=float)
    n = len(x)
    if n == 0:
        return {"n": 0}
    media = x.mean()
    de = x.std(ddof=1) if n > 1 else np.nan
    q1, q3 = np.percentile(x, [25, 75])
    if n > 1:
        ic = stats.t.interval(1 - ALFA, n - 1, loc=media, scale=de / np.sqrt(n))
    else:
        ic = (np.nan, np.nan)
    return {
        "n": n,
        "media": media,
        "mediana": float(np.median(x)),
        "desv_est": de,
        "error_est": de / np.sqrt(n) if n > 1 else np.nan,
        "cv_%": de / media * 100 if n > 1 and media != 0 else np.nan,
        "minimo": x.min(),
        "q1": q1,
        "q3": q3,
        "maximo": x.max(),
        "rango": x.max() - x.min(),
        "asimetria": stats.skew(x, bias=False) if n > 2 else np.nan,
        "curtosis": stats.kurtosis(x, bias=False) if n > 3 else np.nan,
        "ic95_inf": ic[0],
        "ic95_sup": ic[1],
    }


def tabla_descriptiva(df: pd.DataFrame, parametros: list[str], grupo: str | None = None) -> pd.DataFrame:
    filas = []
    if grupo:
        for g, sub in df.groupby(grupo):
            for p in parametros:
                filas.append({"parametro": p, grupo: g, **descriptiva(sub[p])})
    else:
        for p in parametros:
            filas.append({"parametro": p, **descriptiva(df[p])})
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------- #
# Supuestos
# --------------------------------------------------------------------------- #
def normalidad(x) -> dict:
    """Shapiro-Wilk (3 <= n <= 5000)."""
    x = np.asarray(pd.Series(x).dropna(), dtype=float)
    if len(x) < 3 or np.ptp(x) == 0:
        return {"prueba": "Shapiro-Wilk", "estadistico": np.nan, "p": np.nan, "normal": None}
    w, p = stats.shapiro(x)
    return {"prueba": "Shapiro-Wilk", "estadistico": w, "p": p, "normal": bool(p > ALFA)}


def homocedasticidad(grupos: list[np.ndarray]) -> dict:
    """Levene centrado en la mediana (Brown-Forsythe)."""
    if len(grupos) < 2 or any(len(g) < 2 for g in grupos):
        return {"prueba": "Levene", "estadistico": np.nan, "p": np.nan, "homogenea": None}
    s, p = stats.levene(*grupos, center="median")
    return {"prueba": "Levene (Brown-Forsythe)", "estadistico": s, "p": p, "homogenea": bool(p > ALFA)}


# --------------------------------------------------------------------------- #
# Comparación entre grupos (puntos de muestreo, campañas, etc.)
# --------------------------------------------------------------------------- #
def _holm(pvals: list[float]) -> list[float]:
    m = len(pvals)
    orden = np.argsort(pvals)
    ajust = np.empty(m)
    acum = 0.0
    for rango, i in enumerate(orden):
        acum = max(acum, (m - rango) * pvals[i])
        ajust[i] = min(acum, 1.0)
    return ajust.tolist()


def welch_anova(grupos: list[np.ndarray]) -> tuple[float, float, float, float]:
    k = len(grupos)
    n = np.array([len(g) for g in grupos], dtype=float)
    m = np.array([g.mean() for g in grupos])
    v = np.array([g.var(ddof=1) for g in grupos])
    w = n / v
    mw = (w * m).sum() / w.sum()
    a = (w * (m - mw) ** 2).sum() / (k - 1)
    tmp = (((1 - w / w.sum()) ** 2) / (n - 1)).sum()
    b = 1 + 2 * (k - 2) / (k**2 - 1) * tmp
    f = a / b
    df1, df2 = k - 1, (k**2 - 1) / (3 * tmp)
    return f, df1, df2, stats.f.sf(f, df1, df2)


def eta_cuadrado(grupos: list[np.ndarray]) -> float:
    todos = np.concatenate(grupos)
    sst = ((todos - todos.mean()) ** 2).sum()
    ssb = sum(len(g) * (g.mean() - todos.mean()) ** 2 for g in grupos)
    return ssb / sst if sst > 0 else np.nan


def comparar_grupos(df: pd.DataFrame, parametro: str, grupo: str, forzar: str = "auto") -> dict:
    """Elige y aplica la prueba adecuada para comparar un parámetro entre grupos.

    forzar: 'auto' | 'parametrica' | 'no_parametrica'
    """
    datos = {g: pd.to_numeric(s[parametro], errors="coerce").dropna().to_numpy(dtype=float)
             for g, s in df.groupby(grupo)}
    datos = {g: x for g, x in datos.items() if len(x) >= 2}
    nombres = list(datos)
    grupos = list(datos.values())
    k = len(grupos)
    res = {"parametro": parametro, "k_grupos": k, "grupos": nombres}
    if k < 2:
        res["error"] = "Se necesitan al menos 2 grupos con 2 o más observaciones."
        return res

    norm = {g: normalidad(x) for g, x in datos.items()}
    lev = homocedasticidad(grupos)
    todos_normales = all(v["normal"] is not False for v in norm.values())
    homog = lev["homogenea"] is not False
    res["normalidad"] = norm
    res["levene"] = lev

    parametrica = todos_normales if forzar == "auto" else forzar == "parametrica"
    res["enfoque"] = "paramétrico" if parametrica else "no paramétrico"

    if k == 2:
        a, b = grupos
        if parametrica:
            t, p = stats.ttest_ind(a, b, equal_var=homog)
            res["prueba"] = "t de Student" if homog else "t de Welch"
            res["estadistico"] = t
            sp = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
            res["tamano_efecto"] = ("d de Cohen", (a.mean() - b.mean()) / sp if sp > 0 else np.nan)
        else:
            u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
            res["prueba"] = "U de Mann-Whitney"
            res["estadistico"] = u
            res["tamano_efecto"] = ("r biserial", 1 - 2 * u / (len(a) * len(b)))
        res["p"] = p
    else:
        if parametrica and homog:
            f, p = stats.f_oneway(*grupos)
            res["prueba"] = "ANOVA de un factor"
            res["estadistico"] = f
            res["tamano_efecto"] = ("η²", eta_cuadrado(grupos))
            res["p"] = p
            if p <= ALFA:
                tk = stats.tukey_hsd(*grupos)
                res["post_hoc_nombre"] = "Tukey HSD"
                res["post_hoc"] = pd.DataFrame(
                    [{"grupo_a": nombres[i], "grupo_b": nombres[j],
                      "diferencia": grupos[i].mean() - grupos[j].mean(),
                      "p_ajustado": tk.pvalue[i, j]}
                     for i, j in combinations(range(k), 2)]
                )
        elif parametrica:
            f, d1, d2, p = welch_anova(grupos)
            res["prueba"] = "ANOVA de Welch"
            res["estadistico"] = f
            res["tamano_efecto"] = ("η²", eta_cuadrado(grupos))
            res["p"] = p
            if p <= ALFA:
                res.update(_post_hoc_pares(datos, parametrico=True))
        else:
            h, p = stats.kruskal(*grupos)
            n = sum(len(g) for g in grupos)
            res["prueba"] = "H de Kruskal-Wallis"
            res["estadistico"] = h
            res["tamano_efecto"] = ("ε²", (h - k + 1) / (n - k))
            res["p"] = p
            if p <= ALFA:
                res.update(_post_hoc_pares(datos, parametrico=False))
    res["significativo"] = bool(res["p"] <= ALFA)
    return res


def _post_hoc_pares(datos: dict, parametrico: bool) -> dict:
    filas = []
    for (ga, a), (gb, b) in combinations(datos.items(), 2):
        if parametrico:
            _, p = stats.ttest_ind(a, b, equal_var=False)
        else:
            _, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        filas.append({"grupo_a": ga, "grupo_b": gb,
                      "diferencia": (a.mean() - b.mean()) if parametrico else (np.median(a) - np.median(b)),
                      "p": p})
    tabla = pd.DataFrame(filas)
    tabla["p_ajustado"] = _holm(tabla["p"].tolist())
    nombre = "t de Welch por pares (Holm)" if parametrico else "Mann-Whitney por pares (Holm)"
    return {"post_hoc_nombre": nombre, "post_hoc": tabla}


# --------------------------------------------------------------------------- #
# Comparación con un valor normativo (ECA / LMP)
# --------------------------------------------------------------------------- #
def comparar_con_limite(x, limite: float, tipo: str = "maximo") -> dict:
    """Prueba unilateral: ¿la media/mediana supera (máximo) o está por debajo (mínimo) del límite?"""
    x = np.asarray(pd.Series(x).dropna(), dtype=float)
    if len(x) < 3:
        return {"error": "Se necesitan al menos 3 observaciones."}
    alt = "greater" if tipo == "maximo" else "less"
    norm = normalidad(x)
    if norm["normal"] is not False:
        t, p = stats.ttest_1samp(x, limite, alternative=alt)
        prueba, est = "t para una muestra", t
    else:
        dif = x - limite
        if np.all(dif == 0):
            return {"error": "Todos los valores son iguales al límite."}
        w, p = stats.wilcoxon(dif, alternative=alt)
        prueba, est = "Rangos con signo de Wilcoxon", w
    fuera = (x > limite) if tipo == "maximo" else (x < limite)
    return {
        "prueba": prueba, "estadistico": est, "p": p, "limite": limite, "tipo": tipo,
        "n": len(x), "n_incumple": int(fuera.sum()), "pct_incumple": fuera.mean() * 100,
        "incumple_significativo": bool(p <= ALFA),
    }


# --------------------------------------------------------------------------- #
# Correlación entre parámetros
# --------------------------------------------------------------------------- #
def correlaciones(df: pd.DataFrame, parametros: list[str], metodo: str = "spearman") -> pd.DataFrame:
    filas = []
    for a, b in combinations(parametros, 2):
        sub = df[[a, b]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(sub) < 3 or sub[a].nunique() < 2 or sub[b].nunique() < 2:
            continue
        if metodo == "pearson":
            r, p = stats.pearsonr(sub[a], sub[b])
        else:
            r, p = stats.spearmanr(sub[a], sub[b])
        filas.append({"variable_a": a, "variable_b": b, "n": len(sub), "coeficiente": r, "p": p,
                      "fuerza": interpretar_r(r), "significativo": p <= ALFA})
    return pd.DataFrame(filas)


def interpretar_r(r: float) -> str:
    a = abs(r)
    if a < 0.1:
        return "nula"
    if a < 0.3:
        return "débil"
    if a < 0.5:
        return "moderada"
    if a < 0.7:
        return "fuerte"
    return "muy fuerte"


def interpretar(res: dict, nombre: str) -> str:
    """Redacción breve del resultado para informes."""
    if "error" in res:
        return res["error"]
    sig = res["significativo"]
    txt = (f"Para {nombre}, la prueba {res['prueba']} (enfoque {res['enfoque']}) dio "
           f"estadístico = {_n(res['estadistico'], 3)}, p = {fmt_p(res['p'])}. ")
    txt += ("Existen diferencias estadísticamente significativas entre los grupos (p ≤ 0,05)."
            if sig else "No se encontraron diferencias estadísticamente significativas entre los grupos (p > 0,05).")
    if "post_hoc" in res:
        pares = res["post_hoc"]
        sig_p = pares[pares["p_ajustado"] <= ALFA]
        if not sig_p.empty:
            txt += " Según " + res["post_hoc_nombre"] + ", difieren: " + "; ".join(
                f"{r.grupo_a} vs {r.grupo_b}" for r in sig_p.itertuples()) + "."
    return txt


# --------------------------------------------------------------------------- #
# Comparación con el ECA (rangos y Δ de temperatura)
# --------------------------------------------------------------------------- #
def _prueba_una_muestra(x: np.ndarray, valor: float, alt: str) -> tuple[str, float, float]:
    norm = normalidad(x)
    if norm["normal"] is not False:
        t, p = stats.ttest_1samp(x, valor, alternative=alt)
        return "t de Student para una muestra", float(t), float(p)
    dif = x - valor
    if np.all(dif == 0):
        return "Rangos con signo de Wilcoxon", np.nan, 1.0
    w, p = stats.wilcoxon(dif, alternative=alt)
    return "Rangos con signo de Wilcoxon", float(w), float(p)


def evaluar_eca(x, rango) -> dict:
    """Contrasta la tendencia central frente a los límites del ECA.

    rango: (mín, máx) numéricos (alguno puede ser None).
    Para cada límite se calcula:
      - p_excede: H1 la media supera el límite (máx) o queda por debajo (mín) → incumplimiento.
      - p_cumple: H1 la media está del lado permitido → cumplimiento con significancia.
    """
    x = np.asarray(pd.Series(x).dropna(), dtype=float)
    lo, hi = rango
    res = {"n": len(x), "limites": []}
    if len(x) == 0:
        res["error"] = "Sin datos."
        return res
    fuera = np.zeros(len(x), dtype=bool)
    if lo is not None:
        fuera |= x < lo
    if hi is not None:
        fuera |= x > hi
    res["n_incumple"] = int(fuera.sum())
    res["pct_incumple"] = float(fuera.mean() * 100)
    res["normalidad"] = normalidad(x)
    if len(x) < 3:
        res["error"] = "Se necesitan al menos 3 muestras para la prueba inferencial."
        return res
    for tipo, lim in (("mínimo", lo), ("máximo", hi)):
        if lim is None:
            continue
        alt_exc, alt_ok = ("less", "greater") if tipo == "mínimo" else ("greater", "less")
        prueba, est_e, p_exc = _prueba_una_muestra(x, lim, alt_exc)
        _, est_c, p_ok = _prueba_una_muestra(x, lim, alt_ok)
        res["limites"].append({"tipo": tipo, "limite": lim, "prueba": prueba,
                               "estadistico": est_e, "p_excede": p_exc, "p_cumple": p_ok})
    res["prueba"] = res["limites"][0]["prueba"] if res["limites"] else None
    excede = any(l["p_excede"] <= ALFA for l in res["limites"])
    cumple_sig = all(l["p_cumple"] <= ALFA for l in res["limites"]) if res["limites"] else False
    res["veredicto"] = ("incumple" if excede else "cumple" if cumple_sig else "no concluyente")
    return res


# --------------------------------------------------------------------------- #
# Comparación entre muestras individuales
# --------------------------------------------------------------------------- #
def atipicos_iqr(serie: pd.Series) -> pd.Series:
    """Marca valores fuera de [Q1 − 1,5·RIC ; Q3 + 1,5·RIC]."""
    x = pd.to_numeric(serie, errors="coerce")
    q1, q3 = x.quantile([0.25, 0.75])
    ric = q3 - q1
    return (x < q1 - 1.5 * ric) | (x > q3 + 1.5 * ric)


def puntaje_z(serie: pd.Series) -> pd.Series:
    x = pd.to_numeric(serie, errors="coerce")
    de = x.std(ddof=1)
    return (x - x.mean()) / de if de and de > 0 else x * np.nan


def balance_solidos(df: pd.DataFrame) -> pd.DataFrame:
    """Control de calidad analítico: ST ≈ SST + SDT y relación SDT/CE (≈ 0,55–0,75)."""
    out = df[["codigo"]].copy()
    suma = df["sst"] + df["sdt"]
    out["ST medido"] = df["st"]
    out["SST + SDT"] = suma
    out["Diferencia %"] = (df["st"] - suma) / df["st"] * 100
    out["SDT/CE"] = df["sdt"] / df["conductividad"]
    return out


# --------------------------------------------------------------------------- #
# Interpretaciones para el informe
# --------------------------------------------------------------------------- #
def _n(v, d=2):
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


def interpretar_cv(cv: float) -> str:
    if cv != cv:
        return "no calculable"
    if cv < 15:
        return "baja (datos homogéneos)"
    if cv < 30:
        return "moderada"
    return "alta (datos heterogéneos)"


def interpretar_parametro(df: pd.DataFrame, clave: str, nombre: str, unidad: str,
                          lim_txt: str, rango, decimales: int = 2) -> str:
    sub = df[["codigo", clave]].dropna()
    if sub.empty:
        return f"No se registraron datos de {nombre}."
    d = descriptiva(sub[clave])
    i_max = sub[clave].idxmax()
    i_min = sub[clave].idxmin()
    txt = (f"{nombre}: se analizaron {d['n']} muestras; la media fue {_n(d['media'], decimales)} {unidad} "
           f"(mediana {_n(d['mediana'], decimales)}; DE {_n(d['desv_est'], decimales) if d['n'] > 1 else '—'}), "
           f"con un mínimo de {_n(d['minimo'], decimales)} en {sub.loc[i_min, 'codigo']} y un máximo de "
           f"{_n(d['maximo'], decimales)} en {sub.loc[i_max, 'codigo']}. ")
    if d["n"] > 1:
        txt += f"El coeficiente de variación ({_n(d['cv_%'], 1)} %) indica una variabilidad {interpretar_cv(d['cv_%'])}. "
    at = sub.loc[atipicos_iqr(sub[clave]), "codigo"].tolist() if d["n"] >= 4 else []
    if at:
        txt += f"Se identificaron valores atípicos (criterio RIC) en: {', '.join(at)}. "
    if rango is None:
        txt += (f"El ECA-Agua no establece un valor para este parámetro en la categoría evaluada "
                f"({lim_txt}); los resultados se reportan de manera referencial.")
        return txt
    lo, hi = rango
    fuera = sub[((sub[clave] < lo) if lo is not None else False) | ((sub[clave] > hi) if hi is not None else False)]
    if fuera.empty:
        txt += f"Todas las muestras se encuentran dentro del ECA ({lim_txt}). "
    else:
        txt += (f"{len(fuera)} de {d['n']} muestras ({_n(len(fuera) / d['n'] * 100, 1)} %) no cumplen el ECA "
                f"({lim_txt}): {', '.join(fuera['codigo'])}. ")
    ev = evaluar_eca(sub[clave], rango)
    if "error" in ev:
        txt += ev["error"]
        return txt
    det = "; ".join(f"límite {l['tipo']} {_n(l['limite'], decimales)}: p(excede) = {fmt_p(l['p_excede'])}, "
                    f"p(cumple) = {fmt_p(l['p_cumple'])}" for l in ev["limites"])
    txt += f"Según la prueba {ev['prueba']} (α = 0,05; {det}), "
    txt += {
        "incumple": "la tendencia central del parámetro supera de forma estadísticamente significativa el ECA.",
        "cumple": "la tendencia central del parámetro se mantiene dentro del ECA con significancia estadística.",
        "no concluyente": ("no hay evidencia estadística suficiente para afirmar que la tendencia central "
                           "cumpla o incumpla el ECA; se recomienda ampliar el número de muestras."),
    }[ev["veredicto"]]
    return txt


def fmt_p(p: float) -> str:
    if p != p:
        return "—"
    return "< 0,001" if p < 0.001 else f"{p:.3f}".replace(".", ",")
