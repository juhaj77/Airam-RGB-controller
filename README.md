# Airam Music Lights

A Windows desktop application that turns **Airam SmartHome Smart PAR16 RGB GU10**
Wi-Fi spotlights into a real-time, fully configurable music visualizer - controlled
entirely over your **local network**, with no cloud dependency at runtime, no Android
phone, and no microphone required. Works with any number of lamps, from one to as
many as your Wi-Fi network and Tuya account can handle - the author's own setup runs
8, but nothing in the app assumes that specific number anywhere.

It replaces the Airam SmartHome app's built-in "Music Sync" (which is limited to one
bulb at a time and changes colors abruptly) with your own local FFT-based analysis,
smooth attack/release color interpolation, and simultaneous, synchronized control of
every lamp you own.

> **If you only try one mode, try Beat Sync.** Of the six color-mapping modes, it's
> the one that consistently feels the most visually alive in practice - a percussive
> flash-and-decay on every beat instead of the continuous, sometimes-muted blending the
> other modes do. See [section 5](#5-running-the-full-application) for the full writeup,
> or jump straight to [Beat Sync mode](#beat-sync-mode).

> **Read `DEVICE_NOTES.md` first.** It separates *confirmed facts*, *assumptions*, and
> *things you still need to test* about your specific bulbs. This README assumes you
> will run Phase 1 (below) against your real hardware before relying on anything else.

**At a glance:**

- **100% local control** - WASAPI loopback audio + local Tuya LAN protocol, no cloud
  round-trip and no companion app needed once set up.
- **Six color-mapping modes**: RGB Frequency, HSV Music, 8-Band Spectrum, Beat Sync
  (see above), Peak Flash, and Beat Sync White - plus a Custom mode for arbitrary
  frequency ranges.
- **Per-lamp control**: band assignment, phase offset, and independent
  brightness/saturation/hue/sensitivity multipliers for every lamp.
- **Chase / Rotating Light overlay** - a moving highlight (reversible, adjustable
  width/speed/falloff curve, optionally beat-synced) layered on top of any mode.
- **Ambient Scenes** - synchronized, PC-driven looping animations (color cycle,
  breathing, color-temperature breathing) that solve multi-lamp sync properly instead
  of power-cycling smart plugs.
- **Standalone manual control app** (`manual_control.py`) for audio-free color/white/
  chase/ambient control, sharing one config file with the music visualizer.
- **Works with any number of lamps** - nothing in the app hardcodes a specific count.
- **Crash-resilient persistence** - autosaves every 20s, restores your exact last state
  (including the manual app's last-picked color) on restart.
- **Keeps the PC awake** while either app is open, without blocking manual sleep.

Both apps (`main.py` and `manual_control.py`) prevent the PC from **automatically**
going to sleep while they're open (`airam_lights/keep_awake.py`, Windows'
`SetThreadExecutionState` API) - a full system sleep pauses every process at the
hardware level (CPU, network, everything), so there is no way to "keep working through"
one; the only real fix is asking Windows not to idle-sleep in the first place. The
display can still turn off / the session can still lock (that doesn't stop the app),
and this only blocks *automatic, idle-timeout* sleep - manually choosing Sleep from the
Start menu, or a laptop's own lid-close power-plan action, still works as normal. If a
laptop's Wi-Fi adapter still seems to drop out from under an otherwise-awake PC, check
Device Manager -> your Wi-Fi adapter -> Power Management -> "Allow the computer to turn
off this device to save power" (uncheck it) - that's a separate, adapter-level setting
this API does not control.

---

## 1. How this works (architecture)

```
 WASAPI loopback -> FFT / DSP -> Color Mapping -> Per-Lamp Effects -> Lamp Manager -> N Airam bulbs (LAN)
   (audio/)         (dsp/)        (color/)          (engine/)          (lamps/)
```

- **audio/** - WASAPI loopback capture ("what you hear"), decoupled ring buffer.
- **dsp/** - windowed FFT, configurable frequency-band energy extraction, spectral
  centroid/contrast, attack/release smoothing. Pure numpy, no UI/network dependency.
- **color/** - RGB / HSV / 8-band color mapping. Pure functions on floats, no
  dependency on audio or Tuya code, so it can be (and is) unit-tested in isolation.
- **lamps/** - local Tuya (tinytuya) device control, LAN discovery, one worker thread
  per lamp with independent rate limiting and change-thresholding.
- **engine/** - ties the above together via two independently-configurable update
  loops (audio analysis rate vs. visual/smoothing rate); lamp command rate is enforced
  separately again, inside the lamp manager.
- **effects/** - the Chase/rotating-light overlay (`chase.py`), shared between the music
  visualizer and the standalone manual control app (see below) so it only exists once.
- **config/** - JSON configuration (devices, groups, presets, DSP/color settings).
- **diagnostics/** - logging + runtime rate/latency metrics, shown in the Diagnostics tab.
- **ui/** - PySide6 desktop UI (5 tabs: Visualizer, Devices & Setup, Color Mapping,
  8-Band & Per-Lamp, Diagnostics).

The DSP/color engine has **zero import dependency** on the lamp/Tuya layer, and vice
versa - you can develop/test the visualization math with `pytest` alone, no bulbs
required (see `tests/`).

---

## 2. Local control of the Airam bulbs - what's confirmed vs. assumed

See `DEVICE_NOTES.md` for the full breakdown, including the exact confirmed datapoint
(DP) table. Short version:

- **Confirmed end-to-end against real hardware**: local LAN control (no cloud
  round-trip) works, including full RGB color/brightness/power control, verified via
  `tools/phase1_test.py`'s red/green/blue/white cycle on a physical bulb.
- Airam SmartHome bulbs are Wi-Fi-only, no hub - this matches the product page.
- They are built on the **Tuya IoT platform** (product ID `cawpuqfm0ed5ykfj`), using DP
  layout "Type B" (`switch_led`=20, `work_mode`=21, `bright_value_v2`=22,
  `temp_value_v2`=23, `colour_data_v2`=24) - confirmed directly from the bulbs' own
  local `status()` response, not assumed.
- Tuya devices of this class expose a **local LAN protocol** (TCP port 6668,
  encrypted with a per-device `local_key`). This app uses
  [`tinytuya`](https://github.com/jasonacox/tinytuya), a mature open-source
  implementation of that protocol, instead of inventing anything.
- **No datapoint IDs are hardcoded anywhere in this codebase.** Color/brightness/power
  control goes through `tinytuya.BulbDevice`, which reads each bulb's own `status()`
  response and adapts to whatever layout it actually reports. The diagnostics tooling
  (Phase 1 script and the app's Diagnostics tab) always shows you the *real* raw
  datapoints your bulbs return.
- The Tuya cloud API is used for **exactly one thing, once, offline from the
  visualizer**: extracting each bulb's `local_key` during setup, because Tuya does not
  broadcast that key on the LAN for security reasons. All runtime traffic (audio
  analysis -> color -> lamp commands) is 100% local LAN, no cloud round-trip.
- **Still not independently verified against real hardware**: the WHITE work_mode
  control path used by Beat Sync White, White Balance, and White Chase
  (`LampDevice.set_white()`). The DP layout it uses is the same confirmed table above,
  but the specific `tinytuya` calls have not yet been run against a physical bulb - test
  this yourself via the manual app's White Balance tab before relying on it. RGB color
  control is fully confirmed and is what every other mode uses.

---

## 3. Installation

Requires **Python 3.10+** on Windows (tested with recent CPython 3.x; PySide6 and
PyAudioWPatch both ship Windows wheels).

```powershell
cd D:\projects\Airam-RGB-controller
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

For running the automated tests too:

```powershell
pip install -r requirements-dev.txt
```

---

## 4. Phase 1: prove local control works on ONE bulb (do this first)

Don't skip this - it's the whole point of "don't invent undocumented datapoints."

### 4.1 Find your bulb's IP / device ID on the LAN

```powershell
python tools\scan_devices.py
```

This broadcasts a UDP discovery packet and lists every Tuya device that answers, with
IP, device ID, and protocol version. It does **not** give you the `local_key` - Tuya
never broadcasts that on the LAN.

### 4.2 Obtain each bulb's `local_key` (one-time, via the Tuya cloud)

```powershell
python tools\setup_wizard.py
```

This launches `tinytuya`'s interactive setup wizard, which needs a **free** Tuya IoT
Platform developer account linked to your Airam SmartHome app account:

1. Create an account at <https://iot.tuya.com> and create a **Cloud Development**
   project (any region close to Finland, e.g. Western Europe / Central Europe).
2. In that project, subscribe to the **IoT Core** and **Authorization** APIs (under
   "Service API" - both are free-tier).
3. Go to **Cloud -> \[your project\] -> Devices -> Link Tuya App Account**, and scan
   the QR code shown there **using your Airam SmartHome app** (its own QR scanner,
   usually under account/settings - the app itself doesn't need to know anything about
   Tuya; this is purely the cloud platform's device-linking flow, which works
   identically for any Tuya-based white-label app). Your bulbs should now be listed
   as linked devices in the Tuya IoT Platform.
4. Run the wizard above; it asks for your **Access ID**, **Access Secret** (both shown
   on your Cloud project's Overview page), the **data center region**, and your
   account UID (shown next to the linked app account). It then downloads a
   `devices.json` with every device's `local_key` and writes it locally.
5. `tools\setup_wizard.py` automatically imports that into the app's own config file
   (`%APPDATA%\AiramMusicLights\config.json`) and never prints the keys to the
   console.

If this linking step doesn't work for your Airam account for any reason, you can also
obtain a bulb's `local_key` through other local-Tuya tooling you may already have used
(e.g. Home Assistant's Tuya Local integration config flow) and enter it manually in the
app's **Devices** tab instead - the app never requires the wizard specifically, only a
valid `(device_id, ip, local_key, version)` tuple per bulb.

### 4.3 Test ONE bulb manually

```powershell
python tools\phase1_test.py --device "Lamp 1"
```

or, without touching the config file at all:

```powershell
python tools\phase1_test.py --ip 192.168.1.50 --id eb3f... --key 0123456789abcdef
```

This prints:

- online/offline
- the **raw datapoints** your bulb actually returned (not an assumption)
- detected bulb type (A/B/C - see `DEVICE_NOTES.md`)
- measured command latency
- then cycles the bulb red -> green -> blue -> white so you can visually confirm local
  RGB control genuinely works.

Once this passes, update the confirmation table in `DEVICE_NOTES.md` and move on.

---

## 5. Running the full application

```powershell
python main.py
```

### Visualizer tab
Pick your WASAPI loopback device (defaults to your current default playback device -
no microphone involved), watch the level meter and spectrum to confirm audio capture
works, choose a mode, tweak sensitivity/brightness/saturation/attack/release, and press
**Start Music Visualization**.

### Devices & Setup tab
Add lamps manually (or via **Scan Network** for IP/ID, then fill in the key), test
connection/RGB/power per device, rename them, select exactly which ones participate
in visualization, and save/apply named groups (e.g. "All Lamps", "Ceiling", "Left side").
The lamp list, chase rotators, and every per-lamp table scale to however many devices
you've added - there is no fixed lamp count anywhere in the app.

### Color Mapping tab
Full detail for **RGB Frequency** and **Custom** modes (per-channel frequency range,
gain, min/max level, gamma - both modes are literally the same mechanism, Custom just
unlocks arbitrary ranges instead of the bass/mid/treble defaults), **HSV Music**
mode (hue from spectral centroid, brightness from overall energy, saturation from
spectral contrast), and **Beat Sync** mode (see below). Also: response curve
(linear/log/exp2), the network's min-change threshold, mapping presets, and
**Invert brightness** - a single checkbox in the Global section that flips the
brightness response for every mode at once (0 becomes bright, 1 becomes black), for
when you want quiet passages to light up and loud/energetic moments to go dark instead
of the usual way around.

#### Beat Sync mode
The other modes blend colors continuously, which can end up looking muted/washed
toward white if the source material doesn't have big swings between bands. Beat Sync
takes the opposite approach: a simple energy-based beat detector
(`dsp/beat_detector.py`, unit-tested with synthetic pulse trains in
`tests/test_beat_detector.py`) watches one frequency band (kick-drum range, 40-200 Hz,
by default) and on every detected hit jumps the lamps to a **fresh, fully-saturated hue
at full brightness**, then lets brightness decay toward a dim baseline until the next
hit - a percussive flash-and-decay envelope that makes the rhythm obvious instead of a
faint brightness ripple. Three ways to pick the new hue each beat:

- **random** (default): a new hue every hit, forced to differ from the last one by at
  least `min_hue_jump_deg` so you never get two similar colors back to back.
- **step**: advances by a fixed angle each hit (default 137.5°, the "golden angle" -
  cycles through well-spread colors without ever repeating for a long time).
- **spectrum**: hue follows the spectral centroid at the instant of the hit.

`sensitivity` / `min_interval_ms` / `min_energy` tune how trigger-happy the detector
is; `hue snap speed` / `brightness attack` / `brightness decay` tune how sharp vs.
smooth the flash feels. Per-lamp phase offset (8-Band & Per-Lamp tab) still works here
too - stagger it across lamps for a chase/wave effect on every beat.

**Dark pulses**: `dark_pulse_probability` (0..1) is the chance that a given beat first
dips toward black for `dark_pulse_duration_ms` (how dark, via `dark_pulse_depth`)
*before* flashing to its new color, instead of flashing immediately - a rhythm-synced
pause/strobe accent layered on top of the hue and brightness behavior above. Since this
is a real-time reactive system, it can only react to a beat as it happens (it can't
anticipate a future one), so the pause always starts right on the trigger and the
actual color flash is simply delayed until the pause ends - not a pause *before* the
hit, but a hesitation *right on* the hit before committing to the flash.

#### Peak Flash mode
A softer, more continuous cousin of Beat Sync. Instead of a fixed bass-only trigger and
a hue that only changes on a beat, Peak Flash:

- Detects peaks across the **whole spectrum** by default (not just bass), so it reacts
  to any sudden loud moment - kicks, snares, vocal hits, sung notes, anything.
- Blends the color toward **pure white** in proportion to treble/cymbal/sibilance
  energy (`treble_low_hz`-`treble_high_hz`, default 5-16 kHz) - hit a crash cymbal or a
  bright hi-hat and the lamps flash white; when the treble drops back down they return
  to full color. This is a smooth blend (`white attack`/`white release`), not a hard
  switch.
- Keeps brightness **continuously tracking overall loudness** (`baseline brightness
  min/max`) between peaks, with a sharp `flash brightness` boost exactly on each
  detected peak that decays back down (`flash attack`/`flash decay`) - so the lights
  breathe with the music's overall intensity, not just jump on/off.
- Never snaps hue discretely - it **flows continuously**, either as a slow autonomous
  rotation (`hue_source: drift`, speed via `drift speed`) or by continuously following
  the spectral centroid (`hue_source: centroid`). The key control here is **"Color
  richness (hue flow)"**: a smoothing time constant (hundreds of ms up to ~15s) that is
  the actual math behind the "smooth blend" / storytelling feel you get by turning it
  up - higher values make the color arc unfold slowly and richly over an entire song
  section; lower values make it dance more quickly.

Net effect: vivid, maximally saturated color most of the time, punctuated by white
flashes on cymbals/treble peaks and brightness swells tracking the music's energy,
while the underlying hue keeps telling a slow, continuous color "story" instead of
jumping around.

#### Beat Sync White mode
The same rhythm-reactive envelope as Beat Sync (including dark pulses), but drives the
bulb's **WHITE work_mode** (brightness + color temperature) instead of RGB - the lamps
stay genuinely white, animating warm<->cool on the beat rather than jumping between
colors. `temp_mode: random` picks a new temperature every hit (forced to differ from
the last one by `min_temp_jump`); `alternate` ping-pongs cleanly between the warm and
cool ends of your configured `temp_min`/`temp_max` range. Everything else (sensitivity,
min interval, flash/sustain brightness, dark pulses) works exactly like Beat Sync.

> This is the newest lamp-control call in the app (`LampDevice.set_white()`) and,
> unlike RGB, has **not yet been independently verified against the physical bulbs** -
> see `DEVICE_NOTES.md`. Test it via the manual app's White Balance tab first.

### 8-Band & Per-Lamp tab
Edit the 8 frequency bands (defaults to the 20 Hz-12 kHz split from the spec, one band
per lamp), 8-band appearance (base hue, hue step for a rainbow look, saturation,
brightness range), and the **per-lamp effects table**: band assignment, temporal/phase
offset (for wave/chase effects), brightness/saturation/hue/sensitivity multipliers, and
**chase order** per lamp - this is what turns a set of identical bulbs into a
coordinated light installation instead of identical copies of the same signal, and it
applies in every mode, not just 8-band.

#### Chase / Rotating Light overlay
An overlay effect layered on top of **whichever color mode is active** (RGB, HSV,
8-Band, Beat Sync, Peak Flash, Custom - all of them): give a lamp a **chase order**
(0, 1, 2, ...) in the per-lamp effects table to include it in the rotation, then a
moving highlight travels through them in that order, creating a spinning/chasing light
effect on top of whatever colors the active mode is already producing.

- **Speed**: either a constant number of **full rotations per second** (e.g. 0.5 = one
  complete lap around all the chase-ordered lamps every 2 seconds, regardless of how
  many lamps are in the chase), or **synced to the detected beat** - `beat_multiplier`
  sets how many lamp-steps happen per beat (1 = one step per beat, 2 = twice as fast,
  0.5 = one step every two beats) using the chase's own independent beat detector, so it
  speeds up/slows down with the music's tempo without needing any music-theory knowledge.
- **Highlight width**: how many lamp-positions the glow spans (soft falloff). Lower
  (e.g. 0.5-0.8) gives a crisp "single dot traveling" look; higher blurs it across more
  lamps at once.
- **Intensity**: a brightness *boost multiplier* applied on top of whatever brightness
  the active mode already computed for that lamp - it is never an independent/fixed
  brightness. This matters: a lamp the active mode has deliberately dimmed to black
  (e.g. a Beat Sync dark pulse) stays black no matter how high the intensity or how wide
  the highlight is, since boosting zero brightness is still zero. If the chase feels too
  subtle, raise this (default 3x) rather than expecting it to override a dark moment.
- **Color**: either a fixed custom hue/saturation, or **complementary** - the chase
  highlight's hue becomes the opposite (+180°) of whatever hue that lamp is already
  showing from the active mode. For the clearest, most obviously visible effect, use
  **custom** with a hue that's very different from your usual palette (e.g. if your
  mode tends toward blues/greens, try an orange/red custom hue around 20-40°) combined
  with a narrow width.
- **Chase dwell x** (per-lamp effects table, one column per lamp): how long the
  highlight lingers at *this lamp's* chase position relative to the others - 1.0 is
  the default/uniform speed. Lower it for a position that has several physical lamps
  sharing one chase order (e.g. a multi-spot ceiling fixture) if the highlight feels
  like it dwells there noticeably longer than at single-lamp positions - which is a
  real perceptual effect (more lamps lit at once reads as "lingering" even though the
  underlying timing is uniform without this), not just something to live with.

### Diagnostics tab
Audio callback rate, FFT/analysis rate, visual update rate, per-lamp online state /
bulb type / latency / command counts (sent, failed, skipped-as-unchanged), current
mode, and a live log viewer.

Configuration (devices, groups, presets, DSP/color settings - including local keys) is
saved automatically on a clean exit to `%APPDATA%\AiramMusicLights\config.json`, in
human-readable JSON, **and** every 20 seconds while the app is running - so nothing
from a session is lost even if the app is killed abruptly (crash, Task Manager, power
loss) instead of closed normally. Both apps (`main.py` and `manual_control.py`) read
and write this exact same file, so anything tuned in one is already there the next time
you open either. This is verified by `tests/test_config_persistence.py` (every field of
every settings dataclass survives a save/reload round-trip, including old config files
saved before newer features existed) and was additionally exercised end-to-end through
the real UI in both apps (set values via the actual widgets, close, reopen a fresh
window, confirm every value - and the widgets displaying them - match).

This includes the manual app's **actual picked static color/white-balance**
(`ManualStateConfig`) - not just the Chase/Ambient/etc. *settings*, but the literal
color you last applied via "Apply to Selected", restored and re-sent to the lamps the
moment the app starts, regardless of what Chase or Ambient happen to be configured to
(see `tests/test_manual_engine.py`). Turning a selection off does not overwrite this -
it's treated as a power state, not a change in your preferred color.

---

## 6. Manual (no-music) control app

```powershell
python manual_control.py
```

A separate, standalone app for controlling the lamps' colors directly, with no audio
capture and no music analysis at all - for when you just want to set a color or run a
lighting effect without playing anything. It shares the **same config file** as
`main.py` (same devices, local keys, per-lamp chase positions, and Chase settings), so
anything you tune in one shows up in the other.

- **Devices & Setup tab** - identical to the music app's (same code, reused as-is):
  add/scan/test lamps, name them, select which participate.
- **Manual Color tab** - pick a color from a color dialog and apply it to whichever
  lamps are currently selected; also Turn On/Off buttons for the selection.
- **White Balance tab** - drives the bulb's WHITE work_mode instead of RGB: set a
  static brightness + color temperature (0=warmest..1=coolest) for the selection, plus
  a **White Chase** effect - a warm-or-cool region (`target_temp`) rotates through the
  chase-ordered lamps instead of an RGB highlight, using the same rotators/width/speed/
  intensity controls and the same position-grouping as the RGB Chase.
- **Chase / Rotating Light tab** - the RGB Chase overlay described below, run on its
  own ~30 Hz timer instead of driven by audio. "Sync to beat" isn't offered here since
  there's no audio to sync to (picking a beat-synced preset in the music app and then
  opening this app just falls back to the constant speed instead of crashing).
- **Ambient Scenes tab** - self-looping animations (see below) that replace the bulb's
  own onboard "scene" animations specifically to solve **synchronization** across
  multiple lamps.

Only one PC-driven animation actually drives the lamps at a time (whichever you
used/enabled most recently - applying a static color or enabling RGB Chase switches to
RGB, applying White Balance or enabling White Chase switches to White, enabling an
Ambient Scene takes over from either), since a bulb can only be in one work_mode at
once and this app only ever runs one animation loop.

#### Ambient Scenes: solving lamp synchronization properly
If you've been setting the bulbs' own built-in animated "scene" in the Airam app on
each lamp individually, then trying to power-cycle a smart plug and a light switch at
the same instant to line them up - stop doing that. It's fighting a fundamental
limitation: each bulb's onboard scene animation runs on its **own internal clock**,
starting whenever it was individually triggered, and there is no command to say "start
now, in sync with these other lamps." Smart plugs' own switch-on latency makes the
power-cycle trick unreliable on top of that.

Ambient Scenes are computed **once per tick, from one shared clock, on the PC**, and
pushed to every selected lamp together on the same network round - so they are
synchronized by construction, with zero timing trickery required:

- **color_cycle** - every lamp sweeps through the full hue wheel together (a
  synchronized rainbow).
- **breathing** - brightness pulses smoothly between a min and max at a fixed hue (RGB).
- **temp_breathing** - the same smooth pulse, but on color temperature instead
  (WHITE work_mode - warm to cool and back).

`Speed` sets how many full cycles happen per second (e.g. 0.1 = one cycle every 10s).
Every lamp defaults to phase offset 0 = perfectly synchronized; the optional per-lamp
"Phase offset (ms)" table lets you deliberately stagger lamps instead, for a traveling
wave look, if you ever want that - but synchronized is the default and the point.

This intentionally does **not** touch the bulb's own scene datapoint (DP 25) - its
on-wire encoding was never independently confirmed for these bulbs (unlike DP 24's
colour format, which was), and using it wouldn't solve the sync problem anyway even if
decoded. See `DEVICE_NOTES.md` for the full reasoning.

The Chase overlay's underlying math (`airam_lights/effects/chase.py`) is shared code
between this app and `main.py`'s music visualizer - a fix or feature there (like the
lamp-position grouping described below) applies to both automatically, they can never
drift apart into two different implementations.

### Chase / Rotating Light overlay (shared by both apps)

Give a lamp a **chase position** (0, 1, 2, ...) - in the manual app's Chase tab, or in
the music app's 8-Band & Per-Lamp tab's per-lamp effects table - to include it in the
rotation, in that order. **Lamps that share the same position number animate
together, as one group** - this matters because your physical lamp layout is usually
not a single ring; e.g. give the two lamps on each of four walls the same position
number (0, 0, 1, 1, 2, 2, 3, 3) and the chase treats each wall as one step, moving
around the room instead of assuming an actual circle of individually-addressable
positions.

- **Number of rotators**: how many highlights travel the loop at once, evenly spaced
  and always moving together - 2 puts them on opposite sides, 3 a third apart, etc.
- **Speed**: full rotations per second (e.g. 0.5 = one lap every 2 seconds), or, in the
  music app only, synced to the detected beat.
- **Reverse direction**: flips which way the highlight travels around the chase order.
  Available on RGB Chase, White Chase, and Ambient Scenes' `color_cycle` (it has no
  visible effect on `breathing`/`temp_breathing`, whose pulse is symmetric in time).
- **Highlight width**: how many chase positions the glow spans (soft falloff) - lower
  is a crisper "single spot" look.
- **Intensity**: a brightness *boost multiplier* on top of each lamp's own current
  brightness - never an independent/fixed value, so a lamp that's off/black stays that
  way no matter the intensity or width (this was a real bug, now fixed and covered by a
  regression test in `tests/test_chase.py`).
- **Falloff curve**: `linear` (constant-rate falloff from the peak - the peak color is a
  single fleeting instant, which can feel like it "flies by" too quickly) or `bezier`
  (an eased S-curve/smoothstep that dwells near the peak color - and near the
  background - for longer, transitioning fastest in the middle). Try `bezier` if a
  chase color feels too brief.
- **Color**: `custom` (a fixed hue/saturation you set), `complementary` (the opposite
  hue of whatever that lamp's own color currently is), or `hue_shift` (each position
  shows a progressively different hue - a rainbow trail as the light travels around).
- **Dwell x** (per-lamp, in the same position table): how long the highlight lingers
  at that lamp's own position relative to the rest of the loop - 1.0 is uniform/
  default. Lower it for a position where several lamps share one chase order (e.g. a
  multi-spot ceiling fixture) if that position feels like it holds the highlight
  noticeably longer than single-lamp positions do; raise it to deliberately make the
  highlight pause somewhere. Applies to both RGB Chase and White Chase, since they
  share the same chase positions.

Presets (Color Mapping tab, music app) capture the full setup, Chase overlay and
per-lamp chase positions included - not just the color mapping mode's own settings.

---

## 7. Why it feels smooth instead of "crude" like the Airam app

Every level (band energy, spectral centroid, brightness, per-lamp output) passes
through **attack/release exponential smoothing**
(`value += (target - value) * alpha`, with `alpha` derived independently from the
attack and release time constants depending on whether the signal is rising or
falling - see `dsp/smoothing.py`). A bass hit can snap up quickly (short attack) while
decaying gently (long release), and every intermediate value is sent, not just the
start/end - e.g. bass going from 30% to 80% actually produces a sequence like
`30 -> 35 -> 42 -> 51 -> 63 -> 74 -> 80`, never a single jump.

On top of that, the network layer independently **rate-limits** each lamp
(`lamp_command_rate_hz`) and **skips sends that are effectively unchanged**
(`min_change_threshold`), so smoothing doesn't turn into needless network spam - see
`lamps/manager.py`.

---

## 8. Update rates - independently configurable

| Stage | Config field | Default |
|---|---|---|
| Audio analysis (FFT) | `audio.analysis_update_hz` | 60 Hz |
| Visual/color/smoothing | `network.visual_update_hz` | 30 Hz |
| Per-lamp network commands | `network.lamp_command_rate_hz` | 20 Hz (auto backs off on failures) |

These are deliberately separate: the FFT can run faster than the color engine needs,
and the color engine can run faster than any real Wi-Fi bulb can reliably accept
commands. If a lamp starts failing/timing out, its worker thread automatically backs
off (exponentially, capped at 16x its configured interval) without affecting any other
lamp or the UI - each lamp has its own independent worker thread, so this holds
regardless of how many lamps you have.

---

## 9. Running the tests

```powershell
pip install -r requirements-dev.txt
pytest tests/ -v
```

These test the DSP and color-mapping modules in isolation (synthetic sine waves, no
audio hardware; pure float math, no bulbs) - exactly the independence the spec asked
for between the music-analysis engine and the lamp-control layer.

---

## 10. Development phases (status)

- [x] **Phase 1** - local protocol investigation + single-bulb diagnostic script
      (`tools/phase1_test.py`, `tools/scan_devices.py`, `tools/setup_wizard.py`).
- [x] **Phase 2** - multi-lamp device list, selection, naming, groups, manual RGB/power
      test (Devices & Setup tab).
- [x] **Phase 3** - WASAPI loopback audio capture, level meter, spectrum display
      (Visualizer tab, no lamp control involved).
- [x] **Phase 4** - RGB Frequency visualization with attack/release smoothing.
- [x] **Phase 5** - 8-band spectrum mode, HSV mode, configurable frequency ranges,
      per-lamp modifiers, presets.
- [x] **Phase 6** - performance/reliability: per-lamp worker threads, automatic
      backoff, min-change thresholding, diagnostics tab.
- [x] **Phase 7** - Beat Sync / Peak Flash / Beat Sync White color-mapping modes, the
      Chase/Rotating Light overlay (shared between both apps, with reverse direction
      and a linear/bezier falloff curve), Ambient Scenes, and the standalone
      `manual_control.py` app for audio-free lamp control - all confirmed against real
      hardware (see `DEVICE_NOTES.md`), except WHITE work_mode (see section 2).
- [x] **Phase 8** - robustness/polish: config persistence that survives crashes
      (20s autosave) and restores the manual app's exact last-picked color/white
      balance on restart, a Windows keep-awake hook so long sessions survive automatic
      idle sleep, and a full audit removing every hardcoded lamp-count assumption so the
      app works the same with 1 lamp or 20.

## 11. Known limitations / honest caveats

- **RGB color control is confirmed against physical Airam bulbs** end-to-end (local
  LAN, no cloud round-trip) - see `DEVICE_NOTES.md` for the full trace. **WHITE
  work_mode control (Beat Sync White / White Balance / White Chase) is not yet
  independently verified** against real hardware; test it yourself via the manual
  app's White Balance tab before relying on it for anything important.
- `tinytuya`'s LAN scan/wizard APIs have shifted slightly across versions;
  `lamps/discovery.py` and `tools/setup_wizard.py` are written defensively (try
  multiple call signatures / key names) but if your installed `tinytuya` version
  differs meaningfully, check its own `python -m tinytuya scan` / `wizard` output
  directly as a fallback - the app's Devices tab lets you enter everything manually
  regardless.
- Every non-UI module (`audio`, `dsp`, `color`, `lamps`, `config`, `engine`, `effects`)
  is covered by an automated test suite (`pytest tests/`, currently 58 tests: DSP,
  smoothing, color mapping, beat detection, Chase/Ambient overlays including reverse
  direction, and full config-persistence round-trips) plus offscreen Qt smoke tests
  that construct the real UI windows end-to-end.
- The Tuya cloud account-linking step (one-time, during setup) can be finicky
  depending on how your Airam SmartHome account is set up - `DEVICE_NOTES.md` documents
  the exact snags hit during development (the "use the correct app" QR block, the
  "data center is suspended" cloud console error) and working fallbacks for both.
