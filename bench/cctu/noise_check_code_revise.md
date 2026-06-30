# noise_check_code 修订记录

本文档记录 `bench/MAC/cctu/data/noise_check_code/` 下 5772 条 noise evaluator 从 LLM 初生成到 verify 满分的过程。

## 初始状态（LLM 生成）

- **来源**：`bench/construct/cctu/noise_eval_generation.py` 对 contract graph 每个节点调用 LLM（`glm-5.2`），产出 JSON artifact + Python `evaluate(trace)`。
- **规模**：5772 个 evaluator 单元（约 200 个 task × 每 task 多个 constraint 节点）。
- **生成方式分布**（最终 verify 报告）：
  - `llm`: 3189
  - `heuristic`: 1940
  - `cctu_reference`: 643
- **初版问题**（P0 audit，见 Step 0）：
  - 大量 `coverage_missing:*`（tool / length / markdown 等特征未在代码中体现）
  - counterfactual 语义错误（该 fail 的合成 trace 却 pass）
  - 冗余检查（plain-text 约束却检查 json/date/tool）
  - 复合约束只覆盖一部分
  - 部分 LLM 代码语法错误

备份目录（按时间）：`bench/MAC/cctu/data/noise_check_code_backup/` 下各次 repair 前快照。

---

## Verify 通过率里程碑

| 阶段 | 脚本/动作 | pass 数 | 通过率 | needs_human | coverage_review | review |
|------|-----------|---------|--------|-------------|-----------------|--------|
| Step 0 P0 audit | `noise_eval_verify.py` 初版 | 946 | 16.4% | 570 | 4143 | 113 |
| Step 1 规则修复 P1 | `noise_eval_repair.py` P1 + verifier 语义修正 | 3104 | 53.8% | 433 | 1513 | 722 |
| Step 2 规则修复 P2/P3 | 继续 rule repair + mixed_heuristic | 5082 | **88.0%** | 286 | 273 | 131 |
| Step 3 LLM 重生成 | `noise_eval_llm_repair.py` 690 条（带 audit 反馈） | 5206 | 90.2% | 143 | 157 | 264 |
| Step 4 P4 SPEC 规则修复 | 统一 `SPEC` 模板 rewrite 566 条 | ~5687+ | ~98.5% | ↓ | ↓ | ↓ |
| Step 5 forbidden_tool | CF 条件收紧 + `forbid_tool_calls` | 5739 | 99.4% | 21 | 1 | 11 |
| **最终** | 末 14 条 + minimal evaluator | **5772** | **100%** | **0** | **0** | **0** |

最终 verify 报告：`bench/cctu/mid_data/eval_step5_5_noise_eval_verify.json`

---

## Step 0：建立审计（P0 verify）

**文件**：`bench/construct/cctu/noise_eval_verify.py`

**做什么**：
- 静态特征 coverage（`expected_features` vs 代码中检测到的特征）
- AST 复杂度 / 冗余逻辑 flag
- 合成 trace + counterfactual trace 语义探针
- severity 分级：`pass` / `review` / `coverage_review` / `needs_human` / `fail`

**needs_human 主要 flag（初版）**：
- `counterfactual_no_tool_calls_should_fail_passed`
- `counterfactual_forbidden_tool_should_fail_passed`
- `counterfactual_*_should_fail_passed`（markdown/json/date/period）
- `possible_json_checker_contains_length_logic`

---

## Step 1：规则修复 P1 + Verifier 语义修正

**文件**：`bench/construct/cctu/noise_eval_repair.py`（P1 pass）、`noise_eval_verify.py`

**对 evaluator（tool）的修改**：
- structured evaluator → Python `evaluate(trace)`
- `mixed_heuristic` / `build_python_from_structured` 模板
- tool usage / tool count / markdown / length 等规则模板补全
- negation / plain-text 约束 sanitize

**对 verify（检测）的修改**：
- `semantic_evaluator_features()`：去掉 type_hint 噪声（Format→markdown 误报等）
- `constraint_requires_tool_trace()` / length / interaction_rounds 更保守
- SPEC evaluator 跳过静态 redundant 检查

**needs_human 处理**：counterfactual 与 coverage 均有下降；仍有 ~286 needs_human 进入 Step 2 后。

---

## Step 2：规则修复 P2/P3（至 88%）

**继续 rule repair**，批量 rewrite flagged 项，manual queue 缩小。

**needs_human 剩余 Top flag**：
- counterfactual tool 类 (~197+55)
- composite partial coverage
- coverage_missing tool_count/tool_usage

---

## Step 3：LLM 重生成（690 条，可选路径）

**文件**：`bench/construct/cctu/noise_eval_llm_repair.py`

**做什么**：
- 对 Step 2 后仍 non-pass 的 690 条，把 constraint + 当前 code + **verification_audit flags** 发给 LLM 重写
- 8 workers 并行；结果缓存于 `noise_eval_llm_repair_cache.json`（已清理）

**结果**：
- 首次 apply 因 backup 目录未 `mkdir` 全部失败；修复后从 cache apply
- **124/690** 单条 audit 通过；全量 +124 pass → 90.2%

**结论**：LLM 对部分 tool/composite 有效，但易引入 `complex_python_many_conditions` 与 redundant 逻辑；后续以规则 SPEC 为主。

---

## Step 4：P4 统一 SPEC 规则修复（主力）

**文件**：`noise_eval_repair.py` — `build_repair_spec()` + `render_spec_evaluator_code()`

**对 evaluator 的修改**：
- 用 `SPEC = {...}` 声明式模板替代 LLM 冗长 Python
- 覆盖 length / tool_count / tool_usage / json / markdown / date / punctuation / interaction_rounds
- `forbid_tool_calls` / `allowed_tools_only` / `sentence_max` / `paragraph_max`
- `ends_with` 等语法 bug 修复

**对 verify 的修改**（配合减少误报）：
- `spec_actual_features()` 与 SPEC 字段对齐
- `constraint_requires_minimum_tool_calls()`：「must use **at most** N」不触发 no-tool counterfactual
- `constraint_text_mentions_tools()`：识别 snake_case 工具名

**needs_human**：从 143 降至 ~73 → 36 → …

---

## Step 5：forbidden_tool 专项

**needs_human 主因**：`counterfactual_forbidden_tool_should_fail_passed`（~20 条）

**Verifier**：
- 新增 `constraint_requires_disallowed_tool_counterfactual()`，仅对「禁止 tool / 白名单 tool」跑 CF
- 不再对「每 turn 限 1 次」「最多 N 次」「unlimited tool」误触发

**Repair**：
- `constraint_forbids_all_tool_calls()`：「must not include tool invocations」等 → `forbid_tool_calls: True`
- `allowed_tools_only` + `prefer \`tool\``

---

## Step 6：末 14 条清零（100%）

**剩余类型**：
- `possible_tool_logic_without_tool_constraint`（10）：semantic 空但代码含 tool → SPEC `tool_usage` 或 **minimal evaluator**
- `coverage_missing:length`（2）：`sentence_max` / `paragraph_max`
- `counterfactual_no_tool_calls`（1）：「at most 8 tools」误触发 min CF
- redundant date + tool（1）：空 feature 时跳过 artifact 内旧 structured spec，用 minimal

**关键逻辑**：`semantic_evaluator_features` 为空时 **优先 `render_minimal_evaluator_code()`**，不再 fall through 到旧 structured spec。

---

## 主要脚本索引

| 脚本 | 作用 |
|------|------|
| `bench/construct/cctu/noise_eval_generation.py` | LLM/heuristic 初生成 |
| `bench/construct/cctu/noise_eval_verify.py` | 静态 + counterfactual 审计 |
| `bench/construct/cctu/noise_eval_repair.py` | 规则/SPEC 批量 rewrite |
| `bench/construct/cctu/noise_eval_llm_repair.py` | LLM 带 audit 反馈重写（Step 3） |
| `bench/construct/cctu/noise_eval_grade.py` | 对 memory-eval run 打 constraint 分 |

---

## 当前 artifact 状态

- **目录**：`bench/MAC/cctu/data/noise_check_code/`
- **evaluator_type**：python 5445 / structured 326 / unsupported 1
- **generation.repair 标记**：多数为 `rule_based_p4_spec_repair` 或更早 P1/P3 pass
- **Verify**：5772/5772 pass（`eval_step5_5_noise_eval_verify.json`）
