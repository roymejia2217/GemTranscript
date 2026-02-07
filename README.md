# GemTranscript

![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)
![Model](https://img.shields.io/badge/model-Gemini_3.0_Flash-orange?style=flat-square)
![FFmpeg](https://img.shields.io/badge/dependency-FFmpeg-green?style=flat-square)
[![License](https://img.shields.io/github/license/roymejia2217/GemTranscript?style=flat-square)](LICENSE)

Sistema CLI de alto rendimiento para la transcripción masiva de archivos multimedia (Audio y Video), optimizado para velocidad, bajo consumo de ancho de banda y precisión utilizando el modelo **Google Gemini 3.0 Flash**.

## Características Principales

*   **Motor Gemini 3.0 Flash:** Aprovecha la ventana de contexto masiva (1M tokens) para procesar archivos de hasta **8 horas** en una sola pasada.
*   **Optimización Inteligente de Ancho de Banda:** Detecta videos automáticamente y extrae el audio a MP3 mono (32kbps) antes de subirlo, reduciendo el tamaño de transferencia en un ~95% sin pérdida de calidad de reconocimiento.
*   **Soporte Multiformato:** Procesa transparentemente `.mp4`, `.mov`, `.mkv`, `.mp3`, `.wav`, `.m4a`, entre otros.
*   **Concurrencia:** Procesamiento paralelo de múltiples archivos (Workers configurables) para maximizar el throughput.
*   **Compatibilidad Windows:** Sistema de sanitización de nombres y manejo de rutas robusto (Unicode/ASCII) para evitar errores en la API de Google.
*   **Salida Determinista:** Configurado (`temperature=0`) para generar transcripciones estrictamente literales, sin alucinaciones ni metadatos conversacionales.

## Requisitos Previos

1.  **Python 3.10+** instalado.
2.  **FFmpeg** instalado y agregado a las variables de entorno (PATH) del sistema.
3.  Una **API Key de Google Gemini**.

## Instalación

```bash
git clone https://github.com/roymejia2217/GemTranscript.git
cd GemTranscript

# Crear entorno virtual (opcional pero recomendado)
python -m venv venv
.\venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

Crea un archivo `.env` en la raíz del proyecto:

```env
GEMINI_API_KEY=tu_api_key_aqui
```

## Uso

1.  Coloca tus archivos de audio o video en la carpeta `files/`.
2.  Ejecuta el script principal:

```bash
python main.py
```

El sistema detectará automáticamente los archivos, realizará la extracción de audio si es necesaria, subirá los datos a la nube, transcribirá y guardará los resultados en formato `.txt` dentro de la carpeta `output/`.

## Estructura del Proyecto

```text
GemTranscript/
├── config/             # Configuraciones globales (Límites, Modelo)
├── files/              # Directorio de entrada (Audio/Video)
├── logs/               # Registros de ejecución y archivos temporales
├── output/             # Resultados de la transcripción (.txt)
├── src/
│   ├── gemini_client.py   # Cliente API (Subida robusta, Retry logic)
│   ├── media_processor.py # Lógica FFmpeg y detección de medios
│   ├── transcriber.py     # Orquestador y manejo de hilos
│   └── utils.py           # Utilidades de sanitización
├── main.py             # Punto de entrada
└── requirements.txt    # Dependencias
```
