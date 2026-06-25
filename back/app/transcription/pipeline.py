import os
import tempfile
from .audio import preprocess_audio, estimate_tempo
from .pitch import detect_pitch_monophonic, detect_pitch_polyphonic, BASIC_PITCH_AVAILABLE
from .fingering import optimize_fingering
from .musicxml_generator import generate_musicxml, post_process_tablature
from .separation import separate_guitar_stem
from .ai_fingering import GuitarBERTModel

def run_transcription_pipeline(
    file_path: str,
    mode: str = "auto",  # "auto", "monophonic", "polyphonic"
    bpm: float = 120.0,
    title: str = "Mi Transcripción de Guitarra",
    power_chords: bool = False,
    demucs_separation: bool = False,
    fingering_algorithm: str = "heuristic",
    fingering_style: str = "classic"
) -> tuple[list[dict], str]:
    """
    Ejecuta el pipeline completo de procesamiento de audio para guitarra:
    1. Separación opcional de pistas con Demucs.
    2. Preprocesamiento de audio.
    3. Detección de pitch (monofónico o polifónico).
    4. Asignación de cuerdas y trastes (optimización de tablatura).
    5. Generación de estructura music21 y exportación a MusicXML.
    
    Retorna una tupla (notas_con_digitacion, string_musicxml).
    """
    # 1. Separar pista de guitarra opcionalmente
    active_file_path = file_path
    if demucs_separation:
        active_file_path = separate_guitar_stem(file_path)

    # 2. Preprocesamos el audio para análisis y posible detección de BPM
    y, sr = preprocess_audio(active_file_path)
    
    # Si bpm es <= 0, estimar el tempo automáticamente basado en el audio
    if bpm <= 0.0:
        bpm = estimate_tempo(y, sr)
        
    # 1. Determinar el método de pitch detection
    use_polyphonic = False
    if mode == "polyphonic":
        use_polyphonic = True
    elif mode == "monophonic":
        use_polyphonic = False
    else:  # "auto"
        use_polyphonic = BASIC_PITCH_AVAILABLE
        
    notes = []
    
    # 2. Ejecutar la detección
    if use_polyphonic and BASIC_PITCH_AVAILABLE:
        notes = detect_pitch_polyphonic(file_path)
    
    # Si falló la polifonía o se seleccionó monofónico de forma explícita
    if not notes:
        notes = detect_pitch_monophonic(y, sr)
        
    # 3. Optimizar digitación (Asignar cuerdas y trastes) - Heurístico vs AI GuitarBERT
    if fingering_algorithm == "guitar_bert":
        notes_optimized = GuitarBERTModel().transcribe_with_transformer(notes, style=fingering_style)
    else:
        notes_optimized = optimize_fingering(notes)
    
    # Si el modo quintas está activo, expandimos cada nota optimizada para formar un acorde de quinta física
    if power_chords:
        from .pitch import midi_to_note_name
        extended_notes = []
        for r_note in notes_optimized:
            extended_notes.append(r_note) # Agregar nota raíz
            
            s = r_note.get("string")
            f = r_note.get("fret")
            root_midi = r_note.get("midi")
            
            # Solo generamos quintas para notas válidas asignadas a las cuerdas graves 6, 5, 4 y 3
            if s in [3, 4, 5, 6] and f is not None and root_midi is not None:
                # 1. Calcular Quinta (S-1)
                fifth_midi = root_midi + 7
                fifth_fret = f + 3 if s == 3 else f + 2
                fifth_string = s - 1
                fifth_freq = 440.0 * (2.0 ** ((fifth_midi - 69.0) / 12.0))
                
                if 0 <= fifth_fret <= 22:
                    extended_notes.append({
                        "pitch": midi_to_note_name(fifth_midi),
                        "midi": fifth_midi,
                        "frequency": float(fifth_freq),
                        "start_time": r_note["start_time"],
                        "duration": r_note["duration"],
                        "string": fifth_string,
                        "fret": fifth_fret
                    })
                
                # 2. Calcular Octava (S-2)
                octave_midi = root_midi + 12
                octave_fret = f + 3 if s in [3, 4] else f + 2
                octave_string = s - 2
                octave_freq = 440.0 * (2.0 ** ((octave_midi - 69.0) / 12.0))
                
                if 0 <= octave_fret <= 22:
                    extended_notes.append({
                        "pitch": midi_to_note_name(octave_midi),
                        "midi": octave_midi,
                        "frequency": float(octave_freq),
                        "start_time": r_note["start_time"],
                        "duration": r_note["duration"],
                        "string": octave_string,
                        "fret": octave_fret
                    })
        notes_optimized = extended_notes
    
    # 4. Generar el documento con music21
    score = generate_musicxml(notes_optimized, title=title, bpm=bpm)
    
    # 5. Obtener el archivo MusicXML en formato string
    xml_content = ""
    fd, temp_path = tempfile.mkstemp(suffix=".xml")
    try:
        # music21 escribe el archivo en temp_path
        score.write('musicxml', fp=temp_path)
        with open(temp_path, "r", encoding="utf-8") as f:
            xml_content = f.read()
        # Post-procesar para transformar el pentagrama "Tablatura" en clave TAB real
        xml_content = post_process_tablature(xml_content)
    finally:
        os.close(fd)
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        # Eliminar archivo temporal de la separación de Demucs si corresponde
        if demucs_separation and active_file_path != file_path and os.path.exists(active_file_path):
            try:
                os.remove(active_file_path)
            except OSError:
                pass
                
    return notes_optimized, xml_content
