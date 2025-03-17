import os
import sys
from typing import Optional, Dict, Any, List

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .midi_generator import MIDIGenerator
from .ableton_bridge import AbletonBridge, run_async

class MusicFlowCLI:
    """Command-line interface for MusicFlow MIDI generation"""
    
    def __init__(self):
        self.console = Console()
        self.midi_generator = MIDIGenerator()
        self.ableton = AbletonBridge()
        self.ableton_connected = False
        self.running = True
    
    def welcome(self):
        """Display welcome message"""
        welcome_message = """
        # MusicFlow - Interactive MIDI Generation
        
        Create music with natural language prompts.
        - Generate tracks: `generate bass: funky 4/4 bassline with syncopation`
        - Update tracks: `update drums: add more hi-hats`
        - List tracks: `list`
        - Play in Ableton: `play drums` or `play all`
        - Connect to Ableton: `ableton connect`
        - Help: `help`
        - Exit: `exit`
        """
        
        self.console.print(Panel(Markdown(welcome_message), title="MusicFlow", border_style="green"))
    
    def help(self):
        """Display help message"""
        help_message = """
        ## Commands
        
        - `generate [track_name]: [prompt]` - Generate a new MIDI track
          Example: `generate bass: funky bassline in G minor`
        
        - `update [track_name]: [prompt]` - Update an existing track
          Example: `update drums: make the kick pattern more interesting`
        
        - `list` - List all currently generated tracks
        
        ## Ableton Live Integration
        
        - `ableton connect` - Connect to Ableton Live
        - `ableton disconnect` - Disconnect from Ableton Live
        - `ableton status` - Show connection status
        
        - `load [track_name]` - Load a track into Ableton Live
        - `load all` - Load all tracks into Ableton Live
        
        - `play [track_name]` - Play a specific track in Ableton
        - `play all` - Play all tracks in Ableton
        - `stop [track_name]` - Stop a specific track
        - `stop all` - Stop all playback
        
        - `help` - Display this help message
        
        - `exit` - Exit the program
        
        ## Track Types
        
        Common track types: drums, bass, lead, pad, keys, perc
        """
        
        self.console.print(Panel(Markdown(help_message), title="Help", border_style="blue"))
    
    def parse_command(self, user_input: str):
        """Parse user input to determine command and arguments"""
        user_input = user_input.strip()
        
        if user_input.lower() == "help":
            self.help()
        elif user_input.lower() == "list":
            self.list_tracks()
        elif user_input.lower() == "exit" or user_input.lower() == "quit":
            if self.ableton_connected:
                self.console.print("Disconnecting from Ableton Live...")
                run_async(self.ableton.disconnect)
            self.running = False
        elif user_input.lower().startswith("generate"):
            parts = user_input[8:].strip().split(":", 1)
            if len(parts) == 2:
                track_name, prompt = parts[0].strip(), parts[1].strip()
                self.generate_track(prompt, track_name)
            else:
                self.console.print("[red]Please provide both track name and prompt.[/red]")
                self.console.print("[yellow]Example: generate bass: funky bassline in G minor[/yellow]")
        elif user_input.lower().startswith("update"):
            parts = user_input[6:].strip().split(":", 1)
            if len(parts) == 2:
                track_name, prompt = parts[0].strip(), parts[1].strip()
                self.update_track(track_name, prompt)
            else:
                self.console.print("[red]Please provide both track name and prompt.[/red]")
                self.console.print("[yellow]Example: update drums: add more hi-hats[/yellow]")
        # Ableton commands
        elif user_input.lower() == "ableton connect":
            self.connect_to_ableton()
        elif user_input.lower() == "ableton disconnect":
            self.disconnect_from_ableton()
        elif user_input.lower() == "ableton status":
            self.ableton_status()
        elif user_input.lower().startswith("load "):
            track_name = user_input[5:].strip()
            if track_name.lower() == "all":
                self.load_all_tracks_to_ableton()
            else:
                self.load_track_to_ableton(track_name)
        elif user_input.lower().startswith("play "):
            track_name = user_input[5:].strip()
            if track_name.lower() == "all":
                self.play_all_tracks()
            else:
                self.play_track(track_name)
        elif user_input.lower().startswith("stop "):
            track_name = user_input[5:].strip()
            if track_name.lower() == "all":
                self.stop_all_tracks()
            else:
                self.stop_track(track_name)
        else:
            # Treat as a direct generation prompt without specifying track type
            self.generate_track(user_input)
    
    def generate_track(self, prompt: str, track_name: Optional[str] = None):
        """Generate a new MIDI track"""
        self.console.print(f"[bold green]Generating {track_name or 'track'} from prompt:[/bold green] {prompt}")
        
        with self.console.status("Generating MIDI..."):
            result = self.midi_generator.generate_track(prompt, track_name)
        
        if "error" in result:
            self.console.print(f"[bold red]Error:[/bold red] {result['error']}")
            return
        
        self.console.print(f"[bold green]✓[/bold green] Created {result['track_name']} track")
        self.console.print(f"[bold]MIDI file:[/bold] {result['midi_file']}")
        self.console.print(f"[bold]Description:[/bold] {result['details'].get('description', 'No description')}")
        
        # If Ableton is connected, automatically load the track
        if self.ableton_connected:
            self.console.print("\nAutomatically loading track into Ableton Live...")
            self.load_track_to_ableton(result['track_name'])
    
    def update_track(self, track_name: str, prompt: str):
        """Update an existing MIDI track"""
        tracks = self.midi_generator.list_tracks()
        
        if track_name not in tracks:
            self.console.print(f"[bold red]Error:[/bold red] Track '{track_name}' does not exist.")
            self.console.print(f"Available tracks: {', '.join(tracks) if tracks else 'None'}")
            return
        
        self.console.print(f"[bold green]Updating {track_name} with prompt:[/bold green] {prompt}")
        
        with self.console.status("Updating MIDI..."):
            result = self.midi_generator.update_track(track_name, prompt)
        
        if "error" in result:
            self.console.print(f"[bold red]Error:[/bold red] {result['error']}")
            return
        
        self.console.print(f"[bold green]✓[/bold green] Updated {result['track_name']} track")
        self.console.print(f"[bold]MIDI file:[/bold] {result['midi_file']}")
        self.console.print(f"[bold]Description:[/bold] {result['details'].get('description', 'No description')}")
        
        # If Ableton is connected, automatically reload the track
        if self.ableton_connected:
            self.console.print("\nAutomatically reloading track in Ableton Live...")
            self.load_track_to_ableton(result['track_name'])
    
    def list_tracks(self):
        """List all currently generated tracks"""
        tracks = self.midi_generator.list_tracks()
        
        if not tracks:
            self.console.print("[yellow]No tracks generated yet.[/yellow]")
            return
        
        table = Table(title="Generated Tracks")
        table.add_column("Track Name", style="cyan")
        table.add_column("MIDI File", style="green")
        table.add_column("Loaded in Ableton", style="magenta")
        
        for track in tracks:
            track_data = self.midi_generator.tracks[track]
            midi_file = os.path.join(self.midi_generator.output_dir, f"{track}.mid")
            
            in_ableton = "No"
            if self.ableton_connected and track in self.ableton.tracks_map:
                in_ableton = "Yes"
            
            table.add_row(track, midi_file, in_ableton)
        
        self.console.print(table)
    
    # Ableton Live integration methods
    
    def connect_to_ableton(self):
        """Connect to Ableton Live"""
        if self.ableton_connected:
            self.console.print("[yellow]Already connected to Ableton Live[/yellow]")
            return
        
        self.console.print("[bold]Connecting to Ableton Live...[/bold]")
        
        with self.console.status("Connecting..."):
            success = run_async(self.ableton.connect)  # Pass the function, not the result
        
        if success:
            self.ableton_connected = True
            self.console.print("[bold green]✓[/bold green] Connected to Ableton Live")
        else:
            self.console.print(
                "[bold red]Error:[/bold red] Could not connect to Ableton Live. "
                "Make sure Ableton is running with an OSC plugin enabled."
            )
    
    def disconnect_from_ableton(self):
        """Disconnect from Ableton Live"""
        if not self.ableton_connected:
            self.console.print("[yellow]Not connected to Ableton Live[/yellow]")
            return
        
        self.console.print("[bold]Disconnecting from Ableton Live...[/bold]")
        
        with self.console.status("Disconnecting..."):
            success = run_async(self.ableton.disconnect)
        
        if success:
            self.ableton_connected = False
            self.console.print("[bold green]✓[/bold green] Disconnected from Ableton Live")
        else:
            self.console.print("[bold red]Error:[/bold red] Could not disconnect cleanly from Ableton Live")
    
    def ableton_status(self):
        """Show Ableton connection status"""
        if self.ableton_connected:
            self.console.print("[bold green]Connected to Ableton Live[/bold green]")
            
            # Refresh tracks
            with self.console.status("Refreshing track data..."):
                tracks = run_async(self.ableton.refresh_tracks)
            
            table = Table(title="Ableton Live Tracks")
            table.add_column("Track Index", style="cyan")
            table.add_column("Track Name", style="green")
            
            for idx, track in enumerate(self.ableton.tracks):
                table.add_row(str(idx), track.get('name', f"Track {idx}"))
            
            self.console.print(table)
        else:
            self.console.print("[yellow]Not connected to Ableton Live[/yellow]")
            self.console.print("Use [bold]ableton connect[/bold] to establish a connection")
    
    def load_track_to_ableton(self, track_name: str):
        """Load a MIDI track into Ableton Live"""
        if not self.ableton_connected:
            self.console.print("[yellow]Not connected to Ableton Live. Use 'ableton connect' first.[/yellow]")
            return
        
        tracks = self.midi_generator.list_tracks()
        
        if track_name not in tracks:
            self.console.print(f"[bold red]Error:[/bold red] Track '{track_name}' does not exist.")
            self.console.print(f"Available tracks: {', '.join(tracks) if tracks else 'None'}")
            return
        
        # Get the MIDI file path
        midi_file = os.path.join(self.midi_generator.output_dir, f"{track_name}.mid")
        
        self.console.print(f"[bold]Loading {track_name} into Ableton Live...[/bold]")
        
        with self.console.status("Loading track..."):
            success = run_async(self.ableton.load_midi_clip, track_name, midi_file)
        
        if success:
            self.console.print(f"[bold green]✓[/bold green] Loaded {track_name} into Ableton Live")
        else:
            self.console.print(f"[bold red]Error:[/bold red] Could not load {track_name} into Ableton Live")
    
    def load_all_tracks_to_ableton(self):
        """Load all MIDI tracks into Ableton Live"""
        if not self.ableton_connected:
            self.console.print("[yellow]Not connected to Ableton Live. Use 'ableton connect' first.[/yellow]")
            return
        
        tracks = self.midi_generator.list_tracks()
        
        if not tracks:
            self.console.print("[yellow]No tracks to load[/yellow]")
            return
        
        self.console.print(f"[bold]Loading {len(tracks)} tracks into Ableton Live...[/bold]")
        
        for track_name in tracks:
            midi_file = os.path.join(self.midi_generator.output_dir, f"{track_name}.mid")
            
            with self.console.status(f"Loading {track_name}..."):
                success = run_async(self.ableton.load_midi_clip, track_name, midi_file)
            
            if success:
                self.console.print(f"[bold green]✓[/bold green] Loaded {track_name}")
            else:
                self.console.print(f"[bold red]✗[/bold red] Failed to load {track_name}")
        
        self.console.print("[bold green]Finished loading tracks into Ableton Live[/bold green]")
    
    def play_track(self, track_name: str):
        """Play a track in Ableton Live"""
        if not self.ableton_connected:
            self.console.print("[yellow]Not connected to Ableton Live. Use 'ableton connect' first.[/yellow]")
            return
        
        if track_name not in self.ableton.tracks_map:
            self.console.print(f"[yellow]Track '{track_name}' not loaded in Ableton. Loading now...[/yellow]")
            self.load_track_to_ableton(track_name)
        
        self.console.print(f"[bold]Playing {track_name}...[/bold]")
        
        with self.console.status("Starting playback..."):
            success = run_async(self.ableton.play_clip, track_name)
        
        if success:
            self.console.print(f"[bold green]✓[/bold green] Playing {track_name}")
        else:
            self.console.print(f"[bold red]Error:[/bold red] Could not play {track_name}")
    
    def play_all_tracks(self):
        """Play all tracks in Ableton Live"""
        if not self.ableton_connected:
            self.console.print("[yellow]Not connected to Ableton Live. Use 'ableton connect' first.[/yellow]")
            return
        
        if not self.ableton.tracks_map:
            self.console.print("[yellow]No tracks loaded in Ableton. Loading all tracks now...[/yellow]")
            self.load_all_tracks_to_ableton()
        
        self.console.print("[bold]Playing all tracks...[/bold]")
        
        with self.console.status("Starting global playback..."):
            success = run_async(self.ableton.play_all)
        
        if success:
            self.console.print("[bold green]✓[/bold green] Playing all tracks")
        else:
            self.console.print("[bold red]Error:[/bold red] Could not start playback")
    
    def stop_track(self, track_name: str):
        """Stop a track in Ableton Live"""
        if not self.ableton_connected:
            self.console.print("[yellow]Not connected to Ableton Live. Use 'ableton connect' first.[/yellow]")
            return
        
        if track_name not in self.ableton.tracks_map:
            self.console.print(f"[yellow]Track '{track_name}' not loaded in Ableton[/yellow]")
            return
        
        self.console.print(f"[bold]Stopping {track_name}...[/bold]")
        
        with self.console.status("Stopping playback..."):
            success = run_async(self.ableton.stop_clip, track_name)
        
        if success:
            self.console.print(f"[bold green]✓[/bold green] Stopped {track_name}")
        else:
            self.console.print(f"[bold red]Error:[/bold red] Could not stop {track_name}")
    
    def stop_all_tracks(self):
        """Stop all tracks in Ableton Live"""
        if not self.ableton_connected:
            self.console.print("[yellow]Not connected to Ableton Live. Use 'ableton connect' first.[/yellow]")
            return
        
        self.console.print("[bold]Stopping all playback...[/bold]")
        
        with self.console.status("Stopping global playback..."):
            success = run_async(self.ableton.stop_all)
        
        if success:
            self.console.print("[bold green]✓[/bold green] Stopped all playback")
        else:
            self.console.print("[bold red]Error:[/bold red] Could not stop playback")
    
    def run(self):
        """Run the CLI interface"""
        self.welcome()
        
        while self.running:
            user_input = Prompt.ask("\n[bold green]MusicFlow>[/bold green]")
            self.parse_command(user_input)
        
        self.console.print("[bold]Thanks for using MusicFlow![/bold]")


def main():
    """Main entry point for the CLI"""
    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set.")
        print("Please set it with: export OPENAI_API_KEY=your_api_key_here")
        sys.exit(1)
    
    cli = MusicFlowCLI()
    try:
        cli.run()
    except KeyboardInterrupt:
        print("\nExiting MusicFlow...")
        if cli.ableton_connected:
            print("Disconnecting from Ableton Live...")
            run_async(cli.ableton.disconnect)
        sys.exit(0)


if __name__ == "__main__":
    main()
