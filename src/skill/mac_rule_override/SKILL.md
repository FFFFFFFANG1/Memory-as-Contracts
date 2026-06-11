---
name: mac_rule_override
description: Create a narrow scoped MAC override edge for one blocked action when you have strong evidence that the block is wrong and the current action is legitimate.
---

# MAC Rule Override

Use this only after MAC blocks an action and you have a strong, specific reason to believe the block is not justified. In other words, you are confident that the current action is legitimate, within the user's intent, and should be allowed despite the matched rule.

This is for overriding one wrongly blocked action, not for normal `ask` handling. If MAC returned `ask`, follow the AskRequest / Ask Response Flag flow instead of creating an override edge.

Do not retry the blocked action first. Create the narrowest override edge that covers this action, then retry once.

Command:

```bash
mac mac_rule_override RULE_ID \
  --scope-json '{"level":"project","workspace":"/workspace/project","repo":"project"}' \
  --lifecycle-json '{"type":"bounded_task"}' \
  --reason 'block is not justified because this action is legal for the current task'
```

`scope-json` uses MAC `Scope`:
- `level`: one of `per_turn`, `task`, `session`, `component`, `project`, `repo`, `path`, `agent_family`, `organization`, `global`.
- Common fields: `workspace`, `repo`, `path_globs`, `task`, `component`, `agent_family`, `organization`, `user_id`.
- Prefer the narrowest valid scope that covers only the blocked action. For file/folder overrides use `path` with `path_globs`; for one task use `task`; for current repo/project use `repo` or `project` only when a narrower scope would not cover the legitimate action.

`lifecycle-json` uses MAC `Lifecycle`:
- `type`: one of `immediate`, `bounded_time`, `bounded_session`, `bounded_task`, `until_revoked`, `conditional`, `review_after`.
- Common fields: `expires_at`, `until_revoked`, `trigger_event`, `review_after`, `original_text`.
- Prefer `bounded_task`, `bounded_session`, or a short `bounded_time`. Use `until_revoked` only when the user explicitly asks for a durable override.

Boundaries:
- This creates an `override` edge; it does not edit or delete the original rule.
- Only use it when the action is already blocked and you can explain why that block is a false positive.
- Do not use it to bypass uncertainty, convenience, missing context, or a legitimate hard rule.
- Do not create broad or permanent overrides without explicit user approval.
