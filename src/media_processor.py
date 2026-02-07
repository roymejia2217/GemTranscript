from pathlib import Path
from typing import List, Tuple
import mimetypes
import logging
import subprocess
import shutil

class MediaProcessor:
    SUPPORTED_VIDEO_FORMATS = {
        'video/mp4', 'video/mpeg', 'video/mov', 'video/avi',
        'video/x-flv', 'video/mpg', 'video/webm', 'video/wmv', 'video/3gpp',
        'video/mkv', 'video/x-matroska'
    }
    
    SUPPORTED_AUDIO_FORMATS = {
        'audio/mpeg', 'audio/mp4', 'audio/wav', 'audio/x-wav', 
        'audio/ogg', 'audio/flac', 'audio/aac', 'audio/x-m4a', 'audio/mp3'
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.has_ffprobe = shutil.which('ffprobe') is not None
        if not self.has_ffprobe:
            self.logger.warning("ffprobe no encontrado. La duracion de los archivos no podra ser calculada con precision.")

    def get_media_files(self, directory: Path) -> List[Path]:
        media_files = []
        if not directory.exists():
            self.logger.warning(f"Directorio no existe: {directory}")
            return []
            
        for file_path in directory.iterdir():
            if file_path.is_file():
                # Basic mime guess
                mime_type, _ = mimetypes.guess_type(str(file_path))
                
                # Fallback for extensions
                suffix = file_path.suffix.lower()
                if not mime_type:
                    if suffix == '.mkv': mime_type = 'video/x-matroska'
                    elif suffix == '.flv': mime_type = 'video/x-flv'
                    elif suffix == '.m4a': mime_type = 'audio/x-m4a'

                is_video = mime_type in self.SUPPORTED_VIDEO_FORMATS or suffix in {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
                is_audio = mime_type in self.SUPPORTED_AUDIO_FORMATS or suffix in {'.mp3', '.wav', '.m4a', '.flac', '.ogg'}

                if is_video or is_audio:
                    media_files.append(file_path)
                else:
                    self.logger.debug(f"Archivo ignorado: {file_path.name} (Mime: {mime_type})")
        return media_files

    def calculate_segments(
        self,
        duration_seconds: int,
        threshold_seconds: int,
        segment_duration: int
    ) -> List[Tuple[str, str]]:
        """
        Calcula segmentos logicos para el archivo multimedia.
        
        Logica:
        - Si la duracion es menor al umbral, devuelve un solo segmento nulo (archivo completo).
        - Divide en bloques de 'segment_duration'.
        - Fusiona remanentes cortos (<10s) con el segmento anterior.
        """
        if duration_seconds <= threshold_seconds:
            return [(None, None)]

        segments = []
        current_time = 0

        while current_time < duration_seconds:
            start = current_time
            end = min(current_time + segment_duration, duration_seconds)
            
            if (end - start) < 10 and segments:
                prev_start, _ = segments.pop()
                segments.append((prev_start, self._seconds_to_offset(end)))
                break

            segments.append((
                self._seconds_to_offset(start),
                self._seconds_to_offset(end)
            ))

            current_time = end

        self.logger.info(f"Medio de {duration_seconds}s dividido en {len(segments)} segmentos")
        return segments

    @staticmethod
    def _seconds_to_offset(seconds: int) -> str:
        return f"{int(seconds)}s"

    def get_media_duration(self, file_path: Path) -> int:
        if not self.has_ffprobe:
            self.logger.error(f"Imposible determinar duracion exacta sin ffprobe para: {file_path.name}")
            return 0

        try:
            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    str(file_path)
                ],
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout.strip()
            if output == 'N/A' or not output:
                 self.logger.warning(f"ffprobe retorno N/A para {file_path.name}")
                 return 0
                 
            return int(float(output))
        except Exception as e:
            self.logger.warning(f"Error ejecutando ffprobe en {file_path.name}: {e}")
            return 0

    def prepare_audio_for_upload(self, media_path: Path, output_audio_path: Path) -> bool:
        """
        Optimiza archivos para la subida a Gemini.
        
        Logica:
        - Si es Audio (MP3/WAV/etc.): Se usa tal cual (retorna False).
        - Si es Video: Se extrae la pista de audio a MP3 mono 32k (retorna True).
        
        Objetivo: Reducir drasticamente ancho de banda y tiempos de subida.
        """
        # Chequeo rapido de extension para ver si ya es audio compatible
        if media_path.suffix.lower() in {'.mp3', '.m4a', '.wav', '.aac', '.flac', '.ogg'}:
             self.logger.debug(f"{media_path.name} ya es audio, se usara directo.")
             return False

        if not self.has_ffprobe:
            return False

        try:
            cmd = [
                'ffmpeg',
                '-y',              # Sobreescribir
                '-i', str(media_path),
                '-vn',             # Sin video
                '-ac', '1',        # Mono
                '-ar', '16000',    # 16kHz
                '-b:a', '32k',     # Bitrate voz optimizado (50% menos peso que 64k)
                '-f', 'mp3',
                str(output_audio_path)
            ]
            
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error extrayendo audio de {media_path.name}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error inesperado ffmpeg: {e}")
            return False
