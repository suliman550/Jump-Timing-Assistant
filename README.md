# Jump-Timing-Assistant

A lightweight Roblox timing overlay for Keyboard Escape.

This project is a lightweight Windows overlay meant to help a player judge the best moment to press a jump key for a timing-based jump mechanic.

## Safety and scope

The project intentionally avoids unsafe game modification. It does not inject DLLs, modify memory, change Roblox files, or bypass anti-cheat systems.

Because in-game event detection for a shrinking/size mechanic would require invasive hooks, this safe version uses a manual fallback startup method. The overlay still exposes the required `AUTO` and `MANUAL` status labels and keeps the timing logic fully configurable.

## How to run

1. Install Python 3.10+.
2. Install the dependencies:
   - `pip install -r requirements.txt`
3. Launch the overlay:
   - `python jump_timing_assistant.py`
4. Use the configured hotkeys:
   - Toggle overlay: `F7`
   - Start/reset timing: `F8`
   - Reset timer: `F9`
   - Open calibration: `F10`
   - Open settings: `Home` or `End` (including keyboards where these are reached with `Fn`)

The app also appears in the Windows taskbar and notification area. Use the tray icon to show or hide the overlay, open settings, or exit.

## Timing model

The app starts with the Keyboard Escape timing requested for the Roblox technique:

- Shrink trigger: `X`
- Recommended jump: `4500 ms` after the trigger
- Jump input: `Space`, always pressed manually

The target is configurable using:

- `base_jump_ms`
- `timing_offset_ms` (positive or negative)
- `reaction_compensation_ms`
- `perfect_window_ms`
- `jump_start_ms`
- `jump_end_ms`

The default value is intentionally conservative and should be adjusted against the reference video for the exact game and reaction conditions.

The timing logic is:

- Target jump time = base jump timing + manual offset + reaction compensation
- Perfect jump window = target ± perfect window size
- Visual states:
   - `WAIT` before 3500 ms
   - `JUMP` from 3500 ms through 4700 ms
  - `TOO LATE`

## Calibration

Press `F10`, `Home`, or `End` to open the settings/calibration dialog and adjust:

- Base jump timing (ms)
- Perfect window (ms)
- Timing offset (ms), including negative values
- Reaction compensation (ms)
- Shrink, jump, and reset hotkeys
- Jump start and end boundaries
- Overlay background, main text, secondary text, and accent colors using the color pickers

The values are saved to `settings.json` automatically.

## Manual activation fallback

This is the safe, reliable mode that is always available:

- Press `X` when the shrink event occurs. If automatic `X` detection is unavailable, press the activation hotkey (`F8` by default)
- The timer begins immediately at that exact moment
- The overlay displays the live countdown and jump recommendation
- The player presses the configured jump key manually when the overlay says `JUMP`

The tool never presses `Space` automatically.

## Files

- `jump_timing_assistant.py` — main overlay app
- `settings.json` — saved settings
- `calibration_data.json` — recorded calibration attempts
- `requirements.txt` — dependencies
- `tests/test_timing_logic.py` — unit tests for the timing math
- `JumpTimingAssistant.ico` — application icon
- `installer.py` — source for the desktop setup executable

## Note on the referenced video

The instructions in the project file explicitly say not to guess the timing and to validate the timing against the reference video. This implementation therefore keeps the timing as a configurable calibration value rather than inventing a single hard-coded number. The exact match should be tuned by the user against the reference section and their personal reaction speed.
