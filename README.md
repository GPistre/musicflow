# MusicFlow

An interactive MIDI generation tool that uses natural language prompts to create music with direct Ableton Live integration.

## Overview

MusicFlow allows you to generate MIDI tracks for different parts of a song (drums, bass, lead, etc.) using natural language descriptions. For example, you can ask for "a funky 4/4 bassline with syncopation" or "a minimal techno kick pattern with occasional snares".

Each track is generated separately and can be updated with new prompts, enabling an interactive music production experience. Generated tracks can be automatically loaded into Ableton Live for immediate playback and further production.

## Features

- Generate MIDI tracks using natural language descriptions
- Create different track types (drums, bass, lead, etc.)
- Update existing tracks with new prompts
- Conversational interface for intuitive interaction
- Exports standard MIDI files that can be imported into any DAW
- **Direct Ableton Live integration** for immediate playback and production

## Requirements

- Python 3.9+
- Conda (for environment management)
- Ableton Live 11 Suite (for Ableton Live integration)

## Installation

1. Clone this repository:
   ```
   git clone <repository-url>
   cd musicflow
   ```

2. Create and activate the conda environment:
   ```
   conda env create -f environment.yml
   conda activate musicflow
   ```

3. Copy the example `.env` file and add your OpenAI API key:
   ```
   cp .env.example .env
   ```
   Then edit the `.env` file to add your OpenAI API key.

4. For Ableton Live integration:
   - Ensure Ableton Live 11 is installed
   - Install AbletonOSC plugin for Ableton Live:
     - Download from: https://github.com/ideoforms/AbletonOSC/releases
   - Configure AbletonOSC to listen on port 11000
   - Start Ableton Live with AbletonOSC enabled before starting MusicFlow

## Usage

Run the CLI:

```
python musicflow.py
```

### Commands

#### MIDI Generation

- Generate a track: `generate [track_name]: [prompt]`
  Example: `generate bass: funky bassline in G minor with syncopation`

- Update a track: `update [track_name]: [prompt]`
  Example: `update drums: add more hi-hats and make kick pattern more interesting`

- List tracks: `list`

#### Ableton Live Integration

MusicFlow automatically connects to Ableton Live on startup and automatically loads tracks when they're generated.

- Show Ableton connection status: `ableton status`
- Manually load track into Ableton: `load [track_name]`
- Load all tracks into Ableton: `load all`

- Play a specific track in Ableton: `play [track_name]`
- Play all tracks: `play all`
- Stop a track: `stop [track_name]`
- Stop all playback: `stop all`

- Help: `help`
- Exit: `exit`

## Example Session

```
> generate drums: 4/4 techno beat with kick on every beat and offbeat hi-hats
✓ Created drums track
MIDI file: ./output/drums.mid
Description: A standard 4/4 techno beat with kick drums on every quarter note and hi-hats on the offbeats (8th notes).

Automatically loading track into Ableton Live...
Creating a new clip in track drums (index 0)
Successfully loaded notes into clip!
Starting playback of clip...

> generate bass: deep sub bass in F minor with occasional slides
✓ Created bass track
MIDI file: ./output/bass.mid
Description: A deep sub bass in F minor with occasional pitch slides between notes, focusing on the root and fifth.

Automatically loading track into Ableton Live...
Creating a new clip in track bass (index 1)
Successfully loaded notes into clip!
Starting playback of clip...

> update drums: add snare on beats 2 and 4
✓ Updated drums track
MIDI file: ./output/drums.mid
Description: Updated 4/4 techno beat with kick on every beat, offbeat hi-hats, and snare hits on beats 2 and 4.

Automatically reloading track in Ableton Live...
Deleting any existing clip in track drums (index 0)
Creating a new clip in track drums (index 0)
Successfully loaded notes into clip!
Starting playback of clip...
```

## Ableton Live Integration Details

MusicFlow integrates with Ableton Live using Open Sound Control (OSC), allowing you to:

1. Generate MIDI tracks with natural language prompts
2. Create tracks in Ableton Live automatically
3. Load MIDI files into Ableton (with some manual steps)
4. Play/stop individual tracks or the entire session
5. Update tracks and reload them into Ableton

### Setting up OSC with Ableton Live

To enable the Ableton Live integration:

1. Install AbletonOSC:
   - Download from: https://github.com/ideoforms/AbletonOSC/releases
   - Follow the installation instructions from the documentation

2. Configure AbletonOSC:
   - Launch Ableton Live
   - Open the AbletonOSC plugin
   - Set listening port to 11000
   - Start the OSC server from the plugin interface

3. Start MusicFlow, which will automatically connect to Ableton

### Working with Generated MIDI Files

The Ableton Live integration attempts to automatically load MIDI files using OSC commands, but fallbacks to a hybrid workflow if needed:

#### Automatic Mode (Attempted First)
MusicFlow will try to use advanced OSC commands (`/live/clip_slot/create_clip` and `/live/clip/add/notes`) to:

1. Create a new clip in the specified track
2. Add all MIDI notes from the generated file directly to the clip

If this works, you'll see notes being added in real-time in Ableton Live.

#### Manual Fallback (If Automatic Fails)

If automatic loading fails (which may happen depending on your AbletonOSC version):

1. Generate MIDI files with natural language prompts in MusicFlow
2. MusicFlow will create the MIDI files in the `output` directory
3. Use the `load` command to register a virtual track in the system
4. Manually create a track in Ableton Live with the same name
5. Drag the generated MIDI file into the track in Ableton

The playback commands will attempt to control Ableton, but you may need to manually start/stop playback in Ableton depending on your OSC implementation.

This flexible approach allows for rapid iteration on musical ideas through the conversational interface while leveraging Ableton Live's powerful audio engine.

## License

[MIT License](LICENSE)