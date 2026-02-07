import unicodedata
import re

def sanitize_filename_for_api(filename: str) -> str:
    """
    Normaliza nombres de archivo para compatibilidad estricta con APIs (ASCII/UTF-8).
    
    Proceso:
    1. Normaliza Unicode (NFKD) para separar tildes.
    2. Convierte a ASCII descartando caracteres no validos.
    3. Reemplaza espacios y simbolos con guiones bajos.
    4. Limpia redundancias.
    
    Ejemplo: "Vídeo de Introducción.mp4" -> "Video_de_Introduccion.mp4"
    """
    # Normalizacion Unicode (separa caracteres compuestos)
    normalized = unicodedata.normalize('NFKD', filename)
    
    # Reduccion a ASCII estricto
    ascii_bytes = normalized.encode('ascii', 'ignore')
    clean_str = ascii_bytes.decode('ascii')
    
    # Sanitizacion de caracteres especiales para headers HTTP seguros
    clean_str = re.sub(r'[^a-zA-Z0-9._-]', '_', clean_str)
    
    # Limpieza de separadores duplicados
    clean_str = re.sub(r'_+', '_', clean_str)
    
    return clean_str
