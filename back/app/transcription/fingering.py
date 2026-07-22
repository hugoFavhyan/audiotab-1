import math
import logging

logger = logging.getLogger("fingering")

# Afinaciones comunes de guitarra: Cuerdas de 1 (más fina/aguda) a 6 (más gruesa/grave)
TUNINGS = {
    "Standard": {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40},      # E4, B3, G3, D3, A2, E2
    "Drop D": {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 38},        # E4, B3, G3, D3, A2, D2
    "Half-Step Down": {1: 63, 2: 58, 3: 54, 4: 49, 5: 44, 6: 39},  # Eb4, Bb3, Gb3, Db3, Ab2, Eb2
    "Drop C": {1: 62, 2: 57, 3: 53, 4: 48, 5: 43, 6: 36},        # D4, A3, F3, C3, G2, C2
    "Whole-Step Down": {1: 62, 2: 57, 3: 53, 4: 48, 5: 43, 6: 38}, # D4, A3, F3, C3, G2, D2
}

MAX_FRETS = 22

def detect_optimal_tuning(notes: list[dict]) -> tuple[str, dict[int, int]]:
    """
    Analiza las notas MIDI de la composición y determina la afinación óptima de la guitarra
    (Standard, Drop D, Half-Step Down, etc.) que minimiza las notas fuera de rango
    y optimiza la ergonomía de los trastes resultantes.
    """
    if not notes:
        return "Standard", TUNINGS["Standard"]
        
    best_name = "Standard"
    best_map = TUNINGS["Standard"]
    min_penalty = float('inf')
    
    for name, tuning_map in TUNINGS.items():
        penalty = 0.0
        playable_count = 0
        
        for note in notes:
            midi = note["midi"]
            has_option = False
            frets = []
            
            for string, open_pitch in tuning_map.items():
                fret = midi - open_pitch
                if 0 <= fret <= MAX_FRETS:
                    has_option = True
                    frets.append(fret)
                    
            if not has_option:
                # Fuerte penalización si la nota no se puede tocar en esta afinación
                penalty += 150.0
            else:
                playable_count += 1
                best_fret = min(frets)
                # Penalizar trastes muy altos (más de 12) por incomodidad en acordes/solos base
                if best_fret > 12:
                    penalty += (best_fret - 12) * 2.0
                # Ligera recompensa por trastes abiertos o bajos muy cómodos (trastes 1 a 5)
                elif 0 <= best_fret <= 5:
                    penalty -= 0.5
                    
        # Promediar penalización
        if playable_count > 0:
            penalty = penalty / len(notes)
        else:
            penalty = float('inf')
            
        if penalty < min_penalty:
            min_penalty = penalty
            best_name = name
            best_map = tuning_map
            
    logger.info(f"Afinación óptima detectada de forma inteligente: {best_name}")
    return best_name, best_map


def get_possible_fingerings(midi_pitch: int, tuning_map: dict[int, int] = None) -> list[tuple[int, int]]:
    """
    Retorna todas las combinaciones posibles de (cuerda, traste) para una nota MIDI dada bajo una afinación específica.
    """
    if tuning_map is None:
        tuning_map = TUNINGS["Standard"]
        
    options = []
    for string, open_pitch in tuning_map.items():
        fret = midi_pitch - open_pitch
        if 0 <= fret <= MAX_FRETS:
            options.append((string, fret))
    # Ordenar por cuerda (de agudas a graves)
    return options


def optimize_fingering(notes: list[dict], tuning_map: dict[int, int] = None) -> list[dict]:
    """
    Asigna a cada nota un par (cuerda, traste) optimizando la comodidad de digitación.
    Utiliza un algoritmo de costo ergonómico con memoria de posición anterior para minimizar saltos y estiramientos.
    """
    if not notes:
        return []
        
    # Si no se provee afinación, la detectamos dinámicamente de las notas
    if tuning_map is None:
        tuning_name, tuning_map = detect_optimal_tuning(notes)
    else:
        tuning_name = "Custom/Selected"
        
    last_fret = None
    last_string = None
    assigned_notes = []
    
    for note in notes:
        midi = note["midi"]
        options = get_possible_fingerings(midi, tuning_map)
        
        if not options:
            note["string"] = None
            note["fret"] = None
            assigned_notes.append(note)
            continue
            
        # Si es la primera nota, preferimos trastes bajos cómodos (entre 1 y 5) o cuerda al aire
        if last_fret is None or last_string is None:
            # Seleccionar la opción que tenga el traste más cercano a la zona cómoda (traste 2-3)
            best_option = min(options, key=lambda x: (x[1] == 0, abs(x[1] - 3)))
        else:
            best_option = options[0]
            best_cost = float('inf')
            
            for string, fret in options:
                cost = 0.0
                
                # 1. Penalizar cambio drástico de traste (estiramiento de mano de más de 4 trastes)
                if fret != 0 and last_fret != 0:
                    distance = abs(fret - last_fret)
                    if distance > 4:
                        cost += (distance - 4) * 5.0  # Penalización severa por estiramiento excesivo
                    else:
                        cost += distance * 1.2
                elif fret != 0 and last_fret == 0:
                    # Si venimos de cuerda al aire, la mano se posiciona en una zona neutral (traste 3 promedio)
                    cost += abs(fret - 3) * 0.8
                
                # 2. Penalizar saltos excesivos de cuerda (cruces verticales incómodos)
                cost += abs(string - last_string) * 1.5
                
                # 3. Penalizar trastes muy altos (más de 12) por dificultad física, a menos que sea necesario
                if fret > 12:
                    cost += (fret - 12) * 2.5
                
                # 4. Preferir cuerdas al aire de forma moderada por comodidad acústica
                if fret == 0:
                    cost -= 0.5
                    
                if cost < best_cost:
                    best_cost = cost
                    best_option = (string, fret)
                    
        string_selected, fret_selected = best_option
        note["string"] = string_selected
        note["fret"] = fret_selected
        note["tuning_name"] = tuning_name
        
        if fret_selected != 0:
            last_fret = fret_selected
            last_string = string_selected
            
        assigned_notes.append(note)
        
    return assigned_notes
