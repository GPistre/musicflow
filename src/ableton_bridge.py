import os
import time
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import json

from pythonosc import udp_client
from pythonosc.dispatcher import Dispatcher
from pythonosc import osc_server

class AbletonBridge:
    """Bridge to control Ableton Live and load MIDI files into it"""
    
    def __init__(self, host="127.0.0.1", send_port=11000, receive_port=11001):
        self.host = host
        self.send_port = send_port  # Port to send messages to Ableton
        self.receive_port = receive_port  # Port to receive messages from Ableton
        
        self.client = None
        self.server = None
        self.server_thread = None
        self.connected = False
        
        self.tracks = []
        self.tracks_map = {}  # Maps our track names to Ableton track indices
        self.response_data = {}  # Stores responses from Ableton
        self.waiting_for_response = False
    
    def connect(self) -> bool:
        """Connect to Ableton Live"""
        try:
            # Create OSC client to send messages to Ableton
            self.client = udp_client.SimpleUDPClient(self.host, self.send_port)
            
            # Create OSC server to receive messages from Ableton
            dispatcher = Dispatcher()
            dispatcher.map("/*", self._handle_response)  # Handle all OSC messages
            
            try:
                self.server = osc_server.ThreadingOSCUDPServer(
                    (self.host, self.receive_port), dispatcher
                )
                
                # Start server in a separate thread
                self.server_thread = threading.Thread(target=self.server.serve_forever)
                self.server_thread.daemon = True
                self.server_thread.start()
            except Exception as server_error:
                print(f"Warning: Could not start OSC server: {server_error}")
                print("You will not receive responses from Ableton Live.")
                print("This is OK for basic functionality.")
                self.server = None
            
            # Set connection status to true
            self.connected = True
            
            # Print information about AbletonOSC
            print("\n==== Ableton Live OSC Connection ====")
            print("Connected to AbletonOSC on port", self.send_port)
            print("Your AbletonOSC version may not support all commands.")
            print("MIDI files will still be generated correctly.")
            print("You'll need to manually load the MIDI files into Ableton tracks.")
            print("Generated MIDI files will be in the output directory.")
            print("====================================\n")
            
            return True
            
        except Exception as e:
            print(f"Error connecting to Ableton Live: {e}")
            print("Make sure Ableton is running with an OSC plugin enabled.")
            print("Configure the OSC plugin to listen on port", self.send_port)
            self.connected = False
            return False
    
    def _handle_response(self, address, *args):
        """Handle OSC response from Ableton"""
        # Extract the command from the address
        parts = address.split('/')
        command = parts[-1] if len(parts) > 2 else None
        
        # Store the response data
        self.response_data[command] = args
        self.waiting_for_response = False
    
    def _send_and_wait(self, address, *args, timeout=1.0) -> Tuple[bool, Any]:
        """Send OSC message and wait for response"""
        if not self.connected:
            return False, None
        
        try:
            # Clear previous response
            self.response_data = {}
            self.waiting_for_response = True
            
            # Send OSC message
            self.client.send_message(address, args)
            
            # Wait for response
            start_time = time.time()
            while self.waiting_for_response and (time.time() - start_time) < timeout:
                time.sleep(0.01)
            
            # Extract command name from address
            parts = address.split('/')
            command = parts[-1] if len(parts) > 2 else None
            
            # Check if we got a response
            if command in self.response_data:
                return True, self.response_data[command]
            
            # If no response within timeout, we'll still return True for some commands
            # since not all OSC plugins respond to all commands
            if address in ["/live/create_track", "/live/set_track_name"]:
                return True, None
                
            return False, None
        except Exception as e:
            print(f"OSC command error on {address}: {e}")
            return False, None
    
    def refresh_tracks(self) -> List[Dict]:
        """Refresh the list of available tracks in Live"""
        if not self.connected:
            print("Not connected to Ableton Live. Connect first.")
            return []
        
        try:
            # Request track list
            success, track_data = self._send_and_wait("/live/tracks")
            
            if success and track_data:
                # Parse track data
                self.tracks = []
                for i, track_name in enumerate(track_data):
                    if track_name:
                        self.tracks.append({
                            "index": i,
                            "name": str(track_name)
                        })
            
            # If we didn't get valid track data from the OSC response,
            # use our existing track_map as a fallback
            if not self.tracks and self.tracks_map:
                print("Using virtual track mapping since Live didn't return track data")
                self.tracks = [
                    {"index": idx, "name": name}
                    for name, idx in self.tracks_map.items()
                ]
            
            return self.tracks
            
        except Exception as e:
            print(f"Error refreshing tracks: {e}")
            # Return existing tracks as fallback
            return self.tracks
    
    def create_track(self, name: str, track_type: str = "midi") -> int:
        """Create a virtual track mapping (AbletonOSC doesn't support track creation)"""
        if not self.connected:
            print("Not connected to Ableton Live. Connect first.")
            return 0
        
        # Create a virtual track mapping
        new_index = len(self.tracks_map)
        self.tracks_map[name] = new_index
        
        # Let the user know what's happening
        print(f"\nVirtual track: '{name}' (index {new_index})")
        print(f"Please manually create a MIDI track named '{name}' in Ableton Live")
        
        return new_index
    
    def load_midi_clip(self, track_name: str, midi_file: str, clip_name: Optional[str] = None) -> bool:
        """Load a MIDI file into a clip on the specified track"""
        if not self.connected:
            print("Not connected to Ableton Live. Connect first.")
            return False
        
        # Ensure the MIDI file exists
        midi_path = Path(midi_file)
        if not midi_path.exists():
            print(f"MIDI file not found: {midi_file}")
            return False
        
        # Get track index - create track if it doesn't exist
        track_index = self.tracks_map.get(track_name)
        if track_index is None:
            track_index = self.create_track(track_name)
        
        # Use the track name as clip name if none provided
        if not clip_name:
            clip_name = track_name
        
        # Get the absolute path to the MIDI file
        midi_file_absolute = str(midi_path.absolute())
        
        # Try to use the direct clip creation and note addition OSC commands
        try:
            print(f"Attempting to load MIDI file into Ableton Live...")
            
            # First, try to delete any existing clip in the slot
            slot_index = 0  # Use the first clip slot
            
            # Try to extract clip length from filename
            clip_length = 4.0  # Default length in bars
            import re
            # Look for patterns like "_4bars.mid" or "_8_bars.mid"
            bar_match = re.search(r'_(\d+)bars', os.path.basename(midi_file))
            if bar_match:
                clip_length = float(bar_match.group(1))
            
            # Delete any existing clip first
            try:
                print(f"Deleting any existing clip in track {track_name} (index {track_index})")
                self.client.send_message("/live/clip_slot/delete_clip", [track_index, slot_index])
                time.sleep(0.3)  # Give Ableton time to process
            except Exception as delete_error:
                print(f"Note: Error deleting clip (this is normal if no clip exists): {delete_error}")
            
            # Try to create a new clip in the slot
            print(f"Creating a new clip in track {track_name} (index {track_index})")
            try:
                self.client.send_message("/live/clip_slot/create_clip", [track_index, slot_index, clip_length])
                time.sleep(0.5)  # Give Ableton time to process
            except Exception as create_error:
                # If we can't create a clip, maybe one already exists - try to clear it
                print(f"Could not create new clip, attempting to clear existing clip: {create_error}")
                try:
                    self.client.send_message("/live/clip/clear", [track_index, slot_index])
                    time.sleep(0.3)
                except Exception:
                    pass  # Ignore errors from clearing
            
            # Now try to load the MIDI file directly
            import pretty_midi
            try:
                # Read the MIDI file
                midi_data = pretty_midi.PrettyMIDI(midi_file)
                
                # For each note in the MIDI file, add it to the clip
                for instrument in midi_data.instruments:
                    for note in instrument.notes:
                        # Convert note data to the format expected by Ableton
                        pitch = int(note.pitch)
                        velocity = int(note.velocity)
                        start_time = float(note.start)
                        duration = float(note.end - note.start)
                        
                        # Try to add the note to the clip
                        # Add a mute parameter (0 = not muted) since AbletonOSC expects 5 values
                        mute = 0  # Not muted
                        print(f"Adding note: pitch={pitch}, velocity={velocity}, start={start_time}, duration={duration}, mute={mute}")
                        self.client.send_message("/live/clip/add/notes", 
                                                [track_index, slot_index, pitch, start_time, duration, velocity, mute])
                        # Don't wait between notes to speed up the process
                
                print(f"Successfully loaded notes into clip!")
                
                # Calculate clip length from the MIDI file
                time_sig_numerator = 4  # Default to 4/4
                clip_length_bars = 4    # Default to 4 bars
                
                # Try to extract time signature and clip length from filename
                import re
                # Look for patterns like "_4bars.mid" or "_8_bars.mid"
                bar_match = re.search(r'_(\d+)bars', os.path.basename(midi_file))
                if bar_match:
                    clip_length_bars = int(bar_match.group(1))
                
                # Calculate loop end in beats - make sure to send exact values
                loop_end_beats = float(clip_length_bars * time_sig_numerator)
                
                # Set the loop start and end points
                print(f"Setting loop end to {loop_end_beats} beats ({clip_length_bars} bars)")
                try:
                    # Set loop start to 0
                    self.client.send_message("/live/clip/set/loop_start", [track_index, slot_index, 0.0])
                    time.sleep(0.2)  # Give a bit more time for processing
                    
                    # Set loop end to match the clip length
                    self.client.send_message("/live/clip/set/loop_end", [track_index, slot_index, loop_end_beats])
                    time.sleep(0.2)  # Give a bit more time for processing
                    
                    # Enable looping
                    self.client.send_message("/live/clip/set/looping", [track_index, slot_index, 1])
                    time.sleep(0.1)
                    
                    # Set clip length explicitly 
                    try:
                        # Some AbletonOSC versions support setting clip length directly
                        self.client.send_message("/live/clip/set/length", [track_index, slot_index, loop_end_beats])
                    except Exception:
                        # Ignore if this command is not supported
                        pass
                    
                    print("Loop settings applied successfully")
                except Exception as loop_error:
                    print(f"Could not set loop points: {loop_error}")
                    print("You may need to manually set the loop points in Ableton Live")
                
                # Automatically play the clip with the correct command
                try:
                    print(f"Starting playback of clip...")
                    # Use the fire method to play the clip
                    self.client.send_message("/live/clip/fire", [track_index, slot_index])
                    time.sleep(0.1)  # Brief pause
                    
                    # Also try to start global playback
                    self.client.send_message("/live/song/start_playing", [1])
                except Exception as play_error:
                    print(f"Note: Could not auto-play clip: {play_error}")
                
                return True
                
            except Exception as midi_error:
                print(f"Error processing MIDI file: {midi_error}")
                # Fall back to manual loading
        
        except Exception as e:
            print(f"Error creating clip: {e}")
            print("Falling back to manual loading.")
        
        # Print instructions for manual loading if automatic methods fail
        print("\n==== MIDI File Generated ====")
        print(f"MIDI File: {midi_file_absolute}")
        print(f"Virtual Track: '{track_name}'")
        print("\nManual Steps:")
        print(f"1. Create a MIDI track named '{track_name}' in Ableton Live")
        print(f"2. Drag and drop the MIDI file into a clip slot on that track")
        print("============================\n")
        
        return True
    
    def play_clip(self, track_name: str, slot: int = 0) -> bool:
        """Play a specific clip in a track"""
        if not self.connected:
            print("Not connected to Ableton Live. Connect first.")
            return False
        
        track_index = self.tracks_map.get(track_name)
        if track_index is None:
            print(f"Track '{track_name}' not found")
            return False
        
        try:
            # Try to play the clip via OSC using the fire method
            self.client.send_message("/live/clip/fire", [track_index, slot])
            print(f"Fired clip in track {track_name} (index {track_index})")
            
            # Also try to start global playback
            self.client.send_message("/live/song/start_playing", [1])
            return True
        except Exception as e:
            print(f"Error playing clip: {e}")
            return False
    
    def stop_clip(self, track_name: str, slot: int = 0) -> bool:
        """Stop a specific clip in a track"""
        if not self.connected:
            print("Not connected to Ableton Live. Connect first.")
            return False
        
        track_index = self.tracks_map.get(track_name)
        if track_index is None:
            print(f"Track '{track_name}' not found")
            return False
        
        try:
            # Try to stop the clip via OSC
            self.client.send_message("/live/song/stop_playing_clip", [track_index, slot])
            print(f"Sent stop command for track {track_name} (index {track_index})")
            return True
        except Exception as e:
            print(f"Error stopping clip: {e}")
            return False
    
    def set_track_volume(self, track_name: str, volume: float) -> bool:
        """Set the volume of a track (0.0 to 1.0)"""
        if not self.connected:
            print("Not connected to Ableton Live. Connect first.")
            return False
        
        track_index = self.tracks_map.get(track_name)
        if track_index is None:
            print(f"Track '{track_name}' not found")
            return False
        
        try:
            # Try to set track volume
            self.client.send_message("/live/set_track_volume", [track_index, volume])
            print(f"Sent volume command for track {track_name} (index {track_index})")
            return True
        except Exception as e:
            print(f"Error setting track volume: {e}")
            return False
    
    def play_all(self) -> bool:
        """Play all loaded clips"""
        if not self.connected:
            print("Not connected to Ableton Live. Connect first.")
            return False
        
        try:
            # Attempt to start global playback
            self.client.send_message("/live/song/start_playing", [1])
            print("Sent play command to Ableton Live")
            print("Note: You may need to start playback manually in Ableton")
            return True
        except Exception as e:
            print(f"Error starting playback: {e}")
            return False
    
    def stop_all(self) -> bool:
        """Stop all playback"""
        if not self.connected:
            print("Not connected to Ableton Live. Connect first.")
            return False
        
        try:
            # Attempt to stop global playback
            self.client.send_message("/live/song/stop_playing", [1])
            print("Sent stop command to Ableton Live")
            return True
        except Exception as e:
            print(f"Error stopping playback: {e}")
            return False
    
    def disconnect(self) -> bool:
        """Disconnect from Ableton Live"""
        if self.connected:
            try:
                # Stop the server
                if self.server:
                    self.server.shutdown()
                    self.server_thread.join(timeout=1.0)
                    self.server = None
                    self.server_thread = None
                
                self.client = None
                self.connected = False
                return True
            except Exception as e:
                print(f"Error disconnecting from Ableton Live: {e}")
                return False
        return True  # Already disconnected


# Helper to run synchronous code
def run_async(func, *args, **kwargs):
    """Run a function with arguments"""
    return func(*args, **kwargs)