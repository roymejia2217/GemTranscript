from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    # Modelo Gemini Flash: se resuelve dinamicamente si no se especifica
    GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME")
    
    # Rutas base del proyecto
    BASE_DIR = Path(__file__).parent.parent
    FILES_DIR = BASE_DIR / "files"
    OUTPUT_DIR = BASE_DIR / "output"
    LOGS_DIR = BASE_DIR / "logs"

    # Limites de Procesamiento
    # Flash tiene una ventana de contexto masiva (1M+ tokens).
    # El audio consume ~120k tokens/hora. Capacidad maxima ~8.4 horas.
    # Establecemos un limite seguro de 8 horas (28800s) para dejar margen al prompt y respuesta.
    SEGMENT_DURATION_SECONDS = 28800  # 8 horas por segmento
    MEDIA_THRESHOLD_SECONDS = 28800   # Procesar hasta 8 horas como unidad unica

    # Limites de Tasa y Fiabilidad
    API_DELAY_SECONDS = 2  # Espera reducida; Flash es rapido y tiene limites altos
    MAX_RETRIES = 3        # Intentos de reintento estandar
    RETRY_MIN_WAIT = 2     # Espera inicial rapida
    RETRY_MAX_WAIT = 30    # Tope de espera exponencial
    
    # Concurrencia
    MAX_WORKERS = 3        # Archivos a procesar en paralelo

    # Configuracion de Video
    # 1 FPS es suficiente para contexto de transcripcion
    FPS_SAMPLING = 1

    @classmethod
    def validate(cls):
        if not cls.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY no configurada en .env")
        cls.FILES_DIR.mkdir(exist_ok=True)
        cls.OUTPUT_DIR.mkdir(exist_ok=True)
        cls.LOGS_DIR.mkdir(exist_ok=True)
