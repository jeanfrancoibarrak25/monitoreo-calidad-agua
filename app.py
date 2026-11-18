"""Calidad de Agua Stats — interfaz web (Streamlit).

Ejecutar:  streamlit run app.py
"""
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from calidad_agua import estadistica as est
from calidad_agua.db import CAMPOS_META, BaseDatos
from calidad_agua.informe import conclusiones_auto, generar_informe
from calidad_agua.normativa import ECA, MARCO_LEGAL, cumple, limite_texto, rango_efectivo
from calidad_agua.parametros import CORTO, PARAMETROS, etiqueta

st.set_page_config(page_title="Calidad de Agua Stats", page_icon="💧", layout="wide")


@st.cache_resource
def obtener_db():
    return BaseDatos("data/calidad_agua.db")


db = obtener_db()
df = db.todas()

# --------------------------------------------------------------------------- #
st.sidebar.title("💧 Calidad de Agua Stats")
pagina = st.sidebar.radio("Módulo", ["1. Registrar muestras", "2. Base de datos", "3. Estadística descriptiva",
                                     "4. Estadística inferencial", "5. Comparación con el ECA", "6. Informe"])
st.sidebar.divider()
categoria = st.sidebar.selectbox("Categoría ECA (D.S. 004-2017-MINAM)", list(ECA), index=8)
t_ref = st.sidebar.number_input("T° promedio mensual multianual (°C)", value=None, step=0.1,
                                help="Necesaria para evaluar la temperatura (ECA: Δ3 °C).")
norma = ECA[categoria]
st.sidebar.metric("Muestras registradas", len(df))
if not df.empty:
    st.sidebar.metric("Puntos de monitoreo", df["punto"].nunique())


def requiere_datos(minimo=1):
    if len(df) < minimo:
        st.info(f"Se necesitan al menos {minimo} muestra(s). Registra datos en el módulo 1 "
                "o importa `datos_ejemplo.csv`.")
        st.stop()


# --------------------------------------------------------------------------- #
if pagina.startswith("1"):
    st.header("Registrar muestra")
    puntos = sorted(df["punto"].unique()) if not df.empty else []
    with st.form("nueva", clear_on_submit=True):
        st.subheader("Datos de campo")
        c1, c2, c3, c4 = st.columns(4)
        codigo = c1.text_input("Código de muestra *", placeholder="M-101")
        punto_sel = c2.selectbox("Punto de monitoreo *", ["➕ Nuevo…"] + puntos)
        punto_nuevo = c2.text_input("Nombre del punto nuevo", placeholder="P-01 Aguas arriba")
        fecha = c3.date_input("Día *", value=date.today(), format="DD/MM/YYYY")
        hora = c4.time_input("Hora", value=datetime.now().time().replace(second=0, microsecond=0))
        c1, c2, c3, c4 = st.columns(4)
        este = c1.number_input("UTM Este (m)", value=None, step=1.0, format="%.0f")
        norte = c2.number_input("UTM Norte (m)", value=None, step=1.0, format="%.0f")
        zona = c3.text_input("Zona UTM", value="19K", help="Perú: 17M/17L, 18M/18L/18K, 19L/19K")
        alt = c4.number_input("Altitud (m s. n. m.)", value=None, step=1.0, format="%.0f")

        st.subheader("Parámetros")
        cols = st.columns(len(PARAMETROS))
        vals = {}
        for col, (k, p) in zip(cols, PARAMETROS.items()):
            vals[k] = col.number_input(f"{CORTO[k]} ({p['unidad']})", value=None, step=0.01,
                                       min_value=0.0 if k != "temperatura" else None,
                                       max_value=14.0 if k == "ph" else None, help=p["nombre"])
        reactivos = st.text_area("Reactivos / preservantes utilizados (observación)",
                                 placeholder="Ej.: EDTA 0,5 mL; KI-KIO₃ 0,0125 N; almidón")
        obs = st.text_input("Observaciones de campo", placeholder="Clima, color, olor, caudal…")
        if st.form_submit_button("Guardar muestra", type="primary"):
            punto = punto_nuevo.strip() if punto_sel == "➕ Nuevo…" else punto_sel
            if all(v is None for v in vals.values()):
                st.error("Ingresa al menos un parámetro.")
            else:
                try:
                    db.agregar(codigo=codigo, punto=punto, fecha=fecha, hora=hora.strftime("%H:%M") if hora else "",
                               utm_este=este, utm_norte=norte, zona_utm=zona, altitud=alt,
                               reactivos=reactivos, observaciones=obs, **vals)
                    s, d, t = vals["sst"], vals["sdt"], vals["st"]
                    if None not in (s, d, t) and t > 0 and abs(t - s - d) / t > 0.10:
                        st.warning("ST difiere en más de 10 % de SST + SDT; revisa el análisis gravimétrico.")
                    st.success(f"Muestra «{codigo}» guardada.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    st.subheader("Importar desde CSV o Excel")
    st.caption("Columnas: " + ", ".join(CAMPOS_META + list(PARAMETROS)) + ". Ver `datos_ejemplo.csv`.")
    arch = st.file_uploader("Archivo", type=["csv", "xlsx"])
    c1, c2 = st.columns(2)
    if arch and c1.button("Importar archivo"):
        data = pd.read_csv(arch) if arch.name.endswith(".csv") else pd.read_excel(arch)
        try:
            n, errores = db.importar(data)
            st.success(f"{n} muestras importadas.")
            for e in errores:
                st.warning(e)
        except ValueError as e:
            st.error(str(e))
    if c2.button("Cargar datos de ejemplo"):
        n, errores = db.importar(pd.read_csv("datos_ejemplo.csv"))
        st.success(f"{n} muestras de ejemplo cargadas.")
        st.rerun()

# --------------------------------------------------------------------------- #
elif pagina.startswith("2"):
    st.header("Base de datos de muestras")
    requiere_datos()
    st.caption("Puedes editar las celdas y pulsar «Guardar cambios».")
    editado = st.data_editor(df.drop(columns="id"), num_rows="dynamic", width="stretch", hide_index=True)
    c1, c2, c3 = st.columns(3)
    if c1.button("Guardar cambios", type="primary"):
        try:
            db.actualizar(editado)
            st.success("Cambios guardados.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    c2.download_button("Exportar CSV", df.drop(columns="id").to_csv(index=False).encode("utf-8-sig"),
                       "muestras_calidad_agua.csv", "text/csv")
    with c3.popover("Vaciar base de datos"):
        if st.button("Confirmar: borrar todas las muestras"):
            db.vaciar()
            st.rerun()
    if df[["utm_este", "utm_norte"]].notna().all(axis=1).any():
        st.subheader("Ubicación relativa de los puntos (UTM)")
        st.plotly_chart(px.scatter(df, x="utm_este", y="utm_norte", text="codigo", color="punto",
                                   labels={"utm_este": "Este (m)", "utm_norte": "Norte (m)"}),
                        width="stretch")

# --------------------------------------------------------------------------- #
elif pagina.startswith("3"):
    st.header("Estadística descriptiva")
    requiere_datos()
    grupo = st.radio("Agrupar por", ["Ninguno", "punto", "fecha"], horizontal=True)
    claves = [k for k in PARAMETROS if df[k].notna().any()]
    tabla = est.tabla_descriptiva(df, claves, None if grupo == "Ninguno" else grupo)
    tabla["parametro"] = tabla["parametro"].map(CORTO)
    st.dataframe(tabla.round(3), width="stretch", hide_index=True)

    st.subheader("Comparación entre muestras")
    p = st.selectbox("Parámetro", claves, format_func=etiqueta)
    sub = df[["codigo", "punto", p]].dropna().copy()
    sub["z"] = est.puntaje_z(sub[p]).round(2)
    sub["Atípico (RIC)"] = est.atipicos_iqr(sub[p]).map({True: "Sí", False: ""})
    sub["ECA"] = [{True: "Cumple", False: "No cumple", None: "—"}[cumple(v, norma.get(p), t_ref)] for v in sub[p]]
    fig = px.bar(sub, x="codigo", y=p, color="punto", labels={p: etiqueta(p)})
    r = rango_efectivo(norma.get(p), t_ref)
    if r:
        for v in r:
            if v is not None:
                fig.add_hline(y=v, line_dash="dash", line_color="red", annotation_text=f"ECA {v:g}")
    fig.add_hline(y=sub[p].mean(), line_dash="dot", annotation_text="media")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(sub, width="stretch", hide_index=True)
    st.plotly_chart(px.box(df, x="punto", y=p, points="all", labels={p: etiqueta(p)}), width="stretch")

    if {"sst", "sdt", "st"}.issubset(claves):
        st.subheader("Control de calidad: balance de sólidos y relación SDT/CE")
        st.dataframe(est.balance_solidos(df).round(2), width="stretch", hide_index=True)
        st.caption("Esperado: ST ≈ SST + SDT (±10 %) y SDT/CE ≈ 0,55–0,75.")

# --------------------------------------------------------------------------- #
elif pagina.startswith("4"):
    st.header("Estadística inferencial (α = 0,05)")
    requiere_datos(3)
    claves = [k for k in PARAMETROS if df[k].notna().any()]

    st.subheader("Normalidad (Shapiro-Wilk)")
    st.dataframe(pd.DataFrame([{"Parámetro": CORTO[k], **est.normalidad(df[k])} for k in claves]).round(4),
                 width="stretch", hide_index=True)

    st.subheader("Comparación entre grupos")
    grupo = st.radio("Grupos", ["punto", "fecha"], horizontal=True,
                     help="Requiere al menos 2 muestras por grupo (p. ej. varias campañas por punto).")
    forzar = st.radio("Enfoque", ["auto", "parametrica", "no_parametrica"], horizontal=True,
                      format_func={"auto": "Automático", "parametrica": "Paramétrico",
                                   "no_parametrica": "No paramétrico"}.get)
    for k in claves:
        res = est.comparar_grupos(df.assign(fecha=df["fecha"].astype(str)), k, grupo, forzar)
        with st.expander(f"{PARAMETROS[k]['nombre']} — " + ("⚠️ " + res["error"] if "error" in res else
                         f"{res['prueba']}: p = {est.fmt_p(res['p'])}"), expanded="error" not in res):
            if "error" not in res:
                st.write(est.interpretar(res, PARAMETROS[k]["nombre"]))
                if "post_hoc" in res:
                    st.caption(res["post_hoc_nombre"])
                    st.dataframe(res["post_hoc"].round(4), hide_index=True)

    st.subheader("Correlación entre parámetros")
    metodo = st.radio("Coeficiente", ["spearman", "pearson"], horizontal=True)
    cor = est.correlaciones(df, claves, metodo)
    if not cor.empty:
        mat = df[claves].rename(columns=CORTO).corr(method=metodo)
        st.plotly_chart(px.imshow(mat, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdBu_r"),
                        width="stretch")
        cor = cor.assign(variable_a=cor["variable_a"].map(CORTO), variable_b=cor["variable_b"].map(CORTO))
        st.dataframe(cor.round(4), width="stretch", hide_index=True)

# --------------------------------------------------------------------------- #
elif pagina.startswith("5"):
    st.header(f"Comparación con el ECA — {categoria}")
    requiere_datos()
    claves = [k for k in PARAMETROS if df[k].notna().any()]
    tabla = df[["codigo"] + claves].copy()
    eca_fila = {"codigo": "ECA", **{k: limite_texto(norma.get(k), t_ref) for k in claves}}

    def color(col):
        k = col.name
        if k == "codigo":
            return [""] * len(col)
        return ["background-color:#f5b7b1" if cumple(v, norma.get(k), t_ref) is False else "" for v in col]

    st.dataframe(tabla.style.apply(color).format(precision=2), width="stretch", hide_index=True)
    st.dataframe(pd.DataFrame([eca_fila]), width="stretch", hide_index=True)
    if "temperatura" in norma and t_ref is None:
        st.info("Ingresa la T° promedio mensual multianual en la barra lateral para evaluar la temperatura.")

    st.subheader("Contraste inferencial frente al ECA")
    for k in claves:
        p = PARAMETROS[k]
        lim = norma.get(k)
        st.markdown(f"**{p['nombre']}** — ECA: {limite_texto(lim, t_ref)}")
        st.write(est.interpretar_parametro(df, k, p["nombre"], p["unidad"], limite_texto(lim, t_ref),
                                           rango_efectivo(lim, t_ref), p["decimales"]))

# --------------------------------------------------------------------------- #
else:
    st.header("Generar informe técnico (Word)")
    requiere_datos()
    sel = st.multiselect("Muestras a incluir", df["codigo"].tolist(), default=df["codigo"].tolist())
    datos = df[df["codigo"].isin(sel)]

    with st.form("meta"):
        st.subheader("Datos generales")
        c1, c2 = st.columns(2)
        proyecto = c1.text_input("Proyecto / estudio")
        numero = c2.text_input("N.° de informe", placeholder="Informe N.° 001-2026")
        institucion = c1.text_input("Institución / empresa / laboratorio")
        cuerpo = c2.text_input("Cuerpo de agua", placeholder="Río …")
        ubic = c1.text_input("Ubicación (distrito, provincia, región)")
        datum = c2.text_input("Sistema de coordenadas", value="UTM – WGS 84")
        st.subheader("Encargado del monitoreo (firma)")
        c1, c2, c3 = st.columns(3)
        encargado = c1.text_input("Nombre del encargado *")
        cargo = c2.text_input("Cargo / profesión", placeholder="Ingeniero ambiental")
        coleg = c3.text_input("Colegiatura", placeholder="CIP N.° …")
        revisor = c1.text_input("Revisado por (opcional)")
        cargo_rev = c2.text_input("Cargo del revisor")
        coleg_rev = c3.text_input("Colegiatura del revisor")
        lugar = c1.text_input("Lugar de emisión", placeholder="Tacna")
        equipos = st.text_input("Equipos utilizados", placeholder="Multiparámetro HACH HQ40d (calibrado …), GPS Garmin …")
        metodo = st.text_area("Metodología (vacío = texto estándar según R.J. 010-2016-ANA)")
        obs_gen = st.text_area("Observaciones generales (opcional)")
        grupo = st.selectbox("Incluir comparación inferencial entre…", ["(no incluir)", "punto", "fecha"])
        st.subheader("Conclusiones y recomendaciones")
        st.caption("Se proponen conclusiones automáticas; edítalas libremente (una por línea).")
        auto = conclusiones_auto(datos, categoria, t_ref) if not datos.empty else []
        concl = st.text_area("Conclusiones", value="\n".join(auto), height=220)
        recom = st.text_area("Recomendaciones (opcional, una por línea)")
        ok = st.form_submit_button("Generar informe", type="primary")

    with st.expander("Marco legal incluido en el informe"):
        for n, d in MARCO_LEGAL:
            st.markdown(f"- **{n}**: {d}")

    if ok:
        if not encargado.strip():
            st.error("Indica el nombre del encargado del monitoreo.")
        elif datos.empty:
            st.error("Selecciona al menos una muestra.")
        else:
            meta = dict(categoria=categoria, t_ref=t_ref, proyecto=proyecto, numero=numero, institucion=institucion,
                        cuerpo_agua=cuerpo, ubicacion=ubic, datum=datum, encargado=encargado, cargo=cargo,
                        colegiatura=coleg, revisor=revisor, cargo_revisor=cargo_rev, colegiatura_revisor=coleg_rev,
                        lugar_firma=lugar, equipos=equipos, metodo=metodo, observaciones_generales=obs_gen)
            g = None if grupo.startswith("(") else grupo
            buf = generar_informe(datos, meta, concl.splitlines(), recom.splitlines(), grupo=g)
            st.success("Informe generado.")
            st.download_button("⬇️ Descargar informe (.docx)", buf,
                               f"Informe_calidad_agua_{date.today():%Y%m%d}.docx",
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
