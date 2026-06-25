import librosa
import numpy as np
import warnings

# Intentar importar basic-pitch para soporte de polifonía
try:
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH
    BASIC_PITCH_AVAILABLE = True
except ImportError:
    BASIC_PITCH_AVAILABLE = False


def hz_to_note_name(frequency: float) -> str | None:
    """
    Convierte una frecuencia en Hz al nombre de nota científica (ej. 'A4', 'C#3').
    """
    if frequency <= 0 or np.isnan(frequency):
        return None
    # Usar unicode=False para evitar caracteres especiales como ♯ y ♭ que no soporta music21
    note = str(librosa.hz_to_note(frequency, unicode=False))
    return note.replace('♯', '#').replace('♭', '-')


def midi_to_note_name(midi_number: int) -> str:
    """
    Convierte un número MIDI a nombre de nota (ej. 60 -> 'C4').
    """
    # Usar unicode=False para evitar caracteres especiales como ♯ y ♭ que no soporta music21
    note = str(librosa.midi_to_note(midi_number, unicode=False))
    return note.replace('♯', '#').replace('♭', '-')


def detect_pitch_monophonic(y: np.ndarray, sr: int) -> list[dict]:
    """
    Detecta notas en audio monofónico usando el algoritmo PYIN de librosa.
    Agrupa los frames detectados en notas continuas con tiempos de inicio y duración.
    """
    # Rango de guitarra estándar: E2 (~82 Hz) a C6 (~1047 Hz)
    fmin = librosa.note_to_hz('E2')
    fmax = librosa.note_to_hz('C6')
    
    # Ejecutar pYIN
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y, 
        fmin=fmin, 
        fmax=fmax, 
        sr=sr,
        fill_na=None
    )
    
    # Tiempos de cada frame
    times = librosa.times_like(f0, sr=sr)
    
    notes_detected = []
    current_note: str | None = None
    current_start: float | None = None
    
    # Agrupación simple de frames consecutivos con la misma nota aproximada
    for i, freq in enumerate(f0):
        if freq is not None and not np.isnan(freq) and voiced_flag[i]:
            note_name = hz_to_note_name(freq)
            if note_name is None:
                continue
            
            # Si es la misma nota que la anterior, extendemos su duración
            if current_note == note_name:
                pass
            else:
                # Si había otra nota antes, la guardamos
                if current_note is not None and current_start is not None:
                    duration = float(times[i]) - float(current_start)
                    if duration >= 0.05:  # Filtro mínimo de duración
                        notes_detected.append({
                            "pitch": current_note,
                            "midi": int(librosa.note_to_midi(current_note)),
                            "frequency": float(librosa.note_to_hz(current_note)),
                            "start_time": float(current_start),
                            "duration": float(duration)
                        })
                current_note = note_name
                current_start = float(times[i])
        else:
            # Silencio / No voiced
            if current_note is not None and current_start is not None:
                t_end = float(times[i]) if i < len(times) else (len(y) / sr)
                duration = t_end - float(current_start)
                if duration >= 0.05:
                    notes_detected.append({
                        "pitch": current_note,
                        "midi": int(librosa.note_to_midi(current_note)),
                        "frequency": float(librosa.note_to_hz(current_note)),
                        "start_time": float(current_start),
                        "duration": float(duration)
                    })
                current_note = None
                current_start = None
                
    # Agregar la última nota si quedó pendiente
    if current_note is not None and current_start is not None:
        duration = (len(y) / sr) - float(current_start)
        if duration >= 0.05:
            notes_detected.append({
                "pitch": current_note,
                "midi": int(librosa.note_to_midi(current_note)),
                "frequency": float(librosa.note_to_hz(current_note)),
                "start_time": float(current_start),
                "duration": float(duration)
            })

    return notes_detected


def detect_pitch_polyphonic(audio_path: str) -> list[dict]:
    """
    Detecta notas en audio polifónico usando Basic Pitch de Spotify.
    Si no está instalado, lanza un warning y usa un fallback o simulador.
    """
    if not BASIC_PITCH_AVAILABLE:
        warnings.warn("Spotify Basic Pitch no está disponible en este entorno. Se requiere TensorFlow. Se usará el simulador/monofónico de fallback.")
        # Retornar una lista vacía para que el llamador decida si usar monofónico o mock
        return []
        
    try:
        # Predecir usando el modelo oficial
        from basic_pitch.inference import predict as bp_predict
        model_output, midi_data, note_events = bp_predict(audio_path)
        
        notes_detected = []
        # note_events es una lista de NoteEvent de basic_pitch
        # Cada NoteEvent tiene: start_time_s, end_time_s, pitch_midi, amplitude
        for event in note_events:
            note_name = midi_to_note_name(event.pitch_midi)
            notes_detected.append({
                "pitch": note_name,
                "midi": int(event.pitch_midi),
                "frequency": float(librosa.midi_to_hz(event.pitch_midi)),
                "start_time": float(event.start_time_s),
                "duration": float(event.end_time_s - event.start_time_s)
            })
            
        # Ordenar por tiempo de inicio
        notes_detected.sort(key=lambda x: x["start_time"])
        return notes_detected
    except Exception as e:
        warnings.warn(f"Error al ejecutar Spotify Basic Pitch: {e}")
        return []
