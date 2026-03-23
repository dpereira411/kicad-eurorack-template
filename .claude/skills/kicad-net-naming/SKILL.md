# Skill: kicad-net-naming

**Trigger:** user asks to "suggest net names", "name nets", "audit net names", "rename nets", or similar.

## Workflow

1. Run extraction if not already fresh:
   ```bash
   kicad-extract *.kicad_sch > /tmp/extract.json
   ```

   If `kicad-extract` is unavailable, use `kiutils` instead:
   ```bash
   kiutils schematic inspect *.kicad_sch --json > /tmp/kiutils_inspect.json
   ```
   The inspect output includes symbol instances and net labels; use it as a substitute for net/component enumeration.

2. Dump all nets with node lists:
   ```bash
   jq '.nets | to_entries[] | {net: .key, nodes: [.value.nodes[]]}' /tmp/extract.json
   ```

   For targeted lookup of a single net's connectivity (e.g. to identify connected nodes before naming):
   ```bash
   kiutils schematic query_net *.kicad_sch "Net-(R3-Pad1)" --json
   ```

3. Classify each net:
   - **Named** — does not match `Net-(...)` pattern → validate against convention, suggest correction only if it violates the rules
   - **Auto-generated** — matches `Net-(REF-PadN)` or `Net-(REF-SIGNAME)` → must be renamed; trace nodes to infer function

4. For each auto-generated net, apply the decision tree below to produce a suggested name.

5. Output a rename table (Section 1) and KiCad application instructions (Section 2).

---

## Naming Convention (rules, in priority order)

| Category | Pattern | Example |
|---|---|---|
| Raw bus pin | `{RAIL}_BUS` | `12V_BUS` (power header pin before protection) |
| Post-protection rail | `{RAIL}_PROT` | `12V_PROT` (after reverse-polarity MOSFET/diode) |
| Filtered sub-rail (post-ferrite) | `{RAIL}_FILT_{LETTER}` | `5V_FILT_A`, `5V_FILT_B` |
| Jack tip (raw signal) | `{SIG}_{UNIT}_IN` | `CLK_A_IN`, `CV_B_IN` |
| Jack SW/normalling node | `{SIG}_{UNIT}_SW` | `CV_A_SW`, `GATE_B_SW` |
| Post-clamp conditioned input | `{SIG}_{UNIT}_COND` | `CLK_A_COND`, `CV_B_COND` |
| Logic signal (global label) | `/{SIG}_{UNIT}_LOGIC` | `/CLK_A_LOGIC`, `/GATE_B_LOGIC` |
| IC output (internal) | `/{SIG}_{UNIT}` | `/Q_A`, `/NQ_A` |
| Buffered driver output (pre-jack) | `{SIG}_{UNIT}_DRV` | `Q_A_DRV`, `CV_B_DRV` |
| Thru/buffered-invert output | `{SIG}_{UNIT}_THRU` | `IN_A_THRU`, `INV_B_THRU` |
| LED anode node | `{SIG}_{UNIT}_LED` | `Q_A_LED`, `GATE_B_LED` |

**Rules:**
- Power rail names: no `/` prefix, UPPERCASE (matches existing `5V`, `12V`, `GND`)
- Signal nets that cross sheets: use KiCad global label syntax (`/NAME`)
- Internal single-sheet nets that don't cross hierarchy: no `/` prefix
- Never rename a net that already has a human-chosen name unless it violates the convention

---

## Decision Tree for Auto-Generated Nets

Identify by inspecting which component types appear in the node list:

- Nodes include a power header pin (J* with Eurorack pinout) → `{RAIL}_BUS`
- Nodes include a protection MOSFET/diode drain/cathode and no other active component → `{RAIL}_PROT`
- Nodes include a ferrite bead pin + bulk capacitor → `{RAIL}_FILT_{LETTER}`
- Nodes include a jack SW pin + pull resistor → `{SIG}_{UNIT}_SW`
- Nodes include a jack tip pin + input series resistor → `{SIG}_{UNIT}_IN`
- Nodes include a clamp diode output + receiver IC input → `{SIG}_{UNIT}_COND`
- Nodes include an IC output pin + buffer input → classify by IC pin name (`Q`, `~Q`, `CLK`, etc.) → `/{SIG}_{UNIT}`
- Nodes include an output series resistor + IC output → `{SIG}_{UNIT}_DRV`
- Nodes include an LED anode → `{SIG}_{UNIT}_LED`
- Nodes include a jack tip pin on an output jack → `{SIG}_{UNIT}_OUT`

When a net's function is ambiguous, report it as `unclear` in the rename table with the node list and let the user decide.

---

## Output Format

### Section 1: Rename Table

| Current net name | Suggested name | Category | Connected nodes | Rationale |
|---|---|---|---|---|
| Net-(C3-Pad1) | 12V_FILT_A | filtered-rail | C3:1, C1:1, L1:2 | Post-ferrite filtered +12V sub-rail |
| ... | ... | ... | ... | ... |

Sort rows by category: power first, then signal inputs, then logic, then outputs.

### Section 2: KiCad Application Instructions

1. Open the schematic in KiCad.
2. Open Net Inspector: **Inspect → Net Inspector**. Find the auto-generated net, right-click → Highlight to locate it on the canvas.
3. Place a **Net Label** (shortcut `L`) on any wire in that net with the new name.
   - For nets that need to be referenceable across the design, place a **Global Label** (`/NAME`) instead.
4. After all renames, re-run extraction and verify:
   ```bash
   kicad-extract *.kicad_sch > /tmp/extract_renamed.json
   jq '.nets | keys | map(select(startswith("Net-")))' /tmp/extract_renamed.json
   # Should return: []
   ```
5. Re-run ERC to confirm no new unconnected net errors:
   ```bash
   bin/erc-fmt *.kicad_sch --errors-only
   ```
   Error count must not increase.

---

## Verification Checklist

After applying all renames in KiCad:

```bash
# Re-extract
kicad-extract *.kicad_sch > /tmp/extract_renamed.json

# Confirm no auto-generated names remain
jq '.nets | keys | map(select(startswith("Net-")))' /tmp/extract_renamed.json
# Expected: []

# Run ERC — error count must not increase
bin/erc-fmt *.kicad_sch --errors-only
```
