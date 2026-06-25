import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.transcription.pipeline import run_transcription_pipeline
from app.transcription.fingering import optimize_fingering
from app.transcription.musicxml_generator import generate_musicxml, post_process_tablature

test_notes = [
    {"pitch": "E3", "midi": 52, "start_time": 0.0, "duration": 1.0},
    {"pitch": "G3", "midi": 55, "start_time": 1.0, "duration": 1.0},
    {"pitch": "B3", "midi": 59, "start_time": 2.0, "duration": 1.0},
]
notes_optimized = optimize_fingering(test_notes)
score = generate_musicxml(notes_optimized, title="Test", bpm=120)
import tempfile
fd, temp_path = tempfile.mkstemp(suffix=".xml")
try:
    score.write('musicxml', fp=temp_path)
    with open(temp_path, "r", encoding="utf-8") as f:
        xml_content = f.read()
    xml_content = post_process_tablature(xml_content)
    print("--- FIRST PART OF XML CONTENT ---")
    print(xml_content[:3000])
finally:
    os.close(fd)
    if os.path.exists(temp_path):
        os.remove(temp_path)
