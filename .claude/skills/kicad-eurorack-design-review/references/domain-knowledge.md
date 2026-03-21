# Eurorack Analog Module — Skill Domain Knowledge

This is the list of rules, conventions, and checks that apply to **every** Eurorack analog module.
These should be encoded in the skill prompt, not in per-project `spec.json`.

---

## Eurorack Power Conventions

- Power bus provides +12V, -12V, and 0V (ground)
- Some buses provide +5V on pin 16 of 16-pin headers; never assume it's available
- Standard power connector: 2x5 pin shrouded header (10-pin), keyed
- 16-pin variant adds +5V, CV, and gate bus lines
- Pin 1 must be marked on silkscreen; reversed cable is a common failure
- Typical module current draw: 20–80mA per rail; anything above 150mA is unusual

## Power Protection Rules (always check)

- Reverse polarity protection is expected (series diode, MOSFET, or ideal diode)
- Rail filtering from bus noise: ferrite bead or RC filter on each power rail
- Decoupling: 100nF ceramic per IC, placed within 10mm, plus one bulk cap (10–47µF) per rail
- Bulk caps: minimum voltage rating 16V for ±12V rails, 25V preferred
- Ceramic caps: X7R or C0G dielectric; avoid Y5V on signal or decoupling paths

## Signal Level Conventions

| Domain | Typical Range       | Notes                                    |
|--------|---------------------|------------------------------------------|
| Audio  | ±5V (10Vpp)         | Can exceed ±10V from hot modules         |
| CV     | 0V to +10V          | Sometimes -5V to +5V (bipolar)           |
| Gate   | 0V (low), +5V (high)| Threshold ~+2.5V; some modules use +10V  |
| Trigger| 0V to +5V pulse     | Short pulse, <10ms typical               |

## Input Stage Rules (always check)

- Input impedance: minimum 50kΩ, target 100kΩ for audio and CV
- Protection against overvoltage: series resistor (1kΩ–100kΩ) and/or clamp diodes to rails
- CMOS/logic inputs must never float; pull-down or pull-up required when unpatched
- Switched jacks: verify normalled connection provides a defined default state
- AC-coupled inputs: ensure DC bias path exists downstream (resistor to ground or to virtual ground)

## Output Stage Rules (always check)

- Output impedance: should be under 1kΩ, typically 220Ω–1kΩ series resistor at output
- Must tolerate continuous short to ground (patch cable accidents)
- Op-amp outputs driving cables: series resistor (47–220Ω) for stability with capacitive loads
- If output can exceed ±10V, note it — downstream modules may clip or be damaged

## Op-Amp Rules (always check)

- Every op-amp input must have a DC path to a defined voltage (no floating inputs after coupling caps)
- Check common-mode input range against actual signal levels at input pins
- Check output swing against rail voltages (most op-amps don't swing rail-to-rail on ±12V)
- Feedback network: verify stability (no capacitive loads without isolation resistor)
- Unused op-amp sections: non-inverting to ground, output to inverting (voltage follower)

## Passive Component Defaults

- Resistors: 0603 or 0805, 1% metal film, 0.1W minimum
- Ceramic caps: 0603 or 0805, X7R for general, C0G for precision/audio path
- Electrolytics: minimum 16V rating, 25V preferred, mind temperature rating
- Standard op-amps: TL072, TL074, NE5532, OPA1678 (check if design needs rail-to-rail)

## LED Indicators

- Drive current: 1–5mA typical (modern LEDs are bright at 2mA)
- Series resistor from logic or buffered output, not directly from IC output pin
- Check that LED current doesn't load the signal being indicated

## PCB / Mechanical (for layout review, not schematic)

- Mounting holes: M3, at least 2, grounded or isolated depending on panel design
- Panel jacks: 3.5mm mono TS, typical footprint is Thonkiconn PJ398SM or equivalent
- Silkscreen: jack labels readable, component values visible, pin 1 on power header marked
- Courtyard clearance: pots and jacks need physical clearance behind panel
- Board depth must fit within module depth constraint

## Test Points (always check)

- +12V, -12V, and 0V test points required at minimum
- Key signal nodes (filter cutoff CV, VCA control voltage) recommended
- Programming/debug headers if any digital ICs are present

## Common Failure Modes to Flag

- Reversed power connector with no protection → dead ICs
- Output op-amp directly driving cable with no series resistor → oscillation
- AC-coupled input with no DC bias path → input floats to rail, DC offset at output
- LED driven directly from CMOS output → excessive current, logic level drops
- Switched jack normalling wired backwards → signal present when unpatched, absent when patched
- Missing bulk decoupling → audio-rate ripple on power rail
- Op-amp input exceeding common-mode range → output latches to rail
- Pull-down missing on gate/trigger input → erratic behavior when unpatched
