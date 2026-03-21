# Eurorack KiCad template — task runner
# Usage: just <recipe>  (override schematic with: just SCH=mymodule.kicad_sch erc)

SCH := `ls *.kicad_sch 2>/dev/null | head -1`
EXTRACT := "/tmp/extract.json"
BIAS_SCRIPT := ".claude/skills/kicad-eurorack-design-review/scripts/default_bias_audit.py"

# List available recipes
default:
    @just --list

# Run ERC and show human-readable report
erc:
    bin/erc-fmt {{ SCH }}

# Run ERC, errors only
erc-errors:
    bin/erc-fmt {{ SCH }} --errors-only

# Run kicad-extract and cache output to /tmp/extract.json
extract:
    kicad-extract {{ SCH }} > {{ EXTRACT }}
    @echo "Extracted to {{ EXTRACT }}"

# Run default-bias margin audit on switched input jacks
bias: extract
    python3 {{ BIAS_SCRIPT }} \
        --extract {{ EXTRACT }} \
        --thresholds family \
        --format table \
        --enforce hard

# Validate spec.json has all required keys
validate-spec:
    jq -e '.project.name and .project.goal and .design_intent and .constraints and .review_policy' spec.json \
        && echo "spec.json OK"

# Run all deterministic checks (ERC + bias audit + spec validation)
check: validate-spec erc bias
