import os
import subprocess
import tempfile
import shutil
import logging

logger = logging.getLogger("demucs_separator")

def separate_guitar_stem(audio_path: str) -> str:
    """
    Toma un audio original de guitarra/canción completa, corre el modelo Demucs v4 (htdemucs),
    extrae el stem 'other' (donde se ubica la guitarra) y retorna la ruta del archivo WAV resultante.
    Si Demucs no está instalado o falla, retorna el audio original de fallback.
    """
    # 1. Verificar si demucs está instalado en el sistema
    if not shutil.which("demucs"):
        logger.warning("Demucs CLI no está instalado o no se encuentra en el PATH del sistema. Se omitirá la separación y se usará el audio original de fallback.")
        return audio_path

    # 2. Configurar directorio temporal de salida
    temp_dir = tempfile.mkdtemp()
    
    logger.info(f"Iniciando separación de audio con Demucs para {audio_path}...")
    
    # 3. Comando oficial de Demucs
    # --two-stems other (optimiza el tiempo separando la pista en 'other' (guitarra) vs 'el resto')
    cmd = [
        "demucs",
        "--two-stems", "other",
        "-o", temp_dir,
        audio_path
    ]
    
    try:
        # Ejecutar Demucs en segundo plano
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        logger.info("Demucs se ha ejecutado con éxito.")
        
        # 4. Localizar el archivo separado
        # Demucs genera carpetas con la estructura: temp_dir/htdemucs/{id_del_archivo}/other.wav
        filename_no_ext = os.path.splitext(os.path.basename(audio_path))[0]
        target_path = os.path.join(temp_dir, "htdemucs", filename_no_ext, "other.wav")
        
        if os.path.exists(target_path):
            # Mover el archivo fuera del directorio htdemucs a una ruta temporal directa
            final_wav_path = os.path.join(tempfile.gettempdir(), f"separated_{filename_no_ext}.wav")
            shutil.move(target_path, final_wav_path)
            
            # Limpiar directorio temporal de Demucs
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Pista de guitarra extraída con éxito por Demucs: {final_wav_path}")
            return final_wav_path
        else:
            logger.warning("No se pudo localizar el archivo extraído por Demucs. Usando audio original.")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return audio_path
            
    except Exception as e:
        logger.error(f"Error al ejecutar Demucs: {str(e)}. Se usará el audio original sin separar.")
        # Limpiar por si acaso
        shutil.rmtree(temp_dir, ignore_errors=True)
        return audio_path
