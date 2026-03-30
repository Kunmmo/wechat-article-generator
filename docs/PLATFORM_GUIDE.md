# 多平台配置指南

本项目的智能体系统支持多种 AI 编程平台。本指南说明如何在不同平台上配置和使用。

## 目录

- [Cursor](#cursor)
- [Claude Code](#claude-code)
- [GitHub Copilot](#github-copilot)
- [Windsurf (Codeium)](#windsurf)
- [Aider](#aider)
- [通用方式](#通用方式)

---

## Cursor

Cursor 支持两种方式加载智能体规则：

### 方式 1：Skills（推荐）

Skills 位于 `.cursor/skills/` 目录，每个智能体一个子目录。

```
.cursor/skills/
├── triagent-workflow/
│   └── SKILL.md
├── deep-thinker/
│   └── SKILL.md
└── ...
```

**使用方法**：
- 在对话中输入 `@deep-thinker` 或 `@triagent-workflow` 触发
- Skills 会自动被 Cursor 识别

### 方式 2：Rules

Rules 位于 `.cursor/rules/` 目录，使用 `.mdc` 格式。

```
.cursor/rules/
├── triagent-workflow.mdc
├── deep-thinker.mdc
└── ...
```

**自动配置**：
```bash
# 运行配置脚本
./scripts/setup_platform.sh cursor
```

---

## Claude Code

Claude Code（Anthropic 官方 CLI 工具）识别项目根目录的 `CLAUDE.md` 文件和 `.claude/` 目录。

### 配置文件

```
CLAUDE.md                      # 主配置文件
.claude/
├── CLAUDE.md                  # 备选位置（与根目录等效）
├── settings.local.json        # 本地设置（权限、偏好）
└── rules/                     # 分类规则
    ├── article-workflow.md    # 文章工作流规则
    └── code-style.md          # 代码风格规则
agents/                        # 智能体定义目录
├── */AGENT.md                 # 各智能体详细定义
```

**自动配置**：
```bash
./scripts/setup_platform.sh claude
```

### 使用方法

```bash
# 启动 Claude Code
claude

# 触发工作流
> 请阅读 @agents/triagent-workflow/AGENT.md 并写一篇关于 AI 的公众号文章
```

### 高级配置

`.claude/settings.local.json` 可配置：
- `permissions.allow` - 允许的操作
- `permissions.deny` - 禁止的操作
- `preferences` - 用户偏好

---

## GitHub Copilot

GitHub Copilot 通过 `.github/copilot-instructions.md` 和路径特定指令提供项目级指导。

### 配置文件

```
.github/
├── copilot-instructions.md          # 全局 Copilot 指令
└── instructions/                    # 路径特定指令
    ├── agents.instructions.md       # agents/ 目录专用规则
    └── scripts.instructions.md      # scripts/ 目录专用规则
AGENTS.md                            # Copilot 也会读取此文件
```

**路径特定指令格式**：
```markdown
---
applyTo: "agents/**/*.md"
---
# 规则内容...
```

**自动配置**：
```bash
./scripts/setup_platform.sh copilot
```

### 使用方法

在 VS Code 中：
1. 打开 Copilot Chat
2. 输入 `@workspace 写一篇关于 AI 的公众号文章`
3. Copilot 会参考 instructions 和 agents 目录

### 注意事项

- 代码审查功能仅读取前 4000 字符
- 建议保持指令文件在 1000 行以内

---

## Windsurf

Windsurf（Codeium）使用 `.windsurfrules` 文件配置项目规则。

### 配置文件

```
.windsurfrules    # Windsurf 规则文件
```

**自动配置**：
```bash
./scripts/setup_platform.sh windsurf
```

### 使用方法

在 Windsurf 中正常对话，智能体规则会自动加载。

---

## Aider

Aider 使用 `.aider.conf.yml` 或通过 `--read` 参数加载规则。

### 配置方式

**方式 1**：在 `.aider.conf.yml` 中配置
```yaml
read:
  - AGENTS.md
  - agents/triagent-workflow/AGENT.md
```

**方式 2**：命令行参数
```bash
aider --read AGENTS.md --read agents/triagent-workflow/AGENT.md
```

**自动配置**：
```bash
./scripts/setup_platform.sh aider
```

---

## 通用方式

对于其他 AI 工具，可以直接引用 `agents/` 目录：

1. **复制粘贴**：将 `agents/triagent-workflow/AGENT.md` 内容粘贴给 AI
2. **文件引用**：让 AI 读取 `AGENTS.md` 或具体智能体文件
3. **System Prompt**：将智能体定义作为系统提示词

---

## 配置脚本

提供一键配置脚本 `scripts/setup_platform.sh`：

```bash
# 查看支持的平台
./scripts/setup_platform.sh --help

# 配置所有平台
./scripts/setup_platform.sh all

# 配置特定平台
./scripts/setup_platform.sh cursor
./scripts/setup_platform.sh claude
./scripts/setup_platform.sh copilot
./scripts/setup_platform.sh windsurf
./scripts/setup_platform.sh aider
```

---

## 平台支持矩阵

| 特性 | Cursor | Claude Code | Copilot | Windsurf | Aider |
|------|--------|-------------|---------|----------|-------|
| 自动加载规则 | ✅ | ✅ | ✅ | ✅ | ❌ |
| 智能体引用 (@) | ✅ | ✅ | ✅ | ❌ | ❌ |
| 多轮对话上下文 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 工具调用 (MCP) | ✅ | ✅ | ❌ | ❌ | ❌ |
| WebSearch | ✅ | ✅ | ❌ | ❌ | ❌ |
| 文件编辑 | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 常见问题

### Q: 智能体没有被识别？

1. 确认配置文件位置正确
2. 运行 `./scripts/setup_platform.sh <platform>` 重新配置
3. 重启 IDE 或 AI 工具

### Q: 不同平台的智能体表现不同？

这是正常的，因为：
- 不同平台使用的底层模型不同
- 上下文窗口大小不同
- 工具调用能力不同

建议根据平台特点调整使用方式。

### Q: 如何添加新的智能体？

1. 在 `agents/` 目录创建新文件夹
2. 添加 `AGENT.md` 文件
3. 运行 `./scripts/setup_platform.sh all` 同步到所有平台
