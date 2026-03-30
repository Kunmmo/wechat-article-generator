# GitHub Copilot Instructions

## Project: WeChat Article Generator (微信公众号文章生成器)

This is a multi-agent system for generating WeChat Official Account articles with intelligent meme and illustration integration.

## Architecture

The system uses a multi-agent debate workflow where different AI personas collaborate:

1. **News Researcher** (`agents/news-researcher/`) - Searches current events
2. **Deep Thinker** (`agents/deep-thinker/`) - Writes in-depth analysis
3. **Meme Master** (`agents/meme-master/`) - Adds internet culture, marks `[MEME: tag]`
4. **Chief Editor** (`agents/chief-editor/`) - Balances depth and virality
5. **Central Judge** (`agents/central-judge/`) - Quality control, decides workflow direction
6. **Article Renderer** (`agents/article-renderer/`) - Generates final HTML

## Code Style

- Python code follows PEP 8
- Use type hints for function parameters
- Comments in Chinese or English are both acceptable
- Prefer f-strings for string formatting

## Key Files

- `agents/*/AGENT.md` - Agent persona definitions
- `scripts/generate_image.py` - Gemini image generation
- `scripts/meme_retrieval.py` - CLIP-based meme search
- `scripts/render_article.py` - HTML article rendering
- `config/gemini.json` - API configuration (gitignored)

## When Assisting with This Project

1. **Article Generation**: Reference `agents/triagent-workflow/AGENT.md` for workflow
2. **Image Processing**: Check `scripts/` directory for existing utilities
3. **API Integration**: Use `config/gemini.example.json` as reference
4. **Output Format**: Articles should be HTML in `outputs/articles/`

## Language

- Agent prompts and articles: Chinese (简体中文)
- Code comments: English or Chinese
- Documentation: Chinese preferred

## Security

- Never commit API keys
- Check `config/gemini.json` is in `.gitignore`
- Use environment variables for sensitive data
