import librosa
import numpy as np
import io

def preprocess_audio(file_path_or_bytes, target_sr=22050) -> tuple[np.ndarray, int]:
    """
    Carga un archivo de audio (o bytes), lo remuestrea a `target_sr` y lo convierte a mono.
    
    :param file_path_or_bytes: Ruta al archivo de audio o un objeto similar a un archivo (bytes).
    :param target_sr: Frecuencia de muestreo objetivo (ej. 22050 Hz).
    :return: Tupla (y, sr) con el audio normalizado en mono y la tasa de muestreo.
    """
    # Si recibimos bytes, usamos un buffer en memoria
    if isinstance(file_path_or_bytes, bytes):
        file_path_or_bytes = io.BytesIO(file_path_or_bytes)
        
    # Cargar usando librosa (automáticamente convierte a mono si mono=True)
    y, sr = librosa.load(file_path_or_bytes, sr=target_sr, mono=True)
    
    # Normalizar amplitud
    if len(y) > 0:
        max_val = np.max(np.abs(y))
        if max_val > 0:
            y = y / max_val
            
    return y, sr

def estimate_tempo(y: np.ndarray, sr: int) -> float:
    """
    Estima el tempo (BPM) del audio usando librosa.
    Retorna el tempo redondeado como float. Si falla o da 0, retorna 120.0 por defecto.
    """
    try:
        # Usamos beat_track y extraemos el tempo de forma segura para tipos estáticos
        track_res = librosa.beat.beat_track(y=y, sr=sr)
        tempo = track_res[0]
        
        if isinstance(tempo, (list, np.ndarray)):
            bpm = float(tempo[0])
        else:
            bpm = float(tempo)
            
        if np.isnan(bpm) or bpm <= 0:
            return 120.0
        return float(round(bpm, 1))
    except Exception:
        return 120.0
