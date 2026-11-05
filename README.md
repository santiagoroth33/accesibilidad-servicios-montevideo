# datos-espaciales

#PLANTEO DEL PROBLEMA: Accesibilidad a Servicios Básicos en Hogares Montevideanos desde una Perspectiva Espacial

1. Contexto y Relevancia

La calidad de vida en zonas urbanas está directamente vinculada a la proximidad y acceso a servicios básicos esenciales. En Montevideo, la distribución desigual de hospitales, transporte público y escuelas genera disparidades territoriales que afectan a los hogares de manera diferenciada según su ubicación geográfica. Comprender estas distancias es fundamental para identificar áreas con déficit de servicios y orientar políticas de planificación urbana.
    
2. Pregunta Central de Investigación

¿Cuál es la distancia promedio desde los hogares montevideanos a los servicios básicos (hospitales, transporte público y escuelas) y existen disparidades espaciales significativas según zona geográfica o tipo de vivienda?

3. Problema Específico

Identificar y mapear las brechas de accesibilidad a servicios básicos en Montevideo mediante análisis espacial, permitiendo:
	
•	Determinar qué áreas geográficas tienen mayor o menor proximidad a cada servicio

•	Clasificar hogares según su nivel de accesibilidad (óptima, media, crítica)

•	Identificar zonas vulnerables o desatendidas en términos de cobertura de servicios

•	Visualizar patrones espaciales de distribución de servicios vs. ubicación de hogares
    
4. Hipótesis Inicial

Suponemos que existen zonas de Montevideo, particularmente en áreas periféricas, donde la distancia a servicios básicos es significativamente mayor a la de zonas céntricas, lo que afecta la calidad de vida y accesibilidad de sus habitantes.
    
5. Variables de Análisis
	
•	Espaciales: Coordenadas geográficas de hogares y servicios

•	Distancia: Distancia euclidiana o por red vial desde hogares a servicios

•	Cobertura: Cantidad de servicios disponibles por radio de distancia

•	Zona: Identificación de áreas geográficas o barrios

## Estructura del repositorio

```
datos-espaciales/
├── datos/
│   ├── crudos/        # datos originales, no se editan
│   │   ├── municipios/    # sig_municipios.shp, poblacion_municipios.xlsx
│   │   ├── poblacion/     # edades, socioeconomía, movilidad, población educativa, cobertura de salud
│   │   ├── salud/         # policlínicas, uptu_salud.csv
│   │   ├── educacion/     # uptu_educacion.csv
│   │   └── transporte/    # paradas, líneas y horarios del STM
│   └── procesados/    # capas armadas a partir de los crudos (GeoPackage)
├── notebooks/         # proyecto_cdd.ipynb (análisis principal)
├── scripts/
│   └── transporte/    # accesibilidad y necesidad vs. oferta de transporte
├── salidas/
│   ├── figuras/       # gráficos por tema (salud, educacion, transporte)
│   ├── mapas/         # mapas HTML (no se suben, se regeneran con el notebook)
│   └── tablas/        # CSV generados por los scripts
└── docs/              # bitácora, decisiones y material de referencia
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

### Datos que hay que descargar aparte

`datos/crudos/transporte/uptu_pasada_variante.csv` (~61 MB, horarios de ómnibus por parada) no está en el repositorio por su tamaño. Descargarlo del [Catálogo de Datos Abiertos](https://catalogodatos.gub.uy/) (Intendencia de Montevideo, horarios del transporte urbano por parada) y guardarlo en esa carpeta.

### Orden de ejecución (transporte)

```bash
python scripts/transporte/accesibilidad_transporte.py
```

```bash
python scripts/transporte/necesidad_vs_oferta_transporte.py
```