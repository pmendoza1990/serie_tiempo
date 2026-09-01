"""
App básica de Streamlit — Nivel de ríos/quebradas San Roque (CORNARE / MARCO)
--------------------------------------------------------------------
Cada estudiante debe cambiar, como mínimo, el código de la estación
en el sidebar. Los valores de fecha y calidad también son ajustables.

Para correrla:
    streamlit run app_nivel_cornare.py

Dependencias nuevas respecto a la versión original:
    pip install plotly
"""

import os
import requests
import pandas as pd
import numpy as np
import streamlit as st
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------------------------------------------------------
# Coordenadas San Roque
# Se usan solo si la API no trae la latitud/longitud de la estación.
# ------------------------------------------------------------------
LAT_DEFECTO = 6.4862
LON_DEFECTO = -75.0202

API_BASE_URL = "https://marco.cornare.gov.co/api/v1/estaciones"

LLAVE_FECHA = "level_date"
LLAVE_VALOR = "level"
CANDIDATOS_LAT = ["lat", "latitude", "latitud"]
CANDIDATOS_LON = ["lng", "lon", "longitude", "longitud"]

# Ruta del logo/imagen de cabecera. Coloca tu archivo junto a este script
# y actualiza el nombre aquí (por ejemplo "logo_cornare.png").
RUTA_LOGO = "logo.png"

# Foto de referencia de la estación física en campo (sensor de nivel).
# Se muestra junto a la ubicación cuando el código de estación coincide.
RUTA_FOTO_ESTACION = "estacion_29_foto.webp"
CODIGO_FOTO_ESTACION = "29"

st.set_page_config(page_title="Nivel de estación — CORNARE", page_icon="🌊", layout="wide")


# ------------------------------------------------------------------
# Funciones de consulta
# ------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def obtener_serie_nivel(codigo_estacion, desde, hasta, calidad=1, timeout=30):
    """Cacheada por 5 minutos: evita repetir la misma llamada a la API
    si el usuario vuelve a consultar los mismos parámetros."""
    url = f"{API_BASE_URL}/{codigo_estacion}/nivel"
    params = {"desde": desde, "hasta": hasta, "calidad": calidad}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout, verify=False)
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"HTTP {resp.status_code}"
    except requests.exceptions.RequestException as e:
        return None, f"Error de red: {e}"


def obtener_todas_las_paginas(datos_json, timeout=30):
    registros = list(datos_json.get("values", []))
    siguiente_url = datos_json.get("next")
    while siguiente_url:
        try:
            resp = requests.get(siguiente_url, timeout=timeout, verify=False)
        except requests.exceptions.RequestException:
            break
        if resp.status_code != 200:
            break
        pagina = resp.json()
        registros.extend(pagina.get("values", []))
        siguiente_url = pagina.get("next")
    return registros


def detectar_coordenadas(datos_json):
    """Busca lat/lon en las llaves raíz de la respuesta. Si no las encuentra, usa el valor por defecto."""
    if not isinstance(datos_json, dict):
        return LAT_DEFECTO, LON_DEFECTO, False

    lat = next((datos_json[k] for k in CANDIDATOS_LAT if k in datos_json), None)
    lon = next((datos_json[k] for k in CANDIDATOS_LON if k in datos_json), None)

    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon), True
        except (TypeError, ValueError):
            pass
    return LAT_DEFECTO, LON_DEFECTO, False


def calcular_indice_calidad(df):
    """Índice simple (0-100) combinando completitud de la serie y proporción de outliers."""
    if df.empty or len(df) < 2:
        return 0.0, 0, 0, pd.Series(dtype=bool)

    df_idx = df.set_index("fecha")
    frecuencia_tipica = df["fecha"].diff().dropna().mode()
    if len(frecuencia_tipica) == 0:
        return 0.0, 0, 0, pd.Series(dtype=bool)
    frecuencia_tipica = frecuencia_tipica[0]

    rango_completo = pd.date_range(start=df_idx.index.min(), end=df_idx.index.max(), freq=frecuencia_tipica)
    esperados = len(rango_completo)
    huecos = esperados - len(df_idx)
    completitud = max(0.0, 1 - (huecos / esperados)) if esperados > 0 else 0.0

    Q1, Q3 = df["nivel"].quantile(0.25), df["nivel"].quantile(0.75)
    IQR = Q3 - Q1
    lim_inf, lim_sup = Q1 - 1.5 * IQR, Q3 + 1.5 * IQR
    es_outlier = (df["nivel"] < lim_inf) | (df["nivel"] > lim_sup) | (df["nivel"] < 0)
    proporcion_outliers = es_outlier.mean()

    indice = (completitud * 0.7 + (1 - proporcion_outliers) * 0.3) * 100
    return round(indice, 1), int(huecos), int(es_outlier.sum()), es_outlier


# ------------------------------------------------------------------
# Cabecera con logo (si existe el archivo)
# ------------------------------------------------------------------
col_logo, col_titulo = st.columns([1, 5])
with col_logo:
    if os.path.exists(RUTA_LOGO):
        st.image(RUTA_LOGO, width=90)
    else:
        st.markdown("### 🌊")
with col_titulo:
    st.title("Nivel de ríos y quebradas — CORNARE")

# ------------------------------------------------------------------
# Sidebar — parámetros de la consulta (editables por cada estudiante)
# ------------------------------------------------------------------
st.sidebar.header("Parámetros de tu consulta")
nombre_estudiante = st.sidebar.text_input("Nombre del estudiante", "Tu Nombre Aquí")
codigo_estacion = st.sidebar.text_input("Código de estación", "29")

st.sidebar.markdown("**Rango rápido**")
col_r1, col_r2, col_r3 = st.sidebar.columns(3)
rango_rapido = None
if col_r1.button("24h"):
    rango_rapido = 1
if col_r2.button("7 días"):
    rango_rapido = 7
if col_r3.button("30 días"):
    rango_rapido = 30

hoy = pd.Timestamp.now().normalize()
if "fecha_desde" not in st.session_state:
    st.session_state.fecha_desde = hoy - pd.Timedelta(days=7)
if "fecha_hasta" not in st.session_state:
    st.session_state.fecha_hasta = hoy

if rango_rapido is not None:
    st.session_state.fecha_hasta = hoy
    st.session_state.fecha_desde = hoy - pd.Timedelta(days=rango_rapido)

fecha_desde = st.sidebar.date_input("Desde", st.session_state.fecha_desde).strftime("%Y-%m-%d")
fecha_hasta = st.sidebar.date_input("Hasta", st.session_state.fecha_hasta).strftime("%Y-%m-%d")
calidad = st.sidebar.selectbox("Calidad", [1, 0], index=0, help="1 = solo datos validados")
consultar = st.sidebar.button("🔍 Consultar", type="primary")

st.caption(f"Estudiante: **{nombre_estudiante}** · Estación: **{codigo_estacion}**")

# ------------------------------------------------------------------
# Consulta y procesamiento
# ------------------------------------------------------------------
if consultar:
    with st.spinner("Consultando la API..."):
        datos_crudos, error = obtener_serie_nivel(codigo_estacion, fecha_desde, fecha_hasta, calidad)

    if error:
        st.error(f"❌ {error}")
    else:
        registros = obtener_todas_las_paginas(datos_crudos)

        if not registros:
            st.warning("No hay registros para esta estación y rango de fechas. Prueba otro código u otro rango.")
        else:
            df = pd.DataFrame(registros)
            df = df.rename(columns={LLAVE_FECHA: "fecha", LLAVE_VALOR: "nivel"})
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
            df["nivel"] = pd.to_numeric(df["nivel"], errors="coerce")
            df = df.dropna(subset=["fecha", "nivel"]).sort_values("fecha").reset_index(drop=True)

            lat, lon, coords_reales = detectar_coordenadas(datos_crudos)
            indice_calidad, huecos, n_outliers, mask_outliers = calcular_indice_calidad(df)

            # --- Tendencia: último valor vs promedio del período ---
            ultimo_valor = df["nivel"].iloc[-1]
            promedio = df["nivel"].mean()
            delta_tendencia = ultimo_valor - promedio

            # --- Métricas principales ---
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            col1.metric("Lecturas", len(df))
            col2.metric("Nivel actual", f"{ultimo_valor:.2f}", delta=f"{delta_tendencia:+.2f} vs prom.")
            col3.metric("Nivel promedio", f"{promedio:.2f}")
            col4.metric("Nivel mínimo", f"{df['nivel'].min():.2f}")
            col5.metric("Nivel máximo", f"{df['nivel'].max():.2f}")
            col6.metric("Índice de calidad", f"{indice_calidad} / 100")

            # --- Gráfico de la serie (solo con librerías nativas de Streamlit) ---
            st.subheader("Serie de nivel")
            st.line_chart(df.set_index("fecha")["nivel"])
            if n_outliers > 0:
                st.caption(f"⚠️ Se detectaron **{n_outliers}** posibles outliers — revisa el detalle abajo o la tabla de datos crudos.")

            # --- Mapa y foto de la estación ---
            st.subheader("Ubicación de la estación")
            if not coords_reales:
                st.caption("La API no trajo latitud/longitud de la estación — se muestra el punto de partida (Pascual Bravo). Ajusta `CANDIDATOS_LAT` / `CANDIDATOS_LON` si conoces el nombre real de esas llaves.")

            if codigo_estacion.strip() == CODIGO_FOTO_ESTACION and os.path.exists(RUTA_FOTO_ESTACION):
                col_mapa, col_foto = st.columns([2, 1])
                with col_mapa:
                    st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=10)
                with col_foto:
                    st.image(
                        RUTA_FOTO_ESTACION,
                        caption=f"Sensor de nivel en campo — Estación {CODIGO_FOTO_ESTACION}, Quebrada San Roque",
                        use_container_width=True,
                    )
            else:
                st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=10)

            # --- Detalle de calidad ---
            with st.expander("Detalle del índice de calidad"):
                st.write(f"- Huecos de reporte detectados: **{huecos}**")
                st.write(f"- Outliers (IQR + nivel negativo): **{n_outliers}** de {len(df)} lecturas")
                st.write("El índice combina completitud de la serie (70%) y proporción de datos sin outliers (30%).")
                if mask_outliers is not None and len(mask_outliers) > 0 and mask_outliers.any():
                    st.write("**Lecturas marcadas como outlier:**")
                    st.dataframe(df[mask_outliers][["fecha", "nivel"]], use_container_width=True)

            # --- Tabla y descarga ---
            with st.expander("Ver datos crudos"):
                st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Descargar CSV", csv, file_name=f"nivel_estacion_{codigo_estacion}.csv", mime="text/csv")
else:
    st.info("Ajusta los parámetros en el sidebar y presiona **Consultar**.")
