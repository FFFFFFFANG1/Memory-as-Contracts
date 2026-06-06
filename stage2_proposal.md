# Stage 2 Proposal: Event-Sourced Validator Runtime for MAC v4

## 1. 背景与目标

当前 MAC 已经完成了没有 validator snippet 的版本：系统可以从用户输入或项目文档中抽取 rule，并在 action gate 阶段根据 rule 的 scope、lifecycle、tool pattern 和 target pattern 判断当前 action 是否应该被 allow / block / confirm / revise。

这个版本适合处理 direct rule，例如：

```text
Do not edit generated/**.
Do not run git push.
Use uv instead of pip.
```

但它不能自然处理依赖历史状态的 rule，例如：

```text
Before git push, run tests.
Total cost must not exceed $90.
Do not send more than one follow-up email to the same customer per day.
```

这些 rule 的合法性不能只通过当前 action 判断，而需要知道 agent 之前做过什么。因此 MAC v4 需要引入 **action log + persistent rule state + restricted validator snippet**。

核心目标是：

> 把 memory-as-contract 从 “rule matching” 升级成 “event-sourced runtime validation”。

也就是说，rule 不只是被匹配，而是可以维护自己的运行时状态，并在未来 action 发生前进行低延迟检查。

---

## 2. 核心设计原则

### 2.1 Action log 是事实源

MAC 不直接信任 agent 的 hidden reasoning，也不把 validator 的内部变量当作事实源。

真正的事实源是 agent 运行过程中被 post-action hook 记录下来的 structured raw action log。
Action log 只记录已经实际执行并产生 tool result 的 committed tool action；被
pre-action gate 拒绝、撤回或尚未执行的 proposed action 不进入 action log。

这个 log 可以采用类似 nanobot 的格式：

```text
assistant tool call
tool result
timestamp
optional reasoning content
```

比如:
```text
{"name": "edit_file", "arguments": "{\"new_text\": \"## User Information\\n\\n- **Health status**: Generally good, no active chronic conditions\\n- **Focus areas**: Prevention — weight stability, sleep quality, physical fitness, long-term cardiovascular health\\n- **Stress management**: Regular physical exercise + weekend email detox to prevent work bleed\\n- **Allergies**: Seasonal pollen allergy\\n\\n## Past Medical History\\n\\n- **Appendectomy**: Laparoscopic emergency surgery at age 22 for acute appendicitis. Full recovery with no complications.\\n\\n## Preferences\", \"old_text\": \"## User Information\\n\\n- **Health status**: Generally good, no active chronic conditions\\n- **Focus areas**: Prevention — weight stability, sleep quality, physical fitness, long-term cardiovascular health\\n- **Stress management**: Regular physical exercise + weekend email detox to prevent work bleed\\n- **Allergies**: Seasonal pollen allergy\\n\\n## Preferences\", \"path\": \"/Users/fang/.nanobot/workspace/memory/MEMORY.md\"}"}}], "reasoning_content": "The user is sharing their past medical history - a laparoscopic appendectomy at age 22. I should save this to their memory file.\n", "timestamp": "2026-01-05T12:00:00+08:00"} {"role": "tool", "tool_call_id": "call_function_myq1wo08q80a_1", "name": "edit_file", "content": "Warning: file has not been read yet. Read it first to verify content before editing.\nSuccessfully edited /Users/fang/.nanobot/workspace/memory/MEMORY.md", "timestamp": "2026-01-05T12:00:00+08:00"} {"role": "assistant", "content": "Added. Clean history — full recovery with no complications. I'll keep it in your profile.", "reasoning_content": "Done.\n", "timestamp": "2026-01-05T12:00:00+08:00"}
```

但 MAC 不依赖 nanobot 本身。MAC 只要求 host adapter 在 post-action 阶段提供
统一的 committed tool action log entry。pre-action 阶段仍会提供 pending action
给 gate / validator.check，但 pending action 不是 action log entry，除非它后来
真实执行并在 post-action 阶段完成记录。

### 2.2 State 是从 action log 派生出来的持久化视图

state 必须存在，并且必须持久化。

但是 state 不是新的事实源。它只是为了低延迟 validation 而维护的 materialized view。

换句话说：

```text
action log = source of truth
rule state = derived runtime cache
validator = state transition and checking logic
```

如果 state 出错，理论上可以通过 replay action log 重建。

### 2.3 Validator snippet 不保存状态

validator snippet 不能像 global variable 一样保存当前状态。

错误设计：

```text
validator implementation contains:
  dirty = false
  test_ran = false
```

正确设计：

```text
validator snippet contains:
  update(state, entry, log, context)
  check(action, state, log, context)
```

当前 state 的值由 MAC runtime 持久化维护，而不是由脚本自身保存。

### 2.4 Runtime 不依赖 LLM

action-time 不能再调用 LLM。

LLM 可以用于 rule extraction 或 validator snippet generation，但它们发生在
rule 安装阶段，不发生在每次 action gate 阶段。

action-time 只允许做：

```text
load applicable rules
load rule states
run verified local validator snippet
aggregate verdict
write receipt
```

---

## 3. 系统分层

Stage 2 / MAC v4 可以理解为五层。

### Layer 1：Raw Action Log

这是最低层事实记录。

它记录 agent 和环境之间已经真实发生的 tool action，例如：

```text
assistant tool call
tool result
timestamp
raw tool arguments
raw tool output
tool_call_id
optional reasoning content
```

它可以保留 reasoning content，但 validator 不应该依赖 reasoning content。

reasoning content 可以用于 debug、replay、analysis，但不能作为 enforcement evidence。

validator 可依赖的是：

```text
committed tool calls
committed tool results
timestamps
raw action arguments
raw tool outputs
```

validator 不应依赖：

```text
hidden reasoning
agent 自称已经做过的事情
没有被 tool call 或 tool result 证明的内部计划
被 gate 拒绝或用户撤回、但没有实际执行的 proposed action
```

#### ActionLogEntryV1

Stage 2 需要定义一个 canonical committed-action envelope。物理 SQLite schema
可以变化，但 runtime、validator 和 replay 看到的是 `ActionLogEntryV1`：

```text
seq:
  MAC action log store 内单调递增的 commit order。

timestamp:
  post-action hook 观察到该 committed action 的时间；必须带 timezone。

session_id / task_id / agent_id / adapter_id:
  用于 scope、replay 和去重。

tool_call_id:
  host agent 提供的 tool call id；如果 host 没有提供，adapter 必须生成稳定 id。

tool_name:
  native tool name，例如 Bash、Edit、purchase。

host_action:
  semantic action，例如 exec、file.write、purchase。

arguments:
  tool call arguments，尽量保存为 JSON-compatible value；无法解析时保存 raw text。

result:
  parsed tool result，尽量保存为 JSON-compatible value；无法解析时为 null。

result_text:
  raw tool result text。

outcome:
  success / failure / unknown。

reasoning_text:
  optional audit/debug metadata；不能作为 enforcement evidence。
```

Action log append 必须幂等。推荐去重键是：

```text
adapter_id + session_id + tool_call_id
```

如果 host 允许同一个 `tool_call_id` 多次提交不同结果，adapter 必须把 attempt
信息纳入合成 id；否则 replay 会出现重复计数。

---

### Layer 2：Rule / Contract

rule 仍然是 MAC 的基本 memory unit。

每条 rule 表示一个用户或项目来源的 behavioral contract，例如：

```text
Do not edit generated files.
Before git push, run tests.
Keep total booking cost under $90.
Ask before sending external emails.
```

rule 继续拥有：

```text
source evidence
scope
lifecycle
authority
effect
kind
conflict / exception / supersession relation
```

这些逻辑沿用当前 MAC v3 的 contract model。

MAC v4 不改变 rule 的基本语义，而是在 rule 上增加一种新的 enforcement mechanism：validator runtime。

---

### Layer 3：Rule State

每条需要历史判断的 rule 可以拥有一个或多个 state。

例如：

```text
Before git push, run tests.
```

可能维护：

```text
dirty = true / false
test_ran_after_dirty = true / false
```

再比如：

```text
Total cost must not exceed $90.
```

可能维护：

```text
total_cost
currency
counted_transactions
```

这些 state 的特点是：

```text
1. 属于某条 rule；
2. 有明确 scope；
3. 持久化保存；
4. 只能由 MAC validator runtime 更新；
5. 可以从 action log replay 重建；
6. 不由主 agent 直接读写。
```

state 不应该被理解成普通 global variable。它更接近：

> rule-local materialized view over observable agent history.

---

### Layer 4：Validator

validator 是 rule 的 runtime 执行逻辑。

每个 validator snippet 只实现两个 runtime phase：

```text
update(state, entry, log, context)
check(action, state, log, context)
```

每个安装后的 validator 还必须有一个 validator binding，用来说明它在什么
operational surface 上运行。Stage 2 暂时把 binding 分成两类：

```text
check_patterns:
  pre-action 使用，决定某个 pending action 是否需要运行 validator.check。

update_patterns:
  post-action 使用，决定某个 committed Action Log entry 是否需要运行
  validator.update。
```

这两类 pattern 不能混成一个字段。例如 `Before git push, run tests` 的
`check_patterns` 是 git push；如果它只是“push 前查一下是否运行过 test”，则不需要
`update_patterns`，可以在 `check` 中通过 bounded `log.search(spec)` 查询最近
test action。只有需要维护数值或状态型 materialized state 时，才写
`update_patterns`。

Extractor 负责提出 validator enforcement shape：

```text
check_only:
  只需要在 pre-action 对 Pending Action 做检查；可以使用 bounded
  ActionLogView.search(spec)，但不维护 persistent state。

check_update:
  需要 post-action update 从 Action Log 增量维护数值或状态型 state，
  pre-action check 再读取 Pending Action + State。

no_validator:
  不安装 validator snippet；可能继续走 pattern-only gate、prompt retrieval，
  或 manual review。
```

判定规则：

```text
update_patterns 不是“历史依赖”的默认产物。
只有当 rule 需要维护随 action log 增量变化的 state 时才生成 update_patterns，
例如 total_cost、dirty flag、sent_count、last_synced_seq。

如果 rule 只是问“之前是否发生过某类 action”，优先使用 check_only：
check_patterns 命中 Pending Action 后，check 用 log.search(spec) 做 bounded query。
```

Stage 2 的 validator 采用 restricted Python validator snippet，而不是固定模板，
也不是完全自由的 agent code。写 validator 的 LLM prompt 会要求它按
“EFSM-like” 思路组织代码：有限状态、显式 state transition、明确 check 条件。
EFSM 在这里只是生成思路，不是 runtime 的形式化语言。

安装后的 validator package 至少包含：

```text
validator_snippet:
  restricted Python code defining update(state, entry, log, context)
  and check(action, state, log, context)

state_schema / initial_state:
  persisted rule-owned state fields and initial values

update_patterns:
  committed Action Log entries that may call update

check_patterns:
  pending actions that may call check
```

Validator snippet 不靠 static verifier 维护 import 白名单。Stage 2 使用轻量
`ValidatorSandboxRunner` 执行 snippet；只有能在 sandbox dry-run / replay 中跑通
的 validator 才能安装，runtime 也使用同一个 sandbox runner。

推荐的初始实现是 stdlib 优先的 out-of-process worker：

```text
parent process:
  launch Python worker with subprocess timeout
  send snippet, state, pending action / action log entry, and bounded query budget
  receive JSON-serializable state / verdict
  kill worker on timeout or protocol violation

worker process:
  run in isolated/empty environment and temporary cwd
  expose controlled builtins and MAC-provided ActionLogView proxy
  allow only sandbox-provided helper imports
  deny filesystem IO, network/API, subprocess, env access, direct DB access
  enforce output size and JSON-serializable return values

POSIX resource guard:
  set CPU / address-space / file-size limits when available
```

写 validator snippet 的 prompt 必须让 LLM 先区分三种情况：

```text
direct:
  check 只看 Pending Action。

depends on prior action:
  check 看 Pending Action + bounded Action Log query。

depends on accumulated state:
  update 从 Action Log 增量维护 State；
  check 看 Pending Action + State。
```

bounded Action Log query 必须通过 MAC 提供的 ActionLogView helper 完成；snippet
不能直接读数据库，也不能做无界全量扫描。

ActionLogView 的公开 API 是 `search(spec)`，不是 raw SQLite connection。
`spec` 就是 `search` 的参数：一个 SQL-shaped 的 virtual query dict。validator
snippet 只调用 `log.search(spec)`；`spec` 的 `from`、`select`、`where` 字段属于
MAC 定义的虚拟 action-log schema。内部的 ActionLogSearchTranslator 负责把
这个 `spec` 编译成当前 SQLite schema 上的具体操作。

例如 snippet 可以表达：

```python
spec = {
    "from": "actions",
    "select": [
        "seq",
        "timestamp",
        "tool_name",
        "host_action",
        "outcome",
        "arguments",
        "result",
        "result_text"
    ],
    "where": {
        "tool_name": {"in": ["purchase", "checkout", "Bash"]},
        "outcome": {"eq": "success"},
        "seq": {"gt": state["last_seen_seq"]},
        "any_text": {"regex": r"\\$\\s*\\d+(\\.\\d{2})?"}
    },
    "order_by": [{"field": "seq", "direction": "asc"}],
    "limit": 50
}
entries = log.search(spec)
```

这不是允许 validator 写：

```sql
SELECT * FROM action_log WHERE ...
```

原因是 validator 不应该绑定物理表名、列名、索引策略或迁移细节。它只能把
受限的 `spec` 传给 `search`，并绑定稳定 virtual schema。

初始 virtual table 只需要一个：

```text
actions:
  seq
  timestamp
  session_id
  task_id
  agent_id
  adapter_id
  tool_call_id
  tool_name
  host_action
  outcome
  arguments
  result
  result_text
  reasoning_text
```

where 支持有限操作：

```text
eq / ne / in
gt / gte / lt / lte
exists / missing
contains / regex
json_path predicates on arguments.* and result.*
```

`ActionLogSearchSpecV1` 必须先 validate，再 compile。初始约束：

```text
from:
  只能是 actions。

select:
  只能选择 actions virtual table 中的字段。

where:
  只能使用已声明 operator。

order_by:
  只能使用 seq 或 timestamp。

limit:
  必须存在，且不能超过 runtime max limit。
```

所有 `search(spec)` 都必须有 bounded window：

```text
limit <= runtime max limit
and at least one of:
  seq range
  timestamp range
  session/task scope
  tool/action filter
```

runtime 应默认注入当前 session/task scope，除非 validator package 明确声明需要
跨 session 查询并通过 installation review。

ActionLogSearchTranslator 可以用 SQLite JSON function、FTS、普通索引或先取 bounded candidate
再在 Python worker 内做二次过滤。这个实现策略对 validator 不可见。

#### update

`update` 在 post-action 阶段运行。

runtime 调用 verified validator snippet 的 `update`：读取被 `update_patterns`
命中的新 raw action log entry，结合当前 state，返回新的 state。

例如：

```text
看到 edit_file 成功：
  dirty = true
  test_ran_after_dirty = false

看到 pytest 成功：
  test_ran_after_dirty = true

看到 purchase 成功：
  total_cost += price
```

#### check

`check` 在 pre-action 阶段运行。

runtime 调用 verified validator snippet 的 `check`：读取被 `check_patterns`
命中的当前 proposed action、当前 state，以及必要的 bounded action log view，
返回 verdict。

例如：

```text
如果当前 action 是 git push，
并且 dirty = true，
并且 test_ran_after_dirty = false，
则 revise/block。
```

validator 本身不能：

```text
调用 LLM
访问文件系统
访问网络
运行 subprocess
直接读写数据库
修改不属于自己的 state
依赖 hidden reasoning
```

validator 只能通过 MAC runtime 暴露的受限接口读取：

```text
当前 pending action
当前 rule state
raw action log view
runtime context
有限 helper methods
```

#### return protocol

`update` 和 `check` 的返回值必须是 JSON-serializable。

`update` 只允许返回：

```text
new_state:
  完整 rule-local state。

structured_error:
  表示该 entry 无法可靠更新 state；runtime 记录 error receipt，并按 rule risk
  决定是否需要 replay/repair/manual review。
```

`check` 必须返回 structured verdict：

```json
{
  "decision": "allow|revise|confirm|defer|block",
  "reason": "short human-readable reason",
  "evidence_refs": [{"kind": "action_log_seq", "seq": 123}],
  "confidence": 0.0
}
```

`unknown` 不能转成 `allow`。当 evidence 不足且 action 风险较高时，默认返回
`confirm` / `defer` / `revise`，而不是 `allow`。

---

### Layer 5：Validator Generation

validator snippet 不应该由现有 extractor 直接生成。但 Extractor 可以提出
validator enforcement shape，以及 proposed `check_patterns` / `update_patterns`。
后续安装阶段负责校验这些 proposed patterns 是否可执行。

推荐设计是：

```text
ContractExtractor:
  抽取 contract，并提出 enforcement shape、check_patterns、update_patterns

ConflictResolver:
  处理 duplicate / conflict / exception / supersession

ValidatorSnippetGenerator:
  按 EFSM-like prompting 生成 restricted Python validator snippet

ValidatorSnippetVerifier:
  校验 snippet 的语法、函数签名、top-level structure 和 sandbox dry-run/replay 结果

ValidatorSandboxRunner:
  在受限 worker 中执行 snippet，负责 import/IO/API/资源/超时边界

ValidatorTester:
  用 synthetic action log 和 pending actions 做 deterministic dry-run / replay tests

Runtime:
  安装通过 verifier 和 dry-run 的 validator snippet
```

这样可以避免 extractor prompt 过长，也避免让 extractor 同时承担 semantic
extraction 和 validator snippet synthesis 两种职责。Extractor 可以提出 patterns
和 enforcement shape，但不写 Python snippet。Stage 2 不引入固定模板编译层，
也不安装完全自由的 validator code；所有 runtime validator 都必须是 verified
restricted Python snippet。

#### ValidatorVersion

安装后的 validator 必须是不可变版本。一个 `ValidatorVersion` 至少绑定：

```text
validator_version_id
rule_id
snippet_hash
state_schema_version
check_patterns
update_patterns
sandbox_policy_version
action_log_search_spec_version
created_at
status
```

state schema 变化不能静默复用旧 state。必须选择：

```text
1. 从 action log replay/rebuild；
2. 运行显式 state migration；
3. 标记 needs_manual_review。
```

同一条 rule 可以有多个 validator version，但 runtime 只能使用一个 active
version；旧 version 保留用于 audit、receipt 和 replay。

#### ValidatorSnippetGenerator prompt shape

Generator prompt 必须把 rule understanding、observable action surface、query
surface、return protocol 和测试样例分开。推荐结构：

```text
SYSTEM
You generate restricted Python validator snippets for MAC.
Runtime will call:
  update(state, entry, log, context)
  check(action, state, log, context)
You must write EFSM-like code: explicit state, explicit update conditions,
explicit check conditions. Do not use global mutable state.
If evidence is insufficient, return confirm/defer/revise rather than allow.

IMMUTABLE RULE
id: rule_budget_01
text: Total cost must not exceed $90.
effect: deny
scope: current task
authority: user_explicit

ENFORCEMENT PLAN
enforcement_shape: check_update
update_patterns:
  - tool_name in ["purchase", "checkout", "booking"]
    outcome = success
check_patterns:
  - tool_name in ["purchase", "checkout", "booking"]
state_fields:
  spent_cents
  seen_entry_seqs
  unknown_spend_entry_seqs
  last_seen_seq

ACTION LOG ENTRY SCHEMA
ActionLogEntryV1 fields:
  seq, timestamp, session_id, task_id, agent_id, adapter_id, tool_call_id,
  tool_name, host_action, outcome, arguments, result, result_text,
  reasoning_text
reasoning_text is audit-only and must not be enforcement evidence.

ACTION LOG SEARCH API
You may call:
  log.search(spec)
Spec version: ActionLogSearchSpecV1.
from must be "actions".
select fields must come from ActionLogEntryV1.
where supports eq/ne/in/gt/gte/lt/lte/exists/missing/contains/regex/json_path.
Every search must include limit and a bounded window.

VERDICT API
Return one of:
  allow(reason, evidence_refs=None, confidence=1.0)
  revise(reason, evidence_refs=None, confidence=1.0)
  confirm(reason, evidence_refs=None, confidence=1.0)
  defer(reason, evidence_refs=None, confidence=1.0)
  block(reason, evidence_refs=None, confidence=1.0)

RECENT COMMITTED ACTION EXAMPLES
[
  {
    "seq": 10,
    "tool_name": "purchase",
    "outcome": "success",
    "arguments": {"item": "domain", "price": "$12.00"},
    "result": null,
    "result_text": "Purchased domain for $12.00"
  }
]

PENDING ACTION EXAMPLES
[
  {
    "tool_name": "checkout",
    "host_action": "purchase",
    "arguments": {"items": [{"name": "hosting", "amount": 85.0}]}
  }
]

TASK
Generate:
1. initial_state JSON
2. Python validator snippet defining update and check
3. brief notes on when the validator returns confirm/defer/revise
```

如果 prompt 缺少 ActionLogEntry schema、SearchSpec docs、verdict API、tool
capsules 或足够 recent examples，generator 不应产出 hard validator；应返回
`needs_refinement` / `manual-review`。

---

## 4. 工作流程

### 4.1 Rule ingestion 阶段

当用户输入或项目文档中出现一条约束时：

```text
1. Extractor 抽取 candidate rule，并提出 validator enforcement shape / check_patterns / update_patterns。
2. Normalizer 归一化 scope 和 lifecycle。
3. Resolver 判断是否 duplicate、conflict、exception、supersession。
4. 如果 rule 被接受，按 shape 进入 no_validator route 或 validator installation。
```

validator enforcement shape 只有三类：

```text
no_validator:
  不安装 validator snippet；具体 route 可以是 pattern-only gate、prompt retrieval、
  confirm-only 或 manual-review。

check_only:
  安装 validator snippet，但只在 pre-action 运行 check；
  check 可以使用 bounded ActionLogView.search(spec)，不维护 state。

check_update:
  安装 validator snippet；post-action update 维护 state，
  pre-action check 读取 state。
```

例如：

```text
Do not edit generated/**
  -> no_validator / pattern-only

Before git push, run tests
  -> check_only

Total budget must not exceed $90
  -> check_update

Do the safe thing before publishing
  -> no_validator / manual-review or confirm-only
```

---

### 4.2 Validator installation 阶段

如果 rule 需要 validator：

```text
1. 生成 restricted Python validator snippet。
2. 生成并校验 validator binding：check_patterns / update_patterns。
3. ValidatorSnippetVerifier 检查语法、函数签名和 top-level structure。
4. ValidatorSandboxRunner 在受限 worker 中执行 snippet，处理 import/IO/API/资源边界。
5. 用 synthetic action log 和 pending actions 运行 deterministic dry-run / replay tests。
6. 初始化 rule state。
7. 安装 verified validator snippet、validator version 和 binding。
```

如果 validator 生成失败：

```text
1. rule 仍然可以保留为普通 contract；
2. action-time 可以 fallback 到 confirm/defer；
3. 系统可以标记该 rule 需要人工 review 或后续 refinement。
```

---

### 4.3 Post-action 阶段

每次 agent 执行 tool 后：

```text
1. Host adapter 在 tool action 实际执行并返回结果后，记录 raw action log entry。
2. MAC 把该 committed tool action entry 追加到 action log。
3. MAC 用 validator binding 的 update_patterns 找到订阅这类 log entry 的 active validators。
4. 对每个 validator：
   - 读取当前 rule state；
   - 调用 update；
   - 写回新的 rule state；
   - 记录 state update provenance。
```

这里不调用 LLM。

post-action 的目标是让 state 始终跟随 agent 的实际行为更新。未执行、被
gate 拒绝、被用户拒绝或 host 未提交的 action 不更新 action log，也不驱动
validator.update。

运行形态：

```text
post-action:
  for each committed Action Log entry e:
    for each validator k:
      if update_pattern_k(e):
        S_k = update_k(S_k, e, ActionLogView, context)
```

---

### 4.4 Pre-action 阶段

每次 agent 准备执行 tool action 前：

```text
1. Host adapter 把 proposed action 表示成 pending action。
2. MAC 根据 scope、lifecycle、pattern-only rule pattern 和 validator check_patterns
   找到可能适用的 rules。
3. 对 pattern-only rule，沿用当前 deterministic gate。
4. 对带 validator 的 rule：
   - 读取 rule state；
   - 调用 check；
   - 得到 local verdict。
5. MAC 聚合所有 local verdict。
6. 返回最终 decision：
   allow / revise / confirm / block / defer。
7. 写入 receipt。
```

pre-action 的 pending action 只用于当前检查和 receipt，不被追加到 action log。

这里同样不调用 LLM。

运行形态：

```text
pre-action:
  for each Pending Action a:
    for each validator k:
      if check_pattern_k(a):
        verdict_k = check_k(a, S_k, ActionLogView, context)
```

---

## 5. Rule State 的存在形式

Stage 2 的核心判断是：

> state 必须作为持久化 runtime object 存在，但它不能成为独立事实源。

它的语义是：

```text
rule state = action log 的增量派生缓存
```

因此 state 应该满足：

```text
1. 持久化；
2. scoped；
3. versioned；
4. rule-owned；
5. validator-owned update；
6. read-only during check；
7. replayable；
8. auditable。
```

如果不持久化 state，则系统只能做 log-only validation：

```text
每次 check 都从 action log 重新扫描和计算状态。
```

这在短 session 里可行，但不适合长期 agent runtime。

因此 Stage 2 的推荐方案是：

```text
保留 persistent rule state；
同时保证它能从 action log rebuild。
```

---

## 6. Action Log 的可见性边界

validator 可以看到：

```text
1. 当前 proposed action；
2. 过去的 committed raw action log entries；
3. tool call 的 name 和 arguments；
4. tool result 的 content / success signal；
5. 当前 rule state；
6. runtime context；
7. 当前 pending action 的 ask-response flag；
8. MAC 暴露的有限 helper methods。
```

ask-response flag 只表示：agent 已经因为 ask-before rule 向用户发起询问，并且
在该询问之后观察到了用户输入。MAC 不解释用户输入内容，不判断用户是否真的
批准；这属于主 agent 的行为边界。

ask-response flag 是 single-use、pending-action scoped 的 runtime flag：

```text
1. 它绑定到当前 pending action 的 fingerprint，例如 rule id、tool name、
   normalized target、session/task。
2. 它只对下一次相同 pending action 尝试有效。
3. action 成功执行、action 被放弃、target/tool 变化，或 agent 在新的用户输入后
   提出不同 action，都需要重新触发 ask-before 流程。
4. 它不写入 action log，也不写入 rule state。
```

validator 不可以看到：

```text
1. 主 agent hidden reasoning；
2. 主 agent system prompt；
3. 完整数据库；
4. 文件系统；
5. 网络；
6. 环境变量；
7. 其他 rule 的私有 state；
8. 任意工具调用能力；
9. 任意 Python imports；
10. 未经 MAC runtime 提供的 host internals。
11. 用户回复的语义性批准/拒绝判断。
```

可以保存 reasoning content，但它只用于 audit/debug，不能作为 validation evidence。

---

## 7. 为什么不要求预定义 tool schema

Stage 2 不要求 MAC 预先知道所有工具的完整字段。

原因是 raw action log 采用 schema-light design：

```text
MAC 只保存 tool name、raw arguments、raw result、timestamp、tool_call_id
以及 optional reasoning metadata 等 envelope 信息。
```

不同 host agent 的 tool 参数可以原样保存。

validator 通过受限 `log view` 和 helper methods 读取：

```text
tool name
tool arguments
tool result
tool_call_id
timestamp
```

这意味着系统不需要为每个工具预先建模完整 schema。

但为了避免每条 validator 重复写脆弱解析，MAC 可以提供有限 helper，例如：

```text
parse tool arguments
match command pattern
judge tool success conservatively
find previous tool call result
iterate previous entries
```

这些 helper 不是工具 schema，而是 raw log query interface。

---

## 8. Backward Compatibility

MAC v4 必须保持 v3 行为兼容。

也就是说：

```text
没有 validator 的 rule:
  继续走当前 pattern-only gate。

有 validator 的 rule:
  先通过 validator check_patterns 判断是否 relevant；
  如果 matched，再运行 validator.check。

validator update:
  只在 post-action log entry 命中 validator update_patterns 后运行。
```

这样现有 direct rule 不需要重写。

例如：

```text
Do not edit generated/**
```

仍然可以由当前 deterministic pattern gate 处理。

而：

```text
Before git push, run tests.
```

才需要 validator check。它可以是 `check_only`：在 git push 的 pre-action 阶段
用 bounded `log.search(spec)` 查询是否存在相关 test action，不一定需要
persistent state 或 `update_patterns`。

v3 的 `tool_patterns/targets` 继续服务于 pattern-only gate，也可以作为
validator `check_patterns` 的 seed。`update_patterns` 是 Stage 2 新增的
post-action subscription surface，不能从 check surface 隐式推断。

---

## 9. Decision Aggregation

每条 rule 的 validator 只产生 local verdict。

最终 action decision 仍然由 MAC gate 聚合。

聚合需要考虑：

```text
rule strength
scope specificity
authority
lifecycle
exception relation
override relation
ask-response flag
conflict status
validator verdict
```

不能简单地说：

```text
block > confirm > revise > allow
```

因为 narrow exception 可能覆盖 broader prohibition。

因此：

```text
contract-level resolver 和 edge graph 仍然在 validator 之前生效；
validator 只负责判断某条 active rule 在当前 action 上是否 satisfied。
```

---

## 10. 典型例子

### 10.1 Direct Rule

Rule:

```text
Do not edit generated/**.
```

处理：

```text
无需 state。
无需 validator snippet。
当前 action pattern 命中后直接 block。
```

---

### 10.2 History-dependent Rule

Rule:

```text
Before git push, run tests.
```

处理：

```text
post-action:
  不需要 update_patterns；
  test command 成功后会作为 committed Action Log entry 进入 action log。

pre-action:
  check_patterns 命中 pending action 是 git push 时，
  check 用 bounded log.search(spec) 查询最近是否有成功 test action。
```

如果 rule 被解释为更强版本，例如“push 前必须在最后一次源码修改之后运行 test”，
才需要 `check_update`：post-action 维护 dirty / test_ran_after_dirty state，
pre-action 再读取该 state。

---

### 10.3 Accumulated-State Rule

Rule:

```text
Total cost must not exceed $90.
```

处理：

```text
post-action:
  update_patterns 命中 purchase/booking 成功后，累计 total_cost。

pre-action:
  check_patterns 命中 pending action 是新的 purchase/booking 时，
  检查 total_cost + proposed_cost 是否超过限制。
```

金额不要求 action log 物理 schema 预先知道字段位置。validator 可以通过
ActionLogView search 拿到 bounded raw entries，再在 snippet 中从 arguments /
result / result_text 里抽取金额：

```python
def update(state, entry, log, context):
    amount = extract_money(entry)
    if amount is None:
        state["unknown_spend_entry_seqs"].append(entry["seq"])
        return state

    if entry["seq"] not in state["seen_entry_seqs"]:
        state["spent_cents"] += amount["cents"]
        state["seen_entry_seqs"].append(entry["seq"])
    return state

def check(action, state, log, context):
    proposed = extract_money(action)
    if proposed is None:
        candidates = log.search({
            "from": "actions",
            "select": ["seq", "arguments", "result", "result_text"],
            "where": {
                "tool_name": {"in": ["purchase", "checkout", "booking"]},
                "outcome": {"eq": "success"},
                "seq": {"gt": state["last_seen_seq"]}
            },
            "order_by": [{"field": "seq", "direction": "desc"}],
            "limit": 20
        })
        proposed = infer_from_recent_shape(action, candidates)

    if proposed is None:
        return confirm("Cannot determine proposed cost.")

    if state["spent_cents"] + proposed["cents"] > 9000:
        return block("Budget would exceed $90.")
    return allow()
```

如果 price 只会在 tool result 中出现，pre-action 不能假装知道这次 action 的
最终成本；validator 应返回 confirm/defer/revise，或只在 post-action 更新 state
并阻止后续消费。

---

### 10.4 Ask-Before Rule

Rule:

```text
Ask before sending external emails.
```

处理：

```text
post-action:
  update_patterns 命中 external email send 真正执行并返回结果后，记录 committed tool action。

pre-action:
  check_patterns 命中 pending action 是 external email send 时，
  检查当前 action 范围内是否存在 ask-response flag。
```

注意：用户回复本身不写入 action log。MAC 只检查 ask-response flag：agent
是否已经触发 ask-before 流程，以及用户是否真的输入了后续消息。MAC 不判断
用户回复内容是否构成批准；如果用户说“不可以”，主 agent 不应再次提出该
tool action。

ask-response flag 是 single-use、pending-action scoped：它只覆盖下一次相同
tool / target / rule 范围的 pending action。action 成功、被放弃、tool/target
变化，或 agent 基于新的用户输入提出不同 action 后，都需要重新 ask。

---

## 11. Failure Modes

### 11.1 Missing log

如果某个 tool action 没有经过 post-action hook，state 会缺失。

处理原则：

```text
high-risk action should default to confirm/defer rather than allow。
```

---

### 11.2 Incorrect success parsing

tool result 可能是自然语言文本，success 判断可能不可靠。

处理原则：

```text
unknown should not become success。
```

不确定时，应返回：

```text
confirm / revise / defer
```

而不是 allow。

---

### 11.3 State drift

validator update 可能写错，导致 state 和 log 不一致。

处理原则：

```text
state 必须能从 action log rebuild；
系统应该支持 state replay / repair。
```

---

### 11.4 Ambiguous rule

某些 rule 无法自动转成稳定 validator。

处理原则：

```text
不要强行生成 validator snippet；
fallback 到 confirm/defer/manual review。
```

---

### 11.5 Host coverage 不完整

有些 host agent 可能只能 post-log，不能 pre-block。

处理原则：

```text
MAC 应区分：
  enforceable before action
  only observable after action
  only auditable externally
```

只有 pre-action hook 能覆盖的 action 才能真正实时 block。

---

## 12. 推荐实现策略

Stage 2 应该按以下顺序落地：

```text
1. 保留当前 v3 rule extraction / resolver / gate。
2. 增加 raw action log persistence。
3. 增加 persistent rule state。
4. 增加 validator snippet runtime：check_patterns、update_patterns、update/check。
5. 在 ActionGate 中增加 validator check path。
6. 加入 ValidatorSnippetGenerator，prompt 中使用 EFSM-like step-by-step instruction。
7. 加入 ValidatorSnippetVerifier 和 deterministic dry-run / replay tester。
8. 增加 replay/rebuild state 能力。
9. 增加 tests：
   - direct rule 无 validator 仍然有效；
   - no-push-before-test 能 block；
   - test 之后能 allow；
   - budget 累计能 block；
   - state 可以由 action log rebuild。
```

---

## 13. Non-goals

Stage 2 不试图解决：

```text
1. 完整 world model；
2. 任意自然语言 policy 的自动形式化；
3. 对 hidden reasoning 的验证；
4. 对所有 host tool 的完整 schema 建模；
5. 对没有 pre-action hook 的 action 做实时阻断；
6. 让 validator 任意访问外部环境；
7. 让 agent 自己既生成 rule、又执行 rule、又判断自己是否合规。
```

Stage 2 的重点是：

> 用结构化 raw action log 和持久化 rule state，把 contract memory 变成低延迟、可审计、可 replay 的 runtime validator。

---

## 14. 最终定义

**Stage 2 proposal 的核心定义：**

> MAC v4 introduces an event-sourced validator runtime. The system records a schema-light raw action log of committed tool actions through post-action host hooks. Each accepted contract may bind a validator with two functions: `update`, which derives persistent rule-local state from post-action log entries, and `check`, which validates pending actions against the current state and observable committed-action history. The action log remains the source of truth for executed tool actions; rule state is a persistent, scoped, replayable cache. Runtime validation never depends on hidden reasoning or action-time LLM calls.

中文表述：

> Stage 2 把 rule 从静态匹配对象升级为可执行 contract。系统通过 post-action hook 记录已经真实执行的 tool action，用这些 committed action 增量维护每条 rule 的持久化状态，并在 pre-action hook 中用本地 validator 检查当前 pending action 是否合规。action log 是已执行 tool action 的事实源，state 是派生缓存，validator 是状态更新和行为检查逻辑。
