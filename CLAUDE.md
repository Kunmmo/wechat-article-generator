# WeChat Article Generator - Claude Code Instructions

This is a multi-agent article generation system for WeChat Official Accounts. The system uses multiple AI personas that debate and collaborate to produce high-quality content with appropriate imagery.

## Project Overview

- **Purpose**: Generate WeChat articles with depth and virality through multi-agent collaboration
- **Tech Stack**: Python scripts, CLIP for image retrieval, Gemini/SD for image generation
- **Output**: HTML articles in WeChat Official Account style
- **Architecture**: Inspired by Claude Code patterns (query loop, tool abstraction, context compression, coordinator mode)

## Agent System

| Agent | File | Role |
|-------|------|------|
| Coordinator | `agents/coordinator/AGENT.md` | Dynamic orchestration via [DISPATCH] protocol (v3.0) |
| Workflow Controller | `agents/triagent-workflow/AGENT.md` | Legacy static workflow definition |
| News Researcher | `agents/news-researcher/AGENT.md` | Searches for current events |
| Deep Thinker | `agents/deep-thinker/AGENT.md` | Writes in-depth analysis |
| Meme Master | `agents/meme-master/AGENT.md` | Adds internet culture and meme tags |
| Chief Editor | `agents/chief-editor/AGENT.md` | Balances depth and virality |
| Central Judge | `agents/central-judge/AGENT.md` | Evaluates quality, decides PASS/REVISE/POLISH |
| Article Renderer | `agents/article-renderer/AGENT.md` | Renders final HTML with images |

## Workflow Modes

### Coordinator Mode (v3.0 — recommended)

LLM-driven dynamic orchestration. The coordinator agent decides which workers to dispatch and when.

```bash
python scripts/coordinator_workflow.py --topic "AI 发展趋势" --max-rounds 3
```

### Legacy Mode (v2.1)

Hard-coded sequential pipeline with debate loop.

```bash
python scripts/run_workflow.py --topic "AI 发展趋势" --max-rounds 3
```

### Web Interface

```bash
python scripts/web_app.py --port 5000
```

## Architecture (Claude Code-inspired)

```
scripts/
├── query_engine.py          # Loop-based agent engine (inspired by query.ts)
├── coordinator_workflow.py  # Coordinator-driven workflow (v3.0)
├── run_workflow.py          # Legacy workflow runner (v2.1)
├── model_router.py          # Resilient LLM router (retry + circuit breaker + fallback)
├── events.py                # Typed event bus (replaces print monkey-patch)
├── tools/                   # Tool abstraction layer (inspired by Tool.ts)
│   ├── base.py              # ToolSpec, ToolResult, ToolContext
│   ├── registry.py          # Ordered tool registry
│   ├── executor.py          # Parallel/serial tool executor
│   └── implementations.py   # Concrete tool wrappers
├── context/                 # Context window management (inspired by compact/)
│   └── manager.py           # Three-layer compression (micro → auto → full)
├── render_article.py        # HTML/Markdown rendering + image processing
├── evaluate_articles.py     # Quantitative evaluation pipeline
├── clip_score.py            # CLIP Score evaluation
├── vqa_score.py             # VQA Score evaluation
├── gemini_client.py         # Unified Gemini/SD image generation
└── meme_retrieval.py        # CLIP-based meme retrieval (OpenCLIP + CN-CLIP)
```

## Key Directories

```
agents/           # Agent definitions (read these for personas)
scripts/          # Core Python modules
config/           # API configuration (models.json, gemini.json)
outputs/articles/ # Generated HTML articles
memes/            # Meme library with CLIP embeddings
```

## Important Instructions

1. **When generating articles**: Use `coordinator_workflow.py` (v3.0) or `run_workflow.py` (v2.1)
2. **For image processing**: Use `scripts/render_article.py`
3. **API Keys**: Never commit `config/models.json` or `config/gemini.json`
4. **Language**: Output articles in Chinese (简体中文)

## Commands

```bash
# Coordinator workflow (recommended)
python scripts/coordinator_workflow.py --topic "..." --max-rounds 3

# Legacy workflow
python scripts/run_workflow.py --topic "..." --max-rounds 3

# Web interface
python scripts/web_app.py --port 5000

# Build meme index
python scripts/download_hf_memes.py

# Generate image
python scripts/generate_image.py --prompt "..." --output "..." --type "meme"

# Evaluate article
python scripts/evaluate_articles.py --input "article.html" --output "report.json"
```

## Style Guidelines

- Write content in Chinese
- Use conversational tone for Meme Master sections
- Use academic tone for Deep Thinker sections
- Balance depth with readability in final output
