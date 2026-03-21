# kicad-extract Output Schema

Use this file when querying `kicad-extract` JSON output to avoid guessing field paths.

## Top-level keys

- `.meta`: Extraction metadata (project/tool/version/sheet root).
- `.components`: Usually object keyed by reference designator (`"U1"`, `"R32"`, etc), but some extractor versions may emit an array.
- `.nets`: Usually object keyed by net name, but some extractor versions may emit an array.
- `.libraries`: Pin-type info for library parts.

## Shape sanity check (run first)

```bash
kicad-extract TrigHold.kicad_sch > /tmp/extract.json
jq '(.components|type), (.nets|type)' /tmp/extract.json
```

Expected:
- `.components` => `"object"` or `"array"`
- `.nets` => `"object"` or `"array"`

If either is neither object nor array, stop and inspect extractor version/output before writing jq filters.

## Component paths

- `.components["U12"].lib`
- `.components["U12"].value`
- `.components["U12"].footprint`
- `.components["U12"].pins` (object keyed by pin number)
- `.components["U12"].pins["7"].net`

## Net paths

- `.nets["5V"].class`
- `.nets["5V"].nodes[]` (strings like `"U1:5"`)

## Common queries

Component list:

```bash
kicad-extract TrigHold.kicad_sch | jq '
  if (.components|type)=="object" then .components|keys
  elif (.components|type)=="array" then [.components[]|(.ref // .reference)]
  else error("Unsupported .components shape")
  end
'
```

Shape-safe component iteration:

```bash
kicad-extract TrigHold.kicad_sch \
  | jq '
    if (.components|type)=="object" then
      .components | to_entries[] | {ref:.key, value:.value.value}
    elif (.components|type)=="array" then
      .components[] | {ref:(.ref // .reference), value:.value}
    else
      error("Unsupported .components shape")
    end
  '
```

Components with empty/absent pin maps:

```bash
kicad-extract TrigHold.kicad_sch \
  | jq -r '.components | to_entries[] | select((.value.pins // {}) | length == 0) | .key'
```

Nets connected to a specific ref (example `U12`):

```bash
kicad-extract TrigHold.kicad_sch \
  | jq '.components["U12"].pins | to_entries[] | {pin: .key, net: .value.net}'
```

## Notes

- `kicad-extract --full` is additive: default data remains and extra fields are appended.
- Prefer checking for key existence defensively (e.g. `.components["U1"]?`).
- ERC is handled by `bin/erc-fmt`, not `kicad-extract`.
- Do not hardcode a single shape for `.components`/`.nets`; inspect with `type` first.
