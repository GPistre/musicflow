import os
import json
import re
import time
import threading
import concurrent.futures
from typing import Dict, List, Any, Optional, Tuple, Callable
from pathlib import Path
from enum import Enum, auto
from functools import partial
from dataclasses import dataclass

import mido
import pretty_midi

from .llm import LLMGenerator

class TrackStatus(Enum):
    """Status of a track in the generation process"""
    PENDING = auto()     # Task has been created but not yet started
    GENERATING = auto()  # Track is being generated
    COMPLETED = auto()   # Track has been successfully generated
    FAILED = auto()      # Track generation failed
    CANCELED = auto()    # Track generation was canceled

@dataclass
class TrackTask:
    """Information about a track generation or update task"""
    track_name: str
    prompt: str
    status: TrackStatus
    future: Optional[concurrent.futures.Future] = None
    start_time: float = 0.0
    end_time: float = 0.0
    result: Dict[str, Any] = None
    error: Optional[str] = None
    task_id: str = ""
    is_update: bool = False
    callback: Optional[Callable] = None

class MIDIGenerator:
    """Class to handle MIDI generation from LLM outputs"""
    
    def __init__(self, output_dir: str = None):
        self.llm = LLMGenerator()
        self.output_dir = output_dir or os.getenv("OUTPUT_DIR", "./output")
        self.tracks = {}
        self.initialize_system_prompt()
        
        # Ensure output directory exists
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        
        # Initialize thread pool for parallel generation
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        
        # Track management
        self.tasks = {}          # All tasks, keyed by task_id
        self.active_tracks = {}  # Tracks currently being generated, keyed by track_name
        self.lock = threading.RLock()  # Lock for thread-safe operations on shared dictionaries
    
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
        7. Clip length (number of bars, default is 4)
        
        Always respond with a valid JSON object with the following structure:
        {
            "track_type": "[drum|bass|lead|perc|etc.]",
            "bpm": 120,
            "time_signature": "4/4",
            "clip_length": 4,
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
        
        Key Guidelines:
        
        1. For drum tracks, use General MIDI drum note mappings:
           - 35-36: Kick drum
           - 38-40: Snare drum
           - 42-46: Hi-hat (42=closed, 46=open)
           - 49-53: Cymbals
           - 54-59: Toms
        
        2. When provided with context about existing tracks:
           - Match the BPM and time signature of existing tracks
           - Ensure your composition complements the other tracks
           - Consider rhythmic, harmonic, and melodic relationships
           - For bass tracks, follow the harmonic structure implied by other tracks
        
        3. When updating a track:
           - Keep the modifications aligned with the user's request
           - Maintain the original BPM and time signature
           - Preserve the core character while making the requested changes
        
        4. For all tracks:
           - Create musically coherent patterns that loop well
           - Use appropriate note velocities for dynamic expression
           - Include detailed descriptions of what you generated
           - Be creative and musical, following the user's style preferences
           
        5. CRITICAL LENGTH REQUIREMENT - THIS IS THE MOST IMPORTANT RULE:
           - You MUST fill the ENTIRE requested clip length with notes
           - For an 8-bar clip in 4/4 time, you MUST have notes starting at beat 0.0 and notes ending near beat 32.0
           - For any clip, distribute notes evenly throughout ALL bars
           - Each bar must contain multiple notes - don't leave any bars empty
           - The final bar MUST contain notes that end close to the final beat
           - Include long notes, short notes, and varied rhythmic patterns throughout the entire length
           - Verify your note times before responding - the last note's end time should be within 0.5 beats of the clip's end
           - In 4/4 time:
              * 4-bar clip: notes must span from beat 0.0 to approximately beat 16.0
              * 8-bar clip: notes must span from beat 0.0 to approximately beat 32.0 
              * 16-bar clip: notes must span from beat 0.0 to approximately beat 64.0
           
        6. Before returning your JSON, VERIFY:
           - The last note's end time (start + duration) must be within 0.5 beats of the clip length
           - Notes must exist in every section of the clip (beginning, middle, and end)
           - No significant gaps (more than 1 bar) exist between notes
        
        Always analyze the full context before generating your response.
        """
        
        self.llm.add_system_message(system_prompt)
    
    def _generate_track_internal(self, prompt: str, track_name: Optional[str] = None, clip_length: int = 4, task_id: str = None) -> Dict[str, Any]:
        """Internal method to generate MIDI data for a track (runs in thread)"""
        try:
            # Update task status
            if task_id and task_id in self.tasks:
                with self.lock:
                    self.tasks[task_id].status = TrackStatus.GENERATING
                    self.tasks[task_id].start_time = time.time()
            
            # Build context about existing tracks
            context = self._build_track_context()
            
            # Process prompt for clip length specification
            processed_prompt, extracted_length = self._extract_clip_length(prompt)
            if extracted_length:
                clip_length = extracted_length
            
            # Enhanced prompt with context and specific track guidance
            enhanced_prompt = f"Generate MIDI data for the following: {processed_prompt}\n\n"
            enhanced_prompt += f"CRITICAL: Create a clip that is EXACTLY {clip_length} bars long. Generate notes that span the ENTIRE {clip_length} bars.\n\n"
            enhanced_prompt += f"The notes MUST be distributed throughout all {clip_length} bars - from bar 1 to bar {clip_length}.\n"
            enhanced_prompt += f"In 4/4 time, a {clip_length}-bar clip means:\n"
            enhanced_prompt += f"- Start time of first notes: 0.0 beats\n"
            enhanced_prompt += f"- End time of last notes: {clip_length * 4} beats\n"
            enhanced_prompt += f"- Total length: {clip_length * 4} beats\n\n"
            enhanced_prompt += f"REQUIREMENT: Include notes in EVERY bar, with the final notes ending very close to beat {clip_length * 4}.\n"
            enhanced_prompt += f"IMPORTANT: Before submitting your JSON, verify that the last note ends near beat {clip_length * 4}.\n\n"
            
            if context:
                enhanced_prompt += f"Context - Existing tracks in the session:\n{context}\n\n"
                enhanced_prompt += "Make sure the new track complements the existing tracks in terms of rhythm, harmony, and style.\n"
            
            # Get response from LLM
            midi_data = self.llm.generate_response(enhanced_prompt)
            
            if "error" in midi_data:
                # Handle error case
                if task_id and task_id in self.tasks:
                    with self.lock:
                        self.tasks[task_id].status = TrackStatus.FAILED
                        self.tasks[task_id].error = midi_data["error"]
                        self.tasks[task_id].end_time = time.time()
                        
                        # Remove from active tracks
                        if track_name in self.active_tracks:
                            del self.active_tracks[track_name]
                
                return {"error": midi_data["error"]}
            
            # Use provided track name or get from response
            if not track_name and "track_type" in midi_data:
                track_name = midi_data["track_type"]
            
            # Verify clip spans the full requested length
            if "notes" in midi_data and midi_data["notes"]:
                # Find the end time of the last note
                end_times = [(note.get("start", 0) + note.get("duration", 0)) for note in midi_data["notes"]]
                last_end_time = max(end_times) if end_times else 0
                expected_end_time = clip_length * 4  # In 4/4 time
                
                # If the last note doesn't reach at least 90% of the expected length, log a warning
                if last_end_time < expected_end_time * 0.9:
                    print(f"WARNING: Generated clip doesn't fully utilize the requested length.")
                    print(f"Requested: {clip_length} bars ({expected_end_time} beats)")
                    print(f"Actual last note ends at: {last_end_time} beats")
                    # We'll still use the clip, but with a warning
            
            # Store track data
            with self.lock:
                self.tracks[track_name] = midi_data
            
            # Save as MIDI file
            midi_file_path = self.save_as_midi(midi_data, track_name)
            
            result = {
                "track_name": track_name,
                "midi_file": midi_file_path,
                "details": midi_data
            }
            
            # Update task status on success
            if task_id and task_id in self.tasks:
                with self.lock:
                    self.tasks[task_id].status = TrackStatus.COMPLETED
                    self.tasks[task_id].end_time = time.time()
                    self.tasks[task_id].result = result
                    
                    # Remove from active tracks but keep in completed tasks
                    if track_name in self.active_tracks:
                        del self.active_tracks[track_name]
            
            return result
        except Exception as e:
            error_message = f"Error generating track: {str(e)}"
            print(error_message)
            
            # Update task status on error
            if task_id and task_id in self.tasks:
                with self.lock:
                    self.tasks[task_id].status = TrackStatus.FAILED
                    self.tasks[task_id].error = error_message
                    self.tasks[task_id].end_time = time.time()
                    
                    # Remove from active tracks
                    if track_name in self.active_tracks:
                        del self.active_tracks[track_name]
            
            return {"error": error_message}
            
    def _on_task_done(self, task_id: str, future: concurrent.futures.Future) -> None:
        """Callback for when a task is completed"""
        try:
            # Get the result (will raise exception if the task failed)
            result = future.result()
            
            # Task is already updated by _generate_track_internal
            
            # Execute any callback
            with self.lock:
                if task_id in self.tasks and self.tasks[task_id].callback:
                    try:
                        self.tasks[task_id].callback(task_id, result)
                    except Exception as e:
                        print(f"Error in task callback: {e}")
                
        except concurrent.futures.CancelledError:
            # Handle task cancellation
            with self.lock:
                if task_id in self.tasks:
                    self.tasks[task_id].status = TrackStatus.CANCELED
                    self.tasks[task_id].end_time = time.time()
                    
                    # Remove from active tracks
                    track_name = self.tasks[task_id].track_name
                    if track_name in self.active_tracks:
                        del self.active_tracks[track_name]
                        
        except Exception as e:
            # Handle any other exceptions
            error_message = f"Error in task: {str(e)}"
            print(error_message)
            
            with self.lock:
                if task_id in self.tasks:
                    self.tasks[task_id].status = TrackStatus.FAILED
                    self.tasks[task_id].error = error_message
                    self.tasks[task_id].end_time = time.time()
                    
                    # Remove from active tracks
                    track_name = self.tasks[task_id].track_name
                    if track_name in self.active_tracks:
                        del self.active_tracks[track_name]

    def generate_track_async(self, prompt: str, track_name: Optional[str] = None, 
                           clip_length: int = 4, callback: Optional[Callable] = None) -> str:
        """Generate a track asynchronously, returns task_id"""
        # Create a task ID
        task_id = f"generate_{int(time.time())}_{track_name or 'track'}"
        
        # If track name not specified, try to extract it from prompt
        if not track_name:
            # Look for pattern: "generate [track_name]:" or similar
            match = re.search(r'(?:^|\s)([a-zA-Z]+)(?:\s*:)', prompt)
            if match:
                track_name = match.group(1).strip().lower()
        
        # If still no track name, use a placeholder
        if not track_name:
            track_name = f"track_{int(time.time())}"
        
        # Check if track is already being generated
        with self.lock:
            if track_name in self.active_tracks:
                return self.active_tracks[track_name]
            
            # Create the task
            task = TrackTask(
                track_name=track_name,
                prompt=prompt,
                status=TrackStatus.PENDING,
                task_id=task_id,
                is_update=False,
                callback=callback
            )
            
            # Store the task
            self.tasks[task_id] = task
            self.active_tracks[track_name] = task_id
        
        # Submit the task to the thread pool
        future = self.executor.submit(
            self._generate_track_internal, 
            prompt, 
            track_name, 
            clip_length,
            task_id
        )
        
        # Add a callback to handle completion
        future.add_done_callback(partial(self._on_task_done, task_id))
        
        # Update the task with the future
        with self.lock:
            self.tasks[task_id].future = future
        
        return task_id
        
    def generate_track(self, prompt: str, track_name: Optional[str] = None, clip_length: int = 4) -> Dict[str, Any]:
        """Generate MIDI data for a track based on a prompt (synchronous version)"""
        # Call the internal method directly for synchronous operation
        return self._generate_track_internal(prompt, track_name, clip_length)
    
    def _extract_clip_length(self, prompt: str) -> Tuple[str, Optional[int]]:
        """Extract clip length from prompt if specified"""
        # Look for common patterns indicating clip length
        import re
        
        # Pattern: "X bars" or "X-bar" or "length: X bars" or "X measures"
        patterns = [
            r'(\d+)[\s-]bar',
            r'(\d+) bars',
            r'length:?\s*(\d+)',
            r'(\d+) measures',
            r'(\d+) measure',
            r'length of (\d+)'
        ]
        
        # Check each pattern
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                try:
                    # Extract the length as integer
                    length = int(match.group(1))
                    
                    # Validate reasonable length (1-32 bars)
                    if 1 <= length <= 32:
                        # Remove the length specification from the prompt
                        cleaned_prompt = re.sub(pattern, '', prompt, flags=re.IGNORECASE)
                        # Clean up any double spaces
                        cleaned_prompt = re.sub(r'\s+', ' ', cleaned_prompt).strip()
                        return cleaned_prompt, length
                except ValueError:
                    pass  # Not a valid integer
        
        # No valid length found
        return prompt, None
    
    def _build_track_context(self) -> str:
        """Build context information about existing tracks"""
        if not self.tracks:
            return ""
        
        context = []
        
        # Include information about each existing track
        for track_name, track_data in self.tracks.items():
            track_info = [
                f"Track: {track_name}",
                f"Type: {track_data.get('track_type', track_name)}",
                f"BPM: {track_data.get('bpm', 120)}",
                f"Time Signature: {track_data.get('time_signature', '4/4')}",
                f"Description: {track_data.get('description', 'No description')}"
            ]
            
            # Add note information (summarized)
            notes = track_data.get("notes", [])
            if notes:
                # Get pitch range
                pitches = [note.get("pitch", 0) for note in notes]
                min_pitch = min(pitches) if pitches else 0
                max_pitch = max(pitches) if pitches else 0
                
                # Get note count and duration range
                durations = [note.get("duration", 0) for note in notes]
                min_duration = min(durations) if durations else 0
                max_duration = max(durations) if durations else 0
                
                track_info.append(f"Notes: {len(notes)} notes, pitch range {min_pitch}-{max_pitch}, duration range {min_duration:.2f}-{max_duration:.2f} beats")
                
                # For drum tracks, identify common drum elements
                if track_name.lower() == "drums" or track_data.get("track_type", "").lower() == "drums":
                    kick = any(35 <= note.get("pitch", 0) <= 36 for note in notes)
                    snare = any(38 <= note.get("pitch", 0) <= 40 for note in notes)
                    hihat = any(42 <= note.get("pitch", 0) <= 46 for note in notes)
                    cymbals = any(49 <= note.get("pitch", 0) <= 53 for note in notes)
                    
                    elements = []
                    if kick: elements.append("kick")
                    if snare: elements.append("snare")
                    if hihat: elements.append("hi-hat")
                    if cymbals: elements.append("cymbals")
                    
                    if elements:
                        track_info.append(f"Drum elements: {', '.join(elements)}")
            
            context.append("\n".join(track_info))
        
        return "\n\n".join(context)
    
    def _update_track_internal(self, track_name: str, prompt: str, task_id: str = None) -> Dict[str, Any]:
        """Internal method to update an existing track (runs in thread)"""
        try:
            # Update task status
            if task_id and task_id in self.tasks:
                with self.lock:
                    self.tasks[task_id].status = TrackStatus.GENERATING
                    self.tasks[task_id].start_time = time.time()
            
            # Build context about existing tracks
            context = self._build_track_context()
            
            # Process prompt for clip length specification
            processed_prompt, extracted_length = self._extract_clip_length(prompt)
            
            # Get original track data with lock protection
            with self.lock:
                original_track_data = self.tracks.get(track_name, {})
            
            original_bpm = original_track_data.get("bpm", 120)
            original_time_signature = original_track_data.get("time_signature", "4/4")
            original_clip_length = original_track_data.get("clip_length", 4)
            
            # Use extracted length if provided, otherwise keep original
            clip_length = extracted_length if extracted_length else original_clip_length
            
            # Build enhanced prompt with context
            enhanced_prompt = f"Update the {track_name} track with the following: {processed_prompt}.\n\n"
            enhanced_prompt += f"Important: Maintain the same BPM ({original_bpm}) and time signature ({original_time_signature}) as before.\n\n"
            
            # Add detailed clip length instructions
            enhanced_prompt += f"CRITICAL: Create a clip that is EXACTLY {clip_length} bars long. Generate notes that span the ENTIRE {clip_length} bars.\n\n"
            enhanced_prompt += f"The notes MUST be distributed throughout all {clip_length} bars - from bar 1 to bar {clip_length}.\n"
            enhanced_prompt += f"In {original_time_signature} time, a {clip_length}-bar clip means:\n"
            enhanced_prompt += f"- Start time of first notes: 0.0 beats\n"
            
            # Calculate end time based on time signature
            beats_per_bar = int(original_time_signature.split('/')[0])
            expected_end_time = clip_length * beats_per_bar
            enhanced_prompt += f"- End time of last notes: {expected_end_time} beats\n"
            enhanced_prompt += f"- Total length: {expected_end_time} beats\n\n"
            enhanced_prompt += f"REQUIREMENT: Include notes in EVERY bar, with the final notes ending very close to beat {expected_end_time}.\n"
            enhanced_prompt += f"IMPORTANT: Before submitting your JSON, verify that the last note ends near beat {expected_end_time}.\n\n"
            
            # Include detailed information about the track being updated
            if original_track_data:
                enhanced_prompt += f"Original track description: {original_track_data.get('description', 'No description')}\n\n"
            
            # Add context about other tracks to maintain musical coherence
            if context:
                enhanced_prompt += f"Context - Other tracks in the session:\n{context}\n\n"
                enhanced_prompt += "Make sure the updated track still complements the other tracks in terms of rhythm, harmony, and style.\n"
            
            # Get response from LLM
            midi_data = self.llm.generate_response(enhanced_prompt)
            
            if "error" in midi_data:
                # Handle error case
                if task_id and task_id in self.tasks:
                    with self.lock:
                        self.tasks[task_id].status = TrackStatus.FAILED
                        self.tasks[task_id].error = midi_data["error"]
                        self.tasks[task_id].end_time = time.time()
                        
                        # Remove from active tracks
                        if track_name in self.active_tracks:
                            del self.active_tracks[track_name]
                
                return {"error": midi_data["error"]}
            
            # Ensure BPM and time signature are maintained
            midi_data["bpm"] = original_bpm
            midi_data["time_signature"] = original_time_signature
            
            # Verify clip spans the full requested length
            if "notes" in midi_data and midi_data["notes"]:
                # Find the end time of the last note
                end_times = [(note.get("start", 0) + note.get("duration", 0)) for note in midi_data["notes"]]
                last_end_time = max(end_times) if end_times else 0
                
                # Calculate expected end time based on time signature
                beats_per_bar = int(original_time_signature.split('/')[0])
                expected_end_time = clip_length * beats_per_bar
                
                # If the last note doesn't reach at least 90% of the expected length, log a warning
                if last_end_time < expected_end_time * 0.9:
                    print(f"WARNING: Updated clip doesn't fully utilize the requested length.")
                    print(f"Requested: {clip_length} bars ({expected_end_time} beats)")
                    print(f"Actual last note ends at: {last_end_time} beats")
                    # We'll still use the clip, but with a warning
            
            # Update stored track data
            with self.lock:
                self.tracks[track_name] = midi_data
            
            # Save as MIDI file
            midi_file_path = self.save_as_midi(midi_data, track_name)
            
            result = {
                "track_name": track_name,
                "midi_file": midi_file_path,
                "details": midi_data
            }
            
            # Update task status on success
            if task_id and task_id in self.tasks:
                with self.lock:
                    self.tasks[task_id].status = TrackStatus.COMPLETED
                    self.tasks[task_id].end_time = time.time()
                    self.tasks[task_id].result = result
                    
                    # Remove from active tracks but keep in completed tasks
                    if track_name in self.active_tracks:
                        del self.active_tracks[track_name]
            
            return result
            
        except Exception as e:
            error_message = f"Error updating track: {str(e)}"
            print(error_message)
            
            # Update task status on error
            if task_id and task_id in self.tasks:
                with self.lock:
                    self.tasks[task_id].status = TrackStatus.FAILED
                    self.tasks[task_id].error = error_message
                    self.tasks[task_id].end_time = time.time()
                    
                    # Remove from active tracks
                    if track_name in self.active_tracks:
                        del self.active_tracks[track_name]
            
            return {"error": error_message}
    
    def update_track_async(self, track_name: str, prompt: str, callback: Optional[Callable] = None) -> str:
        """Update a track asynchronously, returns task_id"""
        # Create a task ID
        task_id = f"update_{int(time.time())}_{track_name}"
        
        # Check if track exists
        with self.lock:
            if track_name not in self.tracks:
                error = f"Track '{track_name}' does not exist"
                if callback:
                    callback(task_id, {"error": error})
                return error
        
        # Check if track is already being updated
        with self.lock:
            if track_name in self.active_tracks:
                return self.active_tracks[track_name]
            
            # Create the task
            task = TrackTask(
                track_name=track_name,
                prompt=prompt,
                status=TrackStatus.PENDING,
                task_id=task_id,
                is_update=True,
                callback=callback
            )
            
            # Store the task
            self.tasks[task_id] = task
            self.active_tracks[track_name] = task_id
        
        # Submit the task to the thread pool
        future = self.executor.submit(
            self._update_track_internal, 
            track_name, 
            prompt,
            task_id
        )
        
        # Add a callback to handle completion
        future.add_done_callback(partial(self._on_task_done, task_id))
        
        # Update the task with the future
        with self.lock:
            self.tasks[task_id].future = future
        
        return task_id
    
    def update_track(self, track_name: str, prompt: str) -> Dict[str, Any]:
        """Update an existing track with a new prompt (synchronous version)"""
        # Call the internal method directly for synchronous operation
        return self._update_track_internal(track_name, prompt)
    
    def save_as_midi(self, midi_data: Dict[str, Any], track_name: str) -> str:
        """Convert JSON MIDI data to a MIDI file"""
        # Create a PrettyMIDI object
        bpm = midi_data.get("bpm", 120)
        midi = pretty_midi.PrettyMIDI(initial_tempo=bpm)
        
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
        
        # Get time signature and clip length information
        time_sig = midi_data.get("time_signature", "4/4")
        beats_per_bar = int(time_sig.split('/')[0])
        clip_length_bars = midi_data.get("clip_length", 4)
        
        # Calculate clip length in beats
        clip_length_beats = clip_length_bars * beats_per_bar
        
        # Check if we need to adjust the clip to match the requested length
        if instrument.notes:
            # Find the latest end time
            last_end_time = max(note.end for note in instrument.notes)
            
            # Analyze note distribution
            # Divide the clip into sections and check if notes exist in each section
            section_size = beats_per_bar  # One bar per section
            sections_with_notes = set()
            
            for note in instrument.notes:
                # Which section(s) does this note belong to?
                start_section = int(note.start / section_size)
                end_section = int(note.end / section_size)
                
                # Register all sections this note spans
                for section in range(start_section, end_section + 1):
                    sections_with_notes.add(section)
            
            # Calculate how many sections should exist
            total_sections = int(clip_length_beats / section_size)
            
            # Print warnings about note distribution if more than 25% of sections are empty
            if len(sections_with_notes) < total_sections * 0.75:
                empty_sections = set(range(total_sections)) - sections_with_notes
                empty_bars = [sect + 1 for sect in empty_sections]  # Convert to 1-indexed bars
                print(f"WARNING: Generated clip has empty or sparse sections.")
                print(f"Empty or sparse bars: {empty_bars}")
            
            # If clip is too short (less than 95% of target length), extend it
            if last_end_time < clip_length_beats * 0.95:
                print(f"WARNING: Clip is shorter than requested ({last_end_time:.2f} beats vs {clip_length_beats} beats)")
                
                # Add a silent marker note at the end time
                marker = pretty_midi.Note(
                    velocity=1,  # Very low velocity (silent)
                    pitch=0,     # Lowest possible note
                    start=clip_length_beats - 0.001,  # Just before the end
                    end=clip_length_beats             # Exactly at the end
                )
                # Add the marker note to enforce the clip length
                instrument.notes.append(marker)
                
                # Check if we should attempt to fill empty sections
                if len(sections_with_notes) < total_sections * 0.75:
                    print("Attempting to extend patterns to fill the full clip length...")
                    
                    # Try to duplicate notes to fill the gaps
                    if last_end_time < clip_length_beats / 2:
                        # If we're less than half the target length, duplicate the whole pattern
                        original_notes = instrument.notes.copy()
                        
                        # Remove the marker note we just added
                        original_notes.pop()
                        
                        # How many times do we need to repeat the pattern?
                        repeat_times = int(clip_length_beats / last_end_time)
                        
                        for repeat in range(1, repeat_times):
                            for note in original_notes:
                                # Create a copy of the note shifted forward in time
                                shifted_note = pretty_midi.Note(
                                    velocity=note.velocity,
                                    pitch=note.pitch,
                                    start=note.start + (last_end_time * repeat),
                                    end=note.end + (last_end_time * repeat)
                                )
                                
                                # Add the shifted note
                                instrument.notes.append(shifted_note)
                        
                        print(f"Extended pattern by repeating {repeat_times} times")
            
            # If clip is too long, we don't truncate it to avoid cutting off notes
            # Just provide a warning in the file name
            if last_end_time > clip_length_beats * 1.05:  # Allow 5% tolerance
                print(f"WARNING: Clip is longer than requested ({last_end_time:.2f} beats vs {clip_length_beats} beats)")
                track_name = f"{track_name}_long"  # Mark as exceeding requested length
        
        # Create the output file path
        output_file = os.path.join(self.output_dir, f"{track_name}.mid")
        
        # Add clip length to the filename for clarity
        if clip_length_bars != 4:  # Only add if not the default
            output_file = os.path.join(self.output_dir, f"{track_name}_{clip_length_bars}bars.mid")
        
        # Write the MIDI file
        midi.write(output_file)
        
        return output_file
    
    def list_tracks(self) -> List[str]:
        """List all currently generated tracks"""
        with self.lock:
            return list(self.tracks.keys())
    
    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific task"""
        with self.lock:
            if task_id not in self.tasks:
                return None
            
            task = self.tasks[task_id]
            return {
                "track_name": task.track_name,
                "prompt": task.prompt,
                "status": task.status.name,
                "start_time": task.start_time,
                "end_time": task.end_time,
                "error": task.error,
                "is_update": task.is_update,
                "duration": task.end_time - task.start_time if task.end_time > 0 else 0
            }
    
    def list_tasks(self, include_completed: bool = False) -> List[Dict[str, Any]]:
        """List all tasks (active by default, or all if include_completed is True)"""
        with self.lock:
            task_list = []
            for task_id, task in self.tasks.items():
                # Skip completed tasks unless specifically requested
                if not include_completed and task.status in [TrackStatus.COMPLETED, TrackStatus.FAILED, TrackStatus.CANCELED]:
                    if time.time() - task.end_time > 300:  # Keep completed tasks for 5 minutes
                        continue
                
                task_info = {
                    "task_id": task_id,
                    "track_name": task.track_name,
                    "status": task.status.name,
                    "is_update": task.is_update,
                    "start_time": task.start_time,
                    "duration": task.end_time - task.start_time if task.end_time > 0 else time.time() - task.start_time
                }
                
                task_list.append(task_info)
            
            return task_list
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        with self.lock:
            if task_id not in self.tasks:
                return False
            
            task = self.tasks[task_id]
            
            # Only cancel if the task is still running
            if task.status not in [TrackStatus.PENDING, TrackStatus.GENERATING]:
                return False
            
            # Cancel the future if it exists
            if task.future:
                task.future.cancel()
            
            # Update task status
            task.status = TrackStatus.CANCELED
            task.end_time = time.time()
            
            # Remove from active tracks
            if task.track_name in self.active_tracks:
                del self.active_tracks[task.track_name]
            
            return True
    
    def get_active_track_status(self) -> Dict[str, str]:
        """Get a mapping of track names to their current status"""
        with self.lock:
            status_map = {}
            
            # First add all generated tracks as COMPLETED
            for track_name in self.tracks.keys():
                status_map[track_name] = "COMPLETED"
            
            # Then update with active tasks
            for track_name, task_id in self.active_tracks.items():
                if task_id in self.tasks:
                    status_map[track_name] = self.tasks[task_id].status.name
            
            return status_map
    
    def is_track_generating(self, track_name: str) -> bool:
        """Check if a track is currently being generated or updated"""
        with self.lock:
            return track_name in self.active_tracks
    
    def shutdown(self):
        """Shutdown the thread pool and cleanup"""
        # Cancel all running tasks
        with self.lock:
            for task_id, task in self.tasks.items():
                if task.status in [TrackStatus.PENDING, TrackStatus.GENERATING] and task.future:
                    task.future.cancel()
                    task.status = TrackStatus.CANCELED
                    task.end_time = time.time()
            
            self.active_tracks.clear()
        
        # Shutdown thread pool
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None
