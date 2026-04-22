#!/usr/bin/env python3
"""
端到端 CLI 工作流运行器

一条命令完成从选题到 HTML 输出的完整多智能体辩论工作流。

用法:
    python scripts/run_workflow.py --topic "AI 发展趋势"
    python scripts/run_workflow.py --topic "MCP 协议深度解析" --max-rounds 2 --format both
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
from render_article import process_article, render_html, render_markdown
from evaluate_articles import evaluate_article, print_report
from events import EventBus, EventType

logger = get_logger(__name__)

try:
    from meme_retrieval import MemeRetriever
    HAS_RETRIEVER = True
except ImportError:
    HAS_RETRIEVER = False


class WorkflowRunner:
    """三智能体辩论工作流运行器"""

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
        self.score_history = []
        self.config = None

        # Workflow state
        self.news_context = ""
        self.draft = ""
        self.meme_version = ""
        self.edited_version = ""
        self.final_article = ""
        self.judge_decision = ""
        self.judge_feedback = ""

    def _log(self, phase: int, total: int, agent: str, msg: str):
        """通过 EventBus 发出阶段开始事件"""
        self.bus.phase_start(
            phase=phase, total=total, agent=agent,
            message=msg, round_=self.current_round,
        )

    def _load_config(self):
        """预加载配置"""
        try:
            self.config = load_models_config()
        except FileNotFoundError:
            self.bus.warn("config/models.json not found, using defaults")
            self.config = None

    def run(self) -> Optional[str]:
        """执行完整工作流，返回输出文件路径"""
        from events import WorkflowEvent
        self.bus.emit(WorkflowEvent(
            type=EventType.WORKFLOW_START,
            message=f"Workflow v2.1 | Topic: {self.topic} | Max rounds: {self.max_rounds}",
            data={"topic": self.topic, "max_rounds": self.max_rounds, "workflow_id": self.workflow_id},
        ))

        self._load_config()

        try:
            self._run_news_researcher()

            while self.current_round < self.max_rounds:
                self.current_round += 1
                self._run_deep_thinker()
                self._run_meme_master()
                self._run_chief_editor()
                decision = self._run_central_judge()

                if decision == "PASS":
                    break
                elif decision == "REVISE":
                    self.bus.log("REVISE: returning to Deep Thinker", agent="central-judge", round_=self.current_round)
                    continue
                elif decision == "POLISH":
                    self.bus.log("POLISH: returning to Meme Master", agent="central-judge", round_=self.current_round)
                    self.current_round += 1
                    if self.current_round > self.max_rounds:
                        self.bus.warn("Max rounds reached, forcing PASS")
                        break
                    self._run_meme_master()
                    self._run_chief_editor()
                    decision = self._run_central_judge()
                    if decision == "PASS":
                        break
                    if self.current_round >= self.max_rounds:
                        break

            output_path = self._run_renderer()

            if not self.skip_eval and output_path:
                self._run_evaluation()

            self.bus.emit(WorkflowEvent(
                type=EventType.WORKFLOW_END,
                message=f"Workflow completed | Rounds: {self.current_round}",
                round=self.current_round,
                data={"score_history": self.score_history},
            ))
            return output_path

        except Exception as e:
            self.bus.error(f"Workflow failed: {e}")
            logger.exception("Workflow traceback")
            return None

    def _run_news_researcher(self):
        """阶段 1: 时事研究员"""
        self._log(1, 6, "news-researcher", "Searching for news related to topic...")

        system_prompt = load_agent_prompt("news-researcher")
        user_prompt = f"选题: {self.topic}\n\n请搜索与此选题相关的最新资讯。"

        result = call_agent("news-researcher", user_prompt, system_prompt, config=self.config)
        self.news_context = result

        match = re.search(r'\[NEWS_CONTEXT\](.*?)\[/NEWS_CONTEXT\]', result, re.DOTALL)
        if match:
            self.bus.agent_response("news-researcher", char_count=len(result), round_=0)
        else:
            self.bus.warn("[NEWS_CONTEXT] tag not detected, using full output", agent="news-researcher")

    def _run_deep_thinker(self):
        """阶段 2: 深度思考者"""
        is_revision = self.current_round > 1 and self.judge_decision == "REVISE"

        if is_revision:
            self._log(2, 6, "deep-thinker", f"Revision round {self.current_round}")
            user_prompt = (
                f"## 选题: {self.topic}\n\n"
                f"## 时事资讯\n{self.news_context}\n\n"
                f"## 当前版本\n{self.edited_version}\n\n"
                f"## 裁判修订建议\n{self.judge_feedback}\n\n"
                f"请根据以上建议增强文章深度，保留原有亮点。这是修订轮次，不需要完全重写。"
            )
        else:
            self._log(2, 6, "deep-thinker", "Writing in-depth draft from news context...")
            user_prompt = (
                f"## 选题: {self.topic}\n\n"
                f"## 时事资讯\n{self.news_context}\n\n"
                f"请基于以上时事资讯撰写深度草稿。"
            )

        system_prompt = load_agent_prompt("deep-thinker")
        self.draft = call_agent("deep-thinker", user_prompt, system_prompt, config=self.config)
        self.bus.agent_response("deep-thinker", char_count=len(self.draft), round_=self.current_round)

    def _run_meme_master(self):
        """阶段 3: Meme大师"""
        is_polish = self.judge_decision == "POLISH"

        if is_polish:
            self._log(3, 6, "meme-master", "Polish round: enhancing virality")
            user_prompt = (
                f"## 当前版本\n{self.edited_version}\n\n"
                f"## 裁判润色建议\n{self.judge_feedback}\n\n"
                f"请根据以上建议增强网感，添加表情包标记。"
            )
        else:
            self._log(3, 6, "meme-master", "Injecting internet culture into draft...")
            user_prompt = (
                f"## 深度思考者草稿\n{self.draft}\n\n"
                f"请进行网感注入和表情包标记。"
            )

        system_prompt = load_agent_prompt("meme-master")
        self.meme_version = call_agent("meme-master", user_prompt, system_prompt, config=self.config)
        self.bus.agent_response("meme-master", char_count=len(self.meme_version), round_=self.current_round)

    def _run_chief_editor(self):
        """阶段 4: 铁面主编"""
        self._log(4, 6, "chief-editor", "Merging drafts into final version...")

        system_prompt = load_agent_prompt("chief-editor")
        user_prompt = (
            f"## 深度思考者草稿\n{self.draft}\n\n"
            f"## Meme大师改写版\n{self.meme_version}\n\n"
            f"请融合两者优点，输出最终定稿。"
        )

        self.edited_version = call_agent("chief-editor", user_prompt, system_prompt, config=self.config)
        self.final_article = self.edited_version
        self.bus.agent_response("chief-editor", char_count=len(self.edited_version), round_=self.current_round)

    def _run_central_judge(self) -> str:
        """阶段 5: 中控裁判 → 返回决策 PASS/REVISE/POLISH"""
        self._log(5, 6, "central-judge", "Evaluating article quality...")

        system_prompt = load_agent_prompt("central-judge")
        user_prompt = (
            f"## 铁面主编定稿\n{self.edited_version}\n\n"
            f"## 工作流状态\n"
            f"当前轮次: {self.current_round}\n"
            f"最大轮次: {self.max_rounds}\n"
            f"历史评分: {self.score_history}\n\n"
            f"请评估定稿质量并做出决策。"
        )

        result = call_agent("central-judge", user_prompt, system_prompt, config=self.config)

        decision_match = re.search(r'\[JUDGE_DECISION:\s*(PASS|REVISE|POLISH)\]', result)
        if decision_match:
            self.judge_decision = decision_match.group(1)
        else:
            self.judge_decision = "PASS"
            self.bus.warn("Could not parse judge decision, defaulting to PASS", agent="central-judge")

        score = None
        score_match = re.search(r'\*\*总分\*\*\s*\|\s*\*\*(\d+\.?\d*)/10\*\*', result)
        if score_match:
            score = float(score_match.group(1))
        else:
            score_match = re.search(r'总分[：:]\s*(\d+\.?\d*)', result)
            if score_match:
                score = float(score_match.group(1))
        if score is not None:
            self.score_history.append(score)

        self.judge_feedback = result
        self.bus.judge(self.judge_decision, score=score, round_=self.current_round)

        if self.current_round >= self.max_rounds and self.judge_decision != "PASS":
            self.bus.warn(f"Max rounds ({self.max_rounds}) reached, forcing PASS")
            self.judge_decision = "PASS"

        return self.judge_decision

    def _run_renderer(self) -> Optional[str]:
        """阶段 6: 渲染输出"""
        self._log(6, 6, "article-renderer", "Processing images and rendering output...")

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
                self.bus.warn(f"Meme retriever init failed: {e}", agent="article-renderer")

        image_results = process_article(self.final_article, retriever)
        image_results["workflow"] = {
            "rounds": self.current_round,
            "score": f"{self.score_history[-1]}/10" if self.score_history else "N/A",
            "score_history": self.score_history,
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
            "final_decision": self.judge_decision,
            "image_stats": image_results.get("stats", {}),
            "created_at": datetime.now().isoformat(),
        }
        with open(meta_path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        self._image_results = image_results
        return output_path

    def _run_evaluation(self):
        """运行质量评估"""
        self.bus.log("Running quality evaluation...", agent="evaluator")

        try:
            image_results = getattr(self, '_image_results', None)
            report = evaluate_article(
                self.final_article, image_results,
                article_path=f"workflow:{self.workflow_id}"
            )
            print_report(report)

            from dataclasses import asdict
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_topic = re.sub(r'[^\w\u4e00-\u9fff]', '_', self.topic)[:30]
            eval_path = self.output_dir / f"{timestamp}_{safe_topic}_eval.json"
            with open(eval_path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(asdict(report), f, ensure_ascii=False, indent=2)
            self.bus.log(f"Evaluation saved: {eval_path} | Score: {report.overall_score}/{report.quality_level}", agent="evaluator")
        except Exception as e:
            self.bus.warn(f"Evaluation failed: {e}", agent="evaluator")


def main():
    parser = argparse.ArgumentParser(
        description='三智能体辩论工作流 - 端到端 CLI 运行器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/run_workflow.py --topic "AI 发展趋势"
  python scripts/run_workflow.py --topic "MCP 协议" --max-rounds 2 --format both
  python scripts/run_workflow.py --topic "大模型应用" --skip-retrieval --skip-eval
        """
    )
    parser.add_argument('--topic', type=str, required=True,
                        help='文章选题')
    parser.add_argument('--max-rounds', type=int, default=3,
                        help='最大辩论轮次 (默认: 3)')
    parser.add_argument('--output-dir', type=str, default='outputs/articles',
                        help='输出目录 (默认: outputs/articles)')
    parser.add_argument('--format', choices=['html', 'markdown', 'both'],
                        default='html', help='输出格式 (默认: html)')
    parser.add_argument('--skip-retrieval', action='store_true',
                        help='跳过表情包检索')
    parser.add_argument('--skip-eval', action='store_true',
                        help='跳过质量评估')

    args = parser.parse_args()

    runner = WorkflowRunner(
        topic=args.topic,
        max_rounds=args.max_rounds,
        output_dir=args.output_dir,
        output_format=args.format,
        skip_retrieval=args.skip_retrieval,
        skip_eval=args.skip_eval,
    )

    output_path = runner.run()

    if output_path:
        logger.info("工作流完成!")
        logger.info("  输出文件: %s", output_path)
        logger.info("  总轮次: %d", runner.current_round)
        if runner.score_history:
            logger.info("  最终评分: %s/10", runner.score_history[-1])
    else:
        logger.error("工作流未生成输出")
        exit(1)


if __name__ == "__main__":
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())
    main()
