import os
import sys
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from .midi_generator import MIDIGenerator

class MusicFlowCLI:
    """Command-line interface for MusicFlow MIDI generation"""
    
    def __init__(self):
        self.console = Console()
        self.midi_generator = MIDIGenerator()
        self.running = True
    
    def welcome(self):
        """Display welcome message"""
        welcome_message = """
        # MusicFlow - Interactive MIDI Generation
        
        Create music with natural language prompts.
        - Generate tracks: `generate bass: funky 4/4 bassline with syncopation`
        - Update tracks: `update drums: add more hi-hats`
        - List tracks: `list`
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
    
    def list_tracks(self):
        """List all currently generated tracks"""
        tracks = self.midi_generator.list_tracks()
        
        if not tracks:
            self.console.print("[yellow]No tracks generated yet.[/yellow]")
            return
        
        self.console.print("[bold]Generated tracks:[/bold]")
        for track in tracks:
            self.console.print(f"- {track}")
    
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
        sys.exit(0)


if __name__ == "__main__":
    main()
