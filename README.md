# Reporte de Anomalías GPS - Flota de Vehículos Cartagena

Un robusto sistema de análisis de datos GPS para la flota de vehículos en Cartagena (Colombia). Este proyecto procesa reportes crudos de GPS, extrae métricas operativas y genera reportes HTML profesionales interactivos, enfocados en detectar anomalías operativas, paradas no autorizadas y visualización de rutas recurrentes.

> 
> 👉 **[VER EL ÚLTIMO REPORTE INTERACTIVO EN LÍNEA](https://juanc101195.github.io/Reporte_GPS/)** 👈

## 🚀 Características Principales

- **Análisis de Paradas y Zonas Conocidas:** Identificación automática de oficinas y bases (ej: Casa Blanca, Renta Ya) mediante radios de proximidad (200m).
- **Detección Lógica de Anomalías GPS:** 
  - Paradas no autorizadas *mayores a 30 minutos* en horario laboral (08:00 - 20:00).
  - Paradas nocturnas o fuera de la jornada de trabajo.
  - Identificación de visitas recurrentes a ubicaciones ajenas a las operaciones (≥ 2 visitas semanales).
- **Coincidencias de Ruta (Encuentros):** Alertas analíticas automáticas cuando dos o más vehículos coinciden en un radio < 150m durante el mismo bloque horario.
- **Topografía Visual de Reportes:** Generación de un Dashboard HTML general interactivo y de reportes individuales por conductor y placa con mapas en `Folium` incrustados.
- **Integración y Verificación Fotográfica:** Vinculación geométrica de imágenes a los reportes directamente desde Excel. Permite visualizar la foto real del lugar de la parada en el reporte junto con el mapa. 

## 📁 Estructura del Proyecto

```text
analisis_vehiculos_cartagena/
│
├── cli.py               # Interfaz de Línea de Comandos (CLI) principal
├── zonas.json           # Configuración de Zonas Conocidas y sus coordenadas (editable)
├── requirements.txt     # Dependencias de Python requeridas
├── .gitignore           # Ignora datos PII, cachés y reportes pesados en Git
├── README.md            # Documentación del proyecto (este archivo)
│
├── src/                 # Código fuente principal
│   ├── pipeline.py      # Orquestador del flujo de lectura, análisis y reporte
│   ├── io_loader.py     # Carga y parseo confiable de Excel/CSV
│   ├── transform.py     # Limpieza y normalización de textos, fechas y duraciones
│   ├── report_anomalias.py # Algoritmos de anomalías, paradas largas y cruces vehiculares
│   ├── report_html.py   # Motor de inyección de componentes para los Dashboards
│   └── schema.py        # Validaciones base y utilería nativa
│
├── tests/               # Pruebas automatizadas (Test-Driven Development)
│   └── test_report_anomalias.py # Pruebas para las lógicas de anomalía
│
└── reportes/            # Directorio de salida (Ignorado en `.gitignore`)
    ├── img/             # Carpeta requerida para las fotos de la integración visual
    ├── reporte_anomalias.html # Dashboard Ejecutivo General (HTML)
    └── individuales/    # Dashboards desglosados
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
   pip install -r requirements.txt
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

## 🧪 Testing y Control de Calidad Lógica

Debido a la precisión requerida para no presentar falsos reclamos a las flotas, el software incluye una suite de pruebas automatizada de validaciones y de coerción de información. Valida: 
- Que las detenciones fortuitas de menos de 30 minutos no se etiqueten caprichosamente como Anomalía.
- Detecciones limpias de placas superpuestas en el mismo bloque horario y lugar.
- Correcta agrupación de direcciones repetitivas en la semana con formato correcto.

Para validar el ecosistema:
```bash
python -m unittest tests/test_report_anomalias.py -v
```

## ⚠️ Zonas Base Configurables

A diferencia de parámetros fijados duramente al código interno, si en el futuro se fundan nuevas bases vehiculares (O nuevas oficinas de Renta Ya / Casa Blanca), no necesitas conocimientos de programación. 
La adaptación resulta inmediata con solamente editar el diccionario de `zonas.json` adjuntando Latitud, Longitud y Nombre del sector.

## 🔮 Roadmap y Siguientes Pasos (Arquitectura Empresarial)

Este proyecto funciona como un motor analítico avanzado mediante línea de comandos (CLI). Sin embargo, la **siguiente fase evolutiva** natural de este ecosistema contempla transformar esta herramienta en una **arquataforma web empresarial**, orquestando nuestro potente código analítico actual bajo la robustez de **Java / Spring Boot**.

Los pasos a futuro diseñados para el escalamiento son:

1. **Migración a Plataforma Web Institucional (Backend Spring Boot):**
   Eliminar la dependencia de la consola local. Se desarrollará un portal administrativo donde los coordinadores y jefes accederán con credenciales seguras, pudiendo visualizar reportes interactivos bajo demanda directamente en sus navegadores.
2. **Persistencia Histórica (Database Relacional):**
   A través de **Spring Data JPA** y PostgreSQL/MySQL, almacenar las coordenadas, eventos y anomalías para generar trazabilidad de largo plazo. Esto permitirá responder preguntas como: *"¿Cuál ha sido la mejora general del conductor 'Jose' durante todo el año en comparación a Enero?"* sin tener que agrupar 50 Excels.
3. **Automatización Integral y Cron Jobs (`@Scheduled`):**
   Dejar en el pasado las descargas manuales de Excel diarias/semanales. Spring Boot se configurará para conectarse de madrugada a las APIs directas de los fabricantes de GPS (si disponen), alimentar automáticamente el flujo de procesamiento de Python y enviar alertas críticas al correo de los supervisores a primera hora de las anomalías ocurridas ayer.
4. **Sinergia en Microservicios (Java + Python):**
   El robusto sistema de analítica, cálculos espaciales (`haversine`) y cruce de variables en `Pandas` (Python) no se perderá: será encapsulado como un microservicio interno y ultrarrápido (vía `FastAPI`), sirviendo como el "cerebro matemático" mientras *Spring Boot* toma el papel de conductor maestro, frontend proxy, manejo de usuarios, correos y base de datos permanente.
