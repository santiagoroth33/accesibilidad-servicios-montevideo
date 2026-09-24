# Accesibilidad al transporte público por municipio — Montevideo

# ¿Qué tan bien servido por el transporte público está cada uno de
# los municipios de Montevideo?
#
#   - sig_municipios.shp   -> polígonos de los municipios (los "canteros")
#   - v_uptu_paradas.shp   -> puntos: cada parada de ómnibus
#   - v_uptu_lsv.shp       -> líneas: el recorrido de las líneas de servicio
#
# Para cada municipio calculamos, cuatro miradas de la
# accesibilidad y las juntamos en un índice:
#
#   1. Cuántas paradas tiene y cuán densas están (paradas por km²).
#   2. Cuántas líneas distintas lo sirven.
#   3. Cuántos km de recorrido de ómnibus pasan por dentro.
#   4. Qué proporción de su superficie queda a menos de 300 m de una parada
#      ("distancia caminable").
#
# Todo se apoya en que los datos vienen en UTM 21S (EPSG:32721), o sea en
# metros, por lo que podemos medir distancias y áreas directamente sin convertir.

#%%
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import geopandas as gpd

BASE_DIR = Path.cwd() / "transporte" / "raw"

SALIDA = Path("transporte") / "outputs"    # acá guardamos mapas y la tabla final
SALIDA.mkdir(parents=True, exist_ok=True)

RADIO_CAMINABLE = 300               # metros: "a una cuadra y media" de una parada
CRS_METROS = 32721                  # UTM 21S: coordenadas en metros

def estetica(ax):
    ax.set_axis_off()

# 1. Carga de los tres archivos espaciales

municipios = gpd.read_file(BASE_DIR / "sig_municipios.shp")
paradas    = gpd.read_file(BASE_DIR / "v_uptu_paradas.shp")
lineas     = gpd.read_file(BASE_DIR / "v_uptu_lsv.shp")

# Nos aseguramos de que los tres estén en metros (por si algún archivo viniera
# en grados). to_crs no hace nada si ya están en 32721.
municipios = municipios.to_crs(CRS_METROS)
paradas    = paradas.to_crs(CRS_METROS)
lineas     = lineas.to_crs(CRS_METROS)

#%%

# Arreglamos geometrías inválidas (autointersecciones) para que los cálculos
# de área e intersección no fallen.
municipios["geometry"] = municipios.geometry.buffer(0)

# Sacamos geometrías nulas o vacías (rompen los recortes espaciales).
def sin_geom_vacias(gdf):
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

paradas = sin_geom_vacias(paradas)
lineas  = sin_geom_vacias(lineas)

print("Municipios:", len(municipios), "| Paradas (filas):", len(paradas),
      "| Líneas (tramos):", len(lineas))
print("Columnas municipios:", list(municipios.columns))

# Etiqueta legible para cada municipio (el código es una letra: A, B, C, ...)
municipios["muni"] = "Municipio " + municipios["MUNICIPIO"].astype(str).str.strip()

# 2. Una parada física puede aparecer muchas veces

# En v_uptu_paradas hay una fila por cada (parada × línea que la usa). Para
# contar PARADAS nos quedamos con ubicaciones únicas (COD_UBIC_P); para contar
# LÍNEAS usamos DESC_LINEA. Guardamos las dos cosas.
paradas_unicas = paradas.drop_duplicates(subset="COD_UBIC_P").copy()
print(f"Paradas físicas únicas: {len(paradas_unicas)} "
      f"(de {len(paradas)} filas parada por línea)")

# 3. ¿En qué municipio cae cada parada? (unión espacial punto-en-polígono)

paradas_en_muni = gpd.sjoin(
    paradas[["COD_UBIC_P", "DESC_LINEA", "geometry"]],
    municipios[["muni", "geometry"]],
    how="inner", predicate="within",
)

# Paradas únicas por municipio y líneas distintas por municipio
resumen_paradas = (paradas_en_muni
    .groupby("muni")
    .agg(n_paradas=("COD_UBIC_P", "nunique"),
         n_lineas=("DESC_LINEA", "nunique"))
    .reset_index())

# 4. ¿Cuántos km de recorrido pasan por dentro de cada municipio?

# Recortamos las líneas contra cada polígono (clip) y sumamos su largo en km.
km_por_muni = {}
for _, m in municipios.iterrows():
    tramos = gpd.clip(lineas[["geometry"]], m.geometry)
    km_por_muni[m["muni"]] = tramos.length.sum() / 1000
resumen_lineas = (pd.Series(km_por_muni, name="km_recorrido")
                  .rename_axis("muni").reset_index())


# 5. Cobertura: ¿qué parte del municipio está a ≤300 m de una parada?

# Dibujamos un círculo de 300 m alrededor de cada parada, los unimos en una
# sola mancha (el "área servida") y vemos cuánto de esa mancha cae dentro de
# cada municipio.
area_servida = paradas_unicas.buffer(RADIO_CAMINABLE).union_all()
area_servida = gpd.GeoSeries([area_servida], crs=CRS_METROS)

municipios["area_km2"] = municipios.area / 1e6
municipios["area_servida_km2"] = municipios.geometry.intersection(
    area_servida.iloc[0]).area / 1e6
municipios["cobertura_300m"] = (
    100 * municipios["area_servida_km2"] / municipios["area_km2"])

# 6. Juntamos todo en una tabla por municipio

tabla = (municipios[["muni", "area_km2", "cobertura_300m", "geometry"]]
         .merge(resumen_paradas, on="muni", how="left")
         .merge(resumen_lineas, on="muni", how="left"))

tabla[["n_paradas", "n_lineas", "km_recorrido"]] = (
    tabla[["n_paradas", "n_lineas", "km_recorrido"]].fillna(0))

# Densidades (lo que permite comparar municipios de tamaños muy distintos)
tabla["paradas_km2"] = tabla["n_paradas"] / tabla["area_km2"]
tabla["km_recorrido_km2"] = tabla["km_recorrido"] / tabla["area_km2"]

# 7. Índice de accesibilidad (0 a 100)

# No hay una única "verdad": combinamos cuatro señales, cada una llevada a una
# escala 0-1 (0 = el peor municipio, 1 = el mejor) y promediadas. Es simple y
# transparente; se puede discutir el peso de cada parte.
def accesib_0_1(s):
    return (s - s.min()) / (s.max() - s.min())

componentes = ["paradas_km2", "km_recorrido_km2", "n_lineas", "cobertura_300m"]
tabla["indice_accesibilidad"] = (
    100 * tabla[componentes].apply(accesib_0_1).mean(axis=1))

# Ordenamos de mayor a menor accesibilidad
tabla = tabla.sort_values("indice_accesibilidad", ascending=False)

cols_mostrar = ["muni", "area_km2", "n_paradas", "paradas_km2", "n_lineas",
                "km_recorrido", "cobertura_300m", "indice_accesibilidad"]
print("\n=== Accesibilidad al transporte por municipio ===")
print(tabla[cols_mostrar].to_string(index=False, float_format=lambda x: f"{x:,.1f}"))

# Guardamos la tabla (sin la geometría) para reutilizarla
tabla[cols_mostrar].to_csv(SALIDA / "accesibilidad_por_municipio.csv",
                           index=False, encoding="utf-8-sig")

# 8. Mapas

muni_geo = gpd.GeoDataFrame(tabla, geometry="geometry", crs=CRS_METROS)

def mapa_coropletico(ax, columna, titulo, etiqueta):
    muni_geo.plot(column=columna, ax=ax, cmap="YlGnBu", edgecolor="white",
                  linewidth=0.6, legend=True,
                  legend_kwds={"label": etiqueta, "shrink": 0.6})
    for _, r in muni_geo.iterrows():
        c = r.geometry.representative_point()
        ax.annotate(r["muni"].replace("Municipio ", ""), (c.x, c.y),
                    ha="center", va="center", fontsize=9, fontweight="bold")
    ax.set_title(titulo, fontsize=12)
    estetica(ax)

# 8a. Panel con los tres indicadores principales
fig, axes = plt.subplots(1, 3, figsize=(18, 7))
mapa_coropletico(axes[0], "paradas_km2",
                 "Densidad de paradas", "Paradas por km²")
mapa_coropletico(axes[1], "cobertura_300m",
                 f"Cobertura a ≤ {RADIO_CAMINABLE} m", "% del área del municipio")
mapa_coropletico(axes[2], "indice_accesibilidad",
                 "Índice de accesibilidad", "0 (menos) a 100 (más)")
fig.suptitle("Accesibilidad al transporte público por municipio — Montevideo",
             fontsize=15)
fig.tight_layout()
fig.savefig(SALIDA / "mapas_accesibilidad.png", dpi=150, bbox_inches="tight")

# 8b. Mapa de contexto: paradas y recorridos sobre los municipios 

fig2, ax = plt.subplots(figsize=(9, 9))
muni_geo.boundary.plot(ax=ax, color="0.5", linewidth=0.8)
lineas.plot(ax=ax, color="tab:blue", linewidth=0.3, alpha=0.4)
paradas_unicas.plot(ax=ax, color="tab:red", markersize=1, alpha=0.5)
ax.set_title("Paradas (rojo) y recorridos de líneas (azul) sobre los municipios")
estetica(ax)
fig2.tight_layout()
fig2.savefig(SALIDA / "mapa_paradas_y_lineas.png", dpi=150, bbox_inches="tight")

# 9. Ranking en barras

fig3, ax = plt.subplots(figsize=(9, 5))
orden = tabla.sort_values("indice_accesibilidad")
ax.barh(orden["muni"], orden["indice_accesibilidad"], color="teal")
ax.set_xlabel("Índice de accesibilidad (0–100)")
ax.set_title("Ranking de municipios por accesibilidad al transporte")
ax.grid(axis="x", alpha=0.3)
for lado in ("top", "right"):
    ax.spines[lado].set_visible(False)
fig3.tight_layout()
fig3.savefig(SALIDA / "ranking_accesibilidad.png", dpi=150, bbox_inches="tight")

plt.show()

print(f"\nListo. Mapas y tabla guardados en: {SALIDA.resolve()}")

# Los municipios centrales concentran más paradas por km², más líneas
# y casi toda su superficie a una cuadra y media de una parada; los periféricos,
# más grandes y menos densos, quedan más abajo en el índice. Es un retrato de
# la OFERTA de transporte, no de la demanda: lo ideal sería ponderar por
# población o por empleo (datos que no están en esta carpeta) para hablar de
# accesibilidad "por persona".
