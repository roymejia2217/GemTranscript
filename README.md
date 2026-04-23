<p align="center">
  <img src="docs/banner.webp" alt="GemTranscript Banner" />
</p>

<h1 align="center">GemTranscript</h1>

<p align="center">
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Built%20with-Python_3.10%2B-blue?style=flat&logo=python" alt="Python" />
  </a>
  <a href="https://pypi.org/project/google-genai/">
    <img src="https://img.shields.io/badge/SDK-google__genai-orange?style=flat" alt="google-genai" />
  </a>
  <a href="https://pypi.org/project/tenacity/">
    <img src="https://img.shields.io/badge/Retry-Tenacity-green?style=flat" alt="Tenacity" />
  </a>
  <a href="https://ai.google.dev/">
    <img src="https://img.shields.io/badge/Model-Gemini_Flash-blueviolet?style=flat" alt="Gemini Flash" />
  </a>
  <a href="https://ffmpeg.org/">
    <img src="https://img.shields.io/badge/Dependency-FFmpeg-green?style=flat" alt="FFmpeg" />
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=flat" alt="License: MIT" />
  </a>
</p>

<p align="center">
  Herramienta de alto rendimiento para transcripcion por lotes de archivos de audio y video usando Google Gemini Flash, con interfaz grafica y CLI, optimizada para bajo consumo de ancho de banda y salida determinista
</p>

---

## Inicio Rapido

```bash
git clone https://github.com/roymejia2217/GemTranscript.git
cd GemTranscript
python -m venv venv
source venv/bin/activate    # Linux/macOS
# .\venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Crea un archivo `.env` en la raiz del proyecto:

```env
GEMINI_API_KEY=tu_clave_api_aqui
```

Ejecuta con CLI o GUI:

```bash
python main.py        # Modo CLI
python gui.py         # Modo GUI
```

---

## Caracteristicas

| Caracteristica | Descripcion |
|----------------|-------------|
| **Motor Gemini Flash** | Soporta una amplia ventana de contexto para procesar archivos de multiples horas en una sola pasada |
| **Interfaz Grafica (GUI)** | Aplicacion tkinter con seleccion de archivos, barra de progreso, conteo de exitos/fallos y apertura directa de la carpeta de salida |
| **Resolucion Dinamica de Modelos** | Descubre automaticamente modelos Flash disponibles via API, con cadena de respaldo inteligente |
| **Optimizacion de Ancho de Banda** | Extrae audio de video a MP3 mono a 32kbps antes de subir, reduciendo el tamano de transferencia aproximadamente 95% |
| **Soporte Multi-Formato** | Maneja transparentemente MP4, MOV, MKV, MP3, WAV, M4A, FLAC, OGG, AVI, WEBM, FLV y 3GP |
| **Procesamiento Paralelo** | Thread pool configurable (default 3 workers) para transcripcion concurrente de archivos |
| **Ejecucion Idempotente** | Omite archivos que ya tienen una transcripcion correspondiente, permitiendo re-ejecuciones seguras |
| **Manejo de Nombres Unicode** | Sana rutas de archivos y usa hardlinks para trabajar con restricciones de caracteres no-ASCII en la API de Google |
| **Salida Deterministica** | Temperatura fija en 0 para transcripcion textual sin alucinaciones ni metadatos conversacionales |
| **Limpieza Automatica** | Elimina archivos temporales locales y uploads remotos de la API de Google File despues de cada transcripcion |
| **Reintento con Backoff** | Backoff exponencial para fallos transitorios de API, con conteo de reintentos configurable y limites de espera |
| **Seguimiento de Progreso** | Callback de progreso con eventos para inicio, archivo actual, archivo completado y finalizacion |

---

## Requisitos Previos

| Dependencia | Proposito | Instalacion |
|-------------|-----------|-------------|
| **Python** 3.10+ | Entorno de ejecucion | [python.org](https://www.python.org/) |
| **FFmpeg** | Extraccion de audio y deteccion de duracion de medios | `sudo apt install ffmpeg` (Linux), `brew install ffmpeg` (macOS), [ffmpeg.org](https://ffmpeg.org/) (Windows) |
| **FFprobe** | Obtencion de metadatos de medios | Incluido con FFmpeg |
| **Clave API de Google Gemini** | Autenticacion para la API de Gemini | [aistudio.google.com](https://aistudio.google.com/) |
| **GEMINI_MODEL_NAME** (opcional) | Override del modelo Flash automatico | Ver seccion Configuracion de Modelo |

---

## Instalacion

### Instalacion basica

```bash
pip install -r requirements.txt
```

### Instalacion con entry points (acceso global)

```bash
pip install -e .
```

Esto habilita los comandos:

```bash
gemtranscript       # CLI
gemtranscript-gui   # GUI
```

---

## Uso

### Modo CLI

1. Coloca archivos de audio o video en el directorio `files/`.
2. Ejecuta la aplicacion:

```bash
python main.py
```

3. Las transcripciones se guardan como archivos `.txt` en el directorio `output/`, nombrados `{nombre_original}_transcription.txt`.

Los archivos que ya tienen una transcripcion correspondiente se omiten automaticamente.

### Modo GUI

1. Ejecuta la aplicacion grafica:

```bash
python gui.py
# o si instalaste con entry points:
gemtranscript-gui
```

2. Selecciona archivos usando el dialogo de seleccion multiple.
3. Haz clic en "Transcribe" para iniciar el procesamiento.
4. La barra de progreso muestra el estado actual.
5. Al completar, haz clic en "Open Output Folder" para ver los resultados.

La GUI valida al inicio:
- Que `GEMINI_API_KEY` este configurada.
- Que `ffprobe` este disponible.
- Que el modelo Gemini pueda ser resuelto.

---

## Configuracion

El archivo `.env` en la raiz del proyecto controla las opciones de configuracion:

| Variable | Requerido | Descripcion |
|----------|-----------|-------------|
| `GEMINI_API_KEY` | Si | Clave API de Google Gemini. Obtenla en [aistudio.google.com](https://aistudio.google.com/) |
| `GEMINI_MODEL_NAME` | No | Override del nombre del modelo. Si no se especifica, se descubre automaticamente |

Ejemplo de `.env` completo:

```env
GEMINI_API_KEY=tu_clave_api_aqui
GEMINI_MODEL_NAME=gemini-2.0-flash
```

---

## Configuracion de Modelo

GemTranscript resuelve automaticamente el mejor modelo Flash de Gemini disponible.

### Como funciona

1. Si `GEMINI_MODEL_NAME` esta definido en `.env`, se valida que el modelo exista.
2. Si no hay override, se realiza descubrimiento dinamico via `client.models.list()`.
3. Si el descubrimiento falla, se usa la cadena de respaldo:

```
gemini-2.5-flash -> gemini-2.0-flash -> gemini-2.0-flash-001 -> gemini-1.5-flash
```

4. El resultado se guarda en cache en memoria para evitar llamadas API repetidas.

### Override manual

Para forzar un modelo especifico, agrega en `.env`:

```env
GEMINI_MODEL_NAME=gemini-2.0-flash
```

### Si no se encuentra ningun modelo

Si la resolucion falla completamente, mostrara un error claro indicando:

- Que no se pudo encontrar un modelo valido
- Que modelos se intentaron
- Recomendaciones para verificar: clave API, conexion de red, o configuracion manual via `.env`

---

## Compilacion de Ejecutable

Para crear ejecutables standalone en Linux:

```bash
./build.sh
```

Esto:

1. Crea un entorno virtual limpio `build_venv`.
2. Instala las dependencias y PyInstaller.
3. Compila dos ejecutables: `gemtranscript` (CLI) y `gemtranscript-gui` (GUI).
4. Los ejecutables se generan en `dist/`.

Requisitos para compilacion:

- Python 3.10+
- PyInstaller (instalado automaticamente por el script)
- Linux (el script usa comandos Bash)

---

## Pruebas

El proyecto incluye un conjunto de pruebas con pytest:

```bash
pip install -r requirements-dev.txt
pytest
```

Las pruebas cubren:

- Callbacks del transcriber (eventos de progreso)
- Logica de la interfaz grafica
- Resolucion de modelos y manejo de errores

---

## Estructura del Proyecto

```
config/
└── settings.py             # Configuracion global (modelo, rutas, limites, concurrencia)
src/
├── gemini_client.py        # Cliente de API Gemini (upload, poll, transcribe, delete, retry)
├── media_processor.py      # Operaciones FFmpeg, deteccion de medios, calculo de segmentos
├── model_resolver.py      # Resolucion dinamica de modelos Flash via API
├── transcriber.py          # Orquestador (procesamiento por lotes, thread pool, idempotencia)
└── utils.py                # Saneamiento de nombres de archivo para compatibilidad con API
gui.py                      # Punto de entrada GUI (tkinter)
main.py                     # Punto de entrada CLI (validacion, logging, ejecucion)
pyproject.toml              # Configuracion de paquete con entry points
build.sh                    # Script de compilacion para ejecutables Linux
requirements.txt            # Dependencias de produccion
requirements-dev.txt        # Dependencias de desarrollo (pytest)
tests/
├── __init__.py
├── test_transcriber_callbacks.py  # Pruebas de callbacks de progreso
├── test_gui_logic.py             # Pruebas de logica GUI
└── test_model_resolver.py        # Pruebas de resolucion de modelos
```

Directorios de ejecucion (creados automaticamente):

```
files/          # Archivos de medios de entrada
output/         # Archivos de transcripcion (.txt)
logs/           # Logs de ejecucion y extracciones de audio temporales
temp_uploads/   # Hardlinks temporales para nombres Unicode
```

---

## Creditos

| Proyecto | Descripcion | Licencia |
|----------|-------------|----------|
| [google-genai](https://pypi.org/project/google-genai/) | SDK oficial de Google para Gemini | Apache 2.0 |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | Carga de variables de entorno | BSD |
| [tenacity](https://pypi.org/project/tenacity/) | Reintento automatico con backoff | Apache 2.0 |
| [pytest](https://pypi.org/project/pytest/) | Framework de pruebas | MIT |

---

## Licencia

MIT License. Ver [LICENSE](LICENSE) para detalles.
