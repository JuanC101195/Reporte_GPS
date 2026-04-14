# Reporte de Anomalías GPS - Flota de Vehículos Cartagena

Sistema de análisis de datos GPS para la flota de vehículos en Cartagena (Colombia). Procesa reportes crudos de GPS, extrae métricas operativas y genera un **dashboard ejecutivo HTML** interactivo enfocado en detectar anomalías operativas, paradas no autorizadas y patrones recurrentes en lugares desconocidos — todo pensado para que el dueño de la flota decida en 10 segundos a quién llamar a la oficina.

> 
> 👉 **[VER EL ÚLTIMO REPORTE INTERACTIVO EN LÍNEA](https://juanc101195.github.io/Reporte_GPS/)** 👈

![CI](https://github.com/JuanC101195/Reporte_GPS/actions/workflows/ci.yml/badge.svg)

## 🚀 Características Principales

### Dashboard ejecutivo (orientado a decisión)
- **KPI bar** con los 4 números que importan: alertas críticas, horas en zonas desconocidas, conductores monitoreados, conductores en alerta roja.
- **Top conductores para revisar** — tarjetas clickeables con los 5 peores ofensores, ordenados por un **score de sospecha** compuesto (horas, paradas anómalas, lugares frecuentes, actividad fuera de horario).
- **Coloreado por severidad** en todas las tablas (rojo/amarillo/azul según riesgo) — el ojo del supervisor detecta los casos críticos al instante.
- **Miniaturas de Street View + satélite** generadas automáticamente con Google Maps Platform (ver sección "Vista previa automática" más abajo).

### Motor analítico
- **Análisis de Zonas Conocidas:** identificación automática de oficinas, bases y casas de conductores mediante `haversine` con radio de 200m (unificado en `src/geo.py`).
- **Clasificación de paradas:** distingue anomalías genuinas vs. paradas legítimas en zonas conocidas — el reporte filtra automáticamente las legítimas para que sólo veas lo sospechoso.
- **Detección de lugares frecuentes desconocidos:** clusterización por conductor de puntos visitados ≥ 2 veces, con foto embebida, zona de referencia más cercana y timestamps de primera/última visita.
- **Recurrencia por parada:** cada parada larga viene con un contador **"# veces"** — cuántas veces el mismo conductor ha estado dentro de 50m de ese punto en TODO el dataset. Patrón = rojo inmediato.
- **Rango horario explícito:** cada parada muestra `Inicio → Fin` (no sólo la hora de inicio), eliminando la ambigüedad "¿empezó aquí o terminó aquí?".
- **Coincidencias de ruta:** detección de 2+ vehículos en el mismo radio (150m) durante el mismo bloque horario — útil para encontrar reuniones no autorizadas.
- **Performance vectorizada:** `add_derived_columns` usa `numpy.haversine_matrix` broadcasted, 1.6× más rápido que el loop original.

## 📁 Estructura del Proyecto

```text
Reporte_GPS/
│
├── cli.py                    # Interfaz CLI principal (argparse)
├── zonas.json                # Zonas conocidas editables (lat/lon/radio/tipo)
├── pyproject.toml            # Config de ruff, black y pytest
├── requirements.txt          # Dependencias runtime
├── requirements-dev.txt      # Dependencias de desarrollo (pytest, ruff, black)
├── .gitignore                # Bloquea PII, reportes pesados, .env
├── .github/workflows/ci.yml  # CI: ruff + pytest en cada push/PR
├── README.md                 # Este archivo
│
├── src/
│   ├── pipeline.py           # Orquestador (load → validate → transform → HTML → PDF)
│   ├── io_loader.py          # Carga Excel/CSV con doble cabecera + alias normalization
│   ├── transform.py          # Parsing vectorizado, matching por haversine broadcasted
│   ├── geo.py                # haversine_metros (escalar) + haversine_matrix (numpy)
│   ├── maps_preview.py       # Construcción de URLs Street View + Static Map + link Maps
│   ├── validation.py         # Validación de schema y reportes de calidad CSV
│   ├── schema.py             # Columnas canónicas, alias, formatos de fecha
│   ├── report_anomalias.py   # Renderer HTML ejecutivo (KPIs, Top Ofensores, tablas)
│   ├── report_html.py        # Renderer HTML clásico por conductor (Folium)
│   ├── report_pdf.py         # Export a PDF via pdfkit (opcional)
│   │
│   └── anomalias/            # Lógica analítica pura, desacoplada del renderer
│       ├── __init__.py       # Exporta la API pública
│       └── core.py           # Clasificación, clustering, ranking, score de sospecha
│
├── tests/                    # 67 tests con pytest
│   ├── test_geo.py           # haversine escalar y matriz broadcasted
│   ├── test_transform.py     # Parsers, _match_nearest, add_derived_columns
│   ├── test_io_loader.py     # Carga Excel/CSV con alias
│   ├── test_validation.py    # parse_dates, validate_schema, quality reports
│   ├── test_ranking.py       # Score de sospecha + niveles ROJO/AMARILLO/VERDE
│   ├── test_maps_preview.py  # Builders de URL + fallback sin API key
│   ├── test_report_anomalias.py  # Clasificación, clusters, coincidencias
│   ├── bench_transform.py    # Benchmark de performance (no parte del suite)
│   ├── smoke_maps_preview.py # Smoke test end-to-end con API key real
│   ├── audit_report.py       # Inspector de estructura del HTML generado
│   └── inspect_html.py       # Contador de secciones / URLs en el HTML
│
├── docs/                     # Dashboard público servido por GitHub Pages
│   ├── index.html            # Reporte publicado (regenerado sin API key embebida)
│   └── img/                  # Imágenes legacy del flujo manual de fotos
│
└── reportes/                 # Salida local del CLI (ignorado por git)
    ├── reporte_anomalias.html # Dashboard generado localmente (con miniaturas)
    ├── img/                  # Fotos opcionales del flujo manual UBICACION.xlsx
    └── logs/                 # Logs del pipeline
```

## 🛠 Instalación y Configuración

1. **Clonar el repositorio:**
   ```bash
   git clone <URL_DEL_REPOSITORIO>
   cd analisis_vehiculos_cartagena
   ```

2. **Crear y activar un entorno virtual (VENV):**
   Aísla y previene conflictos de paquetes en tu sistema general.
   ```bash
   python -m venv .venv
   
   # En Windows PowerShell corre:
   .\.venv\Scripts\Activate.ps1
   
   # En Mac/Linux corre:
   source .venv/bin/activate
   ```

3. **Instalación de Dependencias:**
   ```bash
   # Runtime (para correr el CLI en producción)
   pip install -r requirements.txt

   # Dev (además incluye pytest, ruff, black, pre-commit)
   pip install -r requirements-dev.txt
   ```

## 💻 Uso y Comandos CLI

El proyecto está diseñado pensando en invocaciones modulares vía línea de comandos.

> **Aviso importante para Windows (PowerShell):** Para que las terminales reconozcan las tildes y ñ es vital inyectar el formato antes de correr por primera vez cada sesión:
> ```powershell
> $env:PYTHONIOENCODING="utf-8"
> ```

**Generación del Reporte Estándar:**
Extrae registros de Excel, localiza anomalías, depura duplicados estáticos y compila HTMLs.
```bash
python cli.py anomalias --input "trabajadores.xlsx" --sheet "Hoja2" --out-dir reportes --periodo "Semana Actual"
```

**Generación de Reporte Mapeado Fotográficamente:**
Si quieres visualizar las fotos capturadas en el reporte, asegúrate de:
1. Depositar los archivos `.jpeg`/`.png` físicamente en `reportes/img/`.
2. Incluir una tabla de Mapeo de fotos (`--photos-file`) que asocie Foto -> Coordenada.
```bash
python cli.py anomalias --input "trabajadores.xlsx" --sheet "Hoja2" --photos-file "UBICACION.xlsx"
```

### 📊 Cómo leer el dashboard ejecutivo

El HTML generado está pensado para **decidir en 10 segundos**. Lee el reporte en este orden:

1. **KPI bar (arriba del todo).** Cuatro números te dan la foto general de la semana:
   - *Alertas críticas* — total de paradas largas (>30 min) en zonas desconocidas.
   - *Horas en zonas desconocidas* — cuánto tiempo total gastó la flota fuera de bases.
   - *Conductores monitoreados* — cuántos vehículos están activos.
   - *En alerta (rojo)* — cuántos conductores superaron el umbral de sospecha.

2. **Panel "🔥 Top conductores para revisar".** Las 5 tarjetas te dicen **a quién llamar primero**. Cada una muestra el nombre, la placa, un Street View del peor punto que visitó y un breakdown del score (horas desconocidas · paradas >30min · lugares frecuentes · horas fuera horario). Hacé clic en una tarjeta y te lleva directo al bloque de clusters de ese conductor más abajo.

3. **Panel "📋 Tablas solicitadas".** Cinco secciones colapsables con la evidencia:
   - *Ubicación repetida semanal por trabajador* — puntos visitados ≥ 2 veces.
   - *Tiempo y visitas en oficina* — control de productividad en bases conocidas.
   - *Coincidencias de ruta* — 2+ vehículos en el mismo radio al mismo tiempo.
   - *Lugares frecuentes desconocidos por conductor* — tabla con miniaturas Street View.
   - *Paradas mayores a 30 minutos en zonas desconocidas* — filtrada automáticamente para ocultar paradas legítimas en bases.

**Lectura del coloreado:**
| Color de fila | Significado |
|---|---|
| 🔴 Rojo (`row-crit`) | Nocturna, duración > 4h, o ≥ 5 visitas al mismo punto |
| 🟡 Amarillo (`row-alta`) | Fuera de horario, > 2h, o 3-4 visitas |
| 🔵 Azul (`row-media`) | Parada rara aislada, baja prioridad |

**Lectura del score de sospecha** (configurable en `src/anomalias/core.py`):

```
score = horas_desconocidas   × 0.5   (señal débil — es su trabajo)
      + paradas_anomalas     × 3     (moderada)
      + lugares_frecuentes   × 15    (señal principal)
      + horas_fuera_horario  × 4     (moderada)
```

Umbrales: **ROJO ≥ 30**, **AMARILLO ≥ 12**, **VERDE** el resto. La calibración está pensada para flotas de delivery con clientes recurrentes donde "horas en zonas desconocidas" no es suspicioso por sí solo — lo que importa es **visitar el mismo punto desconocido 3+ veces**.

---

### 🗺️ Vista previa automática con Google Maps

Además del flujo manual de fotos, el reporte puede mostrar **miniaturas automáticas** de cada parada (Street View + vista satélite) usando la API de Google Maps Platform. No requiere que agregues fotos manualmente: las URLs se construyen al vuelo a partir de las coordenadas y se embeben como `<img>` en el HTML.

**Configuración:**
1. Crea una API key en Google Cloud Console con las APIs **Street View Static API** y **Maps Static API** habilitadas.
2. **Obligatorio — 3 capas de blindaje:**
   - **HTTP Referrer Restriction** (obligatorio si vas a publicar en GitHub Pages): seleccioná "Sitios web" y agregá `https://TU_USUARIO.github.io/*` y `https://TU_USUARIO.github.io/Reporte_GPS/*`.
   - **Quota cap**: bajá `Unsigned requests per day` a ~3.000 en ambas APIs.
   - **Budget alert** de US$1 con avisos al 50/90/100%.
3. Exporta la key como variable de entorno (persistente en User scope):
   ```powershell
   [System.Environment]::SetEnvironmentVariable("GOOGLE_MAPS_API_KEY", "TU_KEY", "User")
   ```
4. Cierra y reabre la terminal para que aplique.
5. Al correr `cli.py anomalias`, las miniaturas aparecerán automáticamente en las tablas de **Top Ofensores**, **Lugares frecuentes desconocidos** y **Paradas mayores a 30 minutos**.

**Degradación grácil:** si la variable no está configurada, el reporte se genera igual pero con un link de texto `"Ver en Maps"` en vez de las miniaturas. No rompe el flujo.

**Versión local vs versión publicada en GitHub Pages:**

Con la HTTP Referrer Restriction activa, las miniaturas **funcionan desde GitHub Pages** (el navegador envía el header `Referer` correcto) pero **dejan de funcionar cuando abrís el HTML local** directamente en el navegador (`file:///...`), porque ese protocolo no envía un Referer válido.

Opciones si querés las miniaturas también en el reporte local:

- **(a)** Abrí el HTML local vía un servidor HTTP simple: `python -m http.server 8000 --directory reportes` y navegá a `http://localhost:8000/reporte_anomalias.html`. El navegador entonces envía un Referer de `localhost` que tendrás que agregar a la lista de referrers permitidos.
- **(b)** Crear una **segunda API key** sin HTTP Referrer Restriction (sólo con API restrictions) para uso exclusivamente local, y usar la primera sólo para el sitio publicado.

**La key nunca se commitea al repo** — `.env` y variantes están en `.gitignore`. Para publicar el HTML en GitHub Pages se recomienda regenerarlo **sin** la env var de modo que caiga al fallback "Ver en Maps" (no expone la key), o con la key habilitada si ya tenés la referrer restriction activa.

## 🧪 Testing y Control de Calidad

La suite tiene **67 tests** organizados en 7 archivos, cubriendo desde los helpers geográficos de bajo nivel hasta el renderer ejecutivo. Cada push y cada PR contra `main` dispara un workflow en GitHub Actions que corre **ruff** (lint) y **pytest** (con coverage).

**Correr todo local:**

```bash
# Lint
ruff check .

# Tests con coverage
pytest --cov=src --cov-report=term-missing
```

**Cobertura por módulo (baseline actual):**

| Módulo | Coverage |
|---|---|
| `src/geo.py` | 100% |
| `src/maps_preview.py` | 100% |
| `src/schema.py` | 100% |
| `src/validation.py` | 91% |
| `src/anomalias/core.py` | 83% |
| `src/io_loader.py` | 77% |
| `src/transform.py` | 48% |

**Qué valida la suite:**

- Paradas cortas (< 30 min) nunca se clasifican como anomalía.
- Cálculo correcto de `haversine_metros` y `haversine_matrix` contra valores conocidos.
- `_paradas_largas` filtra correctamente zonas conocidas (por defecto `only_anomalas=True`).
- `ranking_conductores` ordena correctamente por score y asigna niveles ROJO/AMARILLO/VERDE.
- Score sigue la fórmula documentada (validado contra pesos `WEIGHT_*`).
- Carga de Excel con doble cabecera + normalización de aliases de columnas.
- `parse_coordinates_series` vectorizado con `str.extract`.
- `preview_cell_html` degrada grácilmente cuando no hay `GOOGLE_MAPS_API_KEY`.
- La API key nunca se filtra fuera de los `src` de las miniaturas en el HTML generado.

**Utilidades en `tests/` (no parte del suite de pytest):**

- `tests/bench_transform.py` — benchmark sintético de `add_derived_columns` para medir performance.
- `tests/smoke_maps_preview.py` — smoke test end-to-end que valida el flujo completo con una API key real.
- `tests/audit_report.py` e `tests/inspect_html.py` — inspectores del HTML generado para verificar estructura y conteos.

## ⚠️ Zonas Base Configurables

A diferencia de parámetros fijados duramente al código interno, si en el futuro se fundan nuevas bases vehiculares (O nuevas oficinas de Renta Ya / Casa Blanca), no necesitas conocimientos de programación. 
La adaptación resulta inmediata con solamente editar el diccionario de `zonas.json` adjuntando Latitud, Longitud y Nombre del sector.

## 🔮 Roadmap y Siguientes Pasos

### ✅ Hecho

- **Fase 1 — Higiene y bugs críticos:** eliminación de paths hardcodeados, arreglo del CLI `_anomalias` duplicado, `requirements.txt` recortado, `pyproject.toml` con config de `ruff`/`black`/`pytest`.
- **Fase ruff — Baseline de lint:** 100 errores → 0. Eliminación de código muerto (~40 líneas de variables construidas y nunca leídas).
- **Fase performance — Vectorización:** `add_derived_columns` pasó de iterar fila-a-fila con `.at[]` a usar `haversine_matrix` broadcasted. **1.6× más rápido** a 10k filas. Creación de `src/geo.py` compartido.
- **Fase 2 — Refactor arquitectónico:** `report_anomalias.py` pasó de **1343 → 509 LOC** (-62%). La lógica analítica pura se extrajo a `src/anomalias/core.py` (paquete independiente, testeable, sin dependencias de HTML/Folium). Habilita el plan de microservicio FastAPI descripto abajo.
- **Fase 2c — Demolición de código muerto:** eliminación de ~460 LOC de código muerto en el renderer (resumen ejecutivo roto, heatmap sin render, semáforo sin render, alertas críticas sin insertar). El HTML actual renderiza sólo lo que calcula.
- **Fase tests — Red de seguridad:** 4 tests → **67 tests**. Cobertura de `geo`, `transform`, `io_loader`, `validation`, `anomalias.core`, `maps_preview`. **GitHub Actions CI** con ruff + pytest en cada push.
- **Fase dashboard — Experiencia ejecutiva:** KPI bar, Top Ofensores con ranking por score de sospecha, coloreado de filas por severidad, filtrado automático de "Paradas > 30 min" a sólo zonas desconocidas.
- **Fase maps preview — Miniaturas automáticas:** integración con Google Maps Platform (Street View + Static Maps) con degradación grácil cuando no hay API key y configuración de HTTP Referrer Restriction para el sitio publicado.
- **Fase paradas enriquecidas — UX de director:** cada parada larga muestra `Inicio → Fin` explícito, contador de recurrencia `# veces` y miniaturas clickeables. Decisión en 5 segundos por fila.

### 🔭 Siguientes pasos (arquitectura empresarial)

Este proyecto funciona como un motor analítico avanzado mediante línea de comandos (CLI). Sin embargo, la **siguiente fase evolutiva** natural de este ecosistema contempla transformar esta herramienta en una **plataforma web empresarial**, orquestando nuestro potente código analítico actual bajo la robustez de **Java / Spring Boot**.

Los pasos a futuro diseñados para el escalamiento son:

1. **Migración a Plataforma Web Institucional (Backend Spring Boot):**
   Eliminar la dependencia de la consola local. Se desarrollará un portal administrativo donde los coordinadores y jefes accederán con credenciales seguras, pudiendo visualizar reportes interactivos bajo demanda directamente en sus navegadores.
2. **Persistencia Histórica (Database Relacional):**
   A través de **Spring Data JPA** y PostgreSQL/MySQL, almacenar las coordenadas, eventos y anomalías para generar trazabilidad de largo plazo. Esto permitirá responder preguntas como: *"¿Cuál ha sido la mejora general del conductor 'Jose' durante todo el año en comparación a Enero?"* sin tener que agrupar 50 Excels.
3. **Automatización Integral y Cron Jobs (`@Scheduled`):**
   Dejar en el pasado las descargas manuales de Excel diarias/semanales. Spring Boot se configurará para conectarse de madrugada a las APIs directas de los fabricantes de GPS (si disponen), alimentar automáticamente el flujo de procesamiento de Python y enviar alertas críticas al correo de los supervisores a primera hora de las anomalías ocurridas ayer.
4. **Sinergia en Microservicios (Java + Python):**
   El robusto sistema de analítica, cálculos espaciales (`haversine`) y cruce de variables en `Pandas` (Python) no se perderá: será encapsulado como un microservicio interno y ultrarrápido (vía `FastAPI`), sirviendo como el "cerebro matemático" mientras *Spring Boot* toma el papel de conductor maestro, frontend proxy, manejo de usuarios, correos y base de datos permanente.
