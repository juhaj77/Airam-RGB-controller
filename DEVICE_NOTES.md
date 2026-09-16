# Device investigation notes - Airam Smart PAR16 RGB GU10

This file tracks what is **confirmed**, what is **assumed**, and what still needs to be
**verified against the physical bulbs**. Keep it up to date as you test - it is the
source of truth for "do we actually know this, or are we guessing?".

Product: Airam Kohdelamppu Smart PAR16 827/865 RGB GU10 (2-pack), Prisma FI product
110471012. Controlled today via the "Airam SmartHome" Android app, Wi-Fi only (no hub).

## CONFIRMED (2026-09): full local control chain works end-to-end

`tools/setup_wizard.py` successfully pulled all 8 devices' `local_key`, MAC, and the
Tuya cloud's own datapoint (DP) specification for this exact product
(`product_id: cawpuqfm0ed5ykfj`, "PAR16 4.7W/345lm 827-865+RGB 36D 4713881"). The
wizard's own follow-up **local** (non-cloud) poll then successfully read live `dps`
from all 8 bulbs on the LAN using those keys - e.g.
`{'20': True, '21': 'white', '22': 1000, '23': 0, '24': '000003e803e8', ...}`. This
proves local LAN control works and the keys are correct, independent of anything in
this app's own code.

**Confirmed DP layout (Type B, exactly as guessed in the table below):**

| DP | code | type | notes |
|----|------|------|-------|
| 20 | `switch_led` | Boolean | power on/off |
| 21 | `work_mode` | Enum | `white`, `colour`, `scene`, `music` - must be `colour` for RGB to take effect |
| 22 | `bright_value_v2` | Integer 10-1000 | brightness |
| 23 | `temp_value_v2` | Integer 0-1000 | color temperature |
| 24 | `colour_data_v2` | hex string on the wire, `hhhhssssvvvv` (HSV16, 4+4+4 hex digits) | e.g. `000003e803e8` = h:0, s:1000, v:1000 = full red. Cloud spec describes this DP as JSON `{h,s,v}` but the *local* protocol packs it as this hex string - matches what `tinytuya.BulbDevice` already expects, confirming no custom encoding is needed. |
| 25 | `scene_data_v2` | Json | built-in scenes (1-8) |
| 26 | `countdown_1` | Integer (s) | sleep timer |
| 27 | `music_data` | Json (`h`,`s`,`v`,`bright`,`temperature`,`change_mode`) | likely what the stock Airam Music Sync writes to - **not used by this app**, we drive DP 24/22 directly instead for full multi-lamp control |
| 28 | `control_data` | Json | same shape as music_data, purpose unclear, not used |
| 30/31/32 | `rhythm_mode`/`sleep_mode`/`wakeup_mode` | Raw | unused |
| 34 | `do_not_disturb` | Boolean | unused |
| 41 | `remote_switch` | Boolean | unused |

Account-linking saga (Airam -> Smart Life "use the correct app" -> data center errors)
eventually resolved on the user's end and the cloud wizard succeeded - exact final
fix not narrated back, but the account-linking is a one-time step and is now done.

**Bug found and fixed in this app** (not a device issue): `lamps/tuya_device.py` was
passing `version` to `tinytuya.BulbDevice` as a **string** (`"3.3"`) instead of a
**float** (`3.3`), which silently broke `status()`/`set_colour()` even with a correct
`local_key` - while the wizard's own (correctly-typed) local poll worked fine with the
same key/IP moments earlier. Fixed by casting to `float()` in `_build()`. Also fixed
`tools/phase1_test.py` to print `status.last_error`, which had been silently swallowed.

## Confirmed facts

- The bulbs are Wi-Fi devices that join the home network directly (2.4 GHz, standard
  consumer smart-bulb pattern) - no Zigbee/hub required. This matches the product page
  and the app's pairing flow.
- Airam SmartHome, like the large majority of white-labelled "no-hub Wi-Fi RGB bulb"
  products sold in the EU/Nordics, is built on the **Tuya IoT platform**. Tuya licenses
  its chipsets/firmware and a white-label app shell ("Smart Life" / "Tuya Smart" clones)
  to many brands; Airam is one of them. This is a very strong pattern match, not a
  claim specific to Airam that we independently verified against Tuya's own device
  registry.
- Tuya devices of this class expose a **local LAN protocol** (the same protocol Tuya's
  own local integrations and the well-known `tinytuya` / Home Assistant "Tuya Local"
  projects use): a TCP connection on port 6668, encrypted with a per-device
  **local_key**, using one of protocol versions 3.1/3.3/3.4/3.5. `tinytuya` implements
  all of these and auto-negotiates.
- Tuya "smart bulb" (category `dj`) devices commonly implement one of a small number of
  datapoint (DP) layouts that `tinytuya`'s `BulbDevice` class already knows how to
  detect and speak (see below). This is a documented, tested piece of a widely used
  open-source library - not an invented schema.

## Assumptions (need verification on the physical bulbs)

- That the Airam bulbs actually respond to the Tuya local protocol on port 6668 at all
  (some newer Tuya SKUs ship "cloud-only"/BLE-mesh variants). **Verify with Phase 1.**
- That the bulbs use DP layout "Type B" (switch=20, mode=21, brightness=22,
  color_temp=23, colour=24), which is the most common layout for RGB+CCT Tuya bulbs
  sold in Europe since ~2020. `BulbDevice` auto-detects this from the live `status()`
  response, so the app does **not** hardcode this - it trusts whatever the device
  reports. Still, note it here as the expected outcome.
- That local_key extraction via the standard `tinytuya` cloud wizard works with an
  Airam-branded account. The wizard talks to the Tuya IoT Platform, which is shared
  infrastructure across white-label apps - linking your Airam SmartHome app account as
  a "Smart Life"-compatible account on the Tuya IoT Platform is expected to work the
  same way it does for other white-label apps, but this project has not independently
  confirmed it against an Airam account. **Verify during setup (see README).**
- That protocol version 3.3 or 3.4 is used (most 2021+ Tuya Wi-Fi bulbs). The scanner
  and setup tooling report the actual version; do not assume.

## CONFIRMED: Airam SmartHome cannot link directly via "Link Tuya App Account"

Tested against a real Airam SmartHome account: scanning the Tuya console's account-link
QR code directly with the Airam SmartHome app's own in-app scanner fails with
**"Use the correct app"**. This moves an earlier assumption to a confirmed fact:

- Airam SmartHome is a Tuya OEM/white-label app using an **independent account
  system** - its user accounts are not the same accounts as Tuya Smart/Smart Life, even
  when registered with an identical email+password (confirmed: registering that same
  email/password fresh in Smart Life succeeded with no "already exists" warning,
  producing an empty account with none of the Airam-paired bulbs).
- Tuya has, as policy, restricted the "Link Tuya App Account" QR flow to only the two
  official apps (Tuya Smart / Smart Life) for OEM apps built outside China - this is
  not something specific to Airam or something wrong with our setup.

**Working fallback: Device Sharing.** Tuya's standard app SDK includes a "Share
Device" feature in essentially every Tuya-based app, including white-label ones. Route:

1. In a **Smart Life** app account (any account, does not need to match Airam's
   credentials), keep it ready to receive a share.
2. In **Airam SmartHome**, open a bulb -> device settings ("..." or pencil icon) ->
   **Share Device** (or share the whole home/room at once, if offered) -> enter the
   Smart Life account's phone/email.
3. Accept the share in Smart Life.
4. Now run the Tuya console's "Link Tuya App Account" QR flow scanning with **Smart
   Life** (not Airam SmartHome) - this is an officially supported app, so the "use the
   correct app" block does not apply.
5. Re-run `tools/setup_wizard.py`.

Not yet confirmed: whether a *shared* (not owned) device exposes `local_key` through
this flow the same way an owned device does. If it doesn't, the next fallbacks are (a)
`localtuya`'s "generic Tuya OEM" cloud API account type, which logs in with the OEM
app's own credentials but requires extracting that app's embedded Tuya client
ID/secret from the Airam SmartHome APK (see
https://github.com/rospogrigio/localtuya/issues/1261), or (b) capturing `local_key`
directly off the LAN during the bulb's initial pairing handshake (packet capture), which
works regardless of any cloud-account limitation since it never depends on Tuya's cloud
at all.

## Known Tuya cloud console snag: "Code 28841107: data center is suspended"

Hit during the `tools/setup_wizard.py` cloud step (not a bug in this project - a Tuya
IoT Platform console issue many people hit): the wizard's cloud calls fail with
`Error from Tuya Cloud: Code 28841107: No permission. The data center is suspended.
Please go to the cloud development platform to enable the data center.`

Root cause: either (a) your Airam SmartHome app account was never linked to the Cloud
Development project, or (b) it was linked with the wrong data center selected (Tuya's
region-to-country mapping is not always intuitive - e.g. France/Belgium/Netherlands
fall under "Central Europe" rather than "Western Europe"; Finland's actual mapping was
not independently confirmed here).

Fix:
1. Tuya console -> Cloud -> Development -> [project] -> Devices tab -> "Link Tuya App
   Account" -> "Add App Account".
2. Before generating the QR code, clear any pre-selected data centers and select
   **exactly one**. Try `eu` (Central Europe) first; if linking/scanning still fails,
   redo it with only `eu-w` (Western Europe) selected instead.
3. Scan the QR with the Airam SmartHome app's own scan function.
4. Re-run the wizard using the **same region** you selected during linking.

If this never succeeds for the Airam account specifically, that would itself be a
useful data point for the "assumptions" section above - it would suggest Airam's app
account handling differs from typical Tuya white-label apps. A documented fallback:
Home Assistant's official Tuya integration performs the same account-link flow through
its own login UI and can be used purely to read out each device's local_key from its
device settings, without needing a separate Cloud Development project.

Sources: [Tuya support article on this exact error](https://support.tuya.com/en/help/_detail/Ke4dclb2w7y36),
[Home Assistant community thread with the same fix](https://community.home-assistant.io/t/solved-tuya-cant-link-devices-by-app-account-data-center-error/353200).

## Deliberately NOT used: the bulb's own onboard "scene" animation (DP 25)

The confirmed DP table includes `25: scene_data_v2` (Json) - a built-in, on-device
animation program (color/brightness/temperature "units" the bulb cycles through by
itself once triggered). This is almost certainly what the Airam SmartHome app's scene
picker writes to. Two reasons this project does not use it, by design, not oversight:

1. **On-wire encoding not confirmed.** The local poll in `tools/setup_wizard.py`
   returned it as a packed hex string (`'25': '000e0d0000000000000000c80000'`), not the
   literal JSON the cloud spec describes (the same situation as DP 24/colour_data_v2,
   which turned out to be a simple fixed `hhhhssssvvvv` hex format - but scene_data_v2
   encodes a variable-length list of "units" with per-unit mode/duration/color, a much
   more complex packing that has not been reverse-engineered here). Writing a guessed
   encoding would be exactly the "inventing undocumented datapoints" this project has
   avoided everywhere else.
2. **Even if decoded, it wouldn't solve the actual problem.** Each bulb runs its scene
   program on its own internal clock, starting from whenever it was individually
   triggered - there is no DP for "start now, in sync with these other 7 bulbs." This
   is exactly the power-cycling workaround the user was already fighting, and Wi-Fi
   smart plugs' own switch-on latency makes it unreliable regardless.

**The Ambient Scenes tab (manual app) solves the actual goal instead**: PC-driven
looping animations (`effects/ambient.py`) computed from one shared clock and pushed to
every selected lamp on the same network tick - synchronized by construction, using only
the already-confirmed DP 22/23/24 control path. No DP 25 involvement, no guessing.

## NEW, NOT YET confirmed: WHITE work_mode control (brightness + color temperature)

Added `LampDevice.set_white()` / `ensure_white_mode()` (`lamps/tuya_device.py`) for the
"Beat Sync White" mode and the manual app's White Balance/White Chase features. This
drives DP 22 (`bright_value_v2`) and DP 23 (`temp_value_v2`) via `work_mode="white"`
(DP 21) - the confirmed DP table already lists this DP layout (see above), but unlike
RGB color (verified via `tools/phase1_test.py`'s red/green/blue/white cycle), **the
specific tinytuya calls used here - `set_colourtemp_percentage()` and
`set_brightness_percentage()` - have not yet been run against the physical bulbs**.

What's assumed specifically:
- That `set_colourtemp_percentage()` internally switches work_mode to `"white"` itself
  (mirroring the observation that RGB mode has worked in this app without ever calling
  `ensure_colour_mode()` per-tick - `set_colour()` appears to bundle the mode switch).
  `ensure_white_mode()` is still called once per lamp before its first white command as
  a defensive fallback in case that assumption is wrong.
- That `temp_value_v2`'s 0-1000 range maps linearly warm(0)->cool(1000), which
  `set_colourtemp_percentage()`'s own 0-100% scaling should match directly.

**Before relying on this**, test it manually: open the manual control app
(`python manual_control.py`), go to the White Balance tab, select one lamp, and confirm
moving the color temperature slider visibly shifts it between warm and cool white with
Apply. Update this section with the result.

## Explicitly NOT assumed / NOT invented

- No datapoint IDs are hardcoded as "the Airam schema" anywhere in the lamp-control
  code. `airam_lights/lamps/tuya_device.py` always goes through `tinytuya.BulbDevice`,
  which reads the device's own `status()` response and adapts (type A / B / C). The
  diagnostics page in Phase 1/2 exists specifically to print out the *actual* DPs your
  bulbs return, so any mismatch is visible immediately instead of silently sending
  wrong commands.
- No cloud API calls happen during normal operation. The Tuya IoT Platform cloud API is
  used **only once**, offline from the visualizer, to extract each device's local_key
  during setup (this is how Tuya's own ecosystem is designed - the local_key itself is
  not discoverable purely from the LAN broadcast for security reasons). After that, all
  runtime traffic is local LAN only.

## How to fill in the "confirmed" column yourself

Run, in order:

1. `python tools/scan_devices.py` - confirms the bulbs answer the Tuya UDP broadcast on
   your LAN, and reports IP, device ID (`gwId`), and protocol version per bulb.
2. `python tools/setup_wizard.py` - one-time cloud step to pull local_keys via the Tuya
   IoT Platform, saved into `config/devices.json`.
3. `python tools/phase1_test.py --device "Lamp 1"` - connects locally (no cloud),
   prints the raw `status()` DP dictionary, detected bulb type (A/B/C), and lets you
   send a manual RGB/brightness/on-off test with measured latency.

Update the tables below after running these against your real bulbs.

| Item                     | Expected           | Actual (fill in) |
|--------------------------|---------------------|-------------------|
| Responds to UDP scan     | yes                 |                   |
| Local protocol version   | 3.3 or 3.4          |                   |
| Detected bulb type       | B (20/21/22/23/24)  |                   |
| Colour DP encoding       | hex "rrggbbhhhhssvv" or HSV16 |         |
| Typical command latency  | 20-80 ms on LAN     |                   |
| Max reliable update rate | ~10-20 Hz            |                   |
