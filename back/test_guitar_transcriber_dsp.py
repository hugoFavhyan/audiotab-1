import unittest
from guitar_transcriber_dsp import solve_ergonomic_tab, generate_ascii_tab

class TestGuitarTranscriberDSP(unittest.TestCase):
    def test_c_major_scale_fingering(self):
        """
        Valida que la escala de Do Mayor se transcriba con la digitación estándar de guitarra
        más cómoda/ergonómica (primera posición).
        """
        # C Major scale notes starting from C3 (MIDI 48)
        c_major_notes = [
            {"pitch": "C3", "midi": 48, "start_time": 0.0, "duration": 0.5},
            {"pitch": "D3", "midi": 50, "start_time": 0.5, "duration": 0.5},
            {"pitch": "E3", "midi": 52, "start_time": 1.0, "duration": 0.5},
            {"pitch": "F3", "midi": 53, "start_time": 1.5, "duration": 0.5},
            {"pitch": "G3", "midi": 55, "start_time": 2.0, "duration": 0.5},
            {"pitch": "A3", "midi": 57, "start_time": 2.5, "duration": 0.5},
            {"pitch": "B3", "midi": 59, "start_time": 3.0, "duration": 0.5},
            {"pitch": "C4", "midi": 60, "start_time": 3.5, "duration": 0.5},
        ]
        
        assigned = solve_ergonomic_tab(c_major_notes)
        
        # Validar asignaciones ergonómicas individuales
        self.assertEqual(assigned[0]["string"], 5)
        self.assertEqual(assigned[0]["fret"], 3)  # C3 en Cuerda 5 Traste 3
        
        self.assertEqual(assigned[1]["string"], 4)
        self.assertEqual(assigned[1]["fret"], 0)  # D3 en Cuerda 4 al aire
        
        self.assertEqual(assigned[2]["string"], 4)
        self.assertEqual(assigned[2]["fret"], 2)  # E3 en Cuerda 4 Traste 2
        
        self.assertEqual(assigned[7]["string"], 2)
        self.assertEqual(assigned[7]["fret"], 1)  # C4 en Cuerda 2 Traste 1
        
    def test_ascii_tab_generation(self):
        """
        Valida que se genere la tablatura en formato ASCII correctamente espaciada.
        """
        notes = [
            {"pitch": "C3", "midi": 48, "start_time": 0.0, "duration": 0.5, "string": 5, "fret": 3},
            {"pitch": "E3", "midi": 52, "start_time": 0.5, "duration": 0.5, "string": 4, "fret": 2},
        ]
        tab = generate_ascii_tab(notes)
        
        # Verificar que el dibujo de la tablatura contiene las cuerdas correspondientes
        self.assertTrue(tab.startswith("E|"))
        self.assertIn("A|-3----", tab)
        self.assertIn("D|----2-", tab)

if __name__ == "__main__":
    unittest.main()
