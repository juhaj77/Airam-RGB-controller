"""Run the standalone manual (no-music) light control app: `python manual_control.py`

Lets you pick a static color for selected lamps and run a Chase/rotating-
light effect on its own timer - no audio capture, no music analysis. Shares
the same device list, local Tuya keys, and Chase settings as the music
visualizer (main.py) via the same config file.
"""
from airam_lights.manual_app import main

if __name__ == "__main__":
    main()
