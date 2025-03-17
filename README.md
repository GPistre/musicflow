# MusicFlow

An interactive MIDI generation tool that uses natural language prompts to create music.

## Overview

MusicFlow allows you to generate MIDI tracks for different parts of a song (drums, bass, lead, etc.) using natural language descriptions. For example, you can ask for "a funky 4/4 bassline with syncopation" or "a minimal techno kick pattern with occasional snares".

Each track is generated separately and can be updated with new prompts, enabling an interactive music production experience.

## Features

- Generate MIDI tracks using natural language descriptions
- Create different track types (drums, bass, lead, etc.)
- Update existing tracks with new prompts
- Conversational interface for intuitive interaction
- Exports standard MIDI files that can be imported into any DAW

## Requirements

- Python 3.9+
- Conda (for environment management)

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

## Usage

Run the CLI:

```
python musicflow.py
```

### Commands

- Generate a track: `generate [track_name]: [prompt]`
  Example: `generate bass: funky bassline in G minor with syncopation`

- Update a track: `update [track_name]: [prompt]`
  Example: `update drums: add more hi-hats and make kick pattern more interesting`

- List tracks: `list`

- Help: `help`

- Exit: `exit`

## Example Session

```
> generate drums: 4/4 techno beat with kick on every beat and offbeat hi-hats
✓ Created drums track
MIDI file: ./output/drums.mid
Description: A standard 4/4 techno beat with kick drums on every quarter note and hi-hats on the offbeats (8th notes).

> generate bass: deep sub bass in F minor with occasional slides
✓ Created bass track
MIDI file: ./output/bass.mid
Description: A deep sub bass in F minor with occasional pitch slides between notes, focusing on the root and fifth.

> update drums: add snare on beats 2 and 4
✓ Updated drums track
MIDI file: ./output/drums.mid
Description: Updated 4/4 techno beat with kick on every beat, offbeat hi-hats, and snare hits on beats 2 and 4.
```

## License

[MIT License](LICENSE)