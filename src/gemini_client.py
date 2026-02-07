from google import genai
from google.genai import types
from pathlib import Path
import logging
import mimetypes
import time
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import Config
from .utils import sanitize_filename_for_api

class GeminiTranscriptionClient:
    def __init__(self, api_key: str, model_name: str):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.logger = logging.getLogger(__name__)

    @retry(
        stop=stop_after_attempt(Config.MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=Config.RETRY_MIN_WAIT, max=Config.RETRY_MAX_WAIT),
        reraise=True
    )
    def transcribe_video_segment(
        self,
        video_path: Path,
        start_offset: Optional[str] = None,
        end_offset: Optional[str] = None
    ) -> str:
        """
        Orquesta el flujo completo de transcripcion para un archivo.
        
        Pasos:
        1. Sube el archivo a Google File API.
        2. Espera a que el procesamiento remoto (transcodificacion) termine.
        3. Solicita la generacion de contenido (transcripcion) al modelo.
        4. Asegura la eliminacion del archivo remoto al finalizar.
        """
        uploaded_file = None
        try:
            # 1. Subida segura a File API
            uploaded_file = self._upload_file(video_path)

            # 2. Espera activa de procesamiento
            self._wait_for_file_processing(uploaded_file.name)

            # 3. Generacion de transcripcion
            return self._generate_transcription(uploaded_file, start_offset, end_offset)

        except Exception as e:
            # 'repr' evita errores de codificacion en logs si la excepcion tiene caracteres no-ASCII
            self.logger.warning(f"Error en transcripcion de {video_path.name}: {repr(e)}")
            raise
        finally:
            # 4. Limpieza garantizada
            if uploaded_file:
                self._delete_file(uploaded_file.name)

    def _upload_file(self, video_path: Path):
        self.logger.info(f"Subiendo archivo: {video_path.name}")
        
        # 1. Normalizacion de nombre (fix bug: headers ASCII en libreria client)
        safe_filename = sanitize_filename_for_api(video_path.name)
        
        # Caso ideal: nombre ya es seguro
        if safe_filename == video_path.name:
            return self._perform_upload(video_path, safe_filename)
            
        # 2. Manejo de caracteres especiales mediante alias temporal (hardlink)
        # Se usa 'temp_uploads' para garantizar mismo filesystem (necesario para hardlinks)
        temp_dir = Config.BASE_DIR / "temp_uploads"
        temp_dir.mkdir(exist_ok=True)
        
        safe_path = temp_dir / safe_filename
        
        try:
            # Estrategia de enlace: Hardlink (rapido) > Copia (fallback)
            try:
                if safe_path.exists():
                    safe_path.unlink()
                import os
                os.link(video_path, safe_path)
                self.logger.debug(f"Hardlink temporal creado: {safe_path.name}")
            except OSError:
                import shutil
                self.logger.debug("Hardlink fallo, copiando archivo...")
                shutil.copy2(video_path, safe_path)
            
            # 3. Subida con path seguro
            return self._perform_upload(safe_path, safe_filename)
            
        finally:
            # 4. Limpieza de alias local
            try:
                if safe_path.exists():
                    safe_path.unlink()
            except Exception as e:
                self.logger.warning(f"No se pudo borrar temporal {safe_path}: {e}")

    def _perform_upload(self, path: Path, display_name: str):
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type:
            mime_type = "video/mp4"
            
        return self.client.files.upload(
            file=str(path),
            config=types.UploadFileConfig(
                mime_type=mime_type,
                display_name=display_name
            )
        )

    def _wait_for_file_processing(self, file_name: str):
        """Bloquea la ejecucion hasta que el archivo este 'ACTIVE' (listo) o 'FAILED'."""
        attempt = 0
        while True:
            remote_file = self.client.files.get(name=file_name)
            state = remote_file.state.name
            
            if state == "ACTIVE":
                self.logger.info(f"Archivo listo: {file_name}")
                break
            elif state == "FAILED":
                raise RuntimeError(f"Procesamiento fallido en Google: {state}")
            
            # Backoff adaptativo: mas frecuente al inicio para archivos pequeños
            sleep_time = 1 if attempt < 5 else 2
            self.logger.debug(f"Procesando en nube... ({state})")
            time.sleep(sleep_time)
            attempt += 1

    def _generate_transcription(
        self, 
        uploaded_file, 
        start_offset: Optional[str], 
        end_offset: Optional[str]
    ) -> str:
        parts = []

        # Configurar metadatos si es un segmento
        file_args = {"file_uri": uploaded_file.uri, "mime_type": uploaded_file.mime_type}
        
        if start_offset and end_offset:
            self.logger.info(f"Solicitando segmento: {start_offset} a {end_offset}")
            parts.append(
                types.Part(
                    file_data=types.FileData(**file_args),
                    video_metadata=types.VideoMetadata(
                        start_offset=start_offset,
                        end_offset=end_offset
                    )
                )
            )
        else:
            parts.append(types.Part(file_data=types.FileData(**file_args)))

        # Prompt optimizado para transcripcion pura
        parts.append(
            types.Part(
                text="""
                Actua como un transcriptor profesional experto. Tu tarea es generar una transcripcion VERBATIM (palabra por palabra) del audio de este video.
                
                Reglas ESTRICTAS:
                1. Solo devuelve el texto hablado.
                2. NO incluyas marcas de tiempo.
                3. NO incluyas descripciones de sonidos (como [musica], [risas]).
                4. NO incluyas introducciones ni conclusiones ("Aqui esta la transcripcion...").
                5. Si el audio es ininteligible en una parte, omitela limpiamente.
                6. Respeta la puntuacion y gramatica del idioma original.
                """
            )
        )

        self.logger.info(f"Enviando solicitud a modelo {self.model_name}...")
        
        # Configuracion para determinismo maximo (Temperature 0)
        gen_config = types.GenerateContentConfig(
            temperature=0.0,
            candidate_count=1
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=types.Content(parts=parts),
            config=gen_config
        )

        return response.text.strip() if response.text else ""

    def _delete_file(self, file_name: str):
        try:
            self.client.files.delete(name=file_name)
            self.logger.info(f"Archivo eliminado de File API: {file_name}")
        except Exception as e:
            self.logger.warning(f"No se pudo eliminar archivo {file_name}: {e}")
