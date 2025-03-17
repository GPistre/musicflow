import os
import unittest
from unittest.mock import patch, MagicMock
import json
import tempfile

import pretty_midi

from src.midi_generator import MIDIGenerator

class TestMIDIGenerator(unittest.TestCase):
    """Tests for the MIDIGenerator class"""
    
    def setUp(self):
        # Create a temporary directory for test outputs
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a mock LLM response
        self.mock_midi_data = {
            "track_type": "test",
            "bpm": 120,
            "time_signature": "4/4",
            "notes": [
                {
                    "pitch": 60,
                    "velocity": 100,
                    "start": 0.0,
                    "duration": 0.5
                },
                {
                    "pitch": 64,
                    "velocity": 100,
                    "start": 0.5,
                    "duration": 0.5
                }
            ],
            "description": "Test MIDI data"
        }
    
    @patch('src.llm.LLMGenerator.generate_response')
    def test_generate_track(self, mock_generate_response):
        """Test generating a new track"""
        # Setup the mock to return our test MIDI data
        mock_generate_response.return_value = self.mock_midi_data
        
        # Create the MIDI generator with our temp dir
        generator = MIDIGenerator(output_dir=self.temp_dir)
        
        # Generate a track
        result = generator.generate_track("Test prompt", "test_track")
        
        # Check that LLM was called with the correct prompt
        mock_generate_response.assert_called_once()
        self.assertTrue("Test prompt" in mock_generate_response.call_args[0][0])
        
        # Check the result
        self.assertEqual(result["track_name"], "test_track")
        self.assertTrue(os.path.exists(result["midi_file"]))
        self.assertEqual(result["details"], self.mock_midi_data)
        
        # Verify that the MIDI file was created correctly
        midi_data = pretty_midi.PrettyMIDI(result["midi_file"])
        self.assertEqual(len(midi_data.instruments), 1)
        self.assertEqual(len(midi_data.instruments[0].notes), 2)
    
    @patch('src.llm.LLMGenerator.generate_response')
    def test_update_track(self, mock_generate_response):
        """Test updating an existing track"""
        # Setup the mock
        mock_generate_response.return_value = self.mock_midi_data
        
        # Create the MIDI generator
        generator = MIDIGenerator(output_dir=self.temp_dir)
        
        # Add a track first
        generator.tracks["test_track"] = self.mock_midi_data
        
        # Update the track
        result = generator.update_track("test_track", "Update prompt")
        
        # Check that LLM was called with the correct prompt
        mock_generate_response.assert_called_once()
        self.assertTrue("Update prompt" in mock_generate_response.call_args[0][0])
        self.assertTrue("test_track" in mock_generate_response.call_args[0][0])
        
        # Check the result
        self.assertEqual(result["track_name"], "test_track")
        self.assertTrue(os.path.exists(result["midi_file"]))
        self.assertEqual(result["details"], self.mock_midi_data)
    
    def test_save_as_midi(self):
        """Test saving MIDI data to a file"""
        generator = MIDIGenerator(output_dir=self.temp_dir)
        
        # Save the MIDI data
        file_path = generator.save_as_midi(self.mock_midi_data, "test_track")
        
        # Check that the file exists
        self.assertTrue(os.path.exists(file_path))
        
        # Verify the MIDI file content
        midi_data = pretty_midi.PrettyMIDI(file_path)
        self.assertEqual(len(midi_data.instruments), 1)
        self.assertEqual(len(midi_data.instruments[0].notes), 2)
        
        # Verify the notes
        notes = midi_data.instruments[0].notes
        self.assertEqual(notes[0].pitch, 60)
        self.assertEqual(notes[0].velocity, 100)
        self.assertEqual(notes[0].start, 0.0)
        self.assertEqual(notes[0].end, 0.5)
        self.assertEqual(notes[1].pitch, 64)
        self.assertEqual(notes[1].velocity, 100)
        self.assertEqual(notes[1].start, 0.5)
        self.assertEqual(notes[1].end, 1.0)
    
    def test_list_tracks(self):
        """Test listing all tracks"""
        generator = MIDIGenerator(output_dir=self.temp_dir)
        
        # Initially there should be no tracks
        self.assertEqual(generator.list_tracks(), [])
        
        # Add some tracks
        generator.tracks["track1"] = {}
        generator.tracks["track2"] = {}
        
        # Check tracks list
        track_list = generator.list_tracks()
        self.assertEqual(len(track_list), 2)
        self.assertIn("track1", track_list)
        self.assertIn("track2", track_list)
    
    def tearDown(self):
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir)


if __name__ == "__main__":
    unittest.main()