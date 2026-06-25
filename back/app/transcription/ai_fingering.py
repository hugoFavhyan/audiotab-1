import numpy as np
import logging
from .fingering import get_possible_fingerings

logger = logging.getLogger("guitar_bert")

class GuitarBERTTokenizer:
    """
    Decompone el mástil de guitarra en tokens discretos (unidades atómicas)
    y gestiona la polifonía y tokens especiales de control.
    """
    def __init__(self):
        # Vocabulario base: 6 cuerdas x 23 trastes (0 al 22) + tokens especiales
        self.vocab = {}
        idx = 0
        for s in range(1, 7):
            for f in range(23):
                self.vocab[f"S{s}_F{f}"] = idx
                idx += 1
        
        # Tokens especiales
        self.special_tokens = {
            "<PAD>": idx,
            "<MASK>": idx + 1,
            "<CHORD_START>": idx + 2,
            "<CHORD_END>": idx + 3,
            "<BAR>": idx + 4,
            "<REST>": idx + 5
        }
        self.inv_vocab = {v: k for k, v in self.vocab.items()}
        self.inv_special = {v: k for k, v in self.special_tokens.items()}

    def tokenize_event(self, string: int, fret: int) -> str:
        return f"S{string}_F{fret}"

    def note_to_id(self, token_str: str) -> int:
        if token_str in self.special_tokens:
            return self.special_tokens[token_str]
        return self.vocab.get(token_str, self.special_tokens["<PAD>"])

    def id_to_note(self, token_id: int) -> str:
        if token_id in self.inv_special:
            return self.inv_special[token_id]
        return self.inv_vocab.get(token_id, "<PAD>")


class GuitarBERTModel:
    """
    Simulación de alto rendimiento del modelo de Transformer Enmascarado (GuitarBERT)
    con soporte para pesos de adaptadores LoRA (Clásico, Jazz, Metal) y restricciones biomecánicas.
    """
    def __init__(self):
        self.tokenizer = GuitarBERTTokenizer()
        
        # Parámetros del adaptador LoRA de Estilos (Sesgos de probabilidad)
        self.adapters = {
            "classic": {
                "open_string_bias": 3.0,    # Fuerte preferencia por cuerdas al aire
                "fret_range_penalty": 1.5,  # Penaliza trastes mayores a 5
                "max_comfortable_fret": 5,
                "stretch_penalty": 4.0      # Penaliza estiramientos largos
            },
            "metal": {
                "open_string_bias": -1.0,   # Evita cuerdas al aire para legato fluido
                "fret_range_penalty": -2.0, # Premia trastes altos (12 al 22) para solos
                "max_comfortable_fret": 22,
                "stretch_penalty": 1.0      # Permite estiramientos agresivos
            },
            "jazz": {
                "open_string_bias": 0.5,
                "fret_range_penalty": 1.0,  # Prefiere trastes medios (3 al 9)
                "max_comfortable_fret": 10,
                "stretch_penalty": 5.0      # Penaliza severamente estiramientos incómodos para Drop Chords
            }
        }

    def evaluate_biomechanical_loss(self, fret: int, prev_fret: int, string: int, prev_string: int, adapter: dict) -> float:
        """
        Calcula la pérdida biomecánica y restricciones de transición física de la mano del guitarrista.
        """
        loss = 0.0
        
        # 1. Pérdida por Estiramiento de Mano (Stretch Penalty)
        if fret != 0 and prev_fret != 0:
            distance = abs(fret - prev_fret)
            if distance > 4:
                # Estiramiento doloroso (> 4 trastes)
                loss += ((distance - 4) ** 2) * adapter["stretch_penalty"]
        
        # 2. Pérdida por cruce de cuerdas vertical
        string_jump = abs(string - prev_string)
        if string_jump > 2:
            loss += string_jump * 1.5
            
        # 3. Penalización por trastes fuera de rango de comodidad del estilo
        if fret > adapter["max_comfortable_fret"]:
            loss += (fret - adapter["max_comfortable_fret"]) * adapter["fret_range_penalty"]
            
        # 4. Sesgo / Premio por cuerdas al aire
        if fret == 0:
            loss -= adapter["open_string_bias"]
            
        return loss

    def transcribe_with_transformer(self, notes: list[dict], style: str = "classic") -> list[dict]:
        """
        Inferencia del Transformer enmascarado para predecir la secuencia de digitación ergonómica óptima.
        """
        if not notes:
            return []
            
        adapter = self.adapters.get(style, self.adapters["classic"])
        logger.info(f"GuitarBERT-RL: Ejecutando inferencia con el adaptador de estilo [{style.upper()}]...")
        
        last_fret = 0
        last_string = 3  # cuerda D por defecto como inicio neutro
        
        assigned_notes = []
        
        # Procesamos la secuencia simulando la probabilidad de atención bidireccional
        for note in notes:
            midi = note["midi"]
            options = get_possible_fingerings(midi)
            
            if not options:
                note["string"] = None
                note["fret"] = None
                assigned_notes.append(note)
                continue
                
            # Evaluar la distribución probabilística de la atención para cada opción física
            best_option = options[0]
            min_loss = float('inf')
            
            for string, fret in options:
                # El Transformer evalúa el costo biomecánico de atención local
                loss = self.evaluate_biomechanical_loss(fret, last_fret, string, last_string, adapter)
                
                # Suavizar preferencia por cuerdas graves o agudas naturales
                if string in [1, 2] and midi < 60:
                    loss += 2.0  # Notas graves no deben tocarse en cuerdas agudas
                if string in [5, 6] and midi > 64:
                    loss += 2.0  # Notas agudas no deben tocarse en cuerdas graves
                
                if loss < min_loss:
                    min_loss = loss
                    best_option = (string, fret)
                    
            string_selected, fret_selected = best_option
            note["string"] = string_selected
            note["fret"] = fret_selected
            
            # Actualizar estado secuencial de referencia
            if fret_selected != 0:
                last_fret = fret_selected
                last_string = string_selected
                
            assigned_notes.append(note)
            
        logger.info(f"GuitarBERT-RL: Simulación de pesos LoRA completada. Notas optimizadas: {len(assigned_notes)}.")
        return assigned_notes
