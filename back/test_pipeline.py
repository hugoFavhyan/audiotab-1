import os
import numpy as np
import scipy.io.wavfile as wavfile
from app.transcription.pipeline import run_transcription_pipeline
from app.transcription.fingering import get_possible_fingerings, optimize_fingering
from app.transcription.musicxml_generator import generate_musicxml

def generate_synthetic_guitar_scale(filename="scale_test.wav", sr=22050):
    """
    Genera un archivo WAV sintético con tres notas individuales de guitarra (Mi3, Sol3, Si3)
    para simular una transcripción monofónica limpia.
    """
    # Frecuencias: E3 (~164.81 Hz), G3 (~196.00 Hz), B3 (~246.94 Hz)
    frequencies = [164.81, 196.00, 246.94]
    duration_per_note = 1.0  # segundos por nota
    t = np.linspace(0, duration_per_note, int(sr * duration_per_note), endpoint=False)
    
    audio_signal = []
    for freq in frequencies:
        # Onda senoidal simple para simular la nota
        note_wave = np.sin(2 * np.pi * freq * t)
        # Aplicar un desvanecimiento (fade-out) para simular la vibración de una cuerda
        decay = np.exp(-3 * t)
        note_wave = note_wave * decay
        audio_signal.append(note_wave)
        
    # Concatenar notas y normalizar
    full_signal = np.concatenate(audio_signal)
    full_signal /= np.max(np.abs(full_signal))
    
    # Guardar como WAV de 16-bit PCM
    scaled = np.int16(full_signal * 32767)
    wavfile.write(filename, sr, scaled)
    print(f"Archivo de audio sintético generado: '{filename}'")
    return filename


def test_individual_modules():
    print("\n--- TEST DE MÓDULOS INDIVIDUALES ---")
    # Test de asignación de cuerdas y trastes
    # Notas: E3 (MIDI 52), G3 (MIDI 55), B3 (MIDI 59)
    test_notes = [
        {"pitch": "E3", "midi": 52, "start_time": 0.0, "duration": 1.0},
        {"pitch": "G3", "midi": 55, "start_time": 1.0, "duration": 1.0},
        {"pitch": "B3", "midi": 59, "start_time": 2.0, "duration": 1.0},
    ]
    
    print("\n1. Posibles digitaciones para las notas:")
    for note_data in test_notes:
        options = get_possible_fingerings(note_data["midi"])
        print(f"Nota: {note_data['pitch']} (MIDI {note_data['midi']}) -> Opciones (cuerda, traste): {options}")
        
    print("\n2. Optimizando digitación (algoritmo heurístico):")
    optimized_notes = optimize_fingering(test_notes)
    for note_data in optimized_notes:
        print(f"Nota: {note_data['pitch']} -> Cuerda {note_data['string']}, Traste {note_data['fret']}")
        
    print("\n3. Generando estructura MusicXML con music21:")
    try:
        score = generate_musicxml(optimized_notes, title="Test de Escala de Guitarra", bpm=120)
        print("¡Estructura de music21 generada con éxito!")
    except Exception as e:
        print(f"Error al generar estructura de music21: {e}")


def test_full_pipeline():
    print("\n--- TEST DEL PIPELINE COMPLETO ---")
    wav_path = "scale_test.wav"
    generate_synthetic_guitar_scale(wav_path)
    
    try:
        print("\nEjecutando pipeline...")
        notes, xml_content = run_transcription_pipeline(
            file_path=wav_path,
            mode="monophonic",  # Forzar monofónico para usar el WAV sintético con librosa.pyin
            bpm=120.0,
            title="Escala Sintética de Guitarra"
        )
        
        print("\nNotas detectadas y asignadas:")
        for note_data in notes:
            print(
                f"- Nota: {note_data['pitch']} "
                f"| Inicio: {note_data['start_time']:.2f}s "
                f"| Duración: {note_data['duration']:.2f}s "
                f"| Cuerda: {note_data.get('string')} "
                f"| Traste: {note_data.get('fret')}"
            )
            
        print(f"\nLongitud del XML generado: {len(xml_content)} caracteres.")
        if len(xml_content) > 0:
            print("¡Pipeline ejecutado correctamente de inicio a fin!")
            
    except Exception as e:
        print(f"Ocurrió un error al ejecutar el pipeline completo: {e}")
        print("Nota: Es probable que falte instalar dependencias como librosa o music21 en este entorno de Python.")
    finally:
        # Limpiar archivo temporal sintético
        if os.path.exists(wav_path):
            os.remove(wav_path)
            print(f"Archivo temporal '{wav_path}' eliminado.")


if __name__ == "__main__":
    test_individual_modules()
    test_full_pipeline()
