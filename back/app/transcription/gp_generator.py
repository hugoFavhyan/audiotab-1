import io
import math
import guitarpro

def beats_to_gp_duration(beats: float) -> guitarpro.Duration:
    """
    Mapea una duración en compases (quarter notes) a un objeto guitarpro.Duration.
    """
    standards = [
        (4.0, 1, False),  # Redonda
        (3.0, 2, True),   # Blanca con puntillo
        (2.0, 2, False),  # Blanca
        (1.5, 4, True),   # Negra con puntillo
        (1.0, 4, False),  # Negra
        (0.75, 8, True),  # Corchea con puntillo
        (0.5, 8, False),  # Corchea
        (0.25, 16, False) # Semicorchea
    ]
    # Encontrar la duración estándar más cercana
    closest = min(standards, key=lambda x: abs(x[0] - beats))
    
    gp_dur = guitarpro.Duration()
    gp_dur.value = closest[1]
    gp_dur.isDotted = closest[2]
    return gp_dur

def generate_gp5(notes: list[dict], title: str = "Transcripción Automática", bpm: float = 120.0) -> bytes:
    """
    Genera un archivo binario GuitarPro (.gp5) a partir de la lista de notas digitadas.
    Retorna los bytes del archivo generado.
    """
    # 1. Inicializar canción y metadatos
    song = guitarpro.Song()
    song.title = title
    song.tempo = int(round(bpm)) if bpm > 0 else 120
    
    # Asegurar que haya al menos un track
    if not song.tracks:
        track = guitarpro.Track(song)
        track.name = "Guitarra"
        song.tracks.append(track)
    else:
        track = song.tracks[0]
        track.name = "Guitarra"

    # Configurar afinación estándar de 6 cuerdas (Mi, La, Re, Sol, Si, Mi)
    # PyGuitarPro inicializa las cuerdas por defecto en afinación estándar
    
    # 2. Procesar notas y convertirlas a tiempos de compás (beats)
    notes_sorted = sorted(notes, key=lambda x: x["start_time"])
    
    # Convertir tiempos a beats absolutos (1.0 = una negra / quarter note)
    for n in notes_sorted:
        n["start_beat"] = n["start_time"] * (bpm / 60.0)
        n["dur_beat"] = n["duration"] * (bpm / 60.0)
        
    # Agrupar notas por posición de inicio para soportar polifonía (acordes en el mismo beat)
    # Usaremos una tolerancia pequeña para agrupar notas simultáneas (arpegios/acordes imperfectos)
    tolerance = 0.05
    grouped_beats = []
    
    for n in notes_sorted:
        if n.get("string") is None or n.get("fret") is None:
            continue
            
        # Intentar agrupar con un beat existente cercano
        added = False
        for group in grouped_beats:
            if abs(group["start_beat"] - n["start_beat"]) < tolerance:
                group["notes"].append(n)
                # Duración del grupo es el máximo de las notas
                group["dur_beat"] = max(group["dur_beat"], n["dur_beat"])
                added = True
                break
        if not added:
            grouped_beats.append({
                "start_beat": n["start_beat"],
                "dur_beat": n["dur_beat"],
                "notes": [n]
            })
            
    # Ordenar grupos de beats por su tiempo de inicio
    grouped_beats.sort(key=lambda x: x["start_beat"])
    
    # 3. Determinar número total de compases necesarios (4.0 beats por compás)
    if grouped_beats:
        last_beat = max(g["start_beat"] + g["dur_beat"] for g in grouped_beats)
        total_measures = int(math.ceil(last_beat / 4.0))
    else:
        total_measures = 1
        
    total_measures = max(1, total_measures)
    
    # Sincronizar MeasureHeaders de la canción y Measures del track
    # El Song se inicializa con 1 MeasureHeader por defecto, igual que Track.measures
    while len(song.measureHeaders) < total_measures:
        next_num = len(song.measureHeaders) + 1
        mh = guitarpro.MeasureHeader(number=next_num)
        song.measureHeaders.append(mh)
        
        m = guitarpro.Measure(track, header=mh)
        track.measures.append(m)
        
    # 4. Rellenar cada compás secuencialmente (asegurando exactamente 4.0 beats de duración por compás)
    for m_idx in range(total_measures):
        measure = track.measures[m_idx]
        voice = measure.voices[0]  # Usar Voice 1
        voice.beats = []
        
        measure_start = m_idx * 4.0
        measure_end = measure_start + 4.0
        
        # Filtrar beats agrupados que caen en este compás
        m_groups = [g for g in grouped_beats if measure_start <= g["start_beat"] < measure_end]
        m_groups.sort(key=lambda x: x["start_beat"])
        
        ptr = measure_start
        
        for g in m_groups:
            g_start = g["start_beat"]
            g_dur = g["dur_beat"]
            
            # Si hay un silencio antes del grupo
            if g_start > ptr:
                silence_beats = g_start - ptr
                # Agregar beat de silencio (rest)
                rest_beat = guitarpro.Beat(voice=voice)
                rest_beat.status = guitarpro.BeatStatus.rest
                rest_beat.duration = beats_to_gp_duration(silence_beats)
                voice.beats.append(rest_beat)
                ptr = g_start
                
            # Agregar beat de notas (normal)
            # Acotar duración del beat si supera el límite del compás actual
            if g_start + g_dur > measure_end:
                g_dur = measure_end - g_start
                
            beat = guitarpro.Beat(voice=voice)
            beat.status = guitarpro.BeatStatus.normal
            beat.duration = beats_to_gp_duration(g_dur)
            
            # Crear notas dentro del beat
            for note_data in g["notes"]:
                # GuitarPro cuerdas van de 1 (Mi agudo) a 6 (Mi grave)
                # PyGuitarPro requiere string (1-indexed) y value (traste, 0-indexed)
                gp_note = guitarpro.Note(
                    beat=beat,
                    value=int(note_data["fret"]),
                    string=int(note_data["string"])
                )
                beat.notes.append(gp_note)
                
            voice.beats.append(beat)
            ptr = g_start + g_dur
            
        # Si queda silencio al final del compás
        if ptr < measure_end:
            silence_beats = measure_end - ptr
            rest_beat = guitarpro.Beat(voice=voice)
            rest_beat.status = guitarpro.BeatStatus.rest
            rest_beat.duration = beats_to_gp_duration(silence_beats)
            voice.beats.append(rest_beat)
            
    # 5. Guardar la canción en un stream de bytes en memoria
    buffer = io.BytesIO()
    guitarpro.write(song, buffer)
    return buffer.getvalue()
