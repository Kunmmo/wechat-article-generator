#!/usr/bin/env python3
"""
协调器驱动的工作流运行器

替代 run_workflow.py 中的硬编码顺序调用，采用 Claude Code 风格的
Coordinator 模式：协调器 LLM 通过结构化协议动态编排 worker 智能体。

工作方式：
1. 协调器通过 [DISPATCH: agent-name] 发出任务
2. 运行器解析并执行分派，调用对应的 worker agent
3. Worker 结果以 [TASK_RESULT: agent-name] 注入协调器上下文
4. 协调器评估结果，决定 PASS / REVISE / POLISH
5. 循环直到 PASS 或达到最大轮次

用法:
    python scripts/coordinator_workflow.py --topic "AI 发展趋势"
"""

import re
import json
import uuid
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

from log_config import get_logger
from model_router import call_agent, load_agent_prompt, load_models_config
from events import EventBus, EventType, WorkflowEvent
from context.manager import ContextManager, Message

logger = get_logger(__name__)

try:
    from render_article import process_article, render_html, render_markdown
    from evaluate_articles import evaluate_article, print_report
    HAS_RENDER = True
except ImportError:
    HAS_RENDER = False

try:
    from meme_retrieval import MemeRetriever
    HAS_RETRIEVER = True
except ImportError:
    HAS_RETRIEVER = False


class CoordinatorWorkflow:
    """
    协调器驱动的多智能体工作流

    与旧版 WorkflowRunner 的区别：
    - 协调器 LLM 决定调用顺序（不是硬编码）
    - 上下文通过 ContextManager 管理（压缩 + 预算）
    - 通信通过结构化 XML 协议（不是字符串拼接）
    """

    def __init__(self, topic: str, max_rounds: int = 3,
                 output_dir: str = "outputs/articles",
                 output_format: str = "html",
                 skip_retrieval: bool = False,
                 skip_eval: bool = False,
                 event_bus: Optional[EventBus] = None):
        self.topic = topic
        self.max_rounds = max_rounds
        self.output_dir = Path(output_dir)
        self.output_format = output_format
        self.skip_retrieval = skip_retrieval
        self.skip_eval = skip_eval
        self.bus = event_bus or EventBus()

        self.workflow_id = str(uuid.uuid4())[:8]
        self.current_round = 0
        self.score_history: list[float] = []
        self.final_article = ""
        self.config: Optional[dict] = None
        self._image_results: Optional[dict] = None

        # Context management
        self.context = ContextManager(max_tokens=120000, buffer_tokens=13000)
        self.messages: list[Message] = []

    def run(self) -> Optional[str]:
        """Execute the coordinator-driven workflow."""
        self.bus.emit(WorkflowEvent(
            type=EventType.WORKFLOW_START,
            message=f"Coordinator Workflow v3.0 | Topic: {self.topic} | Max rounds: {self.max_rounds}",
            data={"topic": self.topic, "max_rounds": self.max_rounds},
        ))

        try:
            self.config = load_models_config()
        except FileNotFoundError:
            self.bus.warn("config/models.json not found, using defaults")
            self.config = None

        coordinator_prompt = load_agent_prompt("coordinator")

        self.messages = [
            Message(role="system", content=coordinator_prompt),
        ]

        user_request = (
            f"请为以下选题生成一篇高质量的微信公众号文章。\n\n"
            f"选题: {self.topic}\n"
            f"最大轮次: {self.max_rounds}\n\n"
            f"请开始编排工作流。"
        )
        self.messages.append(Message(role="user", content=user_request))

        try:
            for round_num in range(1, self.max_rounds + 1):
                self.current_round = round_num
                self.bus.log(f"--- Round {round_num}/{self.max_rounds} ---")

                # Ask coordinator for next actions
                coordinator_response = self._call_coordinator()

                # Parse and execute dispatches
                dispatches = self._parse_dispatches(coordinator_response)

                if not dispatches:
                    self.bus.warn("Coordinator issued no dispatches, checking for decision")

                for agent_name, task_prompt in dispatches:
                    self.bus.phase_start(
                        phase=dispatches.index((agent_name, task_prompt)) + 1,
                        total=len(dispatches),
                        agent=agent_name,
                        message=f"Executing dispatch to {agent_name}",
                        round_=round_num,
                    )

                    worker_result = self._call_worker(agent_name, task_prompt)

                    # Inject result back into coordinator context
                    result_msg = Message(
                        role="user",
                        content=f"[TASK_RESULT: {agent_name}]\n{worker_result}\n[/TASK_RESULT]",
                        name=agent_name,
                        metadata={"tool_name": agent_name, "is_worker_result": True},
                    )
                    self.messages.append(result_msg)

                    self.bus.agent_response(agent_name, char_count=len(worker_result), round_=round_num)

                # Ask coordinator for decision
                decision_response = self._call_coordinator_for_decision()
                decision, score = self._parse_decision(decision_response)

                if score is not None:
                    self.score_history.append(score)
                self.bus.judge(decision, score=score, round_=round_num)

                if decision == "PASS":
                    break

                if round_num >= self.max_rounds:
                    self.bus.warn("Max rounds reached, forcing PASS")
                    decision = "PASS"
                    break

                # Inject decision feedback for next round
                self.messages.append(Message(
                    role="user",
                    content=f"决策为 {decision}，请安排下一轮修订。",
                ))

            # Extract final article from the last chief-editor result
            self._extract_final_article()

            # Render
            output_path = self._render() if HAS_RENDER and self.final_article else None

            # Evaluate
            if not self.skip_eval and output_path:
                self._evaluate()

            self.bus.emit(WorkflowEvent(
                type=EventType.WORKFLOW_END,
                message=f"Workflow completed | Rounds: {self.current_round}",
                round=self.current_round,
                data={"score_history": self.score_history},
            ))

            return output_path

        except Exception as e:
            self.bus.error(f"Coordinator workflow failed: {e}")
            import traceback
            logger.exception("Coordinator workflow traceback")
            return None

    def _call_coordinator(self) -> str:
        """Call the coordinator LLM with current context."""
        self.messages = self.context.compress_if_needed(self.messages)
        system_content = self.messages[0].content if self.messages and self.messages[0].role == "system" else ""
        last_user = ""
        for m in reversed(self.messages):
            if m.role == "user":
                last_user = m.content
                break

        response = call_agent(
            "coordinator", last_user,
            system_prompt=system_content,
            temperature=0.7,
            config=self.config,
        )

        self.messages.append(Message(role="assistant", content=response, name="coordinator"))
        return response

    def _call_coordinator_for_decision(self) -> str:
        """Prompt coordinator to make a PASS/REVISE/POLISH decision."""
        decision_prompt = (
            "所有 worker 的本轮结果已注入。"
            "请评估当前定稿质量，给出各维度评分，并输出 [COORDINATOR_DECISION]。"
        )
        self.messages.append(Message(role="user", content=decision_prompt))
        return self._call_coordinator()

    def _call_worker(self, agent_name: str, task_prompt: str) -> str:
        """Call a worker agent."""
        try:
            system_prompt = load_agent_prompt(agent_name)
        except FileNotFoundError:
            system_prompt = ""
            self.bus.warn(f"No AGENT.md for {agent_name}", agent=agent_name)

        return call_agent(
            agent_name, task_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            config=self.config,
        )

    def _parse_dispatches(self, response: str) -> list[tuple[str, str]]:
        """Parse [DISPATCH: name] ... [/DISPATCH] blocks from coordinator response."""
        dispatches = []
        pattern = r'\[DISPATCH:\s*([\w-]+)\]\s*(.*?)\s*\[/DISPATCH\]'
        for match in re.finditer(pattern, response, re.DOTALL):
            agent_name = match.group(1).strip()
            task_prompt = match.group(2).strip()
            dispatches.append((agent_name, task_prompt))
        return dispatches

    def _parse_decision(self, response: str) -> tuple[str, Optional[float]]:
        """Parse [COORDINATOR_DECISION: X] and score from coordinator response."""
        decision = "PASS"
        score = None

        dec_match = re.search(
            r'\[COORDINATOR_DECISION:\s*(PASS|REVISE|POLISH)\]', response
        )
        if dec_match:
            decision = dec_match.group(1)
        else:
            # Fallback: look for JUDGE_DECISION (backward compat)
            dec_match = re.search(r'\[JUDGE_DECISION:\s*(PASS|REVISE|POLISH)\]', response)
            if dec_match:
                decision = dec_match.group(1)
            else:
                self.bus.warn("Could not parse coordinator decision, defaulting to PASS")

        score_match = re.search(r'总分[：:]\s*(\d+\.?\d*)', response)
        if score_match:
            score = float(score_match.group(1))
        else:
            score_match = re.search(r'\*\*总分\*\*\s*\|\s*\*\*(\d+\.?\d*)/10\*\*', response)
            if score_match:
                score = float(score_match.group(1))

        return decision, score

    def _extract_final_article(self):
        """Extract the most recent article content from conversation history."""
        for msg in reversed(self.messages):
            if msg.name == "chief-editor" or (
                msg.metadata.get("tool_name") == "chief-editor"
            ):
                content = msg.content
                # Strip TASK_RESULT wrapper if present
                inner = re.search(
                    r'\[TASK_RESULT:\s*chief-editor\]\s*(.*?)\s*\[/TASK_RESULT\]',
                    content, re.DOTALL
                )
                if inner:
                    self.final_article = inner.group(1).strip()
                else:
                    self.final_article = content.strip()
                return

        # Fallback: use last long assistant message
        for msg in reversed(self.messages):
            if msg.role == "assistant" and len(msg.content) > 500:
                self.final_article = msg.content
                return

    def _render(self) -> Optional[str]:
        """Render article to output files."""
        self.bus.log("Rendering output...", agent="article-renderer")

        title = self.topic
        title_match = re.search(r'^#\s+(.+)$', self.final_article, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()

        retriever = None
        if not self.skip_retrieval and HAS_RETRIEVER:
            try:
                retriever = MemeRetriever()
                retriever.load()
            except Exception as e:
                self.bus.warn(f"Meme retriever init failed: {e}")

        image_results = process_article(self.final_article, retriever)
        image_results["workflow"] = {
            "rounds": self.current_round,
            "score": f"{self.score_history[-1]}/10" if self.score_history else "N/A",
            "score_history": self.score_history,
            "mode": "coordinator",
        }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = re.sub(r'[^\w\u4e00-\u9fff]', '_', self.topic)[:30]
        base_name = f"{timestamp}_{safe_topic}"

        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = None

        if self.output_format in ('html', 'both'):
            html_path = self.output_dir / f"{base_name}.html"
            html = render_html(self.final_article, title, image_results)
            with open(html_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(html)
            self.bus.log(f"HTML output: {html_path}", agent="article-renderer")
            output_path = str(html_path)

        if self.output_format in ('markdown', 'both'):
            md_path = self.output_dir / f"{base_name}.md"
            md_content = render_markdown(self.final_article, image_results)
            with open(md_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(md_content)
            self.bus.log(f"Markdown output: {md_path}", agent="article-renderer")
            if output_path is None:
                output_path = str(md_path)

        meta_path = self.output_dir / f"{base_name}_meta.json"
        meta = {
            "workflow_id": self.workflow_id,
            "topic": self.topic,
            "rounds": self.current_round,
            "max_rounds": self.max_rounds,
            "score_history": self.score_history,
            "mode": "coordinator",
            "image_stats": image_results.get("stats", {}),
            "created_at": datetime.now().isoformat(),
        }
        with open(meta_path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        self._image_results = image_results
        return output_path

    def _evaluate(self):
        """Run quantitative evaluation."""
        self.bus.log("Running quality evaluation...", agent="evaluator")
        try:
            report = evaluate_article(
                self.final_article,
                self._image_results,
                article_path=f"coordinator:{self.workflow_id}",
            )
            print_report(report)

            from dataclasses import asdict
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_topic = re.sub(r'[^\w\u4e00-\u9fff]', '_', self.topic)[:30]
            eval_path = self.output_dir / f"{timestamp}_{safe_topic}_eval.json"
            with open(eval_path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(asdict(report), f, ensure_ascii=False, indent=2)
            self.bus.log(f"Evaluation: {report.overall_score}/100 ({report.quality_level})", agent="evaluator")
        except Exception as e:
            self.bus.warn(f"Evaluation failed: {e}", agent="evaluator")


def main():
    parser = argparse.ArgumentParser(
        description='协调器驱动的多智能体工作流 v3.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/coordinator_workflow.py --topic "AI Agent 技术趋势"
  python scripts/coordinator_workflow.py --topic "MCP 协议" --max-rounds 2
        """
    )
    parser.add_argument('--topic', type=str, required=True, help='Article topic')
    parser.add_argument('--max-rounds', type=int, default=3, help='Max debate rounds (default: 3)')
    parser.add_argument('--output-dir', type=str, default='outputs/articles', help='Output directory')
    parser.add_argument('--format', choices=['html', 'markdown', 'both'], default='html', help='Output format')
    parser.add_argument('--skip-retrieval', action='store_true', help='Skip meme retrieval')
    parser.add_argument('--skip-eval', action='store_true', help='Skip quality evaluation')

    args = parser.parse_args()

    workflow = CoordinatorWorkflow(
        topic=args.topic,
        max_rounds=args.max_rounds,
        output_dir=args.output_dir,
        output_format=args.format,
        skip_retrieval=args.skip_retrieval,
        skip_eval=args.skip_eval,
    )

    output_path = workflow.run()

    if output_path:
        logger.info("Workflow completed!")
        logger.info("  Output: %s", output_path)
        logger.info("  Rounds: %d", workflow.current_round)
        if workflow.score_history:
            logger.info("  Final score: %s/10", workflow.score_history[-1])
    else:
        logger.error("Workflow produced no output")
        exit(1)


if __name__ == "__main__":
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())
    main()
