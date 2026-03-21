# Intent Schema

Path: `spec.json` at project root by default.

Required keys for intent-based modes (`design`, `mfg`, `risk`):

- `.project.name`
- `.project.goal`
- `.design_intent`
- `.constraints`
- `.review_policy`

Recommended structure:

```json
{
  "schema_version": "1.0",
  "project": {
    "name": "My Module",
    "goal": "..."
  },
  "design_intent": {
    "functional_behavior": [],
    "signal_levels": {
      "logic_high_min_v": 2.0,
      "logic_low_max_v": 0.8,
      "target_output_high_v": 5.0
    },
    "io_expectations": {
      "input_type": "eurorack_gate_trigger",
      "output_type": "buffered_gate_trigger"
    }
  },
  "constraints": {
    "power": {
      "supply_rails": ["+12V", "GND"],
      "logic_rail_v": 5.0
    },
    "manufacturing": {
      "assembler": "JLCPCB",
      "allow_dnp": true
    },
    "safety": {
      "must_have_output_series_resistor_ohm_min": 100
    }
  },
  "review_policy": {
    "strict_intent_validation": true,
    "mode_defaults": ["erc", "design", "mfg", "risk"],
    "severity_threshold": "warning"
  }
}
```

Validation command:

```bash
jq -e '.project.name and .project.goal and .design_intent and .constraints and .review_policy' spec.json
```
