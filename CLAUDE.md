# WeChat Article Generator - Claude Code Instructions

This is a multi-agent article generation system for WeChat Official Accounts. The system uses multiple AI personas that debate and collaborate to produce high-quality content with appropriate imagery.

## Project Overview

- **Purpose**: Generate WeChat articles with depth and virality through multi-agent collaboration
- **Tech Stack**: Python scripts, CLIP for image retrieval, Gemini for image generation
- **Output**: HTML articles in WeChat Official Account style

## Agent System

The core system consists of multiple specialized agents defined in `agents/` directory:

| Agent | File | Role |
|-------|------|------|
| Workflow Controller | `agents/triagent-workflow/AGENT.md` | Orchestrates the entire workflow |
| News Researcher | `agents/news-researcher/AGENT.md` | Searches for current events using WebSearch |
| Deep Thinker | `agents/deep-thinker/AGENT.md` | Writes in-depth analysis (use DeepSeek) |
| Meme Master | `agents/meme-master/AGENT.md` | Adds internet culture and meme tags |
| Chief Editor | `agents/chief-editor/AGENT.md` | Balances depth and virality |
| Central Judge | `agents/central-judge/AGENT.md` | Evaluates quality, decides PASS/REVISE/POLISH |
| Article Renderer | `agents/article-renderer/AGENT.md` | Renders final HTML with images |
| Meme Retriever | `agents/meme-retriever/AGENT.md` | CLIP-based meme search |
| Image Generator | `agents/image-generator/AGENT.md` | Generates memes via Gemini |
| Illustration Generator | `agents/illustration-generator/AGENT.md` | Generates article illustrations |

## Workflow

When user requests article generation (e.g., "写一篇关于 AI 的公众号文章"):

1. Read `agents/triagent-workflow/AGENT.md` for complete workflow
2. Follow the multi-agent debate process
3. Use WebSearch for news when acting as News Researcher
4. Output HTML file to `outputs/articles/`

## Key Directories

```
agents/           # Agent definitions (read these for personas)
scripts/          # Python scripts for image processing
config/           # API configuration (gemini.json for image gen)
outputs/articles/ # Generated HTML articles
memes/            # Meme library with CLIP embeddings
```

## Important Instructions

1. **When generating articles**: Always start with `agents/triagent-workflow/AGENT.md`
2. **For image processing**: Use `scripts/render_article.py` 
3. **API Keys**: Never commit `config/gemini.json`, use `config/gemini.example.json` as template
4. **Language**: Output articles in Chinese (简体中文)

## Commands

```bash
# Build meme index
python scripts/download_hf_memes.py

# Generate image (called by agents)
python scripts/generate_image.py --prompt "..." --output "..." --type "meme"

# Render article with images
python scripts/render_article.py --input "article.md" --output "article.html"
```

## Style Guidelines

- Write content in Chinese
- Use conversational tone for Meme Master sections
- Use academic tone for Deep Thinker sections
- Balance depth with readability in final output
