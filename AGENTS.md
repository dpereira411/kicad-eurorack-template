# AGENTS.md

## Skill execution policy

- Skills are located under `.claude/skills`.
- When a user request matches a skill trigger (explicitly named or clearly implied by scope), that skill must be used.
- All **required workflow steps** defined by the skill are mandatory.
- All **required final outputs/sections/artifacts** defined by the skill are mandatory.
- A response is **invalid** if any mandatory skill step or mandatory skill output is missing.
- If a mandatory step cannot be completed, do not finalize conclusions. Report the blocker explicitly and what evidence is still missing.
- Do not silently skip skill requirements, even if partial findings are available.

## Verification requirement

- Before finalizing, explicitly verify completion of the invoked skill's mandatory requirements.
- Include concise evidence references (commands, files, refs/nets/lines, or equivalent) for required outputs.

## Skill directories

## Project info reading policy

- When reading project information, default to the `kicad-extract` CLI first.

## Managing TODO.md

- Add every newly identified problem to `TODO.md`.
- Remove a problem from `TODO.md` once it is resolved.
- Record problems marked `ignore` in `TODO.md` so they can be skipped in future work.
- Running `kicad-extract --schema` will output the output schema.
