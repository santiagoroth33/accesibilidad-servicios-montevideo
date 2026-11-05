# =============================================================================
# Accesibilidad al transporte público por municipio — Montevideo
# =============================================================================
# ¿Qué tan bien servido por el transporte público está cada municipio? Lo
# medimos con datos ESPACIALES y de HORARIOS:
#
#   - sig_municipios.shp        -> polígonos de los municipios
#   - v_uptu_paradas.shp        -> puntos: cada parada de ómnibus
#   - v_uptu_lsv.shp            -> líneas: el recorrido de las líneas
#   - uptu_pasada_variante.csv  -> horarios: cada ómnibus pasando por una parada
#
# Para cada municipio calculamos CINCO miradas de la accesibilidad y las
# juntamos en un índice:
#
#   1. Cuántas paradas tiene y cuán densas están (paradas por km²).
#   2. Cuántas líneas distintas lo sirven.
#   3. Cuántos km de recorrido de ómnibus pasan por dentro.
#   4. Qué proporción de su superficie queda a ≤ 300 m de una parada (cobertura).
#   5. Cuántos ómnibus por hora pasan en promedio por sus paradas en la hora
#      pico de un día hábil (FRECUENCIA: el servicio real, no solo "hay parada").
#
# Las primeras cuatro dicen DÓNDE hay transporte; la quinta, CUÁNTO. Una parada
# donde pasa un bus cada hora no es lo mismo que una donde pasa cada 5 minutos.
#
# Todo en UTM 21S (EPSG:32721), o sea en metros: medimos distancias y áreas
# directo. Se puede ejecutar desde cualquier carpeta.
# Instalación (una sola vez):  pip install geopandas pandas matplotlib
# =============================================================================
#%%
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import geopandas as gpd

# --- Rutas relativas ---------------------------------------------------------
# La raíz del repo se calcula desde este archivo, así corre desde cualquier carpeta
RAIZ = Path(__file__).resolve().parents[2] if "__file__" in globals() else Path.cwd()
MUNI    = RAIZ / "datos" / "crudos" / "municipios"
TRANSP  = RAIZ / "datos" / "crudos" / "transporte"
FIGURAS = RAIZ / "salidas" / "figuras" / "transporte"
TABLAS  = RAIZ / "salidas" / "tablas"
FIGURAS.mkdir(parents=True, exist_ok=True)
TABLAS.mkdir(parents=True, exist_ok=True)

RADIO_CAMINABLE = 300          # metros: "a 3 cuadras" de una parada
CRS_METROS = 32721             # UTM 21S: coordenadas en metros
TIPO_DIA_HABIL = 1             # 1 = hábil, 2 = sábado, 3 = domingo (por volumen)
PICO_INI, PICO_FIN = 700, 900  # hora pico mañana: 7:00 a 8:59 (formato HHMM)
HORAS_PICO = 2                 # el tramo pico dura 2 horas

def estetica(ax):
    ax.set_axis_off()

# =============================================================================
# 1. Carga de los archivos espaciales
# =============================================================================
municipios = gpd.read_file(MUNI / "sig_municipios.shp").to_crs(CRS_METROS)
paradas    = gpd.read_file(TRANSP / "v_uptu_paradas.shp").to_crs(CRS_METROS)
lineas     = gpd.read_file(TRANSP / "v_uptu_lsv.shp").to_crs(CRS_METROS)

# Geometrías válidas y sin vacíos (si no, los recortes fallan).
municipios["geometry"] = municipios.geometry.buffer(0)
def sin_geom_vacias(gdf):
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
paradas = sin_geom_vacias(paradas)
lineas  = sin_geom_vacias(lineas)

municipios["muni"] = "Municipio " + municipios["MUNICIPIO"].astype(str).str.strip()
print("Municipios:", len(municipios), "| Paradas (filas):", len(paradas),
      "| Líneas (tramos):", len(lineas))

# Una fila por (parada x línea): para contar paradas usamos ubicaciones únicas.
paradas_unicas = paradas.drop_duplicates(subset="COD_UBIC_P").copy()

# =============================================================================
# 2. ¿En qué municipio cae cada parada? (punto en polígono)
# =============================================================================
paradas_en_muni = gpd.sjoin(
    paradas[["COD_UBIC_P", "DESC_LINEA", "geometry"]],
    municipios[["muni", "geometry"]],
    how="inner", predicate="within",
)
resumen_paradas = (paradas_en_muni.groupby("muni")
    .agg(n_paradas=("COD_UBIC_P", "nunique"),
         n_lineas=("DESC_LINEA", "nunique"))
    .reset_index())

# =============================================================================
# 3. FRECUENCIA: ómnibus por hora por parada, en hora pico de día hábil
# =============================================================================
# El archivo de horarios trae una fila por cada pasada (un ómnibus pasando por
# una parada a una hora). Contamos cuántas pasan por cada parada en el tramo
# pico (7-9 h) de un día hábil y lo pasamos a ómnibus por hora.
pasadas = pd.read_csv(TRANSP / "uptu_pasada_variante.csv", sep=";",
                      usecols=["tipo_dia", "cod_ubic_parada", "hora"])

pico = pasadas[(pasadas["tipo_dia"] == TIPO_DIA_HABIL) &
               (pasadas["hora"] >= PICO_INI) & (pasadas["hora"] < PICO_FIN)]
buses_por_hora = (pico.groupby("cod_ubic_parada").size() / HORAS_PICO
                  ).rename("frecuencia")   # ómnibus por hora en cada parada

# Pegamos la frecuencia a cada parada y promediamos por municipio. Las paradas
# sin servicio en el pico quedan en 0 (existen, pero no pasa el bus a esa hora).
paradas_frec = paradas_en_muni[["COD_UBIC_P", "muni"]].drop_duplicates()
paradas_frec = paradas_frec.merge(
    buses_por_hora, left_on="COD_UBIC_P", right_index=True, how="left")
paradas_frec["frecuencia"] = paradas_frec["frecuencia"].fillna(0)
resumen_frec = (paradas_frec.groupby("muni")["frecuencia"]
                .mean().reset_index(name="frecuencia_media"))
print(f"Pasadas totales: {len(pasadas):,} | en pico hábil: {len(pico):,}")

# =============================================================================
# 4. Km de recorrido dentro de cada municipio (recorte línea-polígono)
# =============================================================================
km_por_muni = {}
for _, m in municipios.iterrows():
    tramos = gpd.clip(lineas[["geometry"]], m.geometry)
    km_por_muni[m["muni"]] = tramos.length.sum() / 1000
resumen_lineas = (pd.Series(km_por_muni, name="km_recorrido")
                  .rename_axis("muni").reset_index())

# =============================================================================
# 5. Cobertura: ¿qué porcentaje de la superficie del municipio está a ≤ 300 m de una parada?
# =============================================================================
area_servida = gpd.GeoSeries(
    [paradas_unicas.buffer(RADIO_CAMINABLE).union_all()], crs=CRS_METROS)
municipios["area_km2"] = municipios.area / 1e6
municipios["area_servida_km2"] = municipios.geometry.intersection(
    area_servida.iloc[0]).area / 1e6
municipios["cobertura_300m"] = (
    100 * municipios["area_servida_km2"] / municipios["area_km2"])

# =============================================================================
# 6. Una tabla por municipio
# =============================================================================
tabla = (municipios[["muni", "area_km2", "cobertura_300m", "geometry"]]
         .merge(resumen_paradas, on="muni", how="left")
         .merge(resumen_lineas, on="muni", how="left")
         .merge(resumen_frec, on="muni", how="left"))
tabla[["n_paradas", "n_lineas", "km_recorrido", "frecuencia_media"]] = (
    tabla[["n_paradas", "n_lineas", "km_recorrido", "frecuencia_media"]].fillna(0))
tabla["paradas_km2"] = tabla["n_paradas"] / tabla["area_km2"]
tabla["km_recorrido_km2"] = tabla["km_recorrido"] / tabla["area_km2"]

# =============================================================================
# 7. Índice de accesibilidad (0 a 100) con las cinco componentes
# =============================================================================
def a_0_1(s):
    return (s - s.min()) / (s.max() - s.min())

componentes = ["paradas_km2", "km_recorrido_km2", "n_lineas",
               "cobertura_300m", "frecuencia_media"]
tabla["indice_accesibilidad"] = 100 * tabla[componentes].apply(a_0_1).mean(axis=1)
tabla = tabla.sort_values("indice_accesibilidad", ascending=False)

cols = ["muni", "area_km2", "n_paradas", "paradas_km2", "n_lineas",
        "km_recorrido", "cobertura_300m", "frecuencia_media",
        "indice_accesibilidad"]
print("\n=== Accesibilidad al transporte por municipio ===")
print(tabla[cols].to_string(index=False, float_format=lambda x: f"{x:,.1f}"))
tabla[cols].to_csv(TABLAS / "accesibilidad_por_municipio.csv",
                   index=False, encoding="utf-8-sig")

# =============================================================================
# 8. Mapas
# =============================================================================
muni_geo = gpd.GeoDataFrame(tabla, geometry="geometry", crs=CRS_METROS)

def mapa(ax, columna, titulo, etiqueta):
    muni_geo.plot(column=columna, ax=ax, cmap="YlGnBu", edgecolor="white",
                  linewidth=0.6, legend=True,
                  legend_kwds={"label": etiqueta, "shrink": 0.6})
    for _, r in muni_geo.iterrows():
        c = r.geometry.representative_point()
        ax.annotate(r["muni"].replace("Municipio ", ""), (c.x, c.y),
                    ha="center", va="center", fontsize=9, fontweight="bold")
    ax.set_title(titulo, fontsize=12)
    estetica(ax)

fig, axes = plt.subplots(1, 3, figsize=(18, 7))
mapa(axes[0], "cobertura_300m", f"Cobertura a ≤ {RADIO_CAMINABLE} m",
     "% del área del municipio")
mapa(axes[1], "frecuencia_media", "Frecuencia en hora pico (hábil)",
     "ómnibus por hora (promedio por parada)")
mapa(axes[2], "indice_accesibilidad", "Índice de accesibilidad",
     "0 (menos) a 100 (más)")
fig.suptitle("Accesibilidad al transporte público por municipio — Montevideo",
             fontsize=15)
fig.tight_layout()
fig.savefig(FIGURAS / "mapas_accesibilidad.png", dpi=150, bbox_inches="tight")

# Mapa de contexto: paradas y recorridos sobre los municipios
fig2, ax = plt.subplots(figsize=(9, 9))
muni_geo.boundary.plot(ax=ax, color="0.5", linewidth=0.8)
lineas.plot(ax=ax, color="tab:blue", linewidth=0.3, alpha=0.4)
paradas_unicas.plot(ax=ax, color="tab:red", markersize=1, alpha=0.5)
ax.set_title("Paradas (rojo) y recorridos de líneas (azul) sobre los municipios")
estetica(ax)
fig2.tight_layout()
fig2.savefig(FIGURAS / "mapa_paradas_y_lineas.png", dpi=150, bbox_inches="tight")

# =============================================================================
# 9. Ranking en barras
# =============================================================================
fig3, ax = plt.subplots(figsize=(9, 5))
orden = tabla.sort_values("indice_accesibilidad")
ax.barh(orden["muni"], orden["indice_accesibilidad"], color="teal")
ax.set_xlabel("Índice de accesibilidad (0–100)")
ax.set_title("Ranking de municipios por accesibilidad al transporte")
ax.grid(axis="x", alpha=0.3)
for lado in ("top", "right"):
    ax.spines[lado].set_visible(False)
fig3.tight_layout()
fig3.savefig(FIGURAS / "ranking_accesibilidad.png", dpi=150, bbox_inches="tight")

plt.show()
print(f"\nListo. Mapas en {FIGURAS}, tabla en {TABLAS}")
# =============================================================================
# Lectura: la frecuencia agrega información que la sola presencia de paradas no
# da: dos municipios pueden tener cobertura parecida pero muy distinto nivel de
# servicio por hora. Aun así, esto sigue siendo la OFERTA, para saber si llega
# donde se necesita hay que cruzarla con la necesidad (necesidad_vs_oferta_transporte.py).
# =============================================================================
