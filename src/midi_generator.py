import os
import json
from typing import Dict, List, Any, Optional
from pathlib import Path

import mido
import pretty_midi

from .llm import LLMGenerator

class MIDIGenerator:
    """Class to handle MIDI generation from LLM outputs"""
    
    def __init__(self, output_dir: str = None):
        self.llm = LLMGenerator()
        self.output_dir = output_dir or os.getenv("OUTPUT_DIR", "./output")
        self.tracks = {}
        self.initialize_system_prompt()
        
        # Ensure output directory exists
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
    
    def initialize_system_prompt(self):
        """Initialize the system prompt for the LLM"""
        system_prompt = """
        You are MusicFlow, an expert in MIDI composition for electronic music. You will help generate MIDI data for different tracks in a song.
        
        Your task is to generate MIDI note data for various track types (drums, bass, lead, etc.) based on user prompts.
        For each track, you need to provide:
        
        1. Notes (represented as integers from 0-127, where 60 is middle C)
        2. Velocities (0-127, representing how hard a note is played)
        3. Start times (in beats)
        4. Durations (in beats)
        5. BPM (beats per minute)
        6. Time signature (e.g., 4/4, 3/4)
        
        Always respond with a valid JSON object with the following structure:
        {
            "track_type": "[drum|bass|lead|perc|etc.]",
            "bpm": 120,
            "time_signature": "4/4",
            "notes": [
                {
                    "pitch": 60,
                    "velocity": 100,
                    "start": 0.0,
                    "duration": 0.5
                },
                // More notes...
            ],
            "description": "Brief description of what you generated"
        }
        
        For drum tracks, use General MIDI drum note mappings (35=kick, 38=snare, etc.).
        Be creative and musical, following the user's style preferences.        
        """
        
        self.llm.add_system_message(system_prompt)
    
    def generate_track(self, prompt: str, track_name: Optional[str] = None) -> Dict[str, Any]:
        """Generate MIDI data for a track based on a prompt"""
        # Enhanced prompt with specific track guidance if needed
        enhanced_prompt = f"Generate MIDI data for the following: {prompt}"
        
        # Get response from LLM
        midi_data = self.llm.generate_response(enhanced_prompt)
        
        if "error" in midi_data:
            return {"error": midi_data["error"]}
        
        # Use provided track name or get from response
        if not track_name and "track_type" in midi_data:
            track_name = midi_data["track_type"]
        
        # Store track data
        self.tracks[track_name] = midi_data
        
        # Save as MIDI file
        midi_file_path = self.save_as_midi(midi_data, track_name)
        
        return {
            "track_name": track_name,
            "midi_file": midi_file_path,
            "details": midi_data
        }
    
    def update_track(self, track_name: str, prompt: str) -> Dict[str, Any]:
        """Update an existing track with a new prompt"""
        enhanced_prompt = f"Update the {track_name} track with the following: {prompt}. Maintain the same BPM and time signature as before."
        
        # Get response from LLM
        midi_data = self.llm.generate_response(enhanced_prompt)
        
        if "error" in midi_data:
            return {"error": midi_data["error"]}
        
        # Update stored track data
        self.tracks[track_name] = midi_data
        
        # Save as MIDI file
        midi_file_path = self.save_as_midi(midi_data, track_name)
        
        return {
            "track_name": track_name,
            "midi_file": midi_file_path,
            "details": midi_data
        }
    
    def save_as_midi(self, midi_data: Dict[str, Any], track_name: str) -> str:
        """Convert JSON MIDI data to a MIDI file"""
        # Create a PrettyMIDI object
        midi = pretty_midi.PrettyMIDI(initial_tempo=midi_data.get("bpm", 120))
        
        # Create an Instrument instance
        if track_name.lower() == "drums":
            instrument = pretty_midi.Instrument(program=0, is_drum=True, name="Drums")
        else:
            # Map track types to appropriate GM instruments
            program_map = {
                "bass": 33,  # Electric Bass
                "lead": 80,  # Lead Synth
                "pad": 88,   # Pad
                "keys": 0,    # Piano
                "perc": 112,  # Percussion
            }
            program = program_map.get(track_name.lower(), 0)
            instrument = pretty_midi.Instrument(program=program, name=track_name)
        
        # Add notes to the instrument
        for note_data in midi_data.get("notes", []):
            note = pretty_midi.Note(
                velocity=note_data.get("velocity", 100),
                pitch=note_data.get("pitch", 60),
                start=note_data.get("start", 0.0),
                end=note_data.get("start", 0.0) + note_data.get("duration", 0.5)
            )
            instrument.notes.append(note)
        
        # Add the instrument to the PrettyMIDI object
        midi.instruments.append(instrument)
        
        # Create the output file path
        output_file = os.path.join(self.output_dir, f"{track_name}.mid")
        
        # Write the MIDI file
        midi.write(output_file)
        
        return output_file
    
    def list_tracks(self) -> List[str]:
        """List all currently generated tracks"""
        return list(self.tracks.keys())
