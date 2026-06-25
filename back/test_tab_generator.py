import os
import json
import unittest
import tempfile
from app.transcription.musicxml_generator import generate_musicxml, post_process_tablature

# JSON data provided in the prompt
TEST_JSON_DATA = {
  "title": "Transcripción Automática",
  "bpm": 120,
  "notes_count": 181,
  "notes": [
    {
      "pitch": "G2",
      "midi": 43,
      "start_time": 1.2770975056689342,
      "duration": 0.06965986394557833,
      "string": 6,
      "fret": 3
    },
    {
      "pitch": "C3",
      "midi": 48,
      "start_time": 1.3467573696145125,
      "duration": 0.30185941043083897,
      "string": 5,
      "fret": 3
    },
    {
      "pitch": "C3",
      "midi": 48,
      "start_time": 2.2755555555555556,
      "duration": 0.06965986394557833,
      "string": 5,
      "fret": 3
    },
    {
      "pitch": "B2",
      "midi": 47,
      "start_time": 2.345215419501134,
      "duration": 0.1160997732426301,
      "string": 5,
      "fret": 2
    },
    {
      "pitch": "B4",
      "midi": 71,
      "start_time": 2.693514739229025,
      "duration": 0.09287981859410399,
      "string": 1,
      "fret": 7
    },
    {
      "pitch": "B4",
      "midi": 71,
      "start_time": 2.972154195011338,
      "duration": 1.6950566893424033,
      "string": 1,
      "fret": 7
    },
    {
      "pitch": "G2",
      "midi": 43,
      "start_time": 7.430385487528345,
      "duration": 0.1160997732426301,
      "string": 6,
      "fret": 3
    }
  ]
}

class TestTablatureGeneration(unittest.TestCase):
    def test_musicxml_generation_from_json(self):
        """
        Valida que se genera correctamente la tablatura en formato MusicXML a partir de
        las notas del archivo JSON, incluyendo la clave TAB y la información de cuerdas y trastes.
        """
        notes = TEST_JSON_DATA["notes"]
        bpm = TEST_JSON_DATA["bpm"]
        title = TEST_JSON_DATA["title"]
        
        # 1. Generar la estructura de music21
        score = generate_musicxml(notes, title=title, bpm=bpm)
        self.assertIsNotNone(score, "La estructura Score generada es nula")
        
        # 2. Exportar a MusicXML (formato string)
        xml_content = ""
        fd, temp_path = tempfile.mkstemp(suffix=".xml")
        try:
            score.write('musicxml', fp=temp_path)
            with open(temp_path, "r", encoding="utf-8") as f:
                xml_content = f.read()
        finally:
            os.close(fd)
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
        self.assertTrue(len(xml_content) > 0, "El contenido de MusicXML generado está vacío")
        
        # 3. Aplicar post-procesamiento de tablatura (convertir a TAB clef)
        processed_xml = post_process_tablature(xml_content)
        
        # 4. Validar contenido esperado de la tablatura
        # Comprobar que contiene la clave TAB y los detalles del diapasón de guitarra de 6 líneas
        self.assertIn("<sign>TAB</sign>", processed_xml, "No se encontró la clave TAB en el MusicXML post-procesado")
        self.assertIn("<staff-lines>6</staff-lines>", processed_xml, "No se especificaron las 6 líneas de pentagrama en la tablatura")
        
        # Comprobar que están los trastes de afinación estándar (E2, A2, D3, G3, B3, E4)
        self.assertIn("<tuning-step>E</tuning-step>\n          <tuning-octave>2</tuning-octave>", processed_xml)
        self.assertIn("<tuning-step>A</tuning-step>\n          <tuning-octave>2</tuning-octave>", processed_xml)
        self.assertIn("<tuning-step>D</tuning-step>\n          <tuning-octave>3</tuning-octave>", processed_xml)
        
        # Comprobar que contiene información técnica de trastes y cuerdas de las notas
        self.assertIn("<fret>3</fret>", processed_xml, "No se encontró el traste 3 en el MusicXML")
        self.assertIn("<string>6</string>", processed_xml, "No se encontró la cuerda 6 en el MusicXML")
        self.assertIn("<fret>7</fret>", processed_xml, "No se encontró el traste 7 en el MusicXML")
        self.assertIn("<string>1</string>", processed_xml, "No se encontró la cuerda 1 en el MusicXML")

if __name__ == "__main__":
    unittest.main()
