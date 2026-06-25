import math

# Afinación estándar de guitarra: Cuerdas de 1 (más fina/aguda) a 6 (más gruesa/grave)
# Mapeamos la cuerda al MIDI pitch al aire.
TUNING_STANDARD = {
    1: 64,  # E4 (Mi)
    2: 59,  # B3 (Si)
    3: 55,  # G3 (Sol)
    4: 50,  # D3 (Re)
    5: 45,  # A2 (La)
    6: 40,  # E2 (Mi)
}

MAX_FRETS = 22

def get_possible_fingerings(midi_pitch: int) -> list[tuple[int, int]]:
    """
    Retorna todas las combinaciones posibles de (cuerda, traste) para una nota MIDI dada.
    """
    options = []
    for string, open_pitch in TUNING_STANDARD.items():
        fret = midi_pitch - open_pitch
        if 0 <= fret <= MAX_FRETS:
            options.append((string, fret))
    # Ordenar por cuerda (de agudas a graves)
    return options


def optimize_fingering(notes: list[dict]) -> list[dict]:
    """
    Asigna a cada nota un par (cuerda, traste) optimizando la comodidad de digitación.
    Utiliza un algoritmo greedy con memoria de posición anterior para minimizar el salto de trastes.
    """
    if not notes:
        return []
        
    last_fret = None
    last_string = None
    
    assigned_notes = []
    
    for note in notes:
        midi = note["midi"]
        options = get_possible_fingerings(midi)
        
        if not options:
            # Si no entra en el rango de guitarra, se le asigna valor nulo o por defecto
            note["string"] = None
            note["fret"] = None
            assigned_notes.append(note)
            continue
            
        # Si es la primera nota, preferimos trastes bajos o cuerda al aire
        if last_fret is None or last_string is None:
            # Seleccionar opción con menor traste o cuerda al aire (fret == 0)
            best_option = min(options, key=lambda x: (x[1] == 0, x[1]))
        else:
            # Calcular un "costo" para cada opción basada en la distancia al traste y cuerda anterior
            best_option = options[0]
            best_cost = float('inf')
            
            for string, fret in options:
                cost = 0.0
                
                # Penalizar cambio de traste drástico (si no es al aire)
                if fret != 0 and last_fret != 0:
                    cost += abs(fret - last_fret) * 1.5
                elif fret != 0 and last_fret == 0:
                    # Si antes fue al aire y ahora no, penalizamos según posición promedio cómoda (ej. traste 3)
                    cost += abs(fret - 3) * 0.8
                
                # Penalizar salto de cuerdas
                cost += abs(string - last_string) * 1.0
                
                # Preferencia por trastes cómodos (trastes 0 a 12 son más fáciles de tocar que >15)
                if fret > 12:
                    cost += (fret - 12) * 2.0
                    
                # Cuerdas al aire son generalmente preferidas si están cerca de la posición del traste
                if fret == 0:
                    cost -= 0.5
                    
                if cost < best_cost:
                    best_cost = cost
                    best_option = (string, fret)
                    
        string_selected, fret_selected = best_option
        note["string"] = string_selected
        note["fret"] = fret_selected
        
        # Guardar última posición de referencia (si no es cuerda al aire, ayuda a fijar la "mano")
        if fret_selected != 0:
            last_fret = fret_selected
            last_string = string_selected
            
        assigned_notes.append(note)
        
    return assigned_notes
