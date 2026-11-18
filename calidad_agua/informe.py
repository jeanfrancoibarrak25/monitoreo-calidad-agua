"""Generación del informe técnico en Word (.docx)."""
from __future__ import annotations

import io
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import estadistica as est
from .normativa import ECA, MARCO_LEGAL, cumple, limite_texto, rango_efectivo
from .parametros import CORTO, PARAMETROS, formato

AZUL = RGBColor(0x1F, 0x3A, 0x5F)


# --------------------------------------------------------------------------- #
# Utilidades de formato
# --------------------------------------------------------------------------- #
def _sombrear(celda, color_hex: str):
    tcPr = celda._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    tcPr.append(shd)


def _tabla(doc, encabezados, filas, anchos=None, tam=8, colores=None):
    t = doc.add_table(rows=1, cols=len(encabezados))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(encabezados):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(str(h))
        r.bold = True
        r.font.size = Pt(tam)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        _sombrear(c, "1F3A5F")
    for fi, fila in enumerate(filas):
        celdas = t.add_row().cells
        for i, v in enumerate(fila):
            celdas[i].text = ""
            r = celdas[i].paragraphs[0].add_run("" if v is None else str(v))
            r.font.size = Pt(tam)
            celdas[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER if i else WD_ALIGN_PARAGRAPH.LEFT
            if colores and colores.get((fi, i)):
                _sombrear(celdas[i], colores[(fi, i)])
    if anchos:
        for fila in t.rows:
            for i, w in enumerate(anchos):
                fila.cells[i].width = Cm(w)
    return t


def _titulo(doc, texto, nivel=1):
    h = doc.add_heading(texto, level=nivel)
    for r in h.runs:
        r.font.color.rgb = AZUL
    return h


def _parrafo(doc, texto, negrita=False, tam=11, alin=WD_ALIGN_PARAGRAPH.JUSTIFY, cursiva=False):
    p = doc.add_paragraph()
    r = p.add_run(texto)
    r.bold = negrita
    r.italic = cursiva
    r.font.size = Pt(tam)
    p.alignment = alin
    return p


def _nota(doc, texto):
    _parrafo(doc, texto, tam=8, cursiva=True, alin=WD_ALIGN_PARAGRAPH.LEFT)


def _fmt(v, d=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


# --------------------------------------------------------------------------- #
# Gráficos
# --------------------------------------------------------------------------- #
def grafico_parametro(df, clave, rango, lim_txt) -> io.BytesIO | None:
    sub = df[["codigo", clave]].dropna()
    if sub.empty:
        return None
    fig, ax = plt.subplots(figsize=(6.4, 2.9), dpi=150)
    colores = []
    for v in sub[clave]:
        ok = None if rango is None else not ((rango[0] is not None and v < rango[0]) or
                                              (rango[1] is not None and v > rango[1]))
        colores.append("#2E86AB" if ok in (None, True) else "#C0392B")
    ax.bar(sub["codigo"], sub[clave], color=colores, edgecolor="#1F3A5F", linewidth=0.5)
    if rango is not None:
        for v, et in ((rango[0], "ECA mín."), (rango[1], "ECA máx.")):
            if v is not None:
                ax.axhline(v, color="#C0392B", ls="--", lw=1.2)
                ax.text(1.0, v, f" {et} {_fmt(v, 2)}", transform=ax.get_yaxis_transform(),
                        va="center", ha="left", fontsize=7, color="#C0392B")
    media = sub[clave].mean()
    ax.axhline(media, color="#555", ls=":", lw=1)
    ax.text(0.0, media, f"media {_fmt(media, 2)} ", transform=ax.get_yaxis_transform(),
            va="bottom", ha="left", fontsize=7, color="#555")
    p = PARAMETROS[clave]
    ax.set_ylabel(p["unidad"], fontsize=8)
    ax.set_title(f"{p['nombre']} por muestra — ECA: {lim_txt}", fontsize=9)
    ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    ax.tick_params(axis="y", labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    if rango is not None:
        vals = [v for v in rango if v is not None] + sub[clave].tolist()
        ax.set_ylim(min(0, min(vals)) if clave != "ph" else min(vals) - 0.5, max(vals) * 1.12)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


# --------------------------------------------------------------------------- #
# Conclusiones automáticas
# --------------------------------------------------------------------------- #
def conclusiones_auto(df: pd.DataFrame, categoria: str, t_ref: float | None) -> list[str]:
    norma = ECA[categoria]
    out = []
    cumplen, incumplen, sin_eca, sin_eval = [], [], [], []
    for clave, p in PARAMETROS.items():
        sub = df[["codigo", clave]].dropna()
        if sub.empty:
            continue
        lim = norma.get(clave)
        rango = rango_efectivo(lim, t_ref)
        if lim is None:
            sin_eca.append(p["nombre"])
            continue
        if rango is None:
            sin_eval.append(p["nombre"])
            continue
        mal = [r.codigo for r in sub.itertuples() if cumple(getattr(r, clave), lim, t_ref) is False]
        (incumplen if mal else cumplen).append((p["nombre"], mal, len(sub)))
    if cumplen:
        out.append("Los parámetros " + ", ".join(n for n, _, _ in cumplen) +
                   f" cumplen el ECA para Agua ({categoria}) en la totalidad de las muestras evaluadas.")
    for n, mal, tot in incumplen:
        out.append(f"{n} no cumple el ECA en {len(mal)} de {tot} muestras ({', '.join(mal)}), por lo que "
                   "se recomienda identificar las fuentes de aporte en esos puntos y reforzar su seguimiento.")
    if sin_eca:
        out.append("El ECA-Agua (D.S. N.° 004-2017-MINAM) no fija valores para " + ", ".join(sin_eca) +
                   " en la categoría evaluada; estos resultados se presentan como línea de base referencial.")
    if sin_eval:
        out.append("La temperatura no pudo contrastarse con el ECA (Δ °C) porque no se ingresó el promedio "
                   "mensual multianual de referencia del área evaluada.")
    # Inferencial global
    sig = []
    for clave, p in PARAMETROS.items():
        rango = rango_efectivo(norma.get(clave), t_ref)
        if rango is None or df[clave].dropna().shape[0] < 3:
            continue
        ev = est.evaluar_eca(df[clave], rango)
        if ev.get("veredicto") == "incumple":
            sig.append(p["nombre"])
    if sig:
        out.append("A nivel inferencial (α = 0,05), la tendencia central de " + ", ".join(sig) +
                   " supera significativamente el ECA, lo que evidencia un problema sistemático y no puntual.")
    # Correlaciones
    cor = est.correlaciones(df, list(PARAMETROS), "spearman")
    if not cor.empty:
        fuertes = cor[(cor["significativo"]) & (cor["coeficiente"].abs() >= 0.7)].copy()
        if not fuertes.empty:
            fuertes = fuertes.reindex(fuertes["coeficiente"].abs().sort_values(ascending=False).index)
            top = fuertes.head(4)
            txt = "; ".join(f"{CORTO[r.variable_a]}–{CORTO[r.variable_b]} (ρ = {_fmt(r.coeficiente, 2)})"
                            for r in top.itertuples())
            extra = f" y {len(fuertes) - 4} pares más" if len(fuertes) > 4 else ""
            out.append(f"Se hallaron {len(fuertes)} correlaciones muy fuertes y significativas (|ρ| ≥ 0,70), "
                       f"destacando {txt}{extra}; esto indica que los parámetros varían de forma conjunta "
                       "entre muestras, lo que sugiere fuentes de aporte comunes.")
    return out


# --------------------------------------------------------------------------- #
# Informe
# --------------------------------------------------------------------------- #
def generar_informe(df: pd.DataFrame, meta: dict, conclusiones: list[str],
                    recomendaciones: list[str] | None = None, grupo: str | None = None) -> io.BytesIO:
    categoria = meta["categoria"]
    t_ref = meta.get("t_ref")
    norma = ECA[categoria]
    df = df.copy().reset_index(drop=True)
    claves = [c for c in PARAMETROS if df[c].notna().any()]

    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    for m in ("left_margin", "right_margin"):
        setattr(sec, m, Cm(2.0))
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    estilo = doc.styles["Normal"]
    estilo.font.name = "Arial"
    estilo.font.size = Pt(11)
    estilo.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")

    pie = sec.footer.paragraphs[0]
    pie.text = f"{meta.get('institucion') or ''} — Informe de monitoreo de calidad de agua"
    pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pie.runs[0].font.size = Pt(8)

    # ---------------- Portada / encabezado ----------------
    if meta.get("institucion"):
        _parrafo(doc, meta["institucion"].upper(), negrita=True, tam=12, alin=WD_ALIGN_PARAGRAPH.CENTER)
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("INFORME TÉCNICO DE MONITOREO DE CALIDAD DE AGUA")
    r.bold = True
    r.font.size = Pt(16)
    r.font.color.rgb = AZUL
    if meta.get("numero"):
        _parrafo(doc, meta["numero"], negrita=True, alin=WD_ALIGN_PARAGRAPH.CENTER)
    if meta.get("proyecto"):
        _parrafo(doc, meta["proyecto"], tam=12, alin=WD_ALIGN_PARAGRAPH.CENTER)

    # ---------------- 1. Datos generales ----------------
    _titulo(doc, "1. Datos generales")
    f_ini, f_fin = min(df["fecha"]), max(df["fecha"])
    periodo = f_ini.strftime("%d/%m/%Y") if f_ini == f_fin else \
        f"{f_ini.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')}"
    gen = [
        ("Proyecto / estudio", meta.get("proyecto") or "—"),
        ("Encargado del monitoreo", meta.get("encargado") or "—"),
        ("Cargo / colegiatura", " · ".join(x for x in (meta.get("cargo"), meta.get("colegiatura")) if x) or "—"),
        ("Institución / empresa", meta.get("institucion") or "—"),
        ("Cuerpo de agua", meta.get("cuerpo_agua") or "—"),
        ("Ubicación", meta.get("ubicacion") or "—"),
        ("Categoría ECA aplicada", categoria),
        ("Fecha(s) de monitoreo", periodo),
        ("N.° de muestras / puntos", f"{len(df)} muestras en {df['punto'].nunique()} puntos"),
        ("Sistema de coordenadas", meta.get("datum") or "UTM – WGS 84"),
        ("Fecha de emisión", date.today().strftime("%d/%m/%Y")),
    ]
    _tabla(doc, ["Campo", "Detalle"], gen, anchos=[5.5, 11.5], tam=9)

    # ---------------- 2. Objetivo ----------------
    _titulo(doc, "2. Objetivo")
    _parrafo(doc, meta.get("objetivo") or (
        "Evaluar la calidad fisicoquímica del agua mediante la medición de pH, conductividad eléctrica, "
        "temperatura, sólidos suspendidos totales, sólidos disueltos totales, sólidos totales y sulfito, "
        "compararla estadísticamente entre muestras y contrastarla con los Estándares de Calidad Ambiental "
        f"para Agua (D.S. N.° 004-2017-MINAM), {categoria}."))

    # ---------------- 3. Marco legal ----------------
    _titulo(doc, "3. Marco legal")
    for norma_txt, desc in MARCO_LEGAL:
        p = doc.add_paragraph(style="List Bullet")
        r = p.add_run(norma_txt + ": ")
        r.bold = True
        p.add_run(desc)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # ---------------- 4. Metodología ----------------
    _titulo(doc, "4. Metodología")
    _titulo(doc, "4.1 Puntos de monitoreo y muestras", 2)
    filas = []
    for r in df.itertuples():
        filas.append([r.codigo, r.punto, r.fecha.strftime("%d/%m/%Y"), r.hora or "—",
                      _fmt(r.utm_este, 0), _fmt(r.utm_norte, 0), r.zona_utm or "—",
                      _fmt(r.altitud, 0) if pd.notna(r.altitud) else "—"])
    _tabla(doc, ["Código", "Punto", "Día", "Hora", "Este (m)", "Norte (m)", "Zona", "Altitud (m s. n. m.)"],
           filas, tam=8)
    _nota(doc, f"Coordenadas en {meta.get('datum') or 'UTM – WGS 84'}.")
    _titulo(doc, "4.2 Toma de muestras y análisis", 2)
    _parrafo(doc, meta.get("metodo") or (
        "La toma, preservación y transporte de muestras siguió el Protocolo Nacional para el Monitoreo de la "
        "Calidad de los Recursos Hídricos Superficiales (R.J. N.° 010-2016-ANA). El pH, la conductividad "
        "eléctrica y la temperatura se midieron in situ con equipo multiparámetro calibrado; los sólidos "
        "(SST, SDT y ST) se determinaron por gravimetría y el sulfito por titulación yodométrica."))
    if meta.get("equipos"):
        _parrafo(doc, "Equipos utilizados: " + meta["equipos"])
    _titulo(doc, "4.3 Tratamiento estadístico", 2)
    _parrafo(doc, (
        "Se calcularon estadísticos descriptivos (media, mediana, desviación estándar, coeficiente de variación, "
        "mínimo, máximo e intervalo de confianza al 95 %) y se identificaron valores atípicos con el criterio del "
        "rango intercuartílico (1,5·RIC). La normalidad se evaluó con la prueba de Shapiro-Wilk. La comparación "
        "con el ECA se realizó con la prueba t de Student para una muestra (datos normales) o la prueba de rangos "
        "con signo de Wilcoxon (datos no normales), unilateral, con α = 0,05. La asociación entre parámetros se "
        "evaluó con el coeficiente de Spearman"
        + (f" y las diferencias entre {grupo}s con ANOVA/Kruskal-Wallis según los supuestos." if grupo else ".")))

    # ---------------- 5. Resultados ----------------
    _titulo(doc, "5. Resultados")
    _titulo(doc, "5.1 Resultados por muestra y comparación con el ECA", 2)
    enc = ["Código"] + [f"{CORTO[c]}\n({PARAMETROS[c]['unidad']})" for c in claves]
    filas, colores = [], {}
    for fi, r in df.iterrows():
        fila = [r["codigo"]]
        for ci, c in enumerate(claves, start=1):
            fila.append(formato(c, r[c]))
            ok = cumple(r[c], norma.get(c), t_ref)
            if ok is False:
                colores[(fi, ci)] = "F5B7B1"
        filas.append(fila)
    filas.append(["ECA"] + [limite_texto(norma.get(c), t_ref) for c in claves])
    for ci in range(len(claves) + 1):
        colores[(len(filas) - 1, ci)] = "D6EAF8"
    _tabla(doc, enc, filas, tam=8, colores=colores)
    _nota(doc, f"ECA: D.S. N.° 004-2017-MINAM, {categoria}. Celdas en rojo: valor fuera del ECA. "
               "«No regulado»: el ECA no establece valor para la categoría."
               + (f" Temperatura: Δ respecto al promedio mensual multianual de {_fmt(t_ref, 1)} °C." if t_ref else ""))

    _titulo(doc, "5.2 Estadística descriptiva", 2)
    filas = []
    for c in claves:
        d = est.descriptiva(df[c])
        dec = PARAMETROS[c]["decimales"]
        filas.append([CORTO[c], d["n"], _fmt(d["media"], dec), _fmt(d["mediana"], dec), _fmt(d["desv_est"], dec),
                      _fmt(d["cv_%"], 1), _fmt(d["minimo"], dec), _fmt(d["maximo"], dec),
                      f"{_fmt(d['ic95_inf'], dec)} – {_fmt(d['ic95_sup'], dec)}"])
    _tabla(doc, ["Parámetro", "n", "Media", "Mediana", "DE", "CV %", "Mín.", "Máx.", "IC 95 % media"], filas, tam=8)

    _titulo(doc, "5.3 Estadística inferencial", 2)
    _parrafo(doc, "a) Prueba de normalidad (Shapiro-Wilk)", negrita=True)
    filas = []
    for c in claves:
        nr = est.normalidad(df[c])
        filas.append([CORTO[c], _fmt(nr["estadistico"], 3), est.fmt_p(nr["p"]),
                      "—" if nr["normal"] is None else ("Normal" if nr["normal"] else "No normal")])
    _tabla(doc, ["Parámetro", "W", "p", "Distribución"], filas, tam=8)

    _parrafo(doc, "b) Contraste con el ECA (prueba unilateral, α = 0,05)", negrita=True)
    filas = []
    for c in claves:
        rango = rango_efectivo(norma.get(c), t_ref)
        if rango is None:
            filas.append([CORTO[c], limite_texto(norma.get(c), t_ref), "—", "—", "—", "—", "Referencial"])
            continue
        ev = est.evaluar_eca(df[c], rango)
        for l in ev.get("limites", []) or [None]:
            if l is None:
                filas.append([CORTO[c], limite_texto(norma.get(c), t_ref), "—", "—", "—",
                              f"{ev.get('n_incumple', 0)}/{ev['n']}", ev.get("error", "—")])
                continue
            filas.append([CORTO[c], f"{l['tipo']} {_fmt(l['limite'], 2)}", l["prueba"].replace(" para una muestra", ""),
                          est.fmt_p(l["p_excede"]), est.fmt_p(l["p_cumple"]),
                          f"{ev['n_incumple']}/{ev['n']}", ev["veredicto"].capitalize()])
    _tabla(doc, ["Parámetro", "Límite", "Prueba", "p (excede)", "p (cumple)", "Fuera de ECA", "Decisión"],
           filas, tam=8)
    _nota(doc, "p (excede): H₁ la tendencia central sobrepasa el límite. p (cumple): H₁ la tendencia central está "
               "del lado permitido del límite. «No concluyente»: ninguna hipótesis alcanza p ≤ 0,05.")

    if grupo:
        _parrafo(doc, f"c) Comparación entre {grupo}s", negrita=True)
        filas = []
        for c in claves:
            res = est.comparar_grupos(df, c, grupo)
            if "error" in res:
                filas.append([CORTO[c], "—", "—", "—", res["error"]])
                continue
            filas.append([CORTO[c], res["prueba"], _fmt(res["estadistico"], 3), est.fmt_p(res["p"]),
                          "Diferencias significativas" if res["significativo"] else "Sin diferencias"])
        _tabla(doc, ["Parámetro", "Prueba", "Estadístico", "p", "Decisión"], filas, tam=8)

    cor = est.correlaciones(df, claves, "spearman")
    _parrafo(doc, f"{'d' if grupo else 'c'}) Correlación entre parámetros (Spearman)", negrita=True)
    if cor.empty:
        _parrafo(doc, "No hay datos suficientes para calcular correlaciones (mínimo 3 muestras).")
    else:
        filas = [[f"{CORTO[r.variable_a]} – {CORTO[r.variable_b]}", r.n, _fmt(r.coeficiente, 3), est.fmt_p(r.p),
                  r.fuerza.capitalize() + (" (significativa)" if r.significativo else " (no significativa)")]
                 for r in cor.itertuples()]
        _tabla(doc, ["Par", "n", "ρ", "p", "Interpretación"], filas, tam=8)

    if {"sst", "sdt", "st"}.issubset(claves):
        _titulo(doc, "5.4 Control de calidad analítico", 2)
        bs = est.balance_solidos(df)
        filas = [[r["codigo"], _fmt(r["ST medido"], 1), _fmt(r["SST + SDT"], 1), _fmt(r["Diferencia %"], 1),
                  _fmt(r["SDT/CE"], 2)] for _, r in bs.iterrows()]
        _tabla(doc, ["Código", "ST medido", "SST + SDT", "Diferencia %", "SDT/CE"], filas, tam=8)
        _nota(doc, "Se espera que ST ≈ SST + SDT (diferencia menor a ±10 %) y que la relación SDT/CE esté "
                   "aproximadamente entre 0,55 y 0,75 en aguas naturales; desviaciones mayores sugieren revisar "
                   "el procedimiento analítico.")

    _titulo(doc, f"5.{5 if {'sst', 'sdt', 'st'}.issubset(claves) else 4} Gráficos", 2)
    for c in claves:
        buf = grafico_parametro(df, c, rango_efectivo(norma.get(c), t_ref), limite_texto(norma.get(c), t_ref))
        if buf:
            doc.add_picture(buf, width=Cm(16))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ---------------- 6. Interpretación ----------------
    _titulo(doc, "6. Interpretación de resultados en función del ECA")
    for c in claves:
        p = PARAMETROS[c]
        lim = norma.get(c)
        _parrafo(doc, est.interpretar_parametro(df, c, p["nombre"], p["unidad"], limite_texto(lim, t_ref),
                                                rango_efectivo(lim, t_ref), p["decimales"]))
    if grupo:
        for c in claves:
            res = est.comparar_grupos(df, c, grupo)
            if "error" not in res:
                _parrafo(doc, est.interpretar(res, PARAMETROS[c]["nombre"]))

    # ---------------- 7. Observaciones ----------------
    _titulo(doc, "7. Observaciones (reactivos y condiciones de campo)")
    filas = [[r.codigo, r.reactivos or "—", r.observaciones or "—"] for r in df.itertuples()]
    _tabla(doc, ["Código", "Reactivos / preservantes utilizados", "Observaciones de campo"], filas,
           anchos=[2.5, 7.5, 7.0], tam=8)
    if meta.get("observaciones_generales"):
        _parrafo(doc, meta["observaciones_generales"])

    # ---------------- 8. Conclusiones ----------------
    _titulo(doc, "8. Conclusiones")
    for i, c in enumerate([c for c in conclusiones if c.strip()], start=1):
        _parrafo(doc, f"{i}. {c.strip()}")
    if recomendaciones:
        rec = [r for r in recomendaciones if r.strip()]
        if rec:
            _titulo(doc, "9. Recomendaciones")
            for i, c in enumerate(rec, start=1):
                _parrafo(doc, f"{i}. {c.strip()}")

    # ---------------- Firma ----------------
    doc.add_paragraph()
    _parrafo(doc, f"{meta.get('lugar_firma') or ''}{', ' if meta.get('lugar_firma') else ''}"
                  f"{date.today().strftime('%d/%m/%Y')}", alin=WD_ALIGN_PARAGRAPH.RIGHT)
    for _ in range(4):
        doc.add_paragraph()
    firmantes = [("Encargado del monitoreo", meta.get("encargado"), meta.get("cargo"), meta.get("colegiatura"))]
    if meta.get("revisor"):
        firmantes.append(("Revisado por", meta.get("revisor"), meta.get("cargo_revisor"), meta.get("colegiatura_revisor")))
    tf = doc.add_table(rows=1, cols=len(firmantes))
    tf.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (rol, nombre, cargo, coleg) in enumerate(firmantes):
        cel = tf.rows[0].cells[i]
        cel.text = ""
        lineas = ["_______________________________", nombre or "Nombre y apellidos", cargo or "", coleg or "",
                  rol, "Firma y sello"]
        for j, l in enumerate([x for x in lineas if x]):
            p = cel.paragraphs[0] if j == 0 else cel.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(l)
            r.font.size = Pt(10)
            r.bold = j in (1,)

    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out
