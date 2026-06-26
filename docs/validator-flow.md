# Validator Flow

Validator 生命周期分两条主线：**安装/生成**（Contract 激活后）和 **运行时执行**（工具调用前后）。

主要代码入口：

| 阶段 | 模块 | 类/函数 |
|------|------|---------|
| 生成 | `validator_generation.py` | `ValidatorSnippetGenerator.generate_verified` |
| 验证 | `validator_installation.py` | `ValidatorSnippetVerifier.verify` |
| 安装 | `validator_installation.py` | `ValidatorProvisioner.provision` → `ValidatorInstaller.register` |
| Pre-hook | `validators.py` + `rule_evaluation.py` | `ValidatorRuntime.check` |
| Post-hook | `validators.py` + `validator_dispatch.py` | `ValidatorRuntime.update` |

---

## 1. Validator 安装流程（Provisioning）

Contract 变为 `ACTIVE` 且需要 validator 时，由 `MacHookRuntime.resolve_and_store` 触发 `ValidatorProvisioner.provision`。

```mermaid
flowchart TD
    Start([Contract ACTIVE<br/>且 enforcement ≠ no_validator]) --> PreCheck{前置检查}

    PreCheck -->|CHECK_UPDATE + global scope<br/>且无 user_id| Fail1[生成 fail package<br/>stateful global 需要 user identity]
    PreCheck -->|CHECK_UPDATE +<br/>adapter 不支持 post_action| Fail2[生成 fail package<br/>需要 post-action 能力]
    PreCheck -->|通过| GenVerified[generate_verified]

    subgraph Generate["ValidatorSnippetGenerator.generate_verified"]
        GenVerified --> Examples[从 Action Log 抽取<br/>matched_action_examples]
        Examples --> Preflight{_preflight}

        Preflight -->|NO_VALIDATOR| FailP1[fail: 不需要 validator]
        Preflight -->|缺少 tool_capsules| FailP2[fail: 缺少 capsules]
        Preflight -->|缺少 check_patterns| FailP3[fail: 缺少 check patterns]
        Preflight -->|CHECK_UPDATE 缺 update_patterns| FailP4[fail: 缺少 update patterns]
        Preflight -->|通过| BuildPrompt[build_validator_generator_prompt<br/>规则 + enforcement + capsules + 示例]

        BuildPrompt --> Loop{尝试 ≤ max_attempts<br/>默认 3 次}

        Loop --> LLM[LLM 生成 JSON package<br/>check_code / update_code / shared_states]
        LLM --> Parse[_parse_package +<br/>_with_default_shared_states]
        Parse --> Ready{package.is_ready?}
        Ready -->|否| ReturnFail[返回 fail package]
        Ready -->|是| Verify[ValidatorSnippetVerifier.verify]

        subgraph VerifyBox["验证阶段"]
            Verify --> AST[AST 结构检查<br/>签名 / 禁止 mutable globals / dict 访问规范]
            AST --> SandboxCheck[沙箱运行 check<br/>对 check_patterns 构造的 pending action]
            SandboxCheck --> SafetyCheck{check 只读?<br/>缺 arguments 时不能 allow?}
            SafetyCheck -->|CHECK_UPDATE| SandboxUpdate[沙箱运行 update<br/>幂等性 + replay 一致性]
            SafetyCheck -->|CHECK_ONLY| Hash
            SandboxUpdate --> Hash[计算 verification_hash]
        end

        Hash --> Accepted{verification.accepted?}
        Accepted -->|是| SuccessPkg[返回 success package<br/>含 verification_hash]
        Accepted -->|否| Feedback[附加 VERIFIER FEEDBACK<br/>重试]
        Feedback --> Loop
        Loop -->|耗尽重试| FailRetry[fail: verification failed after retries]
    end

    SuccessPkg --> Register[ValidatorInstaller.register]
    ReturnFail --> Register
    Fail1 --> Register
    Fail2 --> Register
    FailRetry --> Register

    subgraph Install["安装阶段"]
        Register --> HasHash{有 verification_hash?}
        HasHash -->|否| InstallFail[记录 FAILED installation]
        HasHash -->|是| CreateVersion[创建 ValidatorVersion<br/>snippet_hash + verification_hash]
        CreateVersion --> ScopeKey[计算 validator scope_key]
        ScopeKey --> StoreInstall[store.install_verified_validator_version]
        StoreInstall --> InstallOK[记录 SUCCESS installation]
    end
```

---

## 2. 运行时 Pre-hook（工具调用前 Gate）

Agent 发起工具调用时，`ActionGate` → `RuleEvaluator` → `ValidatorRuntime.check`。

```mermaid
flowchart TD
    Pending([Pending Action<br/>工具调用前]) --> Gate[ActionGate.gate]
    Gate --> EvalLoop[遍历 ACTIVE / PENDING_CONFLICT 合约<br/>RuleEvaluator.evaluate]

    EvalLoop --> HasValidator{有 ACTIVE<br/>ValidatorVersion?}

    HasValidator -->|否| Fallback{contract 要求 validator?}
    Fallback -->|是| AskMissing[ASK: validator 未安装]
    Fallback -->|否| PatternGate[走 Pattern 匹配路径]

    HasValidator -->|是| BindCheck[bind_validator_check<br/>匹配 check_patterns]
    BindCheck -->|未匹配| Ignore[ignored: validator_not_matched]
    BindCheck -->|匹配| AskResp{有 ask_response?}

    AskResp -->|是| UseAskResp[使用用户回复决策]
    AskResp -->|否| RuntimeCheck[ValidatorRuntime.check]

    subgraph CheckRuntime["ValidatorRuntime.check"]
        RuntimeCheck --> Scope[计算 scope_key]
        Scope --> LoadState[加载 ValidatorState]
        LoadState --> CatchUp{有 update_patterns?}
        CatchUp -->|是| ReplayMissed[_catch_up_state<br/>重放未应用的 log entries]
        CatchUp -->|否| Degraded
        ReplayMissed --> Degraded{state.degraded?}
        Degraded -->|是| AskDegraded[ASK: state stale/degraded]
        Degraded -->|否| Sandbox[ValidatorSandboxRunner.check<br/>子进程沙箱]

        subgraph SandboxCheck["沙箱 check(action, log, context)"]
            Sandbox --> LogSearch[log.read 按需查 Action Log]
            Sandbox --> StateRead[log.state_read 读取 shared_states]
            LogSearch --> Verdict[返回 allow / ask / reject]
            StateRead --> Verdict
        end
    end

    Verdict --> Merge[合并多合约 verdict<br/>reject > ask > allow]
    AskDegraded --> Merge
    AskMissing --> Merge
    UseAskResp --> Merge
    PatternGate --> Merge
    Ignore --> Merge

    Merge --> Decision([GateDecision<br/>ALLOW / ASK / REJECT])
```

---

## 3. 运行时 Post-hook（工具调用后 Update）

工具执行完成并 commit 后，`ValidatorRuntime.record_committed_action` 触发状态更新。

```mermaid
flowchart TD
    Committed([Committed Action<br/>工具执行后]) --> Append[store.append_action_log_entry<br/>写入 ActionLogEntryV1]

    Append --> Dispatch[ValidatorDispatchPlanner<br/>.for_committed_entry]

    Dispatch --> ForEach[遍历 ACTIVE ValidatorVersion]
    ForEach --> Match{contract 有效?<br/>update_patterns 匹配?<br/>bind_validator_update}

    Match -->|否| Skip[跳过该 validator]
    Match -->|是| Update[ValidatorRuntime.update]

    subgraph UpdateRuntime["ValidatorRuntime.update"]
        Update --> SeqCheck{entry.seq ≤<br/>last_applied_seq?}
        SeqCheck -->|是| NoOp[幂等跳过]
        SeqCheck -->|否| SandboxUpdate[ValidatorSandboxRunner.update<br/>子进程沙箱 update entry, log]

        SandboxUpdate --> Persist[put_validator_state<br/>revision++ / last_applied_seq]
        Persist --> Transition[记录 ValidatorStateTransition]
    end

    Update -->|异常| Degrade[标记 state.degraded<br/>记录 runtime error<br/>replay_required=true]

    Transition --> Done([ValidatorState 已更新])
    NoOp --> Done
    Skip --> Done
    Degrade --> Done
```

---

## 4. 整体架构（一图总览）

```mermaid
flowchart LR
    subgraph Offline["离线：Contract → Validator"]
        C[Contract<br/>check/update patterns] --> G[LLM Generator]
        G --> V[Verifier<br/>AST + Sandbox]
        V --> I[Installer<br/>ValidatorVersion]
    end

    subgraph OnlinePre["在线：Pre-hook"]
        PA[Pending Action] --> CHK[check_code<br/>沙箱子进程]
        CHK --> VD[Verdict<br/>allow/ask/reject]
    end

    subgraph OnlinePost["在线：Post-hook"]
        CA[Committed Entry] --> UPD[update_code<br/>沙箱子进程]
        UPD --> ST[(ValidatorState<br/>per scope_key)]
    end

    I --> CHK
    I --> UPD
    AL[(Action Log)] --> CHK
    AL --> UPD
    ST --> CHK
    ST --> UPD
```

---

## 关键设计点

| 阶段 | 入口 | 核心产物 |
|------|------|----------|
| 生成 | `ValidatorSnippetGenerator.generate_verified` | `check_code` + 可选 `update_code` + `shared_states` |
| 验证 | `ValidatorSnippetVerifier.verify` | `verification_hash`（安装必需） |
| 安装 | `ValidatorInstaller.register` | `ValidatorVersion` 写入 store |
| Pre-hook | `ValidatorRuntime.check` | `ValidatorVerdict`（allow/ask/reject） |
| Post-hook | `ValidatorRuntime.update` | 按 `scope_key` 维护 `ValidatorState` |

### Enforcement shape 差异

- **`check_only`**：只有 `check_code`，无状态更新
- **`check_update`**：pre 用 `check`，post 用 `update` 维护 `shared_states`
- **`no_validator`**：跳过整个 validator 流程

### Hook 职责

- **`check_code`**：在 pending tool action 执行前运行，决定该 action 是否满足 contract；可用 `log.state_read` 读取状态，但不能写状态
- **`update_code`**：在 committed tool action 之后运行，通过 `log.state_read` / `log.state_write` 更新既有 `shared_states` key；必须幂等

### 沙箱约束

- 子进程隔离运行（`ValidatorSandboxRunner`）
- 仅允许 `import math` / `import re`
- 通过 `log.read(spec)` 查询 Action Log，不支持 raw SQL
- 通过 `log.state_read(...)` / `log.state_write(...)` 读写已声明的 shared state key
- Verdict API：`allow()` / `ask()` / `reject()`
