# Memory-as-Contracts (MAC) — 项目提案

## 1. Motivation

现有 agent memory 主要解决「回忆有用上下文」，很少系统回答：**用户说过的偏好/禁令/流程，能否在后续行动中被正确提取、更新并执行？**

典型失败：长对话约束被淹没；多次表述冲突不知以谁为准；scope 搞错（全局 vs 项目 vs 例外）；SOP 改版后仍用旧约束。

**核心主张**：Memory 不只是 context，也是用户与 agent 的 **行为合约（contract）**，约束未来 planning 与 tool action。

MAC **不是**完整 memory 系统，而是与现有 memory **并行的治理层**：抽取合约、归一化 scope/lifecycle、冲突消解、action-time 拦截、产出 receipt。

---

## 2. System Design

```text
user turns / 冷启动文档 → adapter → contract 抽取 → scope/lifecycle 归一化
  → 冲突检查 → Contract Store → prompt 检索 → action gate (allow/reject/ask)
  → Action Log + validator 状态 → receipt
```

**Contract 要点**：`text`、`effect`（deny/allow/require/prefer）、`scope`、`lifecycle`、`tool_patterns`（可执行匹配）。种类：prohibition / requirement / procedure / preference / exception / fact。

**Enforcement**：
- **Prompt intake**：规划前注入相关合约
- **Action gate**：每个 pending tool call 前检查，结果仅 `allow` / `reject` / `ask`
- **MAC v4**：跨步状态规则用 Validator Snippet（sandbox 内基于 Action Log 做 check/update）

在线抽取：仅从 **user turn** 批量（每 10 轮）抽取 durable contract。目标 agent 以 coding agent（CC/Codex 类）为主。

**实现分层**：核心库（抽取、存储、gate、validator 运行时）+ 评测 harness（统一 agent runtime、数据构造 pipeline、跑评与 grading 脚本）。

---

## 3. Benchmark Design

**目标**：约束不在 eval turn 的 in-context 里，而是散落在长 user history 中，对比各 memory 方案能否召回并应用正确约束。

**Harness 结构**：统一 agent loop 与 memory provider；各 benchmark 独立的数据构造 pipeline；共享的跑评与打分入口。

**对比方案**（规划）：no memory、long context、BM25/embedding/RRF、mem0/a-mem/letta、cc-style/openclaw-style、**MAC**。

### CCTU — 空间 scope + 冲突噪声

- 来源：CCTU coding agent 长 system prompt 里的 tool 约束
- 拆 constraint → 注入 scope 噪声（global/project/phase/exception）→ 合并 sequence → 生成长 **user-only** history
- ~200 tasks，history ~188 turns，merged sequence ~29 constraints

### SOPBench — 时间维度 + SOP 修订

- 来源：SOPBench 830 tasks 中抽 **200**
- 不测 scope 分层，测 **temporal dynamics**：anchor 约束随 SOP 修订（0–3 次 modification），history 模拟「设计/修改 SOP」
- anchor = 全部 `user_goal` + 采样 K=8（~12/task）

**共用 invariant**：eval turn **不含**目标约束原文，只测 memory 召回。

---

## 4. Current Status

| 模块 | 状态 |
|------|------|
| MAC 核心 | 需要且必须优化 |
| **CCTU** | **搭好，未测** — 数据已 export，construct 完整，noise check 质检中，未跑 memory 对比 |
| **SOP** | **进行中** — step1–4 ✅（200 tasks）；待 export、bridge+grade 联调、process=null 质检、正式 eval |

近期修复：SOPBench university domain 需补全部分 internal_check 的 process 注册，否则 temporal noise 生成阶段会全 skip。

---

## 5. 建议阅读顺序

1. 项目 README 与术语表 → 理解 contract 模型与 gate 语义
2. validator 流程文档 → 理解安装与运行时 check/update
3. 各 benchmark 的构造计划 → 理解 CCTU / SOP 的数据生成逻辑
4. 接入仓库后：配置 LLM 环境变量 → 跑数据构造 → 跑 benchmark 对比实验
