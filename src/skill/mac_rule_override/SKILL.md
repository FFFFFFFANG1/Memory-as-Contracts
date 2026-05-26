---
name: mac_rule_override
description: Create a scoped MAC override edge after an action is blocked and the agent has explicit user approval or enough verified evidence to proceed.
---

# MAC Rule Override

Use this only after MAC blocks an action. Do not retry the blocked action first. Create the narrowest override edge that covers the approved action, then retry.

Command:

```bash
mac mac_rule_override RULE_ID \
  --scope-json '{"level":"project","workspace":"/workspace/project","repo":"project"}' \
  --lifecycle-json '{"type":"bounded_task"}' \
  --reason 'user approved this blocked action'
```

`scope-json` uses MAC `Scope`:
- `level`: one of `per_turn`, `task`, `session`, `component`, `project`, `repo`, `path`, `agent_family`, `organization`, `global`.
- Common fields: `workspace`, `repo`, `path_globs`, `task`, `component`, `agent_family`, `organization`, `user_id`.
- Prefer the narrowest valid scope. For file/folder overrides use `path` with `path_globs`; for one task use `task`; for current repo/project use `repo` or `project`.

`lifecycle-json` uses MAC `Lifecycle`:
- `type`: one of `immediate`, `bounded_time`, `bounded_session`, `bounded_task`, `until_revoked`, `conditional`, `review_after`.
- Common fields: `expires_at`, `until_revoked`, `trigger_event`, `review_after`, `original_text`.
- Prefer `bounded_task`, `bounded_session`, or `bounded_time`. Use `until_revoked` only when the user explicitly asks for a durable override.

Boundaries:
- This creates an `override` edge; it does not edit or delete the original rule.
- Do not create broad or permanent overrides without explicit user approval.
