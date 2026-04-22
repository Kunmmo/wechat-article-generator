"""
具体工具实现

将现有的散落函数调用包装为 ToolSpec 子类。
"""

from __future__ import annotations

import sys
from pathlib import Path
from .base import ToolSpec, ToolResult, ToolContext

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


class MemeRetrievalTool(ToolSpec):
    """CLIP 语义检索表情包"""

    name = "meme_retrieval"
    description = "Search the local meme library using CLIP semantic similarity. Returns the best matching meme image path and similarity score."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Meme search query, e.g. '震惊', '无语'"},
        },
        "required": ["query"],
    }
    is_parallel_safe = True
    is_read_only = True
    timeout_seconds = 30
    max_output_chars = 500

    def __init__(self):
        self._retriever = None

    def _ensure_retriever(self):
        if self._retriever is not None:
            return
        try:
            from meme_retrieval import MemeRetriever
            self._retriever = MemeRetriever()
            self._retriever.load()
        except Exception:
            self._retriever = None

    def execute(self, args: dict, context: ToolContext) -> ToolResult:
        query = args.get("query", "")
        self._ensure_retriever()

        if self._retriever is None:
            return ToolResult(tool_name=self.name, success=False, error="Meme retriever not available")

        path, score, source = self._retriever.get_meme(query)
        return ToolResult(
            tool_name=self.name, success=path is not None,
            output={"path": path, "score": score, "source": source, "query": query},
            metadata={"source": source, "score": score},
        )


class ImageGenerationTool(ToolSpec):
    """通过 Gemini / Stable Diffusion 生成图片"""

    name = "image_generation"
    description = "Generate an image (meme or illustration) using Gemini or Stable Diffusion API."
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Image generation prompt"},
            "image_type": {"type": "string", "enum": ["meme", "illustration"], "default": "meme"},
            "output_path": {"type": "string", "description": "Optional output file path"},
        },
        "required": ["prompt"],
    }
    is_parallel_safe = True
    is_read_only = False
    timeout_seconds = 90

    def execute(self, args: dict, context: ToolContext) -> ToolResult:
        try:
            from gemini_client import generate_image_with_fallback
            path = generate_image_with_fallback(
                prompt=args["prompt"],
                image_type=args.get("image_type", "meme"),
                output_path=args.get("output_path"),
            )
            return ToolResult(
                tool_name=self.name, success=path is not None,
                output={"path": path, "prompt": args["prompt"]},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, error=str(e))


class EvaluationTool(ToolSpec):
    """文章质量量化评估"""

    name = "evaluate_article"
    description = "Run quantitative evaluation on article content: structure, readability, depth, CLIP score."
    input_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Article content (markdown or HTML)"},
            "image_results": {"type": "object", "description": "Optional image processing results"},
        },
        "required": ["content"],
    }
    is_parallel_safe = True
    is_read_only = True
    timeout_seconds = 120
    max_output_chars = 2000

    def execute(self, args: dict, context: ToolContext) -> ToolResult:
        try:
            from evaluate_articles import evaluate_article
            from dataclasses import asdict
            report = evaluate_article(
                content=args["content"],
                image_results=args.get("image_results"),
            )
            return ToolResult(
                tool_name=self.name, success=True,
                output=asdict(report),
                metadata={"score": report.overall_score, "quality": report.quality_level},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, error=str(e))


class WebSearchTool(ToolSpec):
    """Web 搜索（委托给 LLM 自身的搜索能力，或外部 API）"""

    name = "web_search"
    description = "Search the web for current information on a topic. Returns a text summary of search results."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    }
    is_parallel_safe = True
    is_read_only = True
    timeout_seconds = 30
    max_output_chars = 5000

    def execute(self, args: dict, context: ToolContext) -> ToolResult:
        # Web search is typically handled by the LLM's native capabilities
        # (e.g. Gemini grounding, GPT browsing). This tool serves as a
        # schema placeholder for function-calling flows.
        return ToolResult(
            tool_name=self.name, success=True,
            output=f"[Web search for: {args.get('query', '')}] — delegated to LLM native search",
        )


class AgentCallTool(ToolSpec):
    """
    子智能体调用工具

    非并行安全：调用一个子智能体是重型操作，不应与其他子智能体并行。
    灵感来源：Claude Code 的 AgentTool 统一入口。
    """

    name = "agent_call"
    description = "Dispatch a task to a sub-agent (e.g. deep-thinker, meme-master). Returns the agent's text response."
    input_schema = {
        "type": "object",
        "properties": {
            "agent_name": {"type": "string", "description": "Agent name from agents/ directory"},
            "prompt": {"type": "string", "description": "User prompt to send to the agent"},
            "system_prompt": {"type": "string", "description": "Optional override for agent system prompt"},
        },
        "required": ["agent_name", "prompt"],
    }
    is_parallel_safe = False
    is_read_only = False
    timeout_seconds = 180

    def execute(self, args: dict, context: ToolContext) -> ToolResult:
        try:
            from model_router import call_agent, load_agent_prompt

            agent_name = args["agent_name"]
            user_prompt = args["prompt"]
            system_prompt = args.get("system_prompt", "")
            if not system_prompt:
                system_prompt = load_agent_prompt(agent_name)

            result = call_agent(agent_name, user_prompt, system_prompt)
            return ToolResult(
                tool_name=self.name, success=True,
                output=result,
                output_chars=len(result),
                metadata={"agent": agent_name},
            )
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, error=str(e))
