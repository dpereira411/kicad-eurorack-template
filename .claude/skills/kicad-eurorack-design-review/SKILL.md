---
name: kicad-eurorack-design-review
description: Eurorack schematic design review. Use when asked to review, audit, or check the schematic; runs ERC, validates design spec, and checks manufacturing readiness.
metadata:
  short-description: Review KiCad schematic for ERC/design/mfg/risk
---

# kicad-eurorack-design-review

**Description:** Eurorack schematic design review. Use when asked to review, audit, or check the schematic — runs ERC, validates design spec, checks manufacturing readiness. Primary ERC tool: `bin/erc-fmt file.kicad_sch`. Structural data via `kicad-extract` when available.

---

## Workflow

### 1. ERC (always run first)

```bash
bin/erc file.kicad_sch               # full report
bin/erc file.kicad_sch --errors-only # triage

bin/erc-fmt file.kicad_sch               # human-readable full report
bin/erc-fmt file.kicad_sch --errors-only # human-readable triage
```

### 2. Structural analysis (when needed — component lists, net connectivity)

```bash
kicad-extract file.kicad_sch | jq '.components'
kicad-extract file.kicad_sch | jq '.nets'
```

Before running targeted jq filters, always verify shape (map vs array):

```bash
kicad-extract file.kicad_sch > /tmp/extract.json
jq '(.components|type), (.nets|type)' /tmp/extract.json
```

Accepted shapes:
- `.components`: `object` (keyed by reference) or `array` (entries with `ref`/`reference`)
- `.nets`: `object` (keyed by net name) or `array` (entries with `name`)

Use shape-safe iteration patterns:

```bash
# all references (object)
jq '.components | keys' /tmp/extract.json

# iterate components (object)
jq '.components | to_entries[] | {ref:.key, value:.value.value}' /tmp/extract.json

# iterate components (array)
jq '.components[] | {ref:(.ref // .reference), value:.value}' /tmp/extract.json

# direct access (object)
jq '.components["U5"].pins, .nets["5V"].nodes' /tmp/extract.json
```

Do not assume one shape blindly. First inspect type, then use the corresponding query pattern.

If `kicad-extract` is unavailable, state that and limit review to ERC + `spec.json` + BOM CSV.

### 2.1 Bypass capacitor audit (always run for `design` and `risk`)

Schematic-level decoupling checks only — placement proximity cannot be verified from the schematic and is a PCB review concern. Flag it as residual risk, not a finding.

**What the schematic can tell you:**
- Which supply rails each IC draws from (by finding `U*` power pins and their nets)
- Whether the cap count on each rail is ≥ the IC count drawing from that rail
- Whether cap values are appropriate (100nF ceramic for local bypass, 10–47µF bulk per rail)
- Whether bulk caps exist at all on each rail

**What it cannot tell you:**
- Whether a cap is physically close to a specific IC (requires PCB layout)
- Which cap "belongs to" which IC when multiple ICs share a rail

Checks per rail:
- Count ICs with a power pin on the rail.
- Count 100nF (or smaller) caps with one pin on that rail and the other on GND.
- Verify cap count ≥ IC count. If not, flag as `fail`.
- Verify at least one bulk cap (≥10µF) per active rail. If missing, flag as `fail`.
- Note cap values; flag anything other than X7R/C0G dielectric if discernible from value field.

Suggested commands:
```bash
kicad-extract file.kicad_sch > /tmp/extract.json
jq '.components' /tmp/extract.json
jq '.nets' /tmp/extract.json
```

When querying pins for any polarized component (diodes, electrolytic caps, MOSFETs), always include the `name` field alongside `net`:
```bash
# Always use this form for polarized components — never net-only
jq '.components | to_entries[] | select(.key | test("^D")) | {ref: .key, value: .value.value, pins: [.value.pins[] | {num: .num, name: .name, net: .net}]}' /tmp/extract.json
```
A net-only query (`.pins[].net`) discards pin name information that can resolve orientation unambiguously.

### 2.2 Analog integrity + power-source audit (always run for `design` and `risk`)

Run these checks even if ERC is clean:
- No DC return path / floating node where bias is required (for example AC-coupled input with no bias resistor).
- Op-amp inputs outside common-mode range for intended signals (when intent/spec ranges are available).
- Comparator inputs floating in default condition (when default behavior is specified).
- Reversed electrolytics / diodes / incorrect power pin connections.
- Power rail exists but has no source, or rails unintentionally shorted by net/symbol mistakes.
- Required pull-ups/pull-downs for analog IC mode pins (mute/enable/range) when default mode is specified.

If intent/range data is missing for a rule-dependent check, report it as `blocked` with missing evidence.

### 2.3 Current estimate (always run for `mfg`)

Provide an estimated rail current table (at minimum +12V, -12V if used, +5V if used/generated).

Minimum output:
- estimated current per rail in mA
- method used (datasheet typical vs worst-case vs placeholder)
- assumptions and unknowns

If a defensible estimate cannot be produced from available data, report as `blocked` and state what part current data is missing.

### 2.4 Default-bias margin audit (always run for `design` and `risk`)

Run deterministic default-state voltage analysis for every switched input jack.

Mandatory command:
```bash
kicad-extract file.kicad_sch > /tmp/extract.json
python3 .claude/skills/kicad-eurorack-design-review/scripts/default_bias_audit.py \
  --extract /tmp/extract.json \
  --thresholds family \
  --format table \
  --enforce hard
```

Required outputs:
- One row per switched jack with columns:
  - `input_jack_ref`
  - `receiver_pin`
  - `unpatched_path`
  - `computed_v_default`
  - `vih_min`
  - `vil_max`
  - `status`
- Status must be one of `pass` / `fail` / `blocked`.
- Any `fail` or `blocked` from this audit is a `design`/`risk` failure.

### 2.5 Simplification & redundancy audit (run when asked, or when ≥1 medium finding exists)

Scan for components that can be safely removed, combined, or downgraded. Output one row per finding.

**Checks:**

1. **Non-functional passives** — Identify diodes, resistors, or capacitors that carry no current and serve no function in the normal operating range. Typical example: a protection diode permanently reverse-biased because the protected rail is lower than the clamping rail. Verdict: `remove`.

2. **IC used in non-primary role** — Compare each IC's datasheet function against its actual use. Gate drivers (TC4427, UCC27xxx, MCP140x) used purely as logic output buffers are the most common mismatch. Power references (LM4040) used purely as pull-up rail targets are another. State the mismatch, the quiescent current overhead, and the direct replacement. Verdict: `replace`.

3. **IC consolidation** — Identify groups of identical small-package ICs (dual-gate SOT-363/SOT-23-6) performing the same logic function. If ≥3 instances exist and a single hex/octal IC covers the same gate count, name it. State exact IC count delta and Iq delta. Verdict: `consolidate`.

4. **Excess bulk capacitance** — Count bulk caps (≥1µF) per power rail. More than 2 per rail without a high-peak-current load (gate driver, motor driver, high-speed switching regulator) is worth flagging. Note: if TC4427 / similar gate drivers are present, higher bulk is justified (state the peak current spec). Verdict: `justified` or `reduce`.

5. **Ferrite bead topology** — For each ferrite bead, identify which side the IC VDD and decoupling cap are on. Correct topology: `supply → L → IC VDD → local cap → GND`. Incorrect: decoupling cap on supply side of the bead (IC sees bead impedance during transients). Verdict: `correct` / `wrong-side`.

**Required output:** One row per finding with columns `ref`, `finding`, `verdict`, `action`. At minimum, every `U*` should be checked against check 2; every ferrite bead against check 5.



Compare findings against `spec.json`. Required for `design`, `mfg`, and `risk` modes.

Validate spec.json is complete:
```bash
jq -e '.project.name and .project.goal and .design_intent and .constraints and .review_policy' spec.json
```

### 4. IC component review (run when asked to review component choices, or when ≥1 high/critical finding is IC-related)

For each IC in the design, evaluate fitness-for-purpose, availability, assembly difficulty, and whether a better alternative exists. Structure the review as one entry per IC family.

**For each IC, answer:**

1. **Right tool for the job?** Does the IC's primary function match how it is used here? Flag mismatches (e.g., a gate driver used as a signal buffer, a precision reference used for binary normalling).
2. **Quiescent current vs. load current:** State the IC's quiescent/idle current. If it is disproportionately large relative to the signal it drives, flag it.
3. **Package / assembly difficulty:** State the package. Flag anything below SOT-23-6 if hand assembly is expected. Note if fewer larger ICs would cover the same function.
4. **IC count efficiency:** If multiple instances of the same small IC perform the same function (e.g., four 2-gate inverters), identify whether a single multi-gate IC (hex, octal) would reduce BOM line count and placement count.
5. **Sourcing / alternates:** Note single-source risk. List one alternate part that is pin/function compatible.
6. **Verdict:** Keep / Replace / Consolidate / Remove. If Replace or Remove, name the specific alternative and justify it quantitatively (IC count delta, quiescent current delta, package class change).

**Required output format:**

- One section per IC or IC family (group identical parts together).
- A summary table at the end: Ref | Part | Verdict | Replacement.
- State the before/after IC count for the full design.

**Common patterns to flag:**

- MOSFET gate drivers (TC4427, UCC27xxx, MCP1401) used as signal output buffers → replace with CMOS buffer (74HC244, 74HC4050)
- Precision voltage references (LM4040, LM4041, REF02) used solely for logic-level normalling → remove, connect pull-ups to supply rail directly
- Multiple dual-gate ICs (74LVC2Gxx, 74AUP2Gxx) performing the same function → consolidate into hex/quad gate IC
- User Library diodes where pin 1/pin 2 Anode/Cathode assignment is ambiguous → replace with standard KiCad library equivalent
- LDOs with no approved alternate source → add one alternate in BOM notes

### 5. Design retrospective (run when asked "what would you do differently?" or when ≥1 high/critical finding exists)

After completing the standard review, answer the following for the design as found:

**Root cause analysis — for each high/critical finding:**
- What was the underlying decision or omission that created this finding?
- Was it a calculation error, a copy-paste from a prior design, a stale document, or a missing convention?

**Architectural alternatives — answer for each category that had a finding:**

1. **Normalling resistor values:** Calculate `V_default = V_ref × R_input / (R_pullup + R_input)` and verify margin against the *actual receiver VT+* (not nominal CMOS). State the minimum ratio `R_pullup / R_input` needed for reliable HIGH default given the receiver family.

2. **Diode polarity (User Library parts):** For any diode from a User Library (not the official KiCad library), state whether it should be replaced with a standard-library part and which one.

3. **Power rail ferrite topology:** For each ferrite bead, confirm whether ICs draw from the upstream (raw) side or downstream (filtered) side. If ICs are on the raw side, describe the correct wiring change.

4. **Normalling convention documentation:** Identify any jacks where the SW normalling direction (HIGH vs LOW) is ambiguous or inconsistently applied. Propose a net-naming or annotation convention that makes intent explicit.

5. **spec.json discipline:** Note any spec.json fields that are stale or placeholder. State what process would keep it accurate (e.g., "update spec.json in the same commit as any IC or power rail change").

6. **Reference designator / signal name alignment:** Flag any jack whose reference designator does not match its signal function, and describe the correction.

7. **Unresolved design items:** List any "TBD", "unknown purpose", or "incomplete" items that could have been resolved earlier. State what information was available in the schematic that made them resolvable.

**Output format:** One paragraph or bullet per category. Only include categories where a finding exists. End with a prioritized list: what to fix before fabrication, what to fix before next revision, what to document only.

---

## Modes

State which modes are being run at the start of every review.

| Mode | What it checks |
|------|----------------|
| `erc` | ERC violations via `bin/erc-fmt` — always run |
| `design` | Signal levels, IO expectations vs `spec.json` |
| `mfg` | BOM value consistency, production file presence |
| `risk` | Dangling pins, unplaced units, partial instantiation, jack default state verification |

Default: all four modes.

---

## Design-specific checks (always apply)

**Jack default states (`risk`):** For each input jack, trace its SW pin connection + pull resistor to determine the unpatched default. For Thonkiconn jacks, SW = Tip when unpatched, open when plugged. SW→GND + pull-up resistor sets the default level. Verify the voltage divider is clearly above or below the Schmitt threshold — equal series/pull resistors produce ~2.5V (unreliable).
**Diode orientation in User Library (`design`):** Always extract pin `name` fields (not just `net`) for every diode before drawing orientation conclusions. The `kicad-extract` lean-5 format includes `"name": "K"` / `"name": "A"` on pins when the symbol defines them. Use this query pattern:

```bash
jq '.components | to_entries[] | select(.key | test("^D")) | {ref: .key, value: .value.value, pins: [.value.pins[] | {num: .num, name: .name, net: .net}]}' /tmp/extract.json
```

If `name` is present and is "K"/"A" (or "Cathode"/"Anode"), orientation is **resolved** — report pass or fail deterministically. Only raise an orientation ambiguity finding if `name` is absent or non-descriptive (e.g., "1"/"2") for a polarized component from the User Library. Do not flag as ambiguous when the data is present and conclusive.

**Jack label vs signal routing (`design`):** Trace routed nets from named jacks to their logic destinations and verify they match the panel label. Flag any jack whose net routes to a destination that does not match the jack's label.

**Analog integrity (`design`/`risk`):** Explicitly apply the 2.2 checklist and include each item as pass/fail/blocked with evidence.

## Reporting rules

- Always include ERC error count in summary.
- Do not drop individual ERC errors — report each one.
- For `design`/`mfg`/`risk` modes, fail fast if `spec.json` is missing required keys.
- Distinguish `bin/erc-fmt` findings (deterministic, from kicad-cli) from inferred findings.
- Do not cite `.kicad_sch` file paths or line numbers in user-facing findings.
- Treat `.kicad_sch` as machine-oriented source; present evidence using human-readable identifiers instead (reference designators, pin names/numbers, and net names).
- Prefer `kicad-extract` output for structural citations (for example: `R36 pin 2 -> Net-(U5B-Q)`), and only mention raw schematic text parsing when a tool is unavailable.
- Include a **Decoupling Audit** section with one row per active supply rail, listing: rail name, IC count on rail, 100nF cap count, bulk cap count, and status (`pass` / `fail`).
- Cap count < IC count on any rail is a design finding (severity `high`).
- Missing bulk cap on any active rail is a design finding (severity `high`).
- Placement proximity is always residual risk — note it once, do not repeat per IC.
- Missing the **Decoupling Audit** section is an invalid review output.
- Include an **Analog Integrity Audit** section with one row per mandatory check from 2.2, status `pass` / `fail` / `blocked`, and concise evidence.
- Include a **Current Estimate** section with per-rail mA estimates and assumptions, or explicit blocker details.
- Include a **Default-State Margin Audit** section produced by `scripts/default_bias_audit.py`.
- In `family` threshold mode, missing receiver-family thresholds must be reported as `blocked` (not assumed pass).

---

## Reference files

- `references/domain-knowledge.md` — universal Eurorack rules (power, signal levels, input/output stages, op-amp rules, common failure modes). **Apply every rule in this file to every review** unless a finding is explicitly suppressed in `spec.json`.
- `references/intent-schema.md` — intent/spec structure and required keys
- `references/schema.md` — `kicad-extract` JSON output field paths
