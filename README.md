# kicad-eurorack-template

A starting point for Eurorack module schematics in KiCad. Includes a pre-wired power section, AI-assisted design review skills, and a task runner for common checks.

## Prerequisites

| Tool | Install |
|---|---|
| [KiCad](https://www.kicad.org/download/) | Required for schematic editing |
| [kicad-cli](https://docs.kicad.org/8.0/en/cli/cli.html) | Bundled with KiCad — ensure it's on your `PATH` |
| [kicad-extract](https://github.com/your-org/kicad-extract) | `pip install kicad-extract` |
| [just](https://just.systems) | `brew install just` |
| [copier](https://copier.readthedocs.io) | `pip install copier` |
| [Claude Code](https://claude.ai/code) | For AI-assisted design review |

## Creating a new module

```bash
copier copy gh:your-org/kicad-eurorack-template my-module
cd my-module
```

Copier will ask:
- **Module name** — used for filenames, no spaces (e.g. `vco_core`, `dual_vca`)
- **Description** — one-line summary of what the module does
- **HP** — width in HP (default: 8)
- **Max depth** — maximum depth in mm (default: 25)

This generates a KiCad project pre-wired with the Eurorack power section and a `spec.json` pre-filled with your answers.

## First steps after generating

1. Open `<project_name>.kicad_sch` in KiCad
2. Fill in the title block (right-click the sheet border → Properties)
3. Complete `spec.json` — add your IO list, signal domains, key ICs, and concerns
4. Run `just check` to verify the power section passes ERC

## Project structure

```
<project_name>.kicad_sch   Schematic — your design work, never overwritten on update
<project_name>.kicad_pcb   PCB layout — your design work, never overwritten on update
<project_name>.kicad_pro   KiCad project file
spec.json                  Module specification (name, IO, ICs, constraints)
justfile                   Task runner
TODO.md                    Track open problems found during review
bin/erc                    ERC runner (JSON output)
bin/erc-fmt                ERC runner (human-readable output)
.claude/skills/            AI-assisted review and net-naming skills
```

## Tasks

```bash
just check          # Run all deterministic checks: spec validation + ERC + bias audit
just erc            # ERC full report
just erc-errors     # ERC errors only
just extract        # Run kicad-extract, cache to /tmp/extract.json
just bias           # Default-bias margin audit on switched input jacks
just validate-spec  # Verify spec.json has all required keys
```

Override the schematic file if needed:
```bash
just SCH=mymodule.kicad_sch erc
```

## AI-assisted design review

With Claude Code, ask:

```
review the schematic
```

The `kicad-eurorack-design-review` skill runs automatically and covers:
- ERC violations
- Signal levels and IO vs `spec.json`
- Decoupling cap count per rail
- Default-state margin on switched input jacks
- BOM consistency and production file presence
- Dangling pins and unplaced units

To rename auto-generated nets:
```
name the nets
```

## Updating the template

When the template improves (better skills, updated tooling, new checks):

```bash
copier update
```

Framework files (`justfile`, `spec.json`, skills, `bin/`) are updated. Your schematic and PCB are never touched.

## spec.json

Fill this in before running a design review. Required keys:

| Key | Description |
|---|---|
| `project.name` | Module name |
| `project.goal` | One-line description |
| `design_intent` | Signal levels, IO expectations, functional behavior |
| `constraints` | Power rails, manufacturing, safety rules |
| `review_policy` | Which review modes to run, severity threshold |

Validate it any time:
```bash
just validate-spec
```
