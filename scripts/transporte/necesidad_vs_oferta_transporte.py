# =============================================================================
# ¿El transporte llega donde más se necesita?
# Cruce de la OFERTA de transporte con la NECESIDAD socioeconómica, por municipio
# =============================================================================
# IMPORTANTE sobre los nombres: acá NO medimos "demanda" en el sentido económico
# (los viajes que realmente se hacen, los boletos vendidos). La oferta persigue
# a esa demanda efectiva, así que con ella esperaríamos correlación POSITIVA.
# Lo que medimos es la NECESIDAD / DEPENDENCIA del transporte público: quién
# depende del ómnibus porque no tiene auto ni alternativas pagas (pobreza), no
# maneja (niños y adultos mayores) y vive amontonado (densidad). La necesidad NO
# tiene por qué seguir a la oferta: si da negativa, es una señal de INEQUIDAD
# (el sistema sirve al centro denso y rico más que a la periferia que lo necesita).
#
# La necesidad de transporte público es mayor donde hay:
#   - más gente junta            -> densidad de población (hab/km²)
#   - más "pasajeros cautivos"   -> pobreza (menos autos) y población
#                                   dependiente (niños + adultos mayores)
#
# Datos (clave "municipio" = A, B, C, CH, ...):
#   - salidas/tablas/accesibilidad_por_municipio.csv  (la oferta ya calculada)
#   - datos/crudos/poblacion/edades.csv          (población por edad)
#   - datos/crudos/poblacion/socioeconomia.csv   (pobreza, empleo)
#   - datos/crudos/poblacion/movilidad.csv       (dónde trabaja/estudia la gente)
#   - datos/crudos/municipios/sig_municipios.shp (polígonos, para los mapas)
#
# Corré antes scripts/transporte/accesibilidad_transporte.py (genera la oferta).
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
POB     = RAIZ / "datos" / "crudos" / "poblacion"
MUNI    = RAIZ / "datos" / "crudos" / "municipios"
FIGURAS = RAIZ / "salidas" / "figuras" / "transporte"
TABLAS  = RAIZ / "salidas" / "tablas"
OFERTA  = TABLAS / "accesibilidad_por_municipio.csv"
FIGURAS.mkdir(parents=True, exist_ok=True)
TABLAS.mkdir(parents=True, exist_ok=True)

CRS_METROS = 32721

def a_0_1(s):
    return (s - s.min()) / (s.max() - s.min())

def estetica(ax):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.grid(alpha=0.3)

# =============================================================================
# 1. La OFERTA que ya calculamos
# =============================================================================
if not OFERTA.exists():
    raise FileNotFoundError(
        "No encuentro la oferta. Corré primero scripts/transporte/accesibilidad_transporte.py")
oferta = pd.read_csv(OFERTA)
oferta["municipio"] = oferta["muni"].str.replace("Municipio ", "", regex=False).str.strip()

# =============================================================================
# 2. La NECESIDAD socioeconómica: densidad + pobreza + dependientes
# =============================================================================
# --- 2a. Población total y población dependiente (niños + adultos mayores) ---
edades = pd.read_csv(POB / "edades.csv")
DEPENDIENTES = ["pob_0_a_4", "pob_5_a_9", "pob_10_a_14",          # 0 a 14 años
                "pob_80_a_84", "pob_85_a_89", "pob_90+"]           # 80 y más
poblacion = edades.groupby("municipio")["total"].sum().rename("poblacion")
dependiente = (edades[edades["rango_edad"].isin(DEPENDIENTES)]
               .groupby("municipio")["total"].sum())
necesidad = pd.DataFrame({"poblacion": poblacion})
necesidad["pct_dependiente"] = 100 * dependiente / poblacion

# --- 2b. Pobreza y empleo ----------------------------------------------------
socio = pd.read_csv(POB / "socioeconomia.csv")
necesidad = necesidad.merge(
    socio.set_index("municipio")[["pobreza_personas_total", "to_total", "td_total"]],
    left_index=True, right_index=True).rename(
    columns={"pobreza_personas_total": "pobreza",
             "to_total": "tasa_empleo", "td_total": "tasa_desempleo"})

# --- 2c. ¿Cuántos trabajan FUERA de su localidad? (viajes entre zonas) -------
movil = pd.read_csv(POB / "movilidad.csv", encoding="latin1")
fuera = (movil[movil["concepto"].isin(["Otra Localidad de Mvd", "Otro Dpto"])]
         .groupby("municipio")["lugar_trabajo_pct"].sum() * 100)
necesidad["pct_trabaja_fuera"] = fuera

# -----------------------------------------------------------------------------
# NOTA sobre tasa_empleo, tasa_desempleo y pct_trabaja_fuera:
# Estas tres variables se calculan como CONTEXTO socioeconómico y como posibles
# señales de necesidad, pero NO entran en el índice de necesidad ni en los
# gráficos: el índice usa solo densidad + pobreza + pct_dependiente, y la lista
# "cols" no las incluye, así que tampoco llegan al CSV de salida.
# Se dejan calculadas a propósito, por tres motivos:
#   - Para dejar registro de la exploración que se hizo y de las variables que se evaluaron.
#   - tasa_empleo / tasa_desempleo: quedan disponibles para describir el perfil
#     de cada municipio si se quiere ampliar el análisis.
#   - pct_trabaja_fuera: se evaluó como cuarta señal de necesidad (viajes entre
#     zonas), pero se descartó porque ~86% trabaja en su misma localidad y varía
#     muy poco entre municipios, por lo que aportaba poco al índice.
# -----------------------------------------------------------------------------

# =============================================================================
# 3. Densidad de población (necesita el área, que ya está en la oferta)
# =============================================================================
necesidad = necesidad.merge(oferta.set_index("municipio")[["area_km2"]],
                            left_index=True, right_index=True)
necesidad["densidad_pob"] = necesidad["poblacion"] / necesidad["area_km2"]

# =============================================================================
# 4. Índice de NECESIDAD (0 a 100), misma receta que el de oferta
# =============================================================================
COMP_NECESIDAD = ["densidad_pob", "pobreza", "pct_dependiente"]
necesidad["indice_necesidad"] = 100 * necesidad[COMP_NECESIDAD].apply(a_0_1).mean(axis=1)

# =============================================================================
# 5. El CRUCE: oferta frente a necesidad
# =============================================================================
cruce = (oferta.set_index("municipio")
         .join(necesidad.drop(columns="area_km2"))   # area_km2 ya viene en la oferta
         .reset_index())

# Oferta "por persona", no solo por km²
cruce["paradas_1000hab"] = 1000 * cruce["n_paradas"] / cruce["poblacion"]

# Brecha = oferta − necesidad (índices 0-100). >0 sobre-atendido, <0 sub-atendido.
cruce["brecha"] = cruce["indice_accesibilidad"] - cruce["indice_necesidad"]
cruce = cruce.sort_values("brecha")

r = cruce["indice_accesibilidad"].corr(cruce["indice_necesidad"])

cols = ["municipio", "poblacion", "densidad_pob", "pobreza", "pct_dependiente",
        "frecuencia_media", "paradas_1000hab", "cobertura_300m",
        "indice_necesidad", "indice_accesibilidad", "brecha"]
print("\n=== Oferta de transporte frente a necesidad socioeconómica ===")
print(cruce[cols].to_string(index=False, float_format=lambda x: f"{x:,.1f}"))
print(f"\nCorrelación oferta–necesidad: r = {r:.2f}")
print("(positiva: la oferta acompaña a la necesidad; NEGATIVA: va al revés = inequidad)")
cruce[cols].to_csv(TABLAS / "cruce_oferta_necesidad.csv",
                   index=False, encoding="utf-8-sig")

# =============================================================================
# 6. Gráfico 1: oferta vs necesidad
# =============================================================================
fig, ax = plt.subplots(figsize=(8, 8))
sc = ax.scatter(cruce["indice_necesidad"], cruce["indice_accesibilidad"],
                s=cruce["poblacion"] / 400, c=cruce["brecha"],
                cmap="RdYlBu", edgecolor="black", zorder=3)
lim = [-5, 105]
ax.plot(lim, lim, "--", color="grey", label="oferta = necesidad")
for _, r_ in cruce.iterrows():
    ax.annotate(r_["municipio"], (r_["indice_necesidad"], r_["indice_accesibilidad"]),
                xytext=(6, 4), textcoords="offset points", fontweight="bold")
ax.set(xlim=lim, ylim=lim,
       xlabel="Índice de NECESIDAD (densidad + pobreza + dependientes)",
       ylabel="Índice de OFERTA (accesibilidad, con frecuencia)",
       title="¿El transporte llega donde más se necesita?\n"
             "(el tamaño del punto es la población)")
ax.text(80, 8, "Mucha necesidad,\npoca oferta", color="firebrick", ha="center", fontsize=9)
ax.text(20, 95, "Poca necesidad,\nmucha oferta", color="navy", ha="center", fontsize=9)
plt.colorbar(sc, ax=ax, shrink=0.6, label="Brecha (oferta − necesidad)")
ax.legend(loc="lower right")
estetica(ax)
fig.tight_layout()
fig.savefig(FIGURAS / "oferta_vs_necesidad.png", dpi=150, bbox_inches="tight")

# =============================================================================
# 7. Gráfico 2: la brecha, municipio por municipio
# =============================================================================
fig2, ax = plt.subplots(figsize=(9, 5))
colores = np.where(cruce["brecha"] >= 0, "tab:blue", "tab:red")
ax.barh(cruce["municipio"], cruce["brecha"], color=colores)
ax.axvline(0, color="black", linewidth=0.8)
ax.set(xlabel="Brecha = oferta − necesidad",
       title="Municipios sub-atendidos (rojo) y sobre-atendidos (azul)")
estetica(ax)
fig2.tight_layout()
fig2.savefig(FIGURAS / "brecha_oferta_necesidad.png", dpi=150, bbox_inches="tight")

# =============================================================================
# 8. Gráfico 3: frecuencia vs pobreza (¿el "mejor" servicio va a los más pobres?)
# =============================================================================
fig3, ax = plt.subplots(figsize=(8, 6))
ax.scatter(cruce["pobreza"], cruce["frecuencia_media"],
           s=cruce["poblacion"] / 400, color="tab:purple",
           edgecolor="black", zorder=3)
for _, r_ in cruce.iterrows():
    ax.annotate(r_["municipio"], (r_["pobreza"], r_["frecuencia_media"]),
                xytext=(6, 4), textcoords="offset points", fontweight="bold")
ax.set(xlabel="Pobreza (% de personas)",
       ylabel="Frecuencia: ómnibus por hora en pico (promedio por parada)",
       title="¿El servicio más frecuente va a los municipios más pobres?")
estetica(ax)
fig3.tight_layout()
fig3.savefig(FIGURAS / "frecuencia_vs_pobreza.png", dpi=150, bbox_inches="tight")

# =============================================================================
# 9. Mapa de equidad: dónde falta transporte respecto de la necesidad
# =============================================================================
municipios = gpd.read_file(MUNI / "sig_municipios.shp").to_crs(CRS_METROS)
municipios["municipio"] = municipios["MUNICIPIO"].astype(str).str.strip()
muni_geo = municipios.merge(cruce, on="municipio")

fig4, ax = plt.subplots(figsize=(9, 9))
tope = np.abs(cruce["brecha"]).max()
muni_geo.plot(column="brecha", ax=ax, cmap="RdYlBu", vmin=-tope, vmax=tope,
              edgecolor="white", linewidth=0.6, legend=True,
              legend_kwds={"label": "Brecha oferta − necesidad", "shrink": 0.6})
for _, r_ in muni_geo.iterrows():
    c = r_.geometry.representative_point()
    ax.annotate(r_["municipio"], (c.x, c.y), ha="center", va="center",
                fontsize=10, fontweight="bold")
ax.set_title("Mapa de equidad del transporte\n"
             "rojo: mucha necesidad y poca oferta  ·  azul: al revés")
ax.set_axis_off()
fig4.tight_layout()
fig4.savefig(FIGURAS / "mapa_equidad_transporte.png", dpi=150, bbox_inches="tight")

plt.show()
print(f"\nListo. Gráficos en {FIGURAS}, tabla en {TABLAS}")
# =============================================================================
# Lectura: la correlación negativa NO es un error: medimos NECESIDAD, no demanda
# efectiva. Dice que la oferta (más paradas, más cobertura y ómnibus más seguido)
# se concentra en el centro, justo donde hay MENOS pobreza, mientras la periferia
# con más hogares pobres y más dependientes recibe menos de todo. Parte del signo
# es estructural: en Montevideo pobreza (periferia) y densidad (centro) están
# geográficamente opuestas, así que el resultado confirma —no inventa— la división
# centro-periferia. Limitación: es la hora pico de la mañana de un día hábil.
# =============================================================================
