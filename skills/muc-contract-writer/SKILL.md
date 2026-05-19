---
name: muc-contract-writer
description: Use when the user states a durable Memory Use Contract for a project, folder, file, or session, especially rules like always/never/must/do not/default for coding-agent actions. Writes explicit contracts through the local `muc` CLI and avoids recording ordinary per-task style requests.
---

# MUC Contract Writer

Use this skill when a user gives an explicit, durable rule that should constrain future tool use.

At the start of a relevant turn, refresh project instruction sources asynchronously:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync muc refresh-instructions --root . --adapter all --background
```

Do not wait for the refresh unless the user asks for refresh results.

## Write A Contract

Use `muc add-contract` when the instruction is scoped to one of:

- project/repo: "in this repo", "for this project", "default here", "always", "never";
- folder: a folder path or glob such as `src/**`, `docs/**`;
- file: a concrete path such as `src/api.py`;
- session: "for this session", "in this conversation", "until I say otherwise".

Template:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync muc add-contract \
  --text "<verbatim user rule>" \
  --type prohibition|requirement|procedure|preference|exception|fact \
  --modality MUST|MUST_NOT|SHOULD|MAY \
  --strength hard|soft|suggestive \
  --confirmation not_required|required|required_to_override \
  --scope project|folder|file|session \
  --workspace default \
  --action-class edit_file
```

Add `--path "<glob>"` for file or folder scoped rules. Use multiple `--action-class`
flags when needed.

Common mappings:

- "do not/never" -> `--type prohibition --modality MUST_NOT --strength hard`;
- "must/always/default command" -> `--type requirement` or `procedure`, `--modality MUST`;
- "prefer/should" -> `--type preference --modality SHOULD --strength soft`;
- "ask before" -> add `--confirmation required`;
- "unless explicitly asked" -> use `--confirmation required_to_override`.

## Do Not Write

Skip `muc add-contract` for ordinary per-task or per-round requests:

- "帮我写 xxx，清晰一点";
- "这次回答短一点";
- "先看一下这个 bug";
- "这轮别解释太多";
- vague preferences without future scope.

If the scope or durability is ambiguous, ask one concise clarification or treat it
as task-local and do not write a contract.
