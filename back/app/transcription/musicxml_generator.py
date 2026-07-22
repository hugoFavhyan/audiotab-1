from music21 import stream, note, chord, duration, metadata, tempo, key, meter
import numpy as np
import re
import librosa
from fractions import Fraction

def quantize_duration(duration_seconds: float, bpm: float) -> float | Fraction:
    """
    Convierte una duración en segundos a una duración de compás (en pulsos / quarter notes)
    y la cuantiza a los valores musicales estándar y de tresillos más cercanos.
    """
    # Un pulso (quarter note) dura 60 / bpm segundos.
    beat_duration_seconds = 60.0 / bpm
    beats = duration_seconds / beat_duration_seconds
    
    # Lista de duraciones musicales estándar y de tresillos (en quarter notes)
    # Usamos Fraction para una representación matemática perfecta en music21,
    # lo cual evita imprecisiones de punto flotante al generar los grupos de tresillo.
    standard_durations = [
        (Fraction(1, 6), "1/6"), # Semicorchea en tresillo
        (Fraction(1, 4), "1/4"), # Semicorchea estándar
        (Fraction(1, 3), "1/3"), # Corchea en tresillo (1/3 de pulso)
        (Fraction(1, 2), "1/2"), # Corchea estándar
        (Fraction(2, 3), "2/3"), # Negra en tresillo
        (Fraction(3, 4), "3/4"), # Corchea con puntillo
        (Fraction(1, 1), "1"),   # Negra
        (Fraction(4, 3), "4/3"), # Blanca en tresillo
        (Fraction(3, 2), "3/2"), # Negra con puntillo
        (Fraction(2, 1), "2"),   # Blanca
        (Fraction(3, 1), "3"),   # Blanca con puntillo
        (Fraction(4, 1), "4"),   # Redonda
    ]
    
    # Encontrar el valor de fracción más cercano
    closest_dur, _ = min(standard_durations, key=lambda x: abs(float(x[0]) - beats))
    
    # Si es excesivamente pequeño, asignamos la semicorchea en tresillo como mínimo
    if float(closest_dur) < 0.16:
        return Fraction(1, 6)
    return closest_dur


def generate_musicxml(notes: list[dict], title: str = "Transcripción Automática", bpm: float = 120.0) -> stream.Score:
    """
    Genera un objeto Score de music21 a partir de una lista de notas transcritas y optimizadas para guitarra.
    Crea un único pentagrama de tablatura de guitarra (TAB Clef de 6 líneas con plicas de ritmo por debajo).
    Soporta acordes (como notas quintas) agrupando eventos con tiempos de inicio idénticos o casi idénticos.
    """
    from music21.articulations import FretIndication, StringIndication

    # 1. Crear el contenedor principal (Score)
    score = stream.Score()
    score.insert(0, metadata.Metadata(title=title))
    
    # 2. Crear una única parte para la tablatura
    tab_part = stream.Part()
    tab_part.id = "Tablatura"
    tab_part.partName = "Tablatura" # Asegurar que music21 escriba <part-name>Tablatura</part-name> en el XML
    tab_part.append(tempo.MetronomeMark(number=bpm))
    tab_part.append(meter.TimeSignature('4/4'))
    tab_part.append(key.KeySignature(0)) # Do mayor por defecto
    
    # Ordenar las notas por tiempo de inicio para procesarlas secuencialmente
    notes_sorted = sorted(notes, key=lambda x: x["start_time"])
    
    # Agrupar notas concurrentes en eventos de acordes (dentro de una ventana de 0.03s)
    grouped_events = []
    for note_data in notes_sorted:
        placed = False
        for event_group in grouped_events:
            # Si inicia casi al mismo tiempo, pertenece al mismo grupo/acorde
            if abs(event_group[0]["start_time"] - note_data["start_time"]) < 0.03:
                event_group.append(note_data)
                placed = True
                break
        if not placed:
            grouped_events.append([note_data])
            
    # Mantener el registro del tiempo actual en pulsos (beats) para insertar silencios (rests) si es necesario
    current_beat = 0.0
    
    for event_group in grouped_events:
        # Usar el tiempo de inicio de la primera nota del grupo
        start_seconds = event_group[0]["start_time"]
        # Usar la duración de la nota más larga en el grupo
        dur_seconds = max(n["duration"] for n in event_group)
        
        # Convertir tiempo de inicio a beats
        target_beat = start_seconds * (bpm / 60.0)
        
        # Cuantizar duración
        note_beat_dur = quantize_duration(dur_seconds, bpm)
        
        # Si hay una brecha entre el evento actual y la posición actual, insertamos un silencio (Rest)
        if target_beat > current_beat + 0.1: # Tolerancia pequeña
            rest_dur = target_beat - current_beat
            # Cuantizar también la duración del silencio para evitar fracciones extrañas
            quantized_rest_dur = max(0.25, round(rest_dur * 4) / 4)
            
            r_tab = note.Rest()
            r_tab.duration = duration.Duration(quantized_rest_dur)
            tab_part.append(r_tab)
            
            current_beat += quantized_rest_dur
            
        if len(event_group) == 1:
            # Nota simple
            n_data = event_group[0]
            pitch_name = n_data["pitch"]
            string_num = n_data.get("string")
            fret_num = n_data.get("fret")
            
            n_tab = note.Note(pitch_name)
            n_tab.duration = duration.Duration(note_beat_dur)
            
            if string_num is not None and fret_num is not None:
                f = FretIndication(int(fret_num))
                s = StringIndication(int(string_num))
                n_tab.articulations.append(f)
                n_tab.articulations.append(s)
                
            tab_part.append(n_tab)
        else:
            # Acorde (como una nota quinta)
            # Ordenar las notas por frecuencia ascendente (de graves a agudas)
            event_group_sorted = sorted(event_group, key=lambda x: x.get("frequency", librosa.note_to_hz(x["pitch"]) if "librosa" in globals() else 100.0))
            pitches = [n["pitch"] for n in event_group_sorted]
            
            c_tab = chord.Chord(pitches)
            c_tab.duration = duration.Duration(note_beat_dur)
            
            # Asignar la cuerda y el traste a cada nota interna de forma correspondiente
            for i, n_data in enumerate(event_group_sorted):
                string_num = n_data.get("string")
                fret_num = n_data.get("fret")
                if string_num is not None and fret_num is not None:
                    if i < len(c_tab.notes):
                        inner_note = c_tab.notes[i]
                        f = FretIndication(int(fret_num))
                        s = StringIndication(int(string_num))
                        inner_note.articulations.append(f)
                        inner_note.articulations.append(s)
                        
            tab_part.append(c_tab)
            
        current_beat = target_beat + note_beat_dur
        
    score.append(tab_part)
    return score


def post_process_tablature(xml_content: str, notes_sorted: list[dict] | None = None) -> str:
    """
    Busca de forma dinámica la parte 'Tablatura' en el string de XML generado por music21 y reemplaza su clave por
    un bloque de clave TAB y staff-details de 6 líneas con afinación estándar (Mi La Re Sol Si Mi).
    Esto es necesario para que visualizadores como OpenSheetMusicDisplay o AlphaTab lo interpreten
    como tablatura de guitarra real con líneas y trastes, en lugar de un pentagrama clásico.
    Además, inyecta la información de cuerda y traste (<technical><fret> y <string>) en todas las notas de acordes,
    ya que music21 tiene una limitación conocida donde omite la notación técnica en notas agrupadas (Chord notes).
    """
    # 1. Re-ordenar y aplanar las notas para asociar una a una con los tags <note> en el XML secuencialmente
    flat_guitar_notes = []
    if notes_sorted:
        notes_sorted_for_flat = sorted(notes_sorted, key=lambda x: x["start_time"])
        grouped_events = []
        for note_data in notes_sorted_for_flat:
            placed = False
            for event_group in grouped_events:
                if abs(event_group[0]["start_time"] - note_data["start_time"]) < 0.03:
                    event_group.append(note_data)
                    placed = True
                    break
            if not placed:
                grouped_events.append([note_data])
                
        for event_group in grouped_events:
            if len(event_group) == 1:
                flat_guitar_notes.append(event_group[0])
            else:
                # Ordenar igual que en generate_musicxml (de graves a agudas)
                event_group_sorted = sorted(event_group, key=lambda x: x.get("frequency", librosa.note_to_hz(x["pitch"]) if "librosa" in globals() else 100.0))
                for n_data in event_group_sorted:
                    flat_guitar_notes.append(n_data)

    # 2. Buscar dinámicamente el ID de parte basándose en el nombre de la parte "Tablatura"
    match = re.search(r'<score-part id="([^"]+)">\s*<part-name>[^<]*Tablatura[^<]*</part-name>', xml_content, re.IGNORECASE)
    if match:
        part_id = match.group(1)
    else:
        # Si no coincide, buscar el ID de la primera parte de forma genérica en el part-list
        part_match = re.search(r'<score-part id="([^"]+)">', xml_content)
        if part_match:
            part_id = part_match.group(1)
        else:
            part_id = "P1" # Fallback por si acaso
        
    part_tag = f'<part id="{part_id}">'
    part_start_idx = xml_content.find(part_tag)
    if part_start_idx == -1:
        # Si por alguna razón el ID de parte no coincide, buscar cualquier tag de <part id="...">
        part_any_match = re.search(r'<part id="([^"]+)">', xml_content)
        if part_any_match:
            part_tag = part_any_match.group(0)
            part_start_idx = xml_content.find(part_tag)
        else:
            return xml_content
        
    clef_start = xml_content.find('<clef>', part_start_idx)
    clef_end = xml_content.find('</clef>', clef_start)
    
    if clef_start == -1 or clef_end == -1:
        return xml_content
        
    clef_end += 7 # Incluir el tag de cierre </clef>
    
    # Reemplazo de clef clásica por clef TAB de 6 líneas con afinación de guitarra estándar
    tab_clef_and_details = """<clef>
        <sign>TAB</sign>
        <line>5</line>
      </clef>
      <staff-details>
        <staff-lines>6</staff-lines>
        <staff-tuning line="1">
          <tuning-step>E</tuning-step>
          <tuning-octave>2</tuning-octave>
        </staff-tuning>
        <staff-tuning line="2">
          <tuning-step>A</tuning-step>
          <tuning-octave>2</tuning-octave>
        </staff-tuning>
        <staff-tuning line="3">
          <tuning-step>D</tuning-step>
          <tuning-octave>3</tuning-octave>
        </staff-tuning>
        <staff-tuning line="4">
          <tuning-step>G</tuning-step>
          <tuning-octave>3</tuning-octave>
        </staff-tuning>
        <staff-tuning line="5">
          <tuning-step>B</tuning-step>
          <tuning-octave>3</tuning-octave>
        </staff-tuning>
        <staff-tuning line="6">
          <tuning-step>E</tuning-step>
          <tuning-octave>4</tuning-octave>
        </staff-tuning>
      </staff-details>"""
      
    before_part = xml_content[:part_start_idx]
    part_content = xml_content[part_start_idx:]
    
    # Encontrar la clave relativa dentro de part_content
    clef_rel_start = clef_start - part_start_idx
    clef_rel_end = clef_end - part_start_idx
    
    part_content_replaced = part_content[:clef_rel_start] + tab_clef_and_details + part_content[clef_rel_end:]
    xml_content_clef_replaced = before_part + part_content_replaced

    # 3. Post-procesamiento secuencial de notas para inyectar correctamente trastes y cuerdas
    note_pattern = re.compile(r'<note(.*?)</note>', re.DOTALL)
    note_index = 0
    
    def replace_note(match_obj):
        nonlocal note_index
        note_body = match_obj.group(1)
        
        # Saltar si es un silencio (rest)
        if '<rest' in note_body:
            return match_obj.group(0)
            
        if note_index >= len(flat_guitar_notes):
            return match_obj.group(0)
            
        n_data = flat_guitar_notes[note_index]
        note_index += 1
        
        string_num = n_data.get("string")
        fret_num = n_data.get("fret")
        
        if string_num is None or fret_num is None:
            return match_obj.group(0)
            
        technical_str = f"""<notations>
          <technical>
            <fret>{int(fret_num)}</fret>
            <string>{int(string_num)}</string>
          </technical>
        </notations>"""
        
        # Eliminar cualquier <notations>...</notations> previo para evitar duplicados
        note_body_clean = re.sub(r'<notations>.*?</notations>', '', note_body, flags=re.DOTALL)
        
        # Agregar la nueva estructura técnica al final de la nota
        updated_note_body = note_body_clean.rstrip() + "\n        " + technical_str + "\n      "
        return f'<note{updated_note_body}</note>'
        
    final_processed_xml = note_pattern.sub(replace_note, xml_content_clef_replaced)
    return final_processed_xml
