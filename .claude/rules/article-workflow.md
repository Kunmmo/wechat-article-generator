# 文章生成工作流规则

当用户请求生成公众号文章时，遵循以下流程：

## 触发条件

- "写一篇关于 xxx 的公众号文章"
- "用三智能体模式生成内容"
- "启动辩论工作流"

## 执行流程

1. 读取 `agents/triagent-workflow/AGENT.md` 获取完整工作流
2. 依次执行各智能体角色
3. 使用 WebSearch 搜索时事（作为时事研究员时）
4. 输出 HTML 到 `outputs/articles/`

## 图片处理

- `[MEME: tag]` → 先检索 `memes/` 库，无匹配则调用 Gemini 生成
- `[IMG: description]` → 直接调用 Gemini 生成插图
