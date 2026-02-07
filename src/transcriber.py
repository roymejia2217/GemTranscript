import concurrent.futures
from pathlib import Path
from typing import List
import logging
import time
from .gemini_client import GeminiTranscriptionClient
from .media_processor import MediaProcessor
from config.settings import Config

class MediaTranscriber:
    def __init__(self):
        self.gemini_client = GeminiTranscriptionClient(
            Config.GEMINI_API_KEY,
            Config.MODEL_NAME
        )
        self.media_processor = MediaProcessor()
        self.logger = logging.getLogger(__name__)

    def transcribe_media(self, media_path: Path) -> str:
        """
        Orquesta la transcripcion de un archivo.
        Maneja tanto archivos completos como segmentados si exceden el limite.
        """
        self.logger.info(f"Procesando: {media_path.name}")

        duration = self.media_processor.get_media_duration(media_path)
        self.logger.debug(f"Duracion ({media_path.name}): {duration}s")

        # Calculo de segmentos (Generalmente 1 solo segmento de hasta 8h)
        segments = self.media_processor.calculate_segments(
            duration,
            Config.MEDIA_THRESHOLD_SECONDS,
            Config.SEGMENT_DURATION_SECONDS
        )

        transcriptions = []
        total_segments = len(segments)

        for idx, (start_offset, end_offset) in enumerate(segments, 1):
            try:
                if start_offset and end_offset:
                    self.logger.info(f"[{media_path.name}] Segmento {idx}/{total_segments} ({start_offset}-{end_offset})")
                else:
                    self.logger.info(f"[{media_path.name}] Modo completo")

                segment_text = self.gemini_client.transcribe_video_segment(
                    media_path,
                    start_offset,
                    end_offset
                )
                
                if segment_text:
                    transcriptions.append(segment_text)
                    self.logger.debug(f"[{media_path.name}] Segmento {idx} completado.")
                
                if idx < total_segments:
                    time.sleep(Config.API_DELAY_SECONDS)

            except Exception as e:
                self.logger.error(f"[{media_path.name}] Fallo en segmento {idx}: {e}")
                continue

        full_transcription = " ".join(transcriptions)
        return full_transcription

    def save_transcription(self, transcription: str, output_path: Path):
        try:
            output_path.write_text(transcription, encoding='utf-8')
            self.logger.info(f"GUARDADO: {output_path.name}")
        except Exception as e:
            self.logger.error(f"Error guardando {output_path.name}: {e}")

    def _process_single_file(self, file_path: Path) -> bool:
        """
        Worker individual para procesamiento paralelo.
        
        Flujo:
        1. Verifica si ya existe la transcripcion (Idempotencia).
        2. Optimiza el archivo (Video -> Audio MP3) si es necesario.
        3. Realiza la transcripcion.
        4. Limpia archivos temporales.
        """
        output_filename = f"{file_path.stem}_transcription.txt"
        output_path = Config.OUTPUT_DIR / output_filename

        # 1. Idempotencia: Saltar si ya existe
        if output_path.exists():
            self.logger.info(f"SALTADO: {file_path.name} (Ya procesado)")
            return True

        audio_temp_path = None
        try:
            # 2. Optimizacion de Medio
            # Genera un MP3 temporal solo si es video o formato pesado
            temp_audio_name = f"temp_{file_path.stem}.mp3"
            audio_temp_path = Config.LOGS_DIR / temp_audio_name
            
            is_new_file_generated = self.media_processor.prepare_audio_for_upload(file_path, audio_temp_path)
            
            target_file = audio_temp_path if is_new_file_generated else file_path
            
            if is_new_file_generated:
                 self.logger.info(f"Optimizado (Video->Audio): {target_file.name}")
            else:
                 self.logger.info(f"Usando original: {target_file.name}")

            # 3. Transcripcion
            transcription = self.transcribe_media(target_file)
            
            if not transcription:
                self.logger.warning(f"Transcripcion vacia: {file_path.name}")
                return False

            self.save_transcription(transcription, output_path)
            return True

        except Exception as e:
            self.logger.error(f"Error CRITICO en {file_path.name}: {e}", exc_info=True)
            return False
        finally:
            # 4. Limpieza de temporales
            if audio_temp_path and audio_temp_path.exists():
                try:
                    audio_temp_path.unlink()
                    self.logger.debug(f"Temp eliminado: {audio_temp_path.name}")
                except Exception as cleanup_error:
                    self.logger.warning(f"Fallo limpieza temp {audio_temp_path.name}: {cleanup_error}")

    def process_all_files(self):
        media_files = self.media_processor.get_media_files(Config.FILES_DIR)

        if not media_files:
            self.logger.warning(f"No hay archivos en {Config.FILES_DIR}")
            return

        total_files = len(media_files)
        self.logger.info(f"Iniciando lote de {total_files} archivos (Hilos: {Config.MAX_WORKERS})")

        success_count = 0
        fail_count = 0

        # Ejecucion paralela limitada por MAX_WORKERS
        with concurrent.futures.ThreadPoolExecutor(max_workers=Config.MAX_WORKERS) as executor:
            future_to_file = {
                executor.submit(self._process_single_file, f): f 
                for f in media_files
            }
            
            for future in concurrent.futures.as_completed(future_to_file):
                f = future_to_file[future]
                try:
                    is_success = future.result()
                    if is_success:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as exc:
                    self.logger.error(f"Error en hilo {f.name}: {exc}")
                    fail_count += 1
        
        self.logger.info(f"FINALIZADO: {success_count}/{total_files} Exitosos. {fail_count} Fallidos.")
