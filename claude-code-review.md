# Claude Code 源码深度分析报告

## 一、项目概述与目标

这是 `@anthropic-ai/claude-code` 的完整源码快照——Anthropic 官方的 **AI 编程 CLI 平台**。它不是一个简单的聊天 wrapper，而是一个 **完整的 AI 驱动的软件工程代理系统**，运行在终端中，能够理解代码库、执行命令、编辑文件、管理多个并行子代理，并具备记忆、权限控制、上下文压缩等完备的工程化能力。

---

## 二、模块架构全景

### 顶层目录结构

| 目录/文件                                                     | 职责                                           |
| ------------------------------------------------------------- | ---------------------------------------------- |
| `src/`                                                      | CLI 核心源码（~2000+ 文件）                    |
| `web/`                                                      | Next.js 14 Web UI（独立应用）                  |
| `mcp-server/`                                               | MCP Explorer 服务器                            |
| `scripts/`                                                  | 构建（esbuild+Bun）、测试、开发脚本            |
| `docs/`                                                     | 架构文档                                       |
| `<span class="md-inline-path-filename">package.json</span>` | 主包 `@anthropic-ai/claude-code`，Bun 运行时 |

### `src/` 内部核心模块拆解

src/

├── entrypoints/cli.tsx    # 入口：Commander CLI 定义，分发到各运行模式

├── main.tsx               # 主流程：认证、配置、MCP/插件初始化、启动 REPL

├── query.ts               # ⭐ 核心查询循环：模型调用 → 工具执行 → 追踪 → 压缩

├── QueryEngine.ts         # SDK/无头模式的会话包装器

├── Tool.ts                # ⭐ 工具抽象层（类型定义 + buildTool 构建器）

├── tools.ts               # 工具注册表（getAllBaseTools + 过滤 + MCP 合并）

├── commands.ts            # 斜杠命令注册（/compact、/doctor 等）

│

├── tools/                 # 184 个文件，每个工具一个目录

│   ├── BashTool/          # Shell 命令执行

│   ├── FileEditTool/      # 文件编辑（精确替换）

│   ├── FileReadTool/      # 文件读取

│   ├── FileWriteTool/     # 文件写入

│   ├── GrepTool/          # ripgrep 搜索

│   ├── GlobTool/          # 文件匹配

│   ├── AgentTool/         # ⭐ 子代理生成（本地/远程/进程内/swarm）

│   ├── ToolSearchTool/    # 延迟加载工具搜索

│   └── ...                # NotebookEdit、WebFetch 等 20+ 工具

│

├── services/              # 服务层（非框架，函数库模式）

│   ├── api/               # ⭐ Anthropic API 客户端（支持 Bedrock/Vertex/Foundry）

│   ├── compact/           # ⭐ 上下文压缩（autoCompact + microCompact + 全量压缩）

│   ├── tools/             # ⭐ 工具编排 + 流式工具执行器

│   ├── PromptSuggestion/  # ⭐ 推测执行（Speculation）

│   ├── mcp/               # MCP 客户端管理

│   ├── plugins/           # 插件生命周期

│   ├── SessionMemory/     # 会话记忆

│   └── analytics/         # 遥测 + GrowthBook 实验

│

├── state/                 # 全局状态管理（自研 Store + React useSyncExternalStore）

├── coordinator/           # 多代理协调器模式（Prompt 工程）

├── tasks/                 # 后台任务（Local/Remote/InProcess Agent、Shell、Dream）

├── bridge/                # IDE ↔ CLI 双向通信（REST poll + WebSocket）

├── hooks/                 # React hooks + 会话钩子 + 工具权限处理器

├── utils/

│   ├── permissions/       # ⭐ 多层权限系统

│   ├── swarm/             # ⭐ 多代理 Swarm（tmux/iTerm/进程内）

│   ├── ultraplan/         # 远程规划功能

│   └── ...

│

├── memdir/                # CLAUDE.md 记忆体系

├── skills/                # 技能系统（SKILL.md 加载、条件激活）

├── components/            # ~389 个 Ink 终端 UI 组件

├── screens/               # REPL、Doctor、ResumeConversation 三大屏幕

├── voice/                 # 语音输入（Feature Flag 控制）

├── buddy/                 # 伴侣系统（彩蛋特性）

├── vim/                   # Vim 模式

├── plugins/               # 内置插件框架

└── constants/prompts.ts   # ⭐ 系统提示词构建

---

## 三、核心系统深度剖析

### 1. 查询循环（Query Loop）—— 心脏

`<span class="md-inline-path-filename">query.ts</span>` 是整个系统的核心引擎，实现了一个 **多步骤 Agent 循环**：

while (true) {

1. 预算管理（applyToolResultBudget）
2. 上下文压缩判断（autocompact / microcompact / context collapse）
3. 调用模型（callModel → streaming）
4. 流式工具执行（tool_use 出现即开始执行，与生成并行）
5. 收集工具结果 → 追加到消息列表
6. 判断是否需要后续轮次（needsFollowUp）
7. 处理停止条件（token 耗尽、PTL 恢复、用户中断）

}

**关键技术点**：

* **流式工具并行执行**：不等模型生成完毕，`tool_use` 块出现即通过 `StreamingToolExecutor` 开始执行
* **并发安全分区**：`isConcurrencySafe` 的工具可并行，非安全工具串行执行
* **自动上下文压缩**：当 token 接近阈值时自动触发摘要，维持无限对话

### 2. 流式工具执行器（StreamingToolExecutor）—— 性能关键

这是最具技术深度的组件之一：

* 模型 **生成 token 的同时**，已完成解析的 `tool_use` 块立即进入执行队列
* 并发安全的工具（如 `GrepTool`、`GlobTool`、只读 Bash）**并行运行**，上限 10 个
* 非安全工具（如文件编辑）**阻塞队列**直到完成
* Bash 执行出错时通过 `siblingAbortController` **取消同批兄弟任务**
* 支持 `discard()` 在模型回退（streaming fallback）时安全丢弃进行中的工具

### 3. 上下文窗口管理（Context Window Management）—— 核心壁垒

三层压缩机制：

| 层级                   | 机制                                                                                                            | 作用                                            |
| ---------------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| **MicroCompact** | 请求前裁剪旧 tool_result                                                                                        | 增量减少 token 消耗，利用 API cache editing     |
| **AutoCompact**  | 阈值触发自动摘要                                                                                                | 对话中期自动压缩，保持 13k buffer               |
| **Full Compact** | `<span class="md-inline-path-prefix">/</span><span class="md-inline-path-filename">compact</span>` 或自动触发 | 完整摘要 + 后置附件（文件/计划/技能/MCP delta） |

**技术亮点**：

* 压缩后保留 `preCompactDiscoveredTools`，确保 ToolSearch 状态跨压缩存活
* PTL（Prompt Too Long）恢复：`truncateHeadForPTLRetry` 逐步删除最旧的 API 轮次
* 断路器设计：连续 3 次压缩失败后停止重试
* **缓存友好的系统提示词分割**：`SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 将静态部分（跨组织可缓存）与动态部分分离

### 4. 系统提示词工程（System Prompt Engineering）

提示词不是一个固定字符串，而是一个 **精密的多段构建系统**：

[静态前缀 - 跨会话可缓存]

  身份定义 → 系统规则 → 任务执行 → 行为准则 → 工具使用 → 风格规范

[DYNAMIC BOUNDARY - prompt cache 分割线]

[动态后缀 - 会话特定]

  会话引导 → 记忆(CLAUDE.md) → 环境信息 → MCP 指令 → 输出风格 → Token 预算

* 通过 `systemPromptSection` 实现 **段级缓存**（除 `<span class="md-inline-path-prefix">/</span><span class="md-inline-path-filename">clear</span>` 或 `<span class="md-inline-path-prefix">/</span><span class="md-inline-path-filename">compact</span>` 外不重新计算）
* `DANGEROUS_uncachedSystemPromptSection` 用于必须每轮重算的内容
* 协调器模式、Agent 模式、自定义指令通过 `buildEffectiveSystemPrompt` 层叠组合

### 5. 多代理架构（Multi-Agent Architecture）—— 杀手特性

这是 Claude Code 最复杂也最有竞争优势的系统：

**Agent Tool 统一入口**，根据参数分派到不同路径：

AgentTool

├── 普通子代理（runAgent → query 循环）

├── Fork 子代理（共享 prompt cache 前缀，实验性）

├── Swarm 队友（tmux/iTerm 多窗格 或 进程内）

│   ├── 文件邮箱通信（~/.claude/teams/{team}/inboxes/）

│   ├── 权限同步（permissionSync.ts）

│   └── 进程内运行器（inProcessRunner.ts）

├── 远程代理（teleportToRemote → CCR 会话）

├── Worktree 隔离代理（createAgentWorktree）

└── 异步代理（registerAsyncAgent → `<task-notification>` XML 回报）

**协调器模式**是纯 Prompt 工程——没有独立调度进程，而是通过精心设计的系统提示词让模型自主编排 worker：

* Worker 通过 `<task-notification>` XML 向 Coordinator 汇报
* Coordinator 可并行派发研究任务、综合规划
* 每个 Worker 有独立的工具列表和 MCP 访问权限

### 6. 权限系统（Permission System）—— 安全基石

多层防御架构：

工具调用 → Deny规则匹配 → Ask规则匹配 → tool.checkPermissions()

    → 安全检查(bypass-immune) → bypassPermissions模式

    → alwaysAllow规则 → Auto模式分类器

    → acceptEdits快速路径 → YOLO分类器(classifyYoloAction)

    → 交互式权限请求 → Hook/Bridge/Channel 三方竞速

* **四种模式**：`default`（询问）、`plan`（只读）、`bypassPermissions`（绕过）、`auto`（AI 分类器自动决定）
* **Bash 推测性分类**：在工具执行前 **提前启动** 分类器，减少等待延迟
* **Swarm 权限同步**：Worker 的权限请求可转发给 Leader
* **拒绝追踪**：多次拒绝后自动切换到提示模式

### 7. 推测执行（Speculation）—— 延迟优化

用户输入提示建议 → startSpeculation

  → 创建临时 overlay 目录

  → 运行 forked agent（只允许安全只读工具）

  → 在文件编辑边界停止

  → 用户接受 → acceptSpeculation → 合并 overlay 到工作目录

  → 用户拒绝 → abortSpeculation → 丢弃

---

## 四、技术壁垒分析

### 壁垒 1：**上下文窗口智能管理（Context Intelligence）**

这是 Claude Code 最难复制的核心能力。三层压缩机制 + prompt cache 友好的分段设计 + PTL 自动恢复 + 工具结果预算管理，构成了一个 **自适应的上下文生命周期管理系统**。其他平台通常只有简单的截断或单层摘要，无法在保持上下文连贯性的同时最大化利用 token 预算。

### 壁垒 2：**流式工具并行执行引擎**

模型生成与工具执行 **交织并行** 的架构，将每轮交互的端到端延迟压到最低。加上并发安全分区、错误传播（sibling abort）、中断行为控制（cancel vs block），这是一个经过深度工程优化的执行引擎。复制这种程度的并行化需要对 Anthropic API 的流式行为有极深的理解。

### 壁垒 3：**多代理编排系统（Multi-Agent Orchestration）**

从单一 `AgentTool` 统一入口，分派到本地/远程/进程内/Swarm 多种执行后端，加上文件邮箱通信、tmux 多窗格管理、权限跨代理同步、`<task-notification>` XML 汇报协议——这是一个 **完整的分布式代理操作系统**。其他平台至今还在做单代理 loop。

### 壁垒 4：**Prompt 工程的系统化**

Claude Code 的系统提示词不是手写的静态字符串，而是一个 **可编程的、缓存友好的、多层叠加的提示词框架**。段级缓存、动态/静态分区、记忆注入、技能条件激活、MCP 增量更新（delta attachments）、协调器/Agent/自定义指令的层叠规则——这种工程化程度远超任何竞品。

### 壁垒 5：**模型-产品垂直整合**

Claude Code 由 Anthropic 自身构建，与 Claude 模型 **深度绑定**：

* `tool_reference` / `defer_loading` 等 **模型级特性** 直接集成到工具搜索系统
* `cache_deleted_input_tokens` 等 API 特有能力驱动 microcompact
* Beta API features（prompt caching scopes、tool search beta headers）第一时间使用
* 模型的 `tool_use` 流式行为被精确利用做并行执行
* 支持 Bedrock / Vertex / Foundry 等多后端，但核心优化针对原生 API

---

## 五、与竞品对比分析

### 对比矩阵

| 能力维度               | Claude Code                             | Cursor                     | GitHub Copilot | Windsurf | Aider         |
| ---------------------- | --------------------------------------- | -------------------------- | -------------- | -------- | ------------- |
| **多代理协作**   | Swarm + Coordinator + 远程代理          | 单代理 + background agents | 单代理         | 单代理   | 无            |
| **上下文压缩**   | 三层自适应 + cache editing              | 基础摘要                   | 有限窗口       | 有限     | 基础 repo map |
| **流式工具并行** | tool_use 级并行 + 安全分区              | 有但较简单                 | 无             | 基础     | 无            |
| **权限系统**     | 四模式 + 分类器 + 推测 + 多方竞速       | 基础确认                   | 基础           | 基础     | 无            |
| **模型整合深度** | 原生 API + Beta features + prompt cache | 多模型但无深度绑定         | GPT 绑定但较浅 | 多模型   | 多模型        |
| **CLI 原生**     | 是（终端优先）                          | IDE 插件                   | IDE 插件       | IDE      | CLI           |
| **推测执行**     | 完整 overlay + 安全边界                 | 有 tab completion          | 无             | 部分     | 无            |
| **记忆系统**     | CLAUDE.md 层级 + 侧查询召回             | .cursorrules               | 无             | 有限     | 有限          |
| **MCP 生态**     | 原生支持 + 工具延迟加载                 | 支持                       | 无             | 无       | 无            |
| **开放性**       | SDK + CLI + Bridge + Web                | 闭源 IDE                   | 闭源           | 闭源     | 开源          |

### 其他平台的优势

* **Cursor**：IDE 原生体验更流畅，代码补全延迟更低，多模型切换自由度高，UI/UX 对普通开发者更友好
* **GitHub Copilot**：GitHub 生态整合最深，PR/Issue/Actions 无缝衔接，用户基数最大
* **Windsurf**：IDE 体验打磨精细，Flow 模式交互创新
* **Aider**：完全开源，社区驱动，repo-map 技术独特

### 其他平台无法超越的根本原因

**1. 模型-平台的垂直整合不可复制**

Claude Code 是 Anthropic 的 **第一方产品**。它能使用尚未公开的 Beta API（`tool_reference`、`defer_loading`、`cache_deleted_input_tokens`、prompt caching scopes），能针对 Claude 的 `tool_use` 流式行为做纳米级优化。第三方平台永远只能使用公开 API，无法达到这种深度。

**2. 工程复杂度的积累壁垒**

这不是一个可以在几个月内重写的项目。光 `src/` 就有 2000+ 文件，涵盖：

* 完整的终端 UI 框架（389 个 Ink 组件）
* 自研状态管理系统
* 多后端多代理运行时
* 三层上下文压缩
* 四模式权限系统 + AI 分类器
* 技能/插件/MCP 三合一扩展体系
* 文件邮箱 + 权限同步的分布式代理通信

每个子系统都经过大量边界条件处理和故障恢复设计。这是 **数十人年的工程积累**。

**3. Agentic Loop 的细节魔鬼**

看似简单的「调用模型 → 执行工具 → 循环」，在实践中充满了需要精确处理的边界：

* 流式中 tool_use 解析不完整怎么办？（`discard()` + 重建执行器）
* 压缩后 ToolSearch 的发现状态丢失怎么办？（`preCompactDiscoveredTools` 保存到 boundary metadata）
* 并行工具中一个失败另一个还在跑怎么办？（sibling abort controller）
* 用户中断时工具正在写文件怎么办？（`interruptBehavior` per-tool 配置）
* 远程代理断连后如何恢复？（reconnection + session event polling）

这些问题只有在大规模实际使用中才会暴露，解决方案需要对整个系统有全局理解。

**4. 数据飞轮**

Claude Code 的遥测系统（GrowthBook 实验、Datadog 指标、permissionLogging、分类器 token/cost 追踪）为 Anthropic 提供了 **独一无二的真实编程场景数据**，持续驱动模型和产品优化。其他平台的数据只能优化 wrapper，不能优化底层模型。

---

## 六、总结

Claude Code 的源码揭示了一个 **远超"AI Chat + 工具调用"的完整 Agent 操作系统**。它的核心竞争力不在于某一个单点创新，而在于 **系统级的工程深度**——从 token 级的流式并行优化，到上下文窗口的自适应生命周期管理，到多代理分布式编排，再到与模型 API 的毫秒级精确对接。这些能力形成了一个相互咬合的技术壁垒矩阵，使得任何单一维度的追赶都无法撼动其整体优势。


## 一、核心设计哲学

### 1. Agent Loop 是心脏，不是装饰

最核心的架构范式是 **循环式自主决策**，而非单次请求-响应：

while (not_done) {

  context_management()   // 管理有限资源

  model_call()           // 决策

  tool_execution()       // 行动

  result_collection()    // 观察

  continuation_check()   // 元决策：继续还是停止

}

**通用原则：** 任何 Agent 产品的核心价值都在这个循环的"质量"——不是模型有多强，而是循环的每一步有多鲁棒。你需要为每一步设计：正常路径、异常路径、中断路径、恢复路径。

### 2. 有限资源的生命周期管理

Context window 是 Agent 的"工作内存"，它是有限的。Claude Code 的三层压缩（Micro → Auto → Full）体现了一个通用原则：

> **对稀缺资源实施分级回收策略，而非一刀切。**

这适用于任何有限资源：

* Token 预算 → 分级压缩
* API 调用配额 → 分级降级
* 用户注意力 → 渐进式信息展示
* 计算资源 → 动态调度

**通用模式：** 设计一个"资源压力感知器"，在不同压力水平触发不同策略，从轻量级（裁剪旧数据）到重量级（全量摘要重建）。

### 3. 流式并行 = 延迟是产品体验的生命线

Claude Code 的流式工具执行器揭示了一个关键洞察：

> **用户感知延迟 ≠ 实际计算时间，而 ≈ 关键路径上最长的串行环节。**

通用技术方案：

* **生成与执行交织：** 不等全部计划完成就开始执行已确定的部分
* **安全分区并发：** 将操作分为"可并行"和"必须串行"两类，只对后者加锁
* **推测执行（Speculation）：** 在用户确认前预计算可能的下一步，确认后直接合并

---

## 二、通用技术架构模式

### 4. 工具抽象层（Tool Abstraction）

interfaceTool{

name:string

description:string// 给模型看

parameters:JSONSchema// 输入约束

checkPermissions():Result// 安全门控

execute(input):Result// 实际执行

interruptBehavior:'cancel'|'block'// 中断策略

concurrencySafe:boolean// 并发安全标记

}

**通用原则：** 工具不只是"函数"，它是一个带有元数据的 **策略对象**。每个工具需要声明：

* 它做什么（给模型决策用）
* 它需要什么权限（安全层用）
* 它能否并行（调度器用）
* 被中断时怎么处理（生命周期管理用）

### 5. 多层权限系统

Claude Code 的四模式权限设计体现了通用的安全架构原则：

请求 → 静态规则匹配（Deny/Allow 列表）

    → 工具自检（checkPermissions）

    → 动态分类（AI 分类器判断风险等级）

    → 用户确认（兜底）

**通用原则：**

* **白名单兜底：** 默认拒绝，明确允许
* **分级信任：** 不是 yes/no，而是"确定安全 / 可能安全需分类 / 必须问用户"
* **推测性分类：** 在等待执行结果的同时预判下一步的权限需求，减少串行等待
* **权限可记忆：** 用户的授权决策可持久化为规则，减少重复打扰

### 6. Prompt 工程的系统化

> **系统提示词不是"写"出来的，是"编译"出来的。**

通用架构：

SystemPrompt =

  Static(identity + rules + capabilities)       // 可跨会话缓存

+ Dynamic(memory + environment + context)     // 每次会话重算
+ Conditional(skills + plugins + mode)        // 条件激活

关键设计点：

* **缓存友好分割：** 把不变部分前置，变化部分后置，利用 prefix caching 降成本
* **段级管理：** 每段有独立的生命周期（有的每轮更新，有的只初始化一次）
* **可组合叠加：** 不同模式（协调器/Agent/自定义）的 prompt 通过规则叠加而非替换

### 7. 记忆体系的分层设计

即时记忆: 当前对话上下文（受 context window 限制）

会话记忆: CLAUDE.md / 项目级规则（每次对话开始加载）

持久记忆: 用户偏好、历史决策（跨会话存活）

外部记忆: MCP 连接的外部知识源（按需查询）

**通用原则：** 模仿人类记忆的分层——工作记忆小而快，长期记忆大而慢，中间有"巩固"机制（压缩/摘要就是巩固）。

---

## 三、工程实践哲学

### 8. 优雅降级而非崩溃

报告中反复出现的模式：

* PTL（Prompt Too Long）→ 不崩溃，自动截断重试
* 压缩失败 → 断路器设计（3次失败后停止）
* 远程代理断连 → 重连 + 事件轮询恢复
* 并行工具失败 → sibling abort 取消相关任务

**通用原则：** 每个可能失败的环节都需要设计 **降级路径**，而且降级路径本身也需要降级路径（级联兜底）。

### 9. 可观测性内建（Observability as First-Class）

遥测不是事后加的，而是架构的一部分：

* 每次工具调用的 token 消耗、延迟、成功率
* 分类器决策的准确率追踪
* 权限请求的模式分析
* 实验框架（A/B Testing）内建

**通用原则：** 在 Agent 系统中，你无法单靠单元测试保证质量——因为模型行为是非确定性的。必须通过 **运行时可观测性** 来理解系统实际表现并驱动迭代。

### 10. 扩展性三合一

Claude Code 的扩展体系：

* **Skills（技能）：** 条件激活的专家知识包
* **Plugins（插件）：** 生命周期钩子式扩展
* **MCP（协议）：** 标准化外部工具/数据源接入

**通用原则：** 扩展性不是"开个接口"就行，需要在三个维度提供扩展点：

* **知识扩展：** 如何让系统获得新领域知识（不重训模型）
* **能力扩展：** 如何让系统获得新工具/动作
* **行为扩展：** 如何让用户自定义系统的决策逻辑

---

## 四、多代理系统设计原则

### 11. 统一入口 + 多后端分派

AgentTool（统一接口）

  → 路由逻辑（根据任务特征选择后端）

    → 本地进程（轻量快速）

    → 远程服务（重型计算）

    → 隔离环境（安全敏感）

    → Swarm 集群（并行协作）

**通用原则：** 对上层（模型决策层）暴露统一的"启动子代理"接口，将调度复杂性封装在路由层。模型不需要知道子代理跑在哪里，只需要描述任务。

### 12. 通信协议标准化

Claude Code 用 `<task-notification>` XML 和文件邮箱实现代理间通信。

**通用原则：**

* 代理间通信需要 **结构化协议**，不能依赖自由文本
* 异步通信优于同步（文件邮箱/消息队列 vs 直接调用）
* 通信内容应包含：状态（进行中/完成/失败）+ 结果摘要 + 元数据

---

## 五、产品层面的通用启示

### 13. CLI-First 不是限制，是优势

* 终端环境天然适合 Agent：输入输出都是文本，无需复杂 UI 渲染
* 开发者工具的信任链：CLI → SDK → IDE 插件 → Web UI（由底向上构建）
* 可编程性：CLI 天然支持管道、脚本、自动化

### 14. 渐进式信任模型

用户对 AI Agent 的信任需要逐步建立：

手动确认每步 → 记住常见允许 → 自动分类低风险操作 → 全自动模式

**通用原则：** 不要试图一开始就让用户完全信任 Agent。提供一个"信任刻度盘"，让用户按自己的节奏调节自主度。

---

## 总结：构建 AI Agent 产品的核心公式

优秀的 Agent 产品 =

  鲁棒的循环引擎（容错 + 恢复 + 降级）

  × 智能的资源管理（分级压缩 + 缓存优化）

  × 流式并行执行（最小化用户感知延迟）

  × 分层安全模型（权限 + 分类 + 渐进信任）

  × 可编程的 Prompt 框架（缓存友好 + 可组合）

  × 运行时可观测性（遥测 + 实验 + 数据飞轮）

这些是不依赖于特定模型、特定 API 的 **通用工程原则**。即使你用的是 GPT、Gemini 或开源模型，这些架构模式仍然适用——差异只在于具体实现的深度和与模型特性的适配程度。
