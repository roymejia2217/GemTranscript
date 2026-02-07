import logging
import sys
from pathlib import Path

# Añadimos el directorio actual al path para importar modulos locales
sys.path.append(str(Path(__file__).parent))

from config.settings import Config
from src.transcriber import MediaTranscriber

def setup_logging():
    try:
        Config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Configuracion del logger raiz
        logging.basicConfig(
            level=logging.INFO,
            # Formato compacto: NIVEL - Mensaje
            format='%(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(Config.LOGS_DIR / 'transcription.log', encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ],
            force=True
        )
    except Exception as e:
        print(f"Error configurando logging: {e}")
        sys.exit(1)

def main():
    try:
        # Validacion de configuracion (crea directorios necesarios)
        Config.validate()
        
        # Inicializacion de logging
        setup_logging()
        
        logger = logging.getLogger(__name__)
        logger.info("GemTranscript")
        logger.info(f"Modelo configurado: {Config.MODEL_NAME}")

        # Ejecucion principal
        transcriber = MediaTranscriber()
        transcriber.process_all_files()

        logger.info("--- PROCESO COMPLETADO EXITOSAMENTE ---")

    except ValueError as ve:
        logging.error(f"Error de configuracion: {ve}")
        print(f"ERROR CRITICO: {ve}")
        print("Asegurate de crear el archivo .env con GEMINI_API_KEY")
    except Exception as e:
        logging.error(f"Error fatal no controlado: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
