# Memory-as-Contracts 实现计划

这个计划的目标是把 `proposal.md` 中的 MAC 构想拆成可直接执行的实现阶段。后续开发应按 step 推进：每一步先完成目标和验证，再进入下一步；如果遇到未决问题，先把决策写清楚，避免在代码里隐式选择架构。

## 当前仓库状态

项目概念已经从旧的 Memory Use Contracts 名称转向 **Memory-as-Contracts (MAC)**。当前执行决策是：从零构建干净 MAC 实现，不恢复旧 MUC 代码，不做 `muc` CLI 或 `memory_use_contracts` 兼容层。

当前仓库已经建立新的 `memory_as_contracts` 包、`mac` CLI、MAC env vars 和核心 Pydantic 模型。历史 `src/memory_use_contracts`、旧 tests 和旧 skill 文件保持删除状态。

## 总体边界

MAC 不是完整记忆系统。它只负责把用户声明的行为规则、偏好、限制和项目指令转成带 scope/lifecycle/source/provenance 的 contracts，并在 prompt intake 和 action gate 两个位置约束 agent 行为。

普通记忆系统仍负责：

- 一般事实回忆；
- profile memory；
- semantic/vector/graph retrieval；
- 任务背景、论文笔记、普通摘要；
- 非 contract 的长期记忆。

第一版实现应以 coding agents 为主，因为文件、命令、依赖、git 操作更容易定义和评估。general work agents 先做接口和 fixture，不把真实 calendar/email/document 集成作为早期瓶颈。

默认技术选择：

- Python 3.11、`uv`、`typer`、`pydantic`、`openai`、`rich`、SQLite、pytest；
- LLM 只用于写入时抽取、冲突关系分类、验证失败后的单次同步 pattern repair，以及 validator snippet generation；
- action-time gate 必须是确定性的，不调用 LLM；
- 核心检索使用 SQLite FTS/BM25 + structured filters；
- embeddings 只作为后续 ablation，不作为核心依赖；
- 默认 gate-by-default，只有 adapter 显式列入 `exclude_action` 的 action 可以绕过 MAC。

## Step 0: 对齐当前代码基线

目标：确认后续实现从干净 MAC scaffold 重建。

工作内容：

- baseline 决策已定：从零构建。
- 不恢复旧 MUC 文件。
- 不提供 `muc` alias 或 `memory_use_contracts` compatibility wrapper。
- repo 需要保持最小可运行状态：package directory、CLI entry point、basic import test。

边界：

- 本阶段只处理仓库一致性，不实现 extraction/storage/gate 等后续 MAC 行为。
- 不擅自覆盖当前工作区已有改动；当前删除应先视为用户可能有意为之。

仍需决策：

- 无；baseline 已确定为从零构建。
- `README 2.md` 是保留为 quickstart、合并进 README，还是后续删除。

完成标准：

- `UV_CACHE_DIR=.uv-cache uv sync --dev --reinstall-package memory-as-contracts` 后，`UV_CACHE_DIR=.uv-cache uv run python -c "import memory_as_contracts"` 能运行。
- `UV_CACHE_DIR=.uv-cache uv run pytest` 至少能进入有意义的测试阶段，而不是因缺少 package/test directory 失败。
- baseline 决策已写明。

## Step 1: 命名、包结构和 CLI

目标：把项目身份对齐到 MAC，不做旧 MUC 迁移兼容。

工作内容：

- 建立一等 Python namespace，优先使用 `memory_as_contracts`。
- 增加 `mac` CLI entry point。
- 更新 `pyproject.toml`、CLI help、README quickstart 和 env var 读取逻辑。
- 使用 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`MAC_LLM_MODEL`、`MAC_DB_PATH`。

边界：

- 本阶段是机械迁移，不重新设计 storage、extractor、gate。

仍需决策：

- 无；已采用 `memory-as-contracts`、`memory_as_contracts`、`mac`、`MAC_*`。

完成标准：

- `UV_CACHE_DIR=.uv-cache uv run mac --help` 能工作。
- `UV_CACHE_DIR=.uv-cache uv run python -c "import memory_as_contracts"` 能工作。
- 有测试覆盖 CLI 和 config 行为。

## Step 2: 核心数据模型

目标：把 proposal 中的 contract schema、scope、lifecycle、edge、receipt 和 action signature 编成类型化模型。

工作内容：

- 实现 `Rule/Contract`、`ContractSource`、`Scope`、`Lifecycle`、`RuleSemantics`、`ToolPattern`、`RulePatternVersion`、`ContractEdge`、`AvailableAction`、`ActionSignature`、`GateDecision`、`Receipt`。
- 定义 contract kind、modality、strength、status、source kind、edge relation、lifecycle type、decision、match outcome 等 enum。
- 支持 edge 自己的 scope/lifecycle，不能只把关系写成全局替代。
- 保留 source span 和 created_at，用于 provenance、relative time grounding 和 audit。
- 明确 `fact` 边界：fact 可以帮助推理，但不能单独授权、阻断或绕过 action。

边界：

- 模型层必须 host-agent independent。
- 不在本阶段写具体 command parser 或 adapter 逻辑。

仍需决策：

- ID 格式使用 `MAC-001` 风格、UUID，还是数据库自增加前缀。
- 对未知 host action/canonical tag 是严格拒绝还是允许扩展字段。
- path glob 是否统一存 workspace-relative。

完成标准：

- proposal 中的 contract、action signature、edge、receipt 示例都能序列化/反序列化。
- 非法 scope/lifecycle 组合能清晰失败。
- 单元测试覆盖 `fact` 不能执行 enforcement 的规则。

## Step 3: SQLite store、FTS 和迁移机制

目标：建立 durable store，能保存 contracts、edges、rule pattern versions、receipts 和 source snapshots。

工作内容：

- 建表：contracts、contract FTS、contract edges、rule pattern versions、receipts、source snapshots。
- 常用过滤字段用显式列，adapter-specific 扩展保留 JSON 字段。
- 支持 SQLite FTS/BM25 检索 contract text 和 source span。
- 加 `schema_version` 或等价 migration 机制，避免未来 MAC DB schema 被静默误用。

边界：

- store 层不调用 LLM。
- 这里只做基础 search/roundtrip；完整 applicability ranking 放到后续 retrieval/gate。

仍需决策：

- migration 采用手写函数、`schema_version` 表，还是引入 Alembic。
- source snapshot 放 DB 还是文件系统 sidecar。
- SQLite JSON 能力的最低版本要求。

完成标准：

- 空数据库 init 幂等。
- roundtrip 测试覆盖 contract、edge、rule pattern version、receipt 和 snapshot。
- FTS 检索能和结构化过滤一起工作。

## Step 4: 抽取、scope normalization 和 lifecycle normalization

目标：把 user turns 和 cold-start sources 转成候选 contracts，并附带结构化 scope、lifecycle 和 source provenance。

工作内容：

- online extraction 只从 user turns 产生 durable user contracts。
- user-turn extraction 使用 kernel 固定 prompt，保证 durable user contract 的边界稳定。
- cold-start import 支持 project docs、memory files、markdown/SQLite exports；cold-start prompt 由 adapter 按 agent/source 类型提供。
- cold-start source 用 `SourceKind` 和 provenance 标注较低 freshness/authority，不用 LLM 自报 confidence 参与状态决策。
- LLM 输出必须是严格 JSON，经过 schema validation 和必要 repair。
- scope normalization 覆盖 per-turn、task、session、component/module、project、repo、path、agent family、organization、global。
- lifecycle normalization 覆盖 immediate、bounded_time、bounded_session、bounded_task、until_revoked、conditional、review_after。
- relative time 必须用当前用户 timezone grounding。
- 保存原始 span，避免把 agent 推测洗成用户规则。
- periodic extraction trigger 第一版按每 10 个 user turns 触发；token threshold 和 long-session 时间阈值暂不做。

边界：

- agent turns、tool outputs、retrieved memories 只能作为解释上下文，不能未经用户确认成为 durable user-turn contracts。
- action-time gate 不能调用 extractor。

仍需决策：

- 当前决策：user-turn prompt 固定在 kernel；只有 cold-start prompt 是 adapter-owned/per-agent。
- 当前决策：删除 confidence threshold 映射；LLM 不需要输出 confidence，contract 是否 active/candidate/rejected 不由模型自报数字决定。
- 当前决策：只作用于当前 answer/reply/message/tool call 的 per-turn 指令默认不写 durable MAC；若 adapter 保留，只能作为 non-durable immediate/per-turn preference。
- 当前决策：durable user-turn contract 需要多次出现，或显式具备 task、session、project、repo、file/path、component/module、organization、global 等超出单轮回复的 scope。
- 当前决策：periodic extraction trigger 第一版固定为每 10 个 user turns；关键词、token threshold、long-session 时间阈值先不做。

完成标准：

- 测试覆盖用户输入抽取、项目文档导入、relative time grounding、source span 保留、非 contract 文本拒绝。
- live LLM diagnostic 可以 dry-run，不写 DB。

## Step 5: Deterministic pattern materializer 和 rule pattern versions

目标：把能机器检查的 contracts 转成 action-time 可确定执行的 patterns。这里仍保留 compiler/materializer 这一步；它消费 extraction 阶段产出的 `tool_patterns` operational seed，校验当前 adapter tool schema，并在 seed 缺失时使用有限 rule-base fallback。

工作内容：

- 定义 rule pattern version schema：native `tool_patterns`、scope predicate、lifecycle predicate、parser hints。
- extraction 输出 `tool_patterns` seed，用于把自然语言 rule 投影成初始 operational surface。路径和资源约束直接写在 raw arg matcher 中，不再维护独立 `targets`。
- compiler/materializer 的职责是 deterministic：读取 `tool_patterns` seed、校验 native tool/action 是否在 adapter capsules 中、补齐 scope/lifecycle predicate、生成 rule pattern version、执行 action-time evaluation。
- 当 operational seed 缺失时，compiler 只允许使用有限 rule-base fallback：path glob、git push/commit、dependency install、package-manager command、generated-file edit ban 等可机器解析模式。
- action-time pattern 中 native `tool` 使用 exact match；对 tool parameter 的要求使用字段级 matcher，例如 `args.command.regex = "^git\\s+push(\\s|$)"`。
- compiler 只依赖 `tool_patterns`、`semantics`、scope/lifecycle；native tool
  和参数字段是否合法由 Tool Capsules verifier 在 ingestion/materialization 边界检查。
- 不可稳定 rule-base 编译或无法通过 verifier 的规则保持 candidate，不安装 active binding predicate。
- 覆盖 coding 常见规则：path edit bans、git commit/push 限制、dependency manager 限制、test command requirement、generated-file edit ban、confirmation-before-action。
- rule pattern version 独立于 source contract 保存。
- pattern evaluation 只返回 `matched`、`not_matched`。
- 缺少参数或参数不匹配返回 `not_matched`；坏 regex 在 ingestion-time verifier 阶段被拒绝。

边界：

- compiler/materializer 不调用 LLM；需要 LLM 判断的 predicate projection 必须并入 extraction 或 dedup/relation 预算。
- 不删除 compiler 这一步，因为它是 extraction 输出和 action-time gate 之间的 schema validation、adapter grounding、pattern versioning 边界。
- action-time pattern evaluation 不得调用 LLM。
- verifier 失败时最多进行一次同步 LLM pattern refinement，再失败则保持 candidate。

仍需决策：

- 当前决策：pattern language 使用结构化 JSON pattern，允许字段级 regex；v0 不使用 Python policy functions 作为默认 pattern language。
- 当前决策：pattern verifier 本身不调用 LLM；只有验证失败时允许一次同步 repair call，之后必须再次通过同一 verifier。
- 当前决策：保留 compiler/materializer 这一步；它不是自然语言理解模块，而是 deterministic adapter-grounded predicate projection、validation 和 versioning 模块。
- 当前决策：tool name exact match；tool parameter 条件生成 regex。不要把整个 action 压成单一字符串 regex。
- 当前决策：generic command parsing 只覆盖 shell/git/package-manager 基础形态；复杂 host tool 参数解析交给 adapter。
- 当前决策：canonical tags 是内部 enforcement/ranking 概念，但在 receipts/prompt packet 中暴露给审计。

完成标准：

- 测试覆盖 `git push`、路径保护、dependency commands、package manager preferences、坏 regex、未知 tool 和未知参数。
- rule pattern version history 可以持久化和查询。

## Step 6: 相似检索、冲突处理和 scoped edges

目标：让 contract 更新具备可解释的演化历史，而不是静默覆盖。

工作内容：

- 插入新 contract 前，先用 scope 和 lifecycle 过滤掉根本不重叠的旧 contract。
- 对剩余 candidates 做两路相似度：contract text 用 BM25 得到 `score1`；把 `host_action + tool_name + parameter_regex` 拼成 predicate-pattern text 后，用 word overlap 得到 `score2`。
- 最终 similarity 使用 `0.7 * score1 + 0.3 * score2`。
- 取 similarity 大于阈值的 top3 送入 LLM relation classifier；初始阈值从 `0.60` 开始，经本地短规则和 live conflict 样例校准为 `0.35`，后续继续用 live/effectiveness tests 校准。
- LLM relation classifier 是默认关系判断路径；pattern/deterministic classifier 只在 LLM 不可用、输出不可解析或测试 shim 中作为 fallback。
- LLM 判断关系：`duplicate`、`refinement`、`supersedes`、`conflicts_with`、`exception_to`、`independent`。
- 批量插入多条 new rules 时，先对所有 new rules 基于同一份 existing-contract snapshot 做近似召回，再按“是否共享 retrieved existing rule”构建 component graph。
- 没有共享 retrieved existing rule 的 component 可并行调用 relation classifier；共享 retrieved existing rule 的 new rules 合并成一个 batch relation prompt。
- batch relation prompt 显式分为 `new_rules`、每条 new rule 独有的 `unique_retrieved_rules`、多条 new rules 共享的 `overlapped_retrieved_rules`，让 LLM 一次判断 overlap component 内的 new-to-existing edges。
- LLM 只输出 relation edges，不决定最终 status；active/rejected/superseded/pending_conflict 由 deterministic apply phase 按固定 precedence 串行写入。
- 高相似、同方向、同 scope/action 的 paraphrase 不允许作为两个 active rules 共存。
- 实现 precedence：当前 explicit user turn、source authority、更窄 scope、active lifecycle、hard prohibition、bounded exception、pending conflict。
- 保存带 scope/lifecycle 的 edge；只有当前 action/session metadata 匹配 edge scope/lifecycle 时，edge 才激活。
- equal-authority 未解冲突进入 `pending_conflict`，相关 action 在 Step 9 gate 中返回 `block`。

边界：

- 旧 contract 不物理删除，superseded/rejected 仍可审计。
- project-scoped edge 不能全局生效。

仍需决策：

- 当前决策：LLM deduce/relation classification 是 Step 6 默认；deterministic pattern match 是 fallback，不是主路径。
- 当前决策：候选召回先做 scope/lifecycle overlap filter，再做 text BM25 和 predicate-pattern word overlap 的加权相似度。
- 当前决策：predicate-pattern text 由所有 `host_action`、`tool_name`、`parameter_regex` 组成；target/path 仍由 scope 和 predicate 本身参与后续 gate，不混进整个 action 字符串。
- 当前决策：top3 且 similarity 超过阈值才送入 LLM；当前阈值 `0.35`，后续通过 live effectiveness test 校准。
- 当前决策：batch new rules 先全量召回，再用共享 retrieved existing rule 判断是否有 overlap；disjoint components 并行 classification，overlap component 合并成一次 batch classification。
- 当前决策：v0 不在 resolver 里重新处理 same-batch new-new 去重，默认 extractor 已经对同一批 new rules 做过去重；batch prompt 可以携带 overlap context，但 v0 写入只应用 new-to-existing relation edges。
- 当前决策：conflict 和 dedup classification 在插入时同步执行；无法稳定判断的 equal-authority conflict 进入 `pending_conflict`，不推迟到异步 review 才影响 gate。
- 当前决策：dedup 是插入前显式流程；higher-authority duplicate supersedes existing，lower/equal-authority duplicate rejected，refinement 保留 edge 但不静默合并。
- 对于per-turn的要求，是否可以提取为一种preference？这种preference的scope在哪里？preference的更新和消除又怎么处理？

完成标准：

- 测试覆盖 duplicate、project-local supersession、temporary exception、expired edge、equal-authority conflict、lower-authority rejection、batch overlap grouping、disjoint component parallel classification。
- CLI/API 能显示 active contracts 和相关 edges。

## Step 7: Prompt-intake retrieval

目标：在 agent 规划前，返回紧凑、相关、可解释的 contract packet。

工作内容：

- 按 session、project、repo、path、task、agent family、lifecycle、status、edge activation 和相似度检索。
- packet 包含 contract text、source、scope、lifecycle、inclusion reason、conflict status。
- 当前 scope 不由 LLM 或 user turn 自由推断；adapter 必须传入 ambient context：workspace、repo、branch、session/task/user、agent family、now/timezone 等。
- user turn 只用 deterministic regex 扫描 path/folder/glob/component hints；解析到 target hints 后才召回 project/folder/component/file local rules。
- retrieval 分三路：当前 ambient scope 下生效的 preferences、global/session/task/agent-level rules、以及基于 target hints 的 project/folder/component/file reminders。
- 放回 agent prompt 的内容使用压缩但结构化的纯文本，不使用 JSON；默认 token budget 为 `1500`。
- 默认排除 expired/rejected/superseded/out-of-scope contract，除非它们用于解释 active edge/conflict。
- 增加 CLI/API 模拟 prompt-intake retrieval。

边界：

- prompt intake 只影响 planning，不授权绕过 action gate。
- 不把整个 contract store 倒进上下文。
- path/folder/component/file scope 没有 deterministic target hints 时不进入 user-turn prompt-intake。

仍需决策：

- 当前决策：prompt-intake text budget 固定先用 `1500` tokens，后续通过 eval 再调。
- 当前决策：soft preferences 默认进入 prompt-intake packet，但仍必须匹配 ambient scope；path/component preference 仍需要 target hints。
- 当前决策：放回 prompt 的格式是 sectioned plaintext，例如 `Preferences:`、`Global rules:`、`Local reminders:`，不是 JSON。
- packet 是否包含 receipt/conflict history 摘要。

完成标准：

- 测试证明 adapter context 会限制 workspace/repo/session scope，regex target hints 会触发 local rule reminders，而无关 project/path/session rules 不会出现。
- 测试证明 prompt-intake renderer 输出稳定的非 JSON 纯文本，并遵守 `1500` token budget。
- packet 输出稳定，可被 adapter 和 eval harness 使用。

## Step 8: Hook rule base 和 action signature construction

目标：把 host-agent tool call 映射成 MAC action signature。

工作内容：

- 定义 adapter-owned hook rule-base schema。
- 实现 coding action registry：`exec`、`file.read`、`file.write`、`file.delete`、`git.commit`、`git.push`、`dependency.install`、`web.search`。
- 解析 command string 中的 git、package manager、test command、filesystem write、external publish 信号。
- action signature 包含 session、turn、task、time、timezone、workspace、repo、branch、tool、raw arguments、targets、intent、risk、side effect、host action、canonical tags。
- 每个 adapter 可定义 `exclude_action` patterns；pattern 支持 exact `tool_name`、exact `host_action`，以及针对 raw arguments 的 `parameter_regex`。

边界：

- 本阶段只构造 signature，不做 allow/block 决策。
- 真实 Codex/Claude Code/Nanobot/OpenClaw hook 可以稍后实现；这里先需要 shim 和 fixture。
- 默认没有任何 excluded action；即使 `file.read` 也必须进入 gate，除非 adapter 显式配置了更窄的 exclusion pattern。

仍需决策：

- 当前决策：`file.read` 不默认 exclude；信息泄露、隐私、workspace boundary 等 contract 可以约束 read action。
- 当前决策：`exclude_action` 可以细化到 tool 参数，例如只排除 `tool_name=exec` 且 `cmd` 匹配 `^git status` 的 action，不排除同一 tool 下的 `git push`。
- shell command 同时包含 read/write 时如何分类。
- Codex 和 Claude Code 实际能暴露多少 session/workspace/tool metadata。

完成标准：

- 代表性 tool call 能转成稳定 action signature。
- `exclude_action` bypass 行为显式且有测试，包括 tool-name + parameter-regex 的精细匹配，以及默认不 exclude `file.read`。

## Step 9: Action gate 和 receipt logger

目标：在每个 non-excluded action 前执行 contract enforcement，并记录可审计 receipt。

工作内容：

- 实现 gate decisions：gate 只返回 `allow`、`reject` 或 `ask`。
- 用当前 action signature 评估 active contracts 和 active edges。
- 综合 predicate match、scope/lifecycle applicability、status、authority、conflict state。
- 默认所有 non-excluded actions 都 gate。
- preference 不进入 action-time gate；preference 只通过 Step 7 prompt-intake 影响 planning。
- reject/ask reason 必须包含可直接给 agent 的 hint。
- receipt 记录 contracts used、edges applied、contracts ignored with reasons、match outcome、targets、canonical tags、decision、result。
- allow/reject/ask/ignored 都要有 receipt；pattern match outcome 只有 matched/not_matched。
- 提供 `mac_rule_override` CLI：当 action 被 block 后，agent 在获得用户批准或查阅信息到足够 confident 后，可调用 CLI 在被 block 的 rule 上添加 `override` edge；edge 的 scope 和 lifecycle 由 agent 通过 CLI 显式传入。
- override edge 命中当前 action signature 时，gate 忽略对应 block rule，并在 receipt 中记录 `override_applied`。
- 将 override 操作流程写成 skill，放在 `src/skill/mac_rule_override/SKILL.md`。

边界：

- action-time gate 必须 deterministic，不调用 LLM。
- receipt 是核心数据，不是可选日志。
- override 不修改或删除原始 rule，只添加 scoped/lifecycled edge。

仍需决策：

- 当前决策：action gate 使用三态 `allow/reject/ask`。`ask` 创建 `required`
  AskRequest；同 session/task 的下一条 `UserPromptSubmit` 直接把它标记为
  `responded`。single-use flag 只跳过相关 ask-before rule，不代表用户批准。
- 当前决策：soft preference 不进入 gate；只进入 prompt-intake reminder。
- 当前决策：先应用 override/exception，再评估全部 applicable rules，并按
  `reject > ask > allow` 聚合。

完成标准：

- 测试覆盖 hard block、preference bypass gate、excluded action bypass、expired contract、scoped exception/override edge activation、receipt correctness。
- CLI/API 能模拟 gate、显示 receipt，并能用 `mac_rule_override` 创建 override edge。

## Step 10: Pattern verifier 和单次同步 refinement

目标：在 extractor 提议的 pattern 进入 active runtime 前验证其结构正确性。

工作内容：

- 对 `tool_patterns`、`check_patterns`、`update_patterns` 使用同一个 rule-based verifier。
- 按 adapter tool capsules 检查 exact native tool name 和 raw argument name。
- 检查 matcher 与参数类型兼容，并编译所有 regex。
- 首次失败时允许一次同步 LLM refinement；prompt 包含 immutable rule、当前 patterns、verifier errors 和 tool capsules。
- LLM 只能返回三组 patterns，不能修改 text/effect/authority/scope/semantics/validity/source/lifecycle/status。
- refinement 输出必须再次经过相同 verifier；第二次失败则 rule 保持 `candidate`，不安装 active pattern version。

边界：

- 不维护 ambiguity event、rolling window、refinement queue 或 background worker。
- action-time matcher 只返回 `matched/not_matched`，且不调用 LLM。
- refinement 只负责 LLM 输出正确性，不根据运行时 precision/recall 判断 pattern 效果。

完成标准：

- 测试覆盖未知 tool、未知 arg、参数类型不兼容和坏 regex。
- 测试证明 refiner 最多调用一次，且不可修改 immutable rule fields。
- 只有 verifier 通过的 patterns 才能生成 active rule pattern version。

## Step 11: Adapter skeletons 和 cold-start import

目标：把 Codex、Claude Code、OpenClaw、Nanobot 的既有 memory/instruction markdown 接入 MAC，并提供 prompt-intake、action-gate 和 receipt export 的稳定桥接接口。

工作内容：

- 新增 `memory_as_contracts.adapters`，四个 agent 各一个主文件：`codex.py`、`claude_code.py`、`openclaw.py`、`nanobot.py`。
- 新增 shared adapter layer：`AdapterContext`、`MemorySourceSpec`、`ChangedSource`、`AdapterResult`。
- 每个 adapter 暴露统一 API：`discover_sources`、`cold_start_import`、`build_prompt_context`、`build_action_signature`、`gate_event`、`hook_config_snippet`。`refresh_changed_sources` 保留为 may-use-future/disabled surface，不接入自动 adapter path。
- backup 不使用额外 markdown sidecar，直接复用 `source_snapshots` 表。
- cold start 对每个 memory/instruction file 单独 snapshot，并单独调用 extraction；当前实现只在每个 adapter/workspace 首次 `UserPromptSubmit` 时默认执行一次。
- file-diff refresh 读取当前 source file，与 `source_snapshots.content/fingerprint` 做 diff 的机制保留为 future work；当前 adapter 自动路径不执行 diff refresh。
- source kind 规则：repo/project instruction files 标成 `PROJECT_DOC`；user/global instruction files 标成 `USER_PROFILE`；auto memory、dream memory、durable memory files 标成 `MEMORY_FILE`。
- `codex.py` source：`$CODEX_HOME/AGENTS.override.md` 或 `$CODEX_HOME/AGENTS.md`；workspace root 到 cwd 的 `AGENTS.override.md`、`AGENTS.md`、configured fallback filenames。
- `codex.py` trigger：首次 `UserPromptSubmit` 执行一次 cold start；不接入 `PostToolUse`/`Stop` diff refresh。
- `codex.py` hook：提供 Codex official hooks config snippet；`UserPromptSubmit` 返回 `additionalContext`，`PreToolUse` block 时返回 `permissionDecision: "deny"`。
- `claude_code.py` source：managed/user/project `CLAUDE.md`、`CLAUDE.local.md`、`.claude/rules/*.md`、auto memory directory `~/.claude/projects/<project>/memory/**/*.md`。
- `claude_code.py` trigger：首次 `UserPromptSubmit` 执行一次 cold start；`FileChanged`/diff refresh 标记为 future work，不进入当前 hook snippet。
- `claude_code.py` hook：提供 Claude Code settings JSON snippet；`UserPromptSubmit` 返回 prompt reminder，`PreToolUse` block 时返回 deny payload。
- `openclaw.py` source：workspace `MEMORY.md`、`memory/*.md`、`DREAMS.md`，以及存在的 instruction docs。
- `openclaw.py` trigger：首次 prompt bridge 执行一次 cold start；memory diff refresh 标记为 future work。
- `openclaw.py` hook：提供 typed plugin hook bridge shape for `before_prompt_build`/`before_tool_call`；不 auto-install。
- `nanobot.py` source：`SOUL.md`、`USER.md`、`memory/MEMORY.md`、`memory/history.jsonl`，其中 `history.jsonl` 作为 lower-authority memory source。
- `nanobot.py` trigger：首次 observability prompt 执行一次 cold start；Dream/manual diff refresh 标记为 future work。
- `nanobot.py` gate：提供 `gate_nanobot_tool_call(...)` function interface 供手动插入 runner；可提供 observability prompt/diff hook，但不声称已经 native automatic blocking。
- 默认所有 adapters 的 excluded actions 为空，除非 adapter 文件显式配置更窄的 `ExcludedActionPattern`。

边界：

- 只有 host 暴露可行 integration point 时才声称真实 hook；否则只提供 shim/CLI integration 并写明 gap。
- cold-start import 不改变 online source rule：online durable user contracts 仍只能来自 user turns 或用户确认。
- Step 11 不做 auto-install，不写 host 配置文件，只提供 handler 和官方 config snippets。
- receipt 由 Step 9 gate 落库，adapter payload 只导出 receipt id、decision、reason、contracts/edges 摘要。

仍需决策：

- 当前决策：Codex 使用 `AGENTS.md`/`AGENTS.override.md` 和 `UserPromptSubmit`、`PreToolUse`、`PostToolUse` hooks；source diff refresh 不接入当前自动路径。
- 当前决策：Claude Code 使用 `CLAUDE.md`、`CLAUDE.local.md`、`.claude/rules/*.md`、auto memory markdown，以及 `UserPromptSubmit`、`PreToolUse`、`PostToolUse` hooks；`FileChanged` 作为 future work。
- 当前决策：OpenClaw memory 以 workspace markdown files 为主，并通过 typed plugin hooks/function bridge 接入。
- 当前决策：Nanobot memory 使用 `memory/history.jsonl`、`SOUL.md`、`USER.md`、`memory/MEMORY.md`；blocking gate 先做 function interface。
- 当前决策：Codex/Claude 提供 native hook config snippets；OpenClaw/Nanobot 在 Step 11 只声明 bridge/function interface，不声明已完成真实 runner 级阻断。

完成标准：

- 每个 adapter 能发现预期 source files，并正确标注 `SourceKind`。
- cold start 对每个 source file 调用 extractor 一次。
- snapshot diff 对 unchanged files 不调用 extractor，对 changed files 只调用 changed sources，并在成功 extraction 后更新 snapshot content/fingerprint。
- Codex 和 Claude hook handlers 能返回 prompt `additionalContext`，并在
  reject/ask 时返回 host deny payload；ask payload 额外包含 `ask_id`。
- OpenClaw `before_tool_call` bridge 能映射到 MAC gate。
- Nanobot `gate_nanobot_tool_call(...)` 能返回 allow/reject/ask，并暴露
  post-tool 与 user-input interfaces，但不声称 native hook install。
- blocked gate payload 包含 Step 9 hint text，receipt 成功写入 store。

## Step 12: CLI、diagnostics 和开发工作流

目标：让 MAC 在研究和 benchmark 构建阶段可操作、可检查、可调试。

工作内容：

- CLI 覆盖 init、env、live LLM check、user-turn ingest、cold-start import、instruction refresh、contracts、conflicts、predicates、prompt-intake retrieval、gate simulation、receipts 和 pattern verification diagnostics。
- 只维护 `mac` 命令。
- 支持 JSON output，供 eval scripts 使用。
- 支持 human-readable rich table，供手工检查。

边界：

- CLI 只包装 kernel，不写核心业务逻辑。
- diagnostics 默认不 mutate state，除非命令名明确表示写入。

仍需决策：

- 最终命令名和 alias。
- `ingest` 是否只表示 online user-turn ingest，cold-start 是否另叫 `import-source`。
- 暴露多少底层 DB inspection。

完成标准：

- README quickstart 中的命令实际可运行。
- CLI tests 覆盖 human 和 JSON 输出路径。

## Step 13: MACBench-Code prototype

目标：构建第一个 coding-agent contract obedience 评估闭环。

工作内容：

- 定义 benchmark item schema：prior user turns/cold-start sources、generated rules、hidden scope/lifecycle labels、current task prompt、environment state、available actions、expected outcome、violation oracle、expected receipt。
- 生成 coding variants：path edit bans、commit/push restrictions、test command requirements、package-manager restrictions、temporary exceptions、project-local vs global conflicts、stale instructions、user-change preservation。
- 实现 baselines：no memory、full transcript、top-k retrieval、native/structured memory without gate、heuristic-only MAC、text-retrieval-only MAC、hybrid MAC。
- 记录 metrics：hard violation rate、scope accuracy、lifecycle accuracy、edge activation accuracy、predicate precision/recall、pattern verification/repair pass rate、conflict resolution、task success、false block/confirmation、unsafe bypass、receipt correctness、latency、token overhead、extra LLM calls。

边界：

- 在真实 host hooks 成熟前，可先使用 simulated host actions。
- 不把 component tests 夸大成 agent-level runtime validation；报告必须区分 kernel simulation、shim integration 和 real-agent trace。

仍需决策：

- 任务来源用 SWE-bench-style tasks、小型 synthetic repos，还是本地 coding-agent benchmark fixtures。
- 第一篇 prototype 是否必须跑真实 Codex/Claude Code。
- hidden oracles 如何可复现生成。

完成标准：

- 小型 fixture suite 能跑完并输出 metric JSON 与 human-readable report。
- 至少一个 ablation 能展示 context-only memory 与 action-time contract gate 的差异。

## Step 14: MACBench-General prototype

目标：把评估扩展到 general work agents，但不阻塞 coding-first kernel。

工作内容：

- 定义 general-work action registries：email、message、calendar、document、file share、purchase、task update、memory write。
- 构造 MEMTRACK-like 或其他 general-agent tasks，并注入 MAC rules：calendar sharing restrictions、email confirmation requirements、document preferences、week-only policies、session exceptions、global/project conflicts。
- 复用同一套 contract store、prompt-intake retrieval、action gate、receipt 和 pattern verification metrics。

边界：

- 没有真实外部服务集成前，只做 prototype/fixture，不触碰真实 email/calendar/purchase。
- 不引入重型 general memory store；MAC 仍只是 contract layer。

仍需决策：

- general-work 最适合基于哪个 benchmark family。
- embeddings 是否作为 general-work ablation。
- 如何模拟 side effects 而不连接真实外部服务。

完成标准：

- 小型 general-work fixture suite 能通过同一 eval harness 运行。
- 结果与 coding results 分开报告，避免混淆能力边界。

## Step 15: 文档和研究声明对齐

目标：让 implementation、README、proposal 和 evaluation claims 始终一致。

工作内容：

- 每个大 milestone 后更新 README，保证它描述的是 live code，不是 aspirational design。
- proposal 保留研究愿景，README 标明当前实现状态。
- 明确记录 adapter limitations 和真实 host integration gaps。
- 补充 schema、edge activation、pattern verification/repair、action signatures、evaluation methodology 文档。
- 维护 implemented/simulated/deferred changelog。

边界：

- 没有真实 host hook trace 前，不声称已完成 Codex、Claude Code、Nanobot 或 OpenClaw enforcement。
- 不把 unit tests 表述成 runtime validation。

仍需决策：

- 长期是否保留 `proposal.md`、`README.md`、`plan.md` 三份文档，还是拆到 `docs/`。
- 什么证据标准才允许把某功能标为 implemented。

完成标准：

- fresh checkout 的 README setup 和 commands 准确。
- evaluation report 明确标出 exercised path：component、shim，还是 real host-agent path。

## 执行顺序摘要

1. 对齐当前代码基线。
2. 修复命名、包结构和 CLI 兼容。
3. 实现核心 schema。
4. 实现 SQLite store 和 migration。
5. 实现抽取与 scope/lifecycle normalization。
6. 实现 predicate compiler。
7. 实现 conflict graph 和 scoped edges。
8. 实现 prompt-intake retrieval。
9. 实现 action signature construction。
10. 实现 action gate 和 receipts。
11. 实现 pattern verifier 和单次同步 refinement。
12. 实现 adapters。
13. 实现 CLI diagnostics。
14. 实现 MACBench-Code。
15. 实现 MACBench-General。
16. 持续对齐文档和研究声明。

## 第一轮明确不做

- 训练模型。
- 把 embeddings 作为核心依赖。
- 做完整 general memory system。
- 做 UI。
- 做 continuous self-reflection 或 multi-agent debate。
- 在没有真实 hook trace 前声称完成真实 Codex/Claude Code/Nanobot/OpenClaw enforcement。
