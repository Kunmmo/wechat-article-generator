#!/usr/bin/env python3
"""
Web 界面 - Flask + HTMX

提供文章生成的 Web 交互界面：
- 首页：选题输入、参数配置
- 进度：实时工作流进度（SSE）
- 结果：文章预览、下载
- 历史：已生成文章列表

启动方式:
    python scripts/web_app.py
    # 访问 http://localhost:5000
"""

import os
import sys
import json
import queue
import threading
from pathlib import Path
from datetime import datetime

from flask import (
    Flask, render_template_string, request, jsonify,
    Response, send_from_directory, redirect, url_for
)

# Ensure scripts directory is in path
sys.path.insert(0, str(Path(__file__).parent))

from log_config import get_logger

logger = get_logger(__name__)

from events import EventBus, WorkflowEvent, EventType, _STREAM_DONE, _STREAM_FAILED

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

app = Flask(__name__, static_folder=str(FRONTEND_DIST) if FRONTEND_DIST.exists() else None)
app.secret_key = os.urandom(24)


@app.after_request
def add_cors_headers(response):
    """Allow cross-origin requests from the Vite dev server."""
    origin = request.headers.get('Origin', '')
    if origin.startswith('http://localhost:'):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Accept'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "articles"
IMAGES_DIR = PROJECT_ROOT / "outputs" / "images"

# Per-task EventBus instances — no global state mutation
active_tasks: dict[str, dict] = {}

# ============ HTML Templates (inline, no external dependencies) ============

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ title }} - 微信公众号文章生成器</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12/dist/ext/sse.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                   "Microsoft YaHei", sans-serif;
      background: #f0f2f5; color: #333; line-height: 1.6;
    }
    .navbar {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      padding: 16px 32px; color: #fff; display: flex; align-items: center;
      justify-content: space-between; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    .navbar h1 { font-size: 20px; font-weight: 600; }
    .navbar nav a {
      color: rgba(255,255,255,0.85); text-decoration: none; margin-left: 24px;
      font-size: 14px; transition: color 0.2s;
    }
    .navbar nav a:hover, .navbar nav a.active { color: #fff; font-weight: 600; }
    .container { max-width: 960px; margin: 32px auto; padding: 0 16px; }
    .card {
      background: #fff; border-radius: 12px; padding: 32px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 24px;
    }
    .card h2 {
      font-size: 18px; margin-bottom: 20px; padding-bottom: 12px;
      border-bottom: 2px solid #667eea; color: #333;
    }
    label { display: block; font-size: 14px; color: #666; margin-bottom: 6px; font-weight: 500; }
    input[type="text"], select, textarea {
      width: 100%; padding: 10px 14px; border: 1px solid #d9d9d9; border-radius: 8px;
      font-size: 15px; margin-bottom: 16px; transition: border-color 0.2s;
      font-family: inherit;
    }
    input:focus, select:focus, textarea:focus {
      outline: none; border-color: #667eea; box-shadow: 0 0 0 3px rgba(102,126,234,0.1);
    }
    .btn {
      display: inline-block; padding: 10px 28px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff; border: none; border-radius: 8px; font-size: 15px;
      cursor: pointer; font-weight: 500; transition: transform 0.1s, box-shadow 0.2s;
    }
    .btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(102,126,234,0.4); }
    .btn:active { transform: translateY(0); }
    .btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
    .btn-secondary {
      background: #f5f5f5; color: #333; border: 1px solid #d9d9d9;
    }
    .btn-secondary:hover { background: #e8e8e8; box-shadow: none; }
    .row { display: flex; gap: 16px; }
    .row > * { flex: 1; }
    .progress-log {
      background: #1a1a2e; color: #e0e0e0; border-radius: 8px;
      padding: 20px; font-family: "Fira Code", "Consolas", monospace;
      font-size: 13px; max-height: 500px; overflow-y: auto; line-height: 1.8;
    }
    .progress-log .phase { color: #667eea; font-weight: bold; }
    .progress-log .success { color: #52c41a; }
    .progress-log .warning { color: #faad14; }
    .progress-log .error { color: #ff4d4f; }
    .history-item {
      display: flex; justify-content: space-between; align-items: center;
      padding: 14px 0; border-bottom: 1px solid #f0f0f0;
    }
    .history-item:last-child { border-bottom: none; }
    .history-item .meta { color: #999; font-size: 13px; }
    .history-item .title-text { font-weight: 500; color: #333; }
    .badge {
      display: inline-block; padding: 2px 10px; border-radius: 12px;
      font-size: 12px; font-weight: 500;
    }
    .badge-a { background: #f6ffed; color: #52c41a; }
    .badge-b { background: #e6f7ff; color: #1890ff; }
    .badge-c { background: #fff7e6; color: #fa8c16; }
    .badge-d { background: #fff1f0; color: #ff4d4f; }
    .preview-frame {
      border: 1px solid #e8e8e8; border-radius: 8px; overflow: hidden;
      margin-top: 16px;
    }
    .preview-frame iframe {
      width: 100%; height: 600px; border: none;
    }
    .empty-state {
      text-align: center; padding: 60px 20px; color: #999;
    }
    .empty-state p { margin-top: 12px; font-size: 15px; }
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }
    .stat-card {
      background: #f8f9fa; border-radius: 8px; padding: 16px; text-align: center;
    }
    .stat-card .value { font-size: 28px; font-weight: 700; color: #667eea; }
    .stat-card .label { font-size: 13px; color: #999; margin-top: 4px; }
    @media (max-width: 640px) {
      .row { flex-direction: column; }
      .container { padding: 0 12px; }
      .card { padding: 20px; }
    }
  </style>
</head>
<body>
  <div class="navbar">
    <h1>WeChat Article Generator</h1>
    <nav>
      <a href="/" class="{{ 'active' if active_page == 'home' else '' }}">生成</a>
      <a href="/history" class="{{ 'active' if active_page == 'history' else '' }}">历史</a>
      <a href="/dashboard" class="{{ 'active' if active_page == 'dashboard' else '' }}">数据</a>
    </nav>
  </div>
  <div class="container">
    {% block content %}{% endblock %}
  </div>
</body>
</html>
"""

HOME_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
  <h2>生成新文章</h2>
  <form id="generate-form" hx-post="/api/generate" hx-target="#result-area" hx-swap="innerHTML">
    <label for="topic">选题 *</label>
    <input type="text" id="topic" name="topic" placeholder="例: AI 发展趋势与未来展望" required>

    <div class="row">
      <div>
        <label for="max_rounds">最大辩论轮次</label>
        <select name="max_rounds" id="max_rounds">
          <option value="1">1 轮（快速）</option>
          <option value="2">2 轮（平衡）</option>
          <option value="3" selected>3 轮（深入）</option>
        </select>
      </div>
      <div>
        <label for="format">输出格式</label>
        <select name="format" id="format">
          <option value="html" selected>HTML</option>
          <option value="markdown">Markdown</option>
          <option value="both">HTML + Markdown</option>
        </select>
      </div>
    </div>

    <div style="margin-top: 8px;">
      <label>
        <input type="checkbox" name="skip_retrieval" value="1"> 跳过表情包检索（加速生成）
      </label>
    </div>

    <div style="margin-top: 20px;">
      <button type="submit" class="btn" id="submit-btn">开始生成</button>
    </div>
  </form>
</div>

<div id="result-area"></div>

<script>
document.getElementById('generate-form').addEventListener('htmx:beforeRequest', function() {
  document.getElementById('submit-btn').disabled = true;
  document.getElementById('submit-btn').textContent = '生成中...';
});
document.getElementById('generate-form').addEventListener('htmx:afterRequest', function() {
  document.getElementById('submit-btn').disabled = false;
  document.getElementById('submit-btn').textContent = '开始生成';
});
</script>
{% endblock %}
"""

PROGRESS_TEMPLATE = """
<div class="card">
  <h2>工作流进度</h2>
  <div class="progress-log" id="progress-log"
       hx-ext="sse" sse-connect="/api/progress/{{ task_id }}" sse-swap="message">
    <div class="phase">工作流已启动，请稍候...</div>
  </div>
</div>
"""

RESULT_TEMPLATE = """
<div class="card">
  <h2>生成完成</h2>
  <div class="stats-grid" style="margin-bottom: 20px;">
    <div class="stat-card">
      <div class="value">{{ rounds }}</div>
      <div class="label">辩论轮次</div>
    </div>
    <div class="stat-card">
      <div class="value">{{ score }}</div>
      <div class="label">最终评分</div>
    </div>
    <div class="stat-card">
      <div class="value">{{ word_count }}</div>
      <div class="label">字数</div>
    </div>
    <div class="stat-card">
      <div class="value">{{ image_count }}</div>
      <div class="label">图片数</div>
    </div>
  </div>

  <div style="margin-bottom: 16px;">
    <a href="/preview/{{ filename }}" class="btn" target="_blank">预览文章</a>
    <a href="/download/{{ filename }}" class="btn btn-secondary" style="margin-left: 8px;">下载</a>
  </div>

  {% if preview_url %}
  <div class="preview-frame">
    <iframe src="{{ preview_url }}"></iframe>
  </div>
  {% endif %}
</div>
"""

HISTORY_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
  <h2>生成历史</h2>
  {% if articles %}
    {% for article in articles %}
    <div class="history-item">
      <div>
        <div class="title-text">{{ article.topic }}</div>
        <div class="meta">{{ article.created_at }} | {{ article.rounds }} 轮 | {{ article.word_count }} 字</div>
      </div>
      <div>
        {% if article.quality %}
        <span class="badge badge-{{ article.quality|lower }}">{{ article.quality }}</span>
        {% endif %}
        <a href="/preview/{{ article.filename }}" class="btn btn-secondary" style="padding: 4px 12px; font-size: 13px;">查看</a>
      </div>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty-state">
      <p>暂无生成记录</p>
      <a href="/" class="btn" style="margin-top: 16px;">去生成一篇</a>
    </div>
  {% endif %}
</div>
{% endblock %}
"""

DASHBOARD_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
  <h2>数据概览</h2>
  <div class="stats-grid">
    <div class="stat-card">
      <div class="value">{{ stats.total_articles }}</div>
      <div class="label">总文章数</div>
    </div>
    <div class="stat-card">
      <div class="value">{{ stats.avg_score }}</div>
      <div class="label">平均评分</div>
    </div>
    <div class="stat-card">
      <div class="value">{{ stats.avg_rounds }}</div>
      <div class="label">平均轮次</div>
    </div>
    <div class="stat-card">
      <div class="value">{{ stats.total_images }}</div>
      <div class="label">总图片数</div>
    </div>
    <div class="stat-card">
      <div class="value">{{ stats.avg_word_count }}</div>
      <div class="label">平均字数</div>
    </div>
    <div class="stat-card">
      <div class="value">{{ stats.avg_clip_score }}</div>
      <div class="label">平均 CLIP Score</div>
    </div>
  </div>
</div>

{% if stats.quality_distribution %}
<div class="card">
  <h2>质量分布</h2>
  {% for level, count in stats.quality_distribution.items() %}
  <div style="display: flex; align-items: center; margin-bottom: 8px;">
    <span class="badge badge-{{ level|lower }}" style="width: 40px; text-align: center;">{{ level }}</span>
    <div style="flex: 1; margin-left: 12px; background: #f0f0f0; border-radius: 4px; height: 24px;">
      <div style="width: {{ (count / stats.total_articles * 100) if stats.total_articles > 0 else 0 }}%; background: linear-gradient(90deg, #667eea, #764ba2); height: 100%; border-radius: 4px; min-width: 24px; display:flex; align-items:center; justify-content:center; color:#fff; font-size:12px;">
        {{ count }}
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}

{% if stats.retrieval_vs_generation.retrieval > 0 or stats.retrieval_vs_generation.generation > 0 %}
<div class="card">
  <h2>图片来源分布</h2>
  {% set total_imgs = stats.retrieval_vs_generation.retrieval + stats.retrieval_vs_generation.generation %}
  <div style="display: flex; align-items: center; margin-bottom: 8px;">
    <span style="width: 80px; font-size: 14px; color: #666;">检索</span>
    <div style="flex: 1; margin-left: 12px; background: #f0f0f0; border-radius: 4px; height: 24px;">
      <div style="width: {{ (stats.retrieval_vs_generation.retrieval / total_imgs * 100) if total_imgs > 0 else 0 }}%; background: #52c41a; height: 100%; border-radius: 4px; min-width: 24px; display:flex; align-items:center; justify-content:center; color:#fff; font-size:12px;">
        {{ stats.retrieval_vs_generation.retrieval }}
      </div>
    </div>
  </div>
  <div style="display: flex; align-items: center; margin-bottom: 8px;">
    <span style="width: 80px; font-size: 14px; color: #666;">生成</span>
    <div style="flex: 1; margin-left: 12px; background: #f0f0f0; border-radius: 4px; height: 24px;">
      <div style="width: {{ (stats.retrieval_vs_generation.generation / total_imgs * 100) if total_imgs > 0 else 0 }}%; background: #1890ff; height: 100%; border-radius: 4px; min-width: 24px; display:flex; align-items:center; justify-content:center; color:#fff; font-size:12px;">
        {{ stats.retrieval_vs_generation.generation }}
      </div>
    </div>
  </div>
</div>
{% endif %}
{% endblock %}
"""


# ============ Template rendering helper ============

def render(template_str: str, **kwargs):
    """Render a template with base template inheritance"""
    # Simple Jinja2-like extends handling
    if '{% extends "base" %}' in template_str:
        content_match = template_str.split('{% block content %}')[1].split('{% endblock %}')[0]
        full = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content_match)
        return render_template_string(full, **kwargs)
    return render_template_string(template_str, **kwargs)


# ============ Helper functions ============

def _get_history() -> list[dict]:
    """Scan outputs/articles for generated articles"""
    articles = []
    if not OUTPUTS_DIR.exists():
        return articles

    for meta_file in sorted(OUTPUTS_DIR.glob("*_meta.json"), reverse=True):
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            html_file = meta_file.name.replace("_meta.json", ".html")
            html_path = OUTPUTS_DIR / html_file

            # Try to read eval report
            eval_file = meta_file.name.replace("_meta.json", "_eval.json")
            eval_path = OUTPUTS_DIR / eval_file
            quality = ""
            word_count = 0
            if eval_path.exists():
                with open(eval_path, 'r', encoding='utf-8') as f:
                    eval_data = json.load(f)
                quality = eval_data.get("quality_level", "")
                word_count = eval_data.get("structure", {}).get("word_count", 0)

            articles.append({
                "topic": meta.get("topic", "未知选题"),
                "created_at": meta.get("created_at", "")[:16].replace("T", " "),
                "rounds": meta.get("rounds", 0),
                "score_history": meta.get("score_history", []),
                "word_count": word_count or meta.get("image_stats", {}).get("meme_count", 0),
                "quality": quality,
                "filename": html_file if html_path.exists() else "",
            })
        except Exception:
            continue

    return articles


def _get_dashboard_stats() -> dict:
    """Compute aggregate statistics from all generated articles"""
    articles = _get_history()
    stats = {
        "total_articles": len(articles),
        "avg_score": "N/A",
        "avg_rounds": "N/A",
        "total_images": 0,
        "quality_distribution": {},
        "avg_clip_score": "N/A",
        "retrieval_vs_generation": {"retrieval": 0, "generation": 0},
        "avg_word_count": 0,
    }

    if not articles:
        return stats

    scores = []
    rounds = []
    word_counts = []
    clip_scores = []

    for a in articles:
        if a.get("score_history"):
            scores.append(a["score_history"][-1])
        rounds.append(a.get("rounds", 0))
        if a.get("word_count"):
            word_counts.append(a["word_count"])

        q = a.get("quality", "")
        if q:
            stats["quality_distribution"][q] = stats["quality_distribution"].get(q, 0) + 1

    # Scan evaluation reports for more detailed stats
    if OUTPUTS_DIR.exists():
        for eval_file in OUTPUTS_DIR.glob("*_eval.json"):
            try:
                with open(eval_file, 'r', encoding='utf-8') as f:
                    eval_data = json.load(f)
                clip_data = eval_data.get("clip", {})
                if clip_data.get("average_score", 0) > 0:
                    clip_scores.append(clip_data["average_score"])

                img_stats = eval_data.get("structure", {})
                stats["total_images"] += img_stats.get("meme_count", 0) + img_stats.get("image_count", 0)
            except Exception:
                continue

        for meta_file in OUTPUTS_DIR.glob("*_meta.json"):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                img_stats = meta.get("image_stats", {})
                stats["retrieval_vs_generation"]["retrieval"] += img_stats.get("retrieval_count", 0)
                stats["retrieval_vs_generation"]["generation"] += img_stats.get("generation_count", 0)
            except Exception:
                continue

    if scores:
        stats["avg_score"] = f"{sum(scores)/len(scores):.1f}/10"
    if rounds:
        stats["avg_rounds"] = f"{sum(rounds)/len(rounds):.1f}"
    if word_counts:
        stats["avg_word_count"] = int(sum(word_counts) / len(word_counts))
    if clip_scores:
        stats["avg_clip_score"] = f"{sum(clip_scores)/len(clip_scores):.4f}"

    return stats


# ============ Routes ============

@app.route("/")
def home():
    return render(HOME_TEMPLATE, title="生成", active_page="home")


@app.route("/history")
def history():
    articles = _get_history()
    return render(HISTORY_TEMPLATE, title="历史", active_page="history", articles=articles)


@app.route("/dashboard")
def dashboard():
    stats = _get_dashboard_stats()
    return render(DASHBOARD_TEMPLATE, title="数据", active_page="dashboard", stats=stats)


@app.route("/preview/<filename>")
def preview(filename):
    """Serve generated article for preview"""
    if not OUTPUTS_DIR.exists():
        return "文件不存在", 404
    return send_from_directory(str(OUTPUTS_DIR), filename)


@app.route("/download/<filename>")
def download(filename):
    """Download generated article"""
    if not OUTPUTS_DIR.exists():
        return "文件不存在", 404
    return send_from_directory(str(OUTPUTS_DIR), filename, as_attachment=True)


@app.route("/outputs/images/<path:subpath>")
def serve_image(subpath):
    """Serve generated images"""
    return send_from_directory(str(IMAGES_DIR), subpath)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Start article generation via EventBus.

    Accepts both form-encoded (legacy HTMX) and JSON (new React frontend) payloads.
    JSON requests receive a JSON response; form requests receive an HTML fragment.
    """
    is_json = request.is_json
    if is_json:
        body = request.get_json(force=True)
        topic = (body.get("topic") or "").strip()
        max_rounds = int(body.get("max_rounds", 3))
        output_format = body.get("format", "html")
        skip_retrieval = bool(body.get("skip_retrieval", False))
    else:
        topic = request.form.get("topic", "").strip()
        max_rounds = int(request.form.get("max_rounds", 3))
        output_format = request.form.get("format", "html")
        skip_retrieval = request.form.get("skip_retrieval") == "1"

    if not topic:
        if is_json:
            return jsonify({"error": "请输入选题"}), 400
        return "<div class='card'><p style='color:red;'>请输入选题</p></div>", 400

    import uuid
    task_id = str(uuid.uuid4())[:8]
    event_bus = EventBus()

    active_tasks[task_id] = {
        "bus": event_bus,
        "topic": topic,
        "status": "running",
        "result": None,
    }

    def run_workflow():
        try:
            from run_workflow import WorkflowRunner

            runner = WorkflowRunner(
                topic=topic,
                max_rounds=max_rounds,
                output_format=output_format,
                skip_retrieval=skip_retrieval,
                skip_eval=False,
                event_bus=event_bus,
            )
            output_path = runner.run()

            if output_path:
                p = Path(output_path)
                stem = p.stem
                meta_path = p.parent / f"{stem.rsplit('_', 0)[0]}_meta.json"
                title = topic
                final_score = 0.0
                if hasattr(runner, 'score_history') and runner.score_history:
                    final_score = runner.score_history[-1]
                for mf in p.parent.glob(f"*_meta.json"):
                    try:
                        with open(mf, 'r', encoding='utf-8') as f:
                            md = json.load(f)
                        if md.get("topic") == topic:
                            title = md.get("topic", topic)
                            break
                    except Exception:
                        continue

                result = {
                    "output_path": output_path,
                    "filename": p.name,
                    "article_id": p.stem,
                    "title": title,
                    "rounds": getattr(runner, 'current_round', 0),
                    "score": f"{final_score}/10" if final_score else "N/A",
                    "final_score": final_score,
                    "word_count": len(getattr(runner, 'final_article', '')),
                    "image_count": (
                        runner._image_results.get("stats", {}).get("meme_count", 0) +
                        runner._image_results.get("stats", {}).get("illust_count", 0)
                    ) if hasattr(runner, '_image_results') and runner._image_results else 0,
                }
                active_tasks[task_id]["status"] = "completed"
                active_tasks[task_id]["result"] = result
                event_bus.emit_done(result)
            else:
                active_tasks[task_id]["status"] = "failed"
                event_bus.emit_failed("No output generated")

        except Exception as e:
            active_tasks[task_id]["status"] = "failed"
            event_bus.error(str(e))
            event_bus.emit_failed(str(e))

    thread = threading.Thread(target=run_workflow, daemon=True)
    thread.start()

    if is_json:
        return jsonify({"task_id": task_id})
    return render_template_string(PROGRESS_TEMPLATE, task_id=task_id)


@app.route("/api/progress/<task_id>")
def api_progress(task_id):
    """SSE endpoint consuming typed WorkflowEvents from EventBus.

    When Accept header includes 'application/json' (React frontend), events are
    sent as named SSE events with JSON data. Otherwise, HTML fragments (legacy HTMX).
    """
    task = active_tasks.get(task_id)
    if not task:
        return "任务不存在", 404

    want_json = 'application/json' in request.headers.get('Accept', '')
    event_bus: EventBus = task["bus"]
    sub_queue = event_bus.subscribe()

    def generate_json():
        """JSON mode: named SSE events for React frontend"""
        try:
            while True:
                try:
                    item = sub_queue.get(timeout=120)

                    if isinstance(item, tuple):
                        sentinel, payload = item
                        if sentinel == _STREAM_DONE:
                            result = payload or task.get("result", {})
                            yield f"event: workflow_end\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
                            yield "event: done\ndata: {}\n\n"
                            break
                        elif sentinel == _STREAM_FAILED:
                            err = payload or "Unknown error"
                            yield f'event: error\ndata: {json.dumps({"message": err}, ensure_ascii=False)}\n\n'
                            yield "event: done\ndata: {}\n\n"
                            break

                    if isinstance(item, WorkflowEvent):
                        evt = item.to_dict()
                        event_name = evt.get("type", "progress")
                        yield f"event: {event_name}\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"

                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(sub_queue)

    def generate_html():
        """HTML mode: legacy HTMX fragments"""
        try:
            while True:
                try:
                    item = sub_queue.get(timeout=120)

                    if isinstance(item, tuple):
                        sentinel, payload = item
                        if sentinel == _STREAM_DONE:
                            result = payload or task.get("result", {})
                            done_html = render_template_string(RESULT_TEMPLATE,
                                rounds=result.get("rounds", 0),
                                score=result.get("score", "N/A"),
                                word_count=result.get("word_count", 0),
                                image_count=result.get("image_count", 0),
                                filename=result.get("filename", ""),
                                preview_url=f"/preview/{result.get('filename', '')}" if result.get("filename") else "",
                            )
                            yield f"data: {done_html}\n\n"
                            break
                        elif sentinel == _STREAM_FAILED:
                            err = payload or "Unknown error"
                            yield f'data: <div class="card"><p style="color:red;">Generation failed: {err}</p></div>\n\n'
                            break

                    if isinstance(item, WorkflowEvent):
                        safe_msg = item.message.replace("<", "&lt;").replace(">", "&gt;")
                        css = item.css_class
                        yield f'data: <div class="{css}">{safe_msg}</div>\n\n'
                    else:
                        safe = str(item).replace("<", "&lt;").replace(">", "&gt;")
                        yield f'data: <div>{safe}</div>\n\n'

                except queue.Empty:
                    yield f'data: <div class="warning">Waiting...</div>\n\n'
        finally:
            event_bus.unsubscribe(sub_queue)

    gen = generate_json() if want_json else generate_html()
    return Response(gen, mimetype='text/event-stream')


# ============ JSON API for React Frontend ============

KEYWORD_DATA = {
    "emotions": ["焦虑", "治愈", "暴怒", "共情", "emo", "破防", "上头", "窒息", "感动", "无语", "释然", "社恐"],
    "objects": ["AI", "咖啡", "考研", "房价", "猫", "新能源", "奶茶", "元宇宙", "打工人", "减肥", "旅行", "数字游民"],
    "trending": [],
    "styles": ["讽刺", "温情", "硬核", "毒鸡汤", "学术", "段子手", "深度", "科普", "暗黑", "治愈系"],
    "memes": ["狗头", "摆烂", "芭比Q", "绝绝子", "YYDS", "栓Q", "蚌埠住了", "内卷", "躺平", "卷王"],
}


@app.route("/api/keywords")
def api_keywords():
    """Return categorized keywords for the word cloud."""
    data = dict(KEYWORD_DATA)
    meme_tags_path = PROJECT_ROOT / "memes" / "tags.json"
    if meme_tags_path.exists():
        try:
            with open(meme_tags_path, 'r', encoding='utf-8') as f:
                tags_data = json.load(f)
            if isinstance(tags_data, list):
                data["memes"] = list(set(data["memes"] + tags_data[:20]))
            elif isinstance(tags_data, dict):
                all_tags = []
                for v in tags_data.values():
                    if isinstance(v, list):
                        all_tags.extend(v[:5])
                data["memes"] = list(set(data["memes"] + all_tags[:20]))
        except Exception:
            pass
    return jsonify(data)


@app.route("/api/articles")
def api_articles():
    """List all articles with metadata as JSON."""
    articles = []
    if not OUTPUTS_DIR.exists():
        return jsonify(articles)

    for meta_file in sorted(OUTPUTS_DIR.glob("*_meta.json"), reverse=True):
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            stem = meta_file.stem.replace("_meta", "")
            html_file = f"{stem}.html"
            html_path = OUTPUTS_DIR / html_file

            score = 0.0
            sh = meta.get("score_history", [])
            if sh:
                score = sh[-1] if isinstance(sh[-1], (int, float)) else 0.0

            articles.append({
                "id": stem,
                "title": meta.get("topic", "未知选题"),
                "createdAt": meta.get("created_at", ""),
                "score": score,
                "rounds": meta.get("rounds", 0),
                "format": "html" if html_path.exists() else "markdown",
                "previewUrl": f"/api/articles/{stem}/preview",
                "downloadUrl": f"/api/articles/{stem}/download",
            })
        except Exception:
            continue

    return jsonify(articles)


@app.route("/api/articles/<article_id>/preview")
def api_article_preview(article_id):
    """Return raw HTML content for iframe srcdoc rendering."""
    if not OUTPUTS_DIR.exists():
        return "Not found", 404

    html_path = OUTPUTS_DIR / f"{article_id}.html"
    if html_path.exists():
        return send_from_directory(str(OUTPUTS_DIR), f"{article_id}.html")

    for f in OUTPUTS_DIR.glob("*.html"):
        if f.stem == article_id or article_id in f.stem:
            return send_from_directory(str(OUTPUTS_DIR), f.name)

    return "Not found", 404


@app.route("/api/articles/<article_id>/download")
def api_article_download(article_id):
    """Download article as attachment."""
    if not OUTPUTS_DIR.exists():
        return "Not found", 404

    html_path = OUTPUTS_DIR / f"{article_id}.html"
    if html_path.exists():
        return send_from_directory(str(OUTPUTS_DIR), f"{article_id}.html", as_attachment=True)

    for f in OUTPUTS_DIR.glob("*.html"):
        if f.stem == article_id or article_id in f.stem:
            return send_from_directory(str(OUTPUTS_DIR), f.name, as_attachment=True)

    return "Not found", 404


# ============ Frontend Serving (production build) ============

@app.route("/app")
@app.route("/app/<path:path>")
def serve_frontend(path="index.html"):
    """Serve the React frontend from frontend/dist/."""
    if not FRONTEND_DIST.exists():
        return "Frontend not built. Run 'npm run build' in frontend/.", 404
    full = FRONTEND_DIST / path
    if full.is_file():
        return send_from_directory(str(FRONTEND_DIST), path)
    return send_from_directory(str(FRONTEND_DIST), "index.html")


# ============ Entry point ============

if __name__ == "__main__":
    import argparse
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())

    parser = argparse.ArgumentParser(description='微信公众号文章生成器 Web 界面')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=5000, help='监听端口')
    parser.add_argument('--debug', action='store_true', help='调试模式')

    args = parser.parse_args()

    logger.info("微信公众号文章生成器 Web 界面")
    logger.info("访问: http://localhost:%d", args.port)

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
