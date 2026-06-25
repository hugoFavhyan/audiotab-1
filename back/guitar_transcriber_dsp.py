"""
Guitar Audio DSP Transcriber & Ergonomic Tab Generator
------------------------------------------------------
Este script procesa un archivo de audio de guitarra (con posible ruido o distorsión),
aplica técnicas de procesamiento digital de señales (DSP) para limpiar la señal,
detecta notas precisas y las convierte en una tablatura de guitarra optimizada
ergonómicamente mediante un algoritmo de coste de distancia física mínima.
"""

import os
import json
import numpy as np
import scipy.signal as signal
import librosa

# =====================================================================
# 1. PROCESAMIENTO Y FILTRADO DSP (LIMPIEZA DE AUDIO)
# =====================================================================

def clean_and_preprocess_audio(file_path: str, target_sr: int = 22050) -> tuple[np.ndarray, int]:
    """
    Carga el audio y aplica técnicas DSP avanzadas para limpiar la señal:
    - Normalización y conversión a monoaural.
    - Filtro Paso Banda Butterworth (para aislar frecuencias fundamentales de guitarra).
    - HPSS (Separación Armónica-Percusiva) para aislar ataques y reducir ruidos de rasgueo/púas.
    - Puerta de Ruido espectral básica para eliminar componentes de baja amplitud y distorsiones.
    """
    # 1. Cargar el audio
    y, sr = librosa.load(file_path, sr=target_sr, mono=True)
    
    # 2. Normalizar la señal
    if len(y) > 0 and np.max(np.abs(y)) > 0:
        y = y / np.max(np.abs(y))
        
    # 3. Aplicar Filtro Paso Banda Butterworth (Frecuencias típicas de guitarra: ~70Hz a ~1200Hz)
    # Esto elimina ruidos de baja frecuencia (sub-graves) y ruidos/distorsiones de muy alta frecuencia.
    f_low = 70.0  # Hz
    f_high = 1200.0  # Hz
    nyquist = 0.5 * sr
    low = f_low / nyquist
    high = f_high / nyquist
    
    b, a = signal.butter(N=4, Wn=[low, high], btype='band')
    y_filtered = signal.filtfilt(b, a, y)
    
    # 4. Separación Armónica-Percusiva (HPSS)
    # La distorsión añade armónicos ásperos e inestables que distorsionan el tono fundamental.
    # El filtrado armónico ayuda a suavizar la envolvente espectral y concentrarse en el tono puro,
    # mientras que el percusivo ayuda a aislar los onsets (ataques de púa).
    y_harmonic, y_percussive = librosa.effects.hpss(y_filtered)
    
    # 5. Puerta de Ruido Espectral (Noise Gate) en el dominio temporal
    # Silencia las partes donde la energía local está por debajo de un umbral (ruido de fondo o distorsión residual)
    frame_length = 2048
    hop_length = 512
    rmse = librosa.feature.rms(y=y_harmonic, frame_length=frame_length, hop_length=hop_length)[0]
    # Normalizar RMS
    rmse /= (np.max(rmse) if np.max(rmse) > 0 else 1)
    
    # Aplicar puerta de ruido suave sobre la señal armónica filtrada
    threshold = 0.05
    y_clean = np.zeros_like(y_harmonic)
    
    for i in range(len(rmse)):
        start_sample = i * hop_length
        end_sample = min(start_sample + frame_length, len(y_clean))
        if rmse[i] > threshold:
            y_clean[start_sample:end_sample] = y_harmonic[start_sample:end_sample]
            
    # Retornar señal limpia y normalizada
    if np.max(np.abs(y_clean)) > 0:
        y_clean = y_clean / np.max(np.abs(y_clean))
        
    return y_clean, sr


def extract_notes_with_pyin(y: np.ndarray, sr: int) -> list[dict]:
    """
    Aplica detección de onsets para segmentar las notas e interseca esta información con pYIN
    para extraer las notas musicales MIDI con su tiempo de inicio, duración y frecuencia fundamental.
    """
    # Detectar onsets (puntos de ataque de cada nota) para saber cuándo inicia cada una de forma precisa
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, hop_length=512, backtrack=True)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)
    
    # Rango de afinación de guitarra (E2 ~ 82Hz hasta C6 ~ 1047Hz)
    fmin = librosa.note_to_hz('E2')
    fmax = librosa.note_to_hz('C6')
    
    # pYIN (Probabilistic YIN) es altamente resistente al ruido gracias a su modelado probabilístico de transiciones
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y, 
        fmin=fmin, 
        fmax=fmax, 
        sr=sr,
        fill_na=None,
        hop_length=512
    )
    
    times = librosa.times_like(f0, sr=sr)
    detected_notes = []
    
    # Si no se detectan onsets, usamos segmentación por frames de pYIN
    if len(onset_times) == 0:
        # Fallback de agrupación secuencial de pYIN
        current_note = None
        current_start = None
        for i, freq in enumerate(f0):
            if freq is not None and not np.isnan(freq) and voiced_flag[i]:
                note_name = librosa.hz_to_note(freq, unicode=False)
                if current_note != note_name:
                    if current_note is not None:
                        dur = float(times[i] - current_start)
                        if dur >= 0.08:
                            detected_notes.append({
                                "pitch": current_note,
                                "midi": int(librosa.note_to_midi(current_note)),
                                "start_time": float(current_start),
                                "duration": float(dur)
                            })
                    current_note = note_name
                    current_start = times[i]
            else:
                if current_note is not None:
                    dur = float(times[i] - current_start)
                    if dur >= 0.08:
                        detected_notes.append({
                            "pitch": current_note,
                            "midi": int(librosa.note_to_midi(current_note)),
                            "start_time": float(current_start),
                            "duration": float(dur)
                        })
                    current_note = None
                    current_start = None
    else:
        # Segmentación guiada por onsets:
        # Para cada ventana de tiempo entre onsets consecutivos, calculamos la frecuencia pYIN dominante
        for i in range(len(onset_times)):
            start_t = onset_times[i]
            end_t = onset_times[i+1] if i + 1 < len(onset_times) else (len(y) / sr)
            
            # Extraer las frecuencias detectadas en este intervalo
            idx_range = np.where((times >= start_t) & (times < end_t))[0]
            if len(idx_range) == 0:
                continue
                
            freqs_in_segment = [f0[j] for j in idx_range if f0[j] is not None and not np.isnan(f0[j])]
            
            if freqs_in_segment:
                # Usar la mediana de las frecuencias para filtrar picos espurios o vibratos excesivos
                median_freq = np.median(freqs_in_segment)
                note_name = librosa.hz_to_note(median_freq, unicode=False)
                midi_val = int(librosa.note_to_midi(note_name))
                
                detected_notes.append({
                    "pitch": note_name,
                    "midi": midi_val,
                    "start_time": float(start_t),
                    "duration": float(end_t - start_t)
                })
                
    return detected_notes


# =====================================================================
# 2. LOGICA DE LA GUITARRA Y MAPEO DE AFINACIÓN
# =====================================================================

# Cuerdas de guitarra clásica/eléctrica en afinación estándar
# Cuerda 1 (Mi agudo) a Cuerda 6 (Mi grave)
GUITAR_TUNING = {
    1: 64,  # E4
    2: 59,  # B3
    3: 55,  # G3
    4: 50,  # D3
    5: 45,  # A2
    6: 40,  # E2
}

MAX_FRETS = 24  # Soportamos guitarras de hasta 24 trastes

def get_guitar_options(midi_pitch: int) -> list[tuple[int, int]]:
    """
    Encuentra todas las posiciones físicas (cuerda, traste) donde se puede tocar una nota MIDI dada.
    Retorna una lista de tuplas `(cuerda, traste)`.
    """
    positions = []
    for string, open_midi in GUITAR_TUNING.items():
        fret = midi_pitch - open_midi
        if 0 <= fret <= MAX_FRETS:
            positions.append((string, fret))
    return positions


# =====================================================================
# 3. ALGORITMO ERGONÓMICO DE TRANSICIÓN FÍSICA MÍNIMA
# =====================================================================

def solve_ergonomic_tab(notes: list[dict]) -> list[dict]:
    """
    Algoritmo ergonómico de optimización de digitación.
    Determina la mejor posición de cuerda y traste para cada nota minimizando el desplazamiento de la mano.
    Utiliza un diseño basado en costes de transición física:
    - Penaliza grandes desplazamientos entre trastes (distancia longitudinal).
    - Penaliza cambios excesivos de cuerdas (distancia transversal).
    - Prefiere posiciones de traste más bajas y accesibles (trastes 0 a 12).
    - Otorga una ligera bonificación a cuerdas al aire (traste 0) debido a su facilidad física.
    """
    if not notes:
        return []
        
    last_fret = None
    last_string = None
    optimized_notes = []
    
    for note_data in notes:
        midi = note_data["midi"]
        options = get_guitar_options(midi)
        
        if not options:
            # Fuera de rango de guitarra estándar
            note_data["string"] = None
            note_data["fret"] = None
            optimized_notes.append(note_data)
            continue
            
        # Si es la primera nota, priorizamos trastes cómodos o cuerdas al aire
        if last_fret is None or last_string is None:
            # Preferir traste 0 o trastes más bajos
            best_position = min(options, key=lambda pos: (pos[1] != 0, pos[1]))
        else:
            best_position = options[0]
            best_cost = float('inf')
            
            for string, fret in options:
                cost = 0.0
                
                # 1. Distancia longitudinal (trastes)
                if fret != 0 and last_fret != 0:
                    cost += abs(fret - last_fret) * 1.5  # Peso del desplazamiento por el mástil
                elif fret != 0 and last_fret == 0:
                    # Salto desde cuerda al aire a traste (aproximamos una posición neutral en traste 3)
                    cost += abs(fret - 3) * 0.8
                
                # 2. Distancia transversal (cuerdas)
                cost += abs(string - last_string) * 1.0  # Coste de saltar cuerdas vecinas
                
                # 3. Trastes altos son menos ergonómicos / de difícil acceso (ej. más allá del traste 12)
                if fret > 12:
                    cost += (fret - 12) * 2.0
                    
                # 4. Facilidad de cuerda al aire
                if fret == 0:
                    cost -= 0.5  # Recompensa por cuerda libre
                    
                if cost < best_cost:
                    best_cost = cost
                    best_position = (string, fret)
                    
        string_selected, fret_selected = best_position
        note_data["string"] = string_selected
        note_data["fret"] = fret_selected
        
        # Guardar la última posición de referencia (siempre que no sea cuerda al aire, para mantener anclada la mano)
        if fret_selected != 0:
            last_fret = fret_selected
            last_string = string_selected
            
        optimized_notes.append(note_data)
        
    return optimized_notes


# =====================================================================
# 4. EXPORTACIÓN Y REPRESENTACIÓN VISUAL
# =====================================================================

def generate_ascii_tab(notes: list[dict]) -> str:
    """
    Genera una representación visual en texto plano (ASCII Tab) a partir de notas
    que contienen las asignaciones ergonómicas de cuerda y traste.
    """
    # Crear 6 líneas para las cuerdas (1: Mi agudo, ..., 6: Mi grave)
    strings = {i: [] for i in range(1, 7)}
    
    # Ordenar por tiempo de inicio para que la tablatura fluya secuencialmente de izquierda a derecha
    sorted_notes = sorted(notes, key=lambda x: x["start_time"])
    
    for note_data in sorted_notes:
        string_idx = note_data.get("string")
        fret_val = note_data.get("fret")
        
        if string_idx is None or fret_val is None:
            continue
            
        # Añadir trastes a su cuerda correspondiente y guiones a las demás
        for s in range(1, 7):
            if s == string_idx:
                strings[s].append(f"-{fret_val}-")
            else:
                # Mantener el espaciado alineado según el tamaño del texto del traste
                spacing_len = len(f"-{fret_val}-")
                strings[s].append("-" * spacing_len)
                
    # Unir las listas para formar las cuerdas visuales
    guitar_names = {1: "E|", 2: "B|", 3: "G|", 4: "D|", 5: "A|", 6: "E|"}
    ascii_lines = []
    for s in range(1, 7):
        line_content = "".join(strings[s])
        ascii_lines.append(f"{guitar_names[s]}{line_content}")
        
    return "\n".join(ascii_lines)


# =====================================================================
# EJECUCIÓN DE PRUEBA DE CONCEPTO
# =====================================================================

if __name__ == "__main__":
    # Generamos un set de notas de prueba para simular la transcripción
    # de la escala Do Mayor (C Major Scale) tocada secuencialmente.
    # Do (MIDI 48), Re (MIDI 50), Mi (MIDI 52), Fa (MIDI 53), Sol (MIDI 55), La (MIDI 57), Si (MIDI 59), Do (MIDI 60).
    test_scale_notes = [
        {"pitch": "C3", "midi": 48, "start_time": 0.0, "duration": 0.5},
        {"pitch": "D3", "midi": 50, "start_time": 0.5, "duration": 0.5},
        {"pitch": "E3", "midi": 52, "start_time": 1.0, "duration": 0.5},
        {"pitch": "F3", "midi": 53, "start_time": 1.5, "duration": 0.5},
        {"pitch": "G3", "midi": 55, "start_time": 2.0, "duration": 0.5},
        {"pitch": "A3", "midi": 57, "start_time": 2.5, "duration": 0.5},
        {"pitch": "B3", "midi": 59, "start_time": 3.0, "duration": 0.5},
        {"pitch": "C4", "midi": 60, "start_time": 3.5, "duration": 0.5},
    ]
    
    print("--- 1. NOTAS MUSICALES DETECTADAS POR EL SUBSISTEMA DSP ---")
    for n in test_scale_notes:
        print(f"Nota: {n['pitch']} (MIDI {n['midi']}) | Inicio: {n['start_time']}s")
        
    print("\n--- 2. RESOLUCIÓN DE AMBIGÜEDAD ERGONÓMICA DE LA MANO ---")
    optimized_scale = solve_ergonomic_tab(test_scale_notes)
    for n in optimized_scale:
        print(f"Nota: {n['pitch']} -> Cuerda: {n['string']}, Traste: {n['fret']}")
        
    print("\n--- 3. REPRESENTACIÓN VISUAL EN TEXTO PLANO (TABLATURA ASCII) ---")
    tab_ascii = generate_ascii_tab(optimized_scale)
    print(tab_ascii)
