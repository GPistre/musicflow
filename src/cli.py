import os
import sys
import time
import threading
from typing import Optional, Dict, Any, List, Tuple

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.status import Status
from rich.live import Live
from rich import box

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style

from .midi_generator import MIDIGenerator, TrackStatus
from .ableton_bridge import AbletonBridge, run_async

class MusicFlowCLI:
    """Command-line interface for MusicFlow MIDI generation"""
    
    def __init__(self):
        self.console = Console()
        self.midi_generator = MIDIGenerator()
        self.ableton = AbletonBridge()
        self.ableton_connected = False
        self.running = True
        
        # Task tracking
        self.task_status_lock = threading.RLock()
        self.task_status_thread = None
        self.show_task_status = False
        self.task_callbacks = {}  # Map of task_id to callback functions
        self.last_status_update = 0
        self.pending_notifications = []  # Messages to show when user returns to prompt
        
        # Set up history file in user's home directory
        history_file = os.path.expanduser("~/.musicflow_history")
        self.prompt_session = PromptSession(
            history=FileHistory(history_file),
            auto_suggest=AutoSuggestFromHistory(),
            enable_history_search=True,
            complete_style="readline"
        )
        
        # Set up command completer
        self.command_completer = WordCompleter([
            'generate', 'update', 'list', 'help', 'exit', 'quit',
            'play', 'stop', 'load', 'ableton status', 'status',
            'tasks', 'cancel'
        ], ignore_case=True)
        
        # Set up prompt style
        self.prompt_style = Style.from_dict({
            'prompt': 'bold green',
        })
        
        # Auto-connect to Ableton on startup
        self.console.print("[bold]Connecting to Ableton Live...[/bold]")
        with self.console.status("Connecting..."):
            success = run_async(self.ableton.connect)
        
        if success:
            self.ableton_connected = True
            self.console.print("[bold green]✓[/bold green] Connected to Ableton Live")
        else:
            self.console.print("[yellow]Could not connect to Ableton Live. Some features will be limited.[/yellow]")
            self.console.print("[yellow]You can still generate MIDI files, but they won't auto-load into Ableton.[/yellow]")
    
    def _on_task_complete(self, task_id: str, result: Dict[str, Any]):
        """Handle task completion"""
        with self.task_status_lock:
            # Store task notification for display when user is back at prompt
            if "error" in result:
                message = f"[bold red]Error in task {task_id}:[/bold red] {result['error']}"
            else:
                track_name = result.get('track_name', 'Unknown')
                message = f"[bold green]✓[/bold green] Completed {track_name} generation"
                
                # Auto-load to Ableton if connected
                if self.ableton_connected:
                    message += " (Auto-loading to Ableton...)"
                    self.load_track_to_ableton(track_name)
            
            self.pending_notifications.append(message)
            
            # If user defined a specific callback, call it
            if task_id in self.task_callbacks:
                try:
                    callback = self.task_callbacks.pop(task_id)
                    callback(task_id, result)
                except Exception as e:
                    print(f"Error in callback: {e}")
    
    def _build_task_status_table(self) -> Table:
        """Build a table showing status of active tasks"""
        tasks = self.midi_generator.list_tasks()
        if not tasks:
            return None
            
        table = Table(box=box.ROUNDED, expand=False, title="Active Tasks", title_style="bold blue")
        table.add_column("Track", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Duration", style="yellow")
        table.add_column("Type", style="magenta")
        
        for task in tasks:
            track_name = task['track_name']
            status = task['status']
            duration = task['duration']
            task_type = "Update" if task['is_update'] else "Generate"
            
            # Format duration
            duration_str = f"{duration:.1f}s" if duration < 60 else f"{int(duration // 60)}m {int(duration % 60)}s"
            
            # Style based on status
            if status == "COMPLETED":
                status_style = "[green]COMPLETED[/green]"
            elif status == "GENERATING":
                status_style = "[blue]GENERATING[/blue]"
            elif status == "PENDING":
                status_style = "[yellow]PENDING[/yellow]"
            elif status == "FAILED":
                status_style = "[red]FAILED[/red]"
            else:
                status_style = status
                
            table.add_row(track_name, status_style, duration_str, task_type)
        
        return table
    
    def welcome(self):
        """Display welcome message"""
        welcome_message = """
        # MusicFlow - Interactive MIDI Generation
        
        Create music with natural language prompts.
        - Generate tracks: `generate bass: funky 4/4 bassline with syncopation`
        - Update tracks: `update drums: add more hi-hats`
        - List tracks: `list`
        - Play in Ableton: `play drums` or `play all`
        - Help: `help`
        - Exit: `exit`
        
        ✨ NEW! Parallel Generation - Start multiple tracks at once! ✨
        - Check status: `status`
        - Cancel task: `cancel task_id`
        
        Tracks are automatically loaded into Ableton Live when created or updated!
        """
        
        self.console.print(Panel(Markdown(welcome_message), title="MusicFlow", border_style="green"))
    
    def help(self):
        """Display help message"""
        help_message = """
        ## Commands
        
        - `generate [track_name]: [prompt]` - Generate a new MIDI track
          Example: `generate bass: funky bassline in G minor`
          
          You can specify clip length in the prompt:
          Example: `generate lead: 8-bar melodic lead in C major`
        
        - `update [track_name]: [prompt]` - Update an existing track
          Example: `update drums: make the kick pattern more interesting`
          
          You can change clip length during update:
          Example: `update bass: extend to 16 bars with more variation`
        
        - `list` - List all currently generated tracks
        
        ## Parallel Generation
        
        MusicFlow now supports parallel track generation! You can:
        - Start multiple track generations and updates at the same time
        - Continue using the app while tracks are being generated
        - Check the status of all running tasks
        
        - `status` or `tasks` - Show status of currently running tasks
        - `cancel [task_id]` - Cancel a running task by its ID
        
        ## Ableton Live Integration
        
        Ableton Live is automatically connected at startup. Tracks are automatically loaded
        into Ableton and played when created or updated.
        
        - `ableton status` - Show Ableton connection status
        - `load [track_name]` - Manually load a track into Ableton Live
        - `load all` - Load all tracks into Ableton Live
        
        - `play [track_name]` - Play a specific track in Ableton
        - `play all` - Play all tracks in Ableton
        - `stop [track_name]` - Stop a specific track
        - `stop all` - Stop all playback
        - `reset all` - Delete all tracks and clips (use with caution)
        
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
        elif user_input.lower() == "status" or user_input.lower() == "tasks":
            self.show_tasks_status()
        elif user_input.lower().startswith("cancel "):
            task_id = user_input[7:].strip()
            self.cancel_task(task_id)
        elif user_input.lower() == "exit" or user_input.lower() == "quit":
            if self.ableton_connected:
                self.console.print("Disconnecting from Ableton Live...")
                run_async(self.ableton.disconnect)
            self.midi_generator.shutdown()
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
            self.console.print("Ableton is automatically connected at startup.")
            self.console.print("If you need to reconnect, please restart the application.")
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
        elif user_input.lower() == "reset all":
            self.reset_all()
        else:
            # Treat as a direct generation prompt without specifying track type
            self.generate_track(user_input)
    
    def generate_track(self, prompt: str, track_name: Optional[str] = None):
        """Generate a new MIDI track"""
        self.console.print(f"[bold green]Generating {track_name or 'track'} from prompt:[/bold green] {prompt}")
        
        # Display existing track context if available
        existing_tracks = self.midi_generator.list_tracks()
        if existing_tracks:
            context_table = Table(title="Existing Tracks (Context for Generation)")
            context_table.add_column("Track", style="cyan")
            context_table.add_column("BPM", style="magenta")
            context_table.add_column("Time Sig", style="magenta")
            context_table.add_column("Bars", style="magenta")
            context_table.add_column("Description", style="green")
            
            for track in existing_tracks:
                # Get track data safely
                track_data = {}
                try:
                    track_data = self.midi_generator.tracks.get(track, {})
                except Exception:
                    pass
                
                context_table.add_row(
                    track,
                    str(track_data.get("bpm", 120)),
                    track_data.get("time_signature", "4/4"),
                    str(track_data.get("clip_length", 4)),
                    track_data.get("description", "No description")[:50] + "..." if len(track_data.get("description", "")) > 50 else track_data.get("description", "No description")
                )
            
            self.console.print(context_table)
            self.console.print("[italic]New track will be generated to complement these existing tracks.[/italic]\n")
        
        # Start task in background
        self.console.print("[bold]Starting generation in background...[/bold]")
        task_id = self.midi_generator.generate_track_async(
            prompt=prompt, 
            track_name=track_name,
            callback=self._on_task_complete
        )
        
        # Tell user their task is running
        self.console.print(f"[bold cyan]Task started:[/bold cyan] {task_id}")
        self.console.print("[italic]You can continue using MusicFlow while generation happens in the background.[/italic]")
        self.console.print("[italic]Type 'status' to check on running tasks.[/italic]")
        
        # Show status
        self.show_tasks_status()
    
    def update_track(self, track_name: str, prompt: str):
        """Update an existing MIDI track"""
        tracks = self.midi_generator.list_tracks()
        
        if track_name not in tracks:
            self.console.print(f"[bold red]Error:[/bold red] Track '{track_name}' does not exist.")
            self.console.print(f"Available tracks: {', '.join(tracks) if tracks else 'None'}")
            return
        
        # Check if track is already being updated
        if self.midi_generator.is_track_generating(track_name):
            self.console.print(f"[bold yellow]Warning:[/bold yellow] Track '{track_name}' is already being generated/updated.")
            self.console.print("You can cancel the current task with 'cancel [task_id]'")
            self.show_tasks_status()
            return
        
        self.console.print(f"[bold green]Updating {track_name} with prompt:[/bold green] {prompt}")
        
        # Display detailed information about the track being updated
        target_track_data = self.midi_generator.tracks[track_name]
        track_panel = Panel(
            f"Track: [bold]{track_name}[/bold]\n"
            f"BPM: {target_track_data.get('bpm', 120)}\n"
            f"Time Signature: {target_track_data.get('time_signature', '4/4')}\n"
            f"Clip Length: {target_track_data.get('clip_length', 4)} bars\n"
            f"Description: {target_track_data.get('description', 'No description')}",
            title="Track to Update",
            border_style="yellow"
        )
        self.console.print(track_panel)
        
        # Display other tracks as context
        other_tracks = [t for t in tracks if t != track_name]
        if other_tracks:
            context_table = Table(title="Other Tracks (Context for Update)")
            context_table.add_column("Track", style="cyan")
            context_table.add_column("BPM", style="magenta")
            context_table.add_column("Time Sig", style="magenta")
            context_table.add_column("Bars", style="magenta")
            context_table.add_column("Description", style="green")
            
            for track in other_tracks:
                track_data = self.midi_generator.tracks[track]
                context_table.add_row(
                    track,
                    str(track_data.get("bpm", 120)),
                    track_data.get("time_signature", "4/4"),
                    str(track_data.get("clip_length", 4)),
                    track_data.get("description", "No description")[:50] + "..." if len(track_data.get("description", "")) > 50 else track_data.get("description", "No description")
                )
            
            self.console.print(context_table)
            self.console.print("[italic]Update will maintain compatibility with these tracks.[/italic]\n")
        
        # Start task in background
        self.console.print("[bold]Starting update in background...[/bold]")
        task_id = self.midi_generator.update_track_async(
            track_name=track_name, 
            prompt=prompt,
            callback=self._on_task_complete
        )
        
        # Tell user their task is running
        self.console.print(f"[bold cyan]Task started:[/bold cyan] {task_id}")
        self.console.print("[italic]You can continue using MusicFlow while update happens in the background.[/italic]")
        self.console.print("[italic]Type 'status' to check on running tasks.[/italic]")
        
        # Show status
        self.show_tasks_status()
    
    def show_tasks_status(self):
        """Show status of running tasks"""
        status_table = self._build_task_status_table()
        if status_table:
            self.console.print(status_table)
        else:
            self.console.print("[yellow]No active tasks[/yellow]")
    
    def cancel_task(self, task_id: str):
        """Cancel a running task"""
        result = self.midi_generator.cancel_task(task_id)
        if result:
            self.console.print(f"[bold green]Cancelled task:[/bold green] {task_id}")
        else:
            self.console.print(f"[bold red]Error:[/bold red] Task '{task_id}' not found or already completed")
            
        # Show updated status
        self.show_tasks_status()
    
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
    
    def reset_all(self):
        """Reset everything - clear all tracks and clips"""
        from rich.prompt import Confirm
        
        # Confirm the action since it's destructive
        confirm = Confirm.ask("⚠️  [bold red]This will delete all tracks and clips. Are you sure?[/bold red]")
        if not confirm:
            self.console.print("[yellow]Reset cancelled.[/yellow]")
            return
        
        # Clear MIDI generator tracks
        self.console.print("[bold]Clearing all generated tracks...[/bold]")
        self.midi_generator.tracks = {}
        
        # Clear Ableton clips if connected
        if self.ableton_connected:
            self.console.print("[bold]Clearing all clips in Ableton Live...[/bold]")
            
            # First stop all playback
            run_async(self.ableton.stop_all)
            
            with self.console.status("Clearing clips..."):
                # For each track in Ableton, try to delete clips
                for track_name, track_index in self.ableton.tracks_map.items():
                    try:
                        # Delete clip in slot 0 (our default slot)
                        self.ableton.client.send_message("/live/clip_slot/delete_clip", [track_index, 0])
                        self.console.print(f"[green]Cleared clip in track {track_name}[/green]")
                    except Exception as e:
                        self.console.print(f"[yellow]Could not clear clip in track {track_name}: {e}[/yellow]")
            
            # Reset track mappings
            self.ableton.tracks_map = {}
        
        self.console.print("[bold green]✓[/bold green] Reset complete. All tracks and clips have been cleared.")
    
    def _get_dynamic_completer(self):
        """Get a completer with current track names"""
        # Start with the basic commands
        commands = [
            'generate', 'update', 'list', 'help', 'exit', 'quit',
            'play', 'stop', 'load', 'ableton status', 'reset all'
        ]
        
        # Add track-specific commands
        track_names = self.midi_generator.list_tracks()
        for track in track_names:
            commands.append(f"play {track}")
            commands.append(f"stop {track}")
            commands.append(f"load {track}")
            commands.append(f"update {track}:")
        
        # Add "all" options
        commands.append("play all")
        commands.append("stop all")
        commands.append("load all")
        
        return WordCompleter(commands, ignore_case=True)
        
    def _check_pending_notifications(self):
        """Check and display any pending notifications"""
        with self.task_status_lock:
            if self.pending_notifications:
                self.console.print("\n")  # Add some space
                for notification in self.pending_notifications:
                    self.console.print(notification)
                self.pending_notifications.clear()
    
    def run(self):
        """Run the CLI interface"""
        self.welcome()
        
        while self.running:
            try:
                # Check for task updates
                self._check_pending_notifications()
                
                # Get dynamic completer with current track names
                dynamic_completer = self._get_dynamic_completer()
                
                # Get user input with advanced editing features
                user_input = self.prompt_session.prompt(
                    [('class:prompt', '\nMusicFlow> ')],
                    completer=dynamic_completer,
                    style=self.prompt_style,
                    complete_while_typing=True
                )
                
                # Parse and execute the command
                if user_input.strip():  # Only process non-empty input
                    self.parse_command(user_input)
            except KeyboardInterrupt:
                # Handle Ctrl+C gracefully
                self.console.print("\n[yellow]Operation cancelled.[/yellow]")
                continue
            except EOFError:
                # Handle Ctrl+D (EOF) to exit
                self.console.print("\n[yellow]Exiting...[/yellow]")
                self.running = False
                break
        
        # Clean up any background tasks
        self.midi_generator.shutdown()
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
