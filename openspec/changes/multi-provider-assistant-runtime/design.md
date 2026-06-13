## Context

当前 assistant 运行时的真实依赖链如下：

```text
AssistantService
  -> SessionManager
    -> ClaudeAgentOptions / ClaudeSDKClient
      -> Claude-specific hooks / permissions / transcript format
```

这意味着現有 assistant 不只是"默认模型是 Claude"，而是"运行时协议就是 Claude SDK"。若直接将 Gemini 或 OpenAI/ChatGPT 塞进这条链路，会在以下维度立即失配：

- 会话创建与恢复协议
- tool use / permission hook 生命周期
- subagent 调度
- transcript 持久化与 reconnect 语义
- 中断、继续、提问等状态机

因此本变更不追求"Gemini / OpenAI 等价替换 Claude"，而是定义一個更现实的多阶段路线：

1. 先抽象 runtime provider 边界
2. 先落地 Gemini 与 OpenAI/ChatGPT 的 lite assistant
3. 再按项目需要补足 workflow-grade 能力
4. 最后才评估是否值得扩展到 full runtime parity

## Goals / Non-Goals

**Goals**

- 将 assistant runtime 抽象为 provider-agnostic 接口
- 让 Gemini-only 与 OpenAI-only 部署可启用项目内 assistant，而不是被 Anthropic 阻断
- 为前端提供统一的 provider 状态与能力矩阵，按能力启用/禁用功能
- 保留 Claude full runtime，不破坏現有高阶能力
- 明确本项目的 workflow-grade 能力边界，为后续多 provider 编排能力做铺垫

**Non-Goals**

- 首期不追求 Gemini / OpenAI 与 Claude 在 subagent、resume、hook 上完全对等
- 首期不重写 workflow-orchestration spec，也不要求 Gemini 或 OpenAI 立即接管現有多阶段自治流程
- 首期不引入新的第三方 agent SDK；Gemini provider 优先复用現有文本/多模态调用能力，OpenAI/ChatGPT provider 优先复用現有 OpenAI 兼容能力与项目工具封装

## Decisions

### 决策 1：引入 AssistantRuntimeProvider 抽象，而不是在現有 Claude 分支上打补丁

建议新增统一 provider 接口，核心关注点为：

```text
Assistant API / UI
        |
        v
AssistantService
        |
        +-- AssistantRuntimeProvider (interface)
              |
              +-- ClaudeRuntimeProvider   [full]
              +-- GeminiLiteProvider      [lite]
              +-- OpenAILiteProvider      [lite]
```

接口至少覆盖：

- provider 标识与可用性检测
- 新建会话 / 继续会话
- 发送消息（文本，可選图片）
- 统一流式事件输出
- capability 暴露
- provider-specific 错误到统一错误模型的映射

**理由**：这样 Claude 保持现状，Gemini 与 OpenAI 都不必去拟态 Claude 的内部协议，只要实现共享 contract 即可。

### 决策 2：用能力矩阵和能力层级表达 provider 的边界

建议定义统一 capability 结构，例如：

```json
{
  "provider": "gemini-lite",
  "tier": "lite",
  "supports_streaming": true,
  "supports_images": true,
  "supports_tool_calls": true,
  "supports_interrupt": true,
  "supports_resume": false,
  "supports_subagents": false,
  "supports_permission_hooks": false
}
```

并补充一個面向项目业务的能力层级：

- `lite`：项目内问答、提示辅助、有限工具调用
- `workflow-grade`：项目状态检测、分阶段任务推进、受限子任务调度
- `full`：接近 Claude runtime 的长会话恢复、复杂 subagent、hook/permission 体系

前端与路由按 capability 决定：

- 是否显示 subagent / 高级模型路由说明
- 是否允许 resume 旧会话
- 是否展示"当前 provider 不支持此能力"的结构化提示

**理由**：Gemini 与 OpenAI 首期都无法等价支持 Claude full runtime，能力矩阵可以避免 API 与 UI 继续隐含"所有 provider 能力相同"的错误假设；能力层级则帮助团队判断项目真正需要补哪一层。

### 决策 3：Gemini 与 OpenAI 首期采用 bounded copilot，而不是自治型 agent

Gemini-lite 与 OpenAI-lite assistant 的目标形态：

- 支持项目内问答与创作辅助
- 支持读取项目上下文和必要文件
- 支持有限、白名单化工具调用
- 支持文本 + 图片输入
- 支持流式回复

首期明确不支持：

- subagent dispatch
- 长时恢复 resume / transcript replay parity
- Claude 风格 permission hooks
- 复杂工作流自治推进

这更接近"项目内 copilot"，而不是"自治型 workflow agent"。

**理由**：这是最小可行路线，能最早消除 Anthropic 单点依赖，同时不把项目拖进大规模 runtime 仿真；Gemini 与 OpenAI 都能先在这一层落地。

### 决策 4：将“本项目需要的 full”重定义为 workflow-grade，而不是 Claude parity

ArcReel 不是一般聊天产品，而是小说转短视频工作流系统。它真正需要的高阶能力主要是：

- 读取项目状态并判断当前工作流阶段
- 分阶段推进角色/线索、预处理、剧本生成、资产生成
- 触发受限的子任务执行并汇总结果

这类能力应被定义为 `workflow-grade`，它高于 lite，但不等于 Claude SDK 全套协议。

**理由**：这样可以把项目需要的产品能力与 Claude 专有 runtime 细节拆开，避免错误地把所有高阶需求都变成"必须复制 Claude"。

### 决策 5：系统配置语义从“Anthropic 必填”改为“当前 assistant provider 所需配置”

现状问题是把 assistant provider requirement 误表述成系统级 hard requirement。

调整后建议的语义：

- 若当前 assistant provider = `claude`，则 Anthropic key 为必需
- 若当前 assistant provider = `gemini-lite`，则 Gemini text/multimodal 所需配置为必需
- 若当前 assistant provider = `openai-lite`，则 OpenAI/ChatGPT 所需配置为必需
- 若系统仅使用 Gemini 或 OpenAI 生成链路且未启用 Claude assistant，则不应因为缺少 Anthropic 被标记为配置不完整

同时，设置页应显式区分：

- `生成能力配置`
- `助手 provider 配置`
- `当前激活 provider`
- `当前 provider 的 tier / capability`

### 决策 6：同步聊天端点保持稳定 URI，但改变内部路由语义

`POST /api/v1/agent/chat` 与現有 assistant session 相关端点不立即改 URI。

调整点在于：

- 路由先解析当前激活 provider
- 按 provider capability 决定是否允许某操作
- 对不支持的能力返回结构化 `unsupported_capability` 错误

这样可以降低前端迁移成本，并让 Claude、Gemini 与 OpenAI/ChatGPT 共用同一套 UI 通道。

## Architecture Sketch

```text
┌──────────────────────────────┐
│ Frontend Assistant Panel     │
│ - reads provider status      │
│ - reads capability matrix    │
└──────────────┬───────────────┘
               │
               v
┌──────────────────────────────┐
│ AssistantService             │
│ - normalize requests         │
│ - select active provider     │
│ - normalize stream events    │
└───────┬────────────────┬─────┘
        │                │
        v                v
┌──────────────┐   ┌──────────────┐
│ ClaudeRuntime│   │ GeminiLite   │   │ OpenAILite   │
│ [full]       │   │ [lite]       │   │ [lite]       │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
  │                  │                  │
  v                  v                  v
Claude Agent SDK     Gemini backend +   OpenAI backend +
transcripts/hooks    bounded tool exec  bounded tool exec
```

## Rollout Plan

### Phase 1

- 抽出 provider 接口
- 保持 Claude 为默认 provider
- 新增 provider 状态与 capability API 字段

### Phase 2

- 实作 GeminiLiteProvider 与 OpenAILiteProvider
- 打通同步对话、基础流式、图片输入、有限工具调用
- 前端按 capability 做降级显示

### Phase 3

- 优先补 ArcReel 真正需要的 workflow-grade 能力，如项目状态检测、分阶段推进与受限子任务调度
- 分别评估 Gemini 与 OpenAI 哪一侧更适合先承载 workflow-grade 能力

### Phase 4

- 再评估是否继续支持 Gemini 或 OpenAI 的 resume、长会话持久化、复杂 subagent 与更重的 runtime parity

## Workflow-grade Contract

ArcReel 真正需要补齐的不是 Claude 专属 hook 细节，而是可跨 provider 复用的 workflow-grade contract。该 contract 应至少包含：

- `inspect_project_state(project_name)`：读取项目、剧集、资产与任务状态，生成结构化阶段判断
- `plan_next_stage(project_state)`：基于当前阶段给出下一步可执行任务，而不是只返回自由文本建议
- `run_bounded_task(task_type, scope)`：执行受限子任务，如角色梳理、线索梳理、剧本预处理、分镜推进
- `emit_checkpoint(summary, artifacts)`：在关键阶段输出可回放的阶段总结，供前端与后续会话复用
- `list_supported_workflows()`：让前端明确当前 provider 支持哪些工作流动作，而不是默认所有按钮都可用

这一定义将 workflow-grade 能力限定在“项目状态感知 + 分阶段推进 + 受限执行”，避免重新落回 Claude SDK 的 permission hook / transcript parity 语义。

## Workflow-grade Provider Recommendation

首個 workflow-grade provider 建议优先選择 `gemini-lite` 对应的 Gemini 路线，而不是 OpenAI-lite。

理由如下：

- ArcReel 現有生成链路已经大量复用 Gemini 相关配置与能力，部署方更可能已有 Gemini 凭证
- Gemini 路线对项目内文本与多模态上下文的复用成本更低，更适合从“项目 copilot”演进到“工作流推进器”
- 对当前二开場景，Gemini-first 能更直接消除“只有 Gemini key 但 assistant 不能用”的核心痛点

OpenAI 仍然是有价值的第二条路线，主要优势在于通用 tool-calling 生态与 ChatGPT 兼容性；但从 ArcReel 的现状与迁移摩擦看，作为第二阶段补位更合理。

## Migration Notes

从单一 Claude runtime 迁移到多 provider assistant 后，运维与前端需要接受“能力按 provider 分层”的事实：

- `claude`：默认 provider，保留 full runtime，支持更完整的会话恢复、高阶自治与現有 Claude SDK 语义
- `gemini-lite`：支持项目内对话、文本/图片输入、基础流式与有限工具调用；不支持 full runtime 级别 resume / subagent
- `openai-lite`：支持项目内对话、文本输入、基础流式与有限工具调用；首期同样不承诺 Claude parity

迁移时应遵循以下原则：

- 現有 Anthropic 用户无需修改即可继续使用 Claude full runtime
- Gemini-only 或 OpenAI-only 部署需要先将 `assistant_provider` 切换到对应 provider，之后不应再被 Anthropic 缺失阻断
- 前端应基于 capability matrix 隐藏或禁用 unsupported 功能，而不是假设所有 provider 都支持 resume、subagent 与高级 hook

## Risks / Trade-offs

- **最大风险**：抽象层若直接照搬 Claude 概念，Gemini 与 OpenAI provider 仍会被迫拟态 Claude，抽象失效
- **产品取舍**：Gemini 与 OpenAI 首期能力较弱，用户会看到 provider 之间存在功能差异
- **兼容成本**：前端当前默认 assistant 能力完整可用，加入 capability matrix 后需补一轮显式分支
- **实现复杂度**：若试图在首期同时支持 subagent 和 resume，会显著放大工期与失敗概率

## Open Questions

- Gemini 与 OpenAI 的工具执行是完全由服务端 orchestration 驱动，还是允许模型返回结构化 tool intent 再由服务端执行？
- 現有 transcript / snapshot 数据结构是否需要允许 `provider=tier=lite` 的会话类型？
- 是否允许用户在 UI 中切换 active provider，还是首期仅允许系统配置中選择默认 provider？