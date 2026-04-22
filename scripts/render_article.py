#!/usr/bin/env python3
"""
文章渲染脚本 - 处理表情包和插图，生成最终 HTML

流程：
1. 解析文章中的 [MEME: xxx] 和 [IMG: xxx] 标记
2. 表情包：先 CLIP 检索，失败则调用 Gemini 生成
3. 插图：直接调用 Gemini 生成
4. 替换标记为实际图片，生成 HTML
"""

import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

from log_config import get_logger
from meme_retrieval import MemeRetriever
from gemini_client import generate_image

logger = get_logger(__name__)

try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False


# ============ 文章处理 ============

def parse_img_tag(tag: str) -> Tuple[str, str]:
    """
    解析 [IMG: xxx] 标记
    
    Returns:
        (描述, 风格)
    """
    # 尝试分割描述和风格
    if '，' in tag:
        parts = tag.rsplit('，', 1)
        if '风格' in parts[-1]:
            return parts[0].strip(), parts[-1].strip()
    if ',' in tag:
        parts = tag.rsplit(',', 1)
        if 'style' in parts[-1].lower() or '风格' in parts[-1]:
            return parts[0].strip(), parts[-1].strip()
    
    return tag.strip(), "科技扁平风格"


def process_article(content: str, retriever: Optional[MemeRetriever] = None) -> dict:
    """
    处理文章中的所有图片标记
    
    Args:
        content: 带有 [MEME: xxx] 和 [IMG: xxx] 标记的文章内容
        retriever: 表情包检索器（可选）
    
    Returns:
        {
            "memes": {"tag": {"path": "...", "source": "retrieval/generation"}},
            "illustrations": {"desc": {"path": "...", "style": "..."}},
            "stats": {"meme_count": x, "illust_count": y, "generated": z}
        }
    """
    results = {
        "memes": {},
        "illustrations": {},
        "stats": {
            "meme_count": 0,
            "illust_count": 0,
            "retrieval_count": 0,
            "generation_count": 0
        }
    }
    
    # 处理表情包 [MEME: xxx]
    meme_pattern = r'\[MEME:\s*([^\]]+)\]'
    meme_tags = set(re.findall(meme_pattern, content))
    
    for tag in meme_tags:
        tag = tag.strip()
        logger.info("处理表情包: %s", tag)
        
        if retriever and retriever.embeddings is not None:
            path, score, source = retriever.get_meme(tag)
            results["memes"][tag] = {
                "path": path,
                "score": score,
                "source": source,
            }
            if source == "retrieval" or source == "retrieval_fallback":
                results["stats"]["retrieval_count"] += 1
            elif source == "generation":
                results["stats"]["generation_count"] += 1
            logger.info("  -> %s: %s (score: %.3f)", source, path, score)
        else:
            gen_path = generate_image(tag, "meme")
            if gen_path:
                results["memes"][tag] = {
                    "path": gen_path,
                    "score": 1.0,
                    "source": "generation"
                }
                results["stats"]["generation_count"] += 1
            else:
                results["memes"][tag] = {
                    "path": None,
                    "score": 0,
                    "source": "failed"
                }
    
    results["stats"]["meme_count"] = len(meme_tags)
    
    # 处理插图 [IMG: xxx]
    img_pattern = r'\[IMG:\s*([^\]]+)\]'
    img_tags = set(re.findall(img_pattern, content))
    
    for tag in img_tags:
        description, style = parse_img_tag(tag)
        logger.info("处理插图: %s (%s)", description, style)
        
        # 插图直接生成
        full_prompt = f"{description}, {style}"
        gen_path = generate_image(full_prompt, "illustration")
        
        if gen_path:
            results["illustrations"][tag] = {
                "path": gen_path,
                "description": description,
                "style": style,
                "source": "generation"
            }
            results["stats"]["generation_count"] += 1
        else:
            results["illustrations"][tag] = {
                "path": None,
                "description": description,
                "style": style,
                "source": "failed"
            }
    
    results["stats"]["illust_count"] = len(img_tags)
    
    return results


def markdown_to_html(content: str) -> str:
    """
    将 Markdown 转换为 HTML
    """
    if HAS_MARKDOWN:
        # 使用 markdown 库
        md = markdown.Markdown(extensions=['tables', 'fenced_code'])
        html = md.convert(content)
        return html
    
    # 简单的 Markdown 转换（备选方案）
    lines = content.split('\n')
    html_lines = []
    in_blockquote = False
    in_list = False
    in_table = False
    
    for line in lines:
        stripped = line.strip()
        
        # 处理水平线
        if stripped == '---' or stripped == '***':
            if in_blockquote:
                html_lines.append('</blockquote>')
                in_blockquote = False
            html_lines.append('<div class="divider"></div>')
            continue
        
        # 处理标题
        if stripped.startswith('# '):
            html_lines.append(f'<h1>{stripped[2:]}</h1>')
            continue
        elif stripped.startswith('## '):
            html_lines.append(f'<h2>{stripped[3:]}</h2>')
            continue
        elif stripped.startswith('### '):
            html_lines.append(f'<h3>{stripped[4:]}</h3>')
            continue
        
        # 处理引用
        if stripped.startswith('> '):
            if not in_blockquote:
                html_lines.append('<blockquote>')
                in_blockquote = True
            quote_content = stripped[2:]
            # 处理引用内的加粗
            quote_content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', quote_content)
            html_lines.append(f'<p>{quote_content}</p>')
            continue
        elif in_blockquote and stripped == '':
            html_lines.append('</blockquote>')
            in_blockquote = False
            continue
        
        # 处理列表
        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            list_content = stripped[2:]
            list_content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', list_content)
            html_lines.append(f'<li>{list_content}</li>')
            continue
        elif stripped.startswith(('1. ', '2. ', '3. ', '4. ', '5. ')):
            if not in_list:
                html_lines.append('<ol>')
                in_list = True
            list_content = stripped[3:]
            list_content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', list_content)
            html_lines.append(f'<li>{list_content}</li>')
            continue
        elif in_list and stripped == '':
            if '<ol>' in ''.join(html_lines[-10:]):
                html_lines.append('</ol>')
            else:
                html_lines.append('</ul>')
            in_list = False
            continue
        
        # 处理表格
        if '|' in stripped and stripped.startswith('|'):
            if not in_table:
                html_lines.append('<table>')
                in_table = True
            if stripped.replace('|', '').replace('-', '').replace(' ', '') == '':
                continue  # 跳过分隔行
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            row_html = '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>'
            html_lines.append(row_html)
            continue
        elif in_table and '|' not in stripped:
            html_lines.append('</table>')
            in_table = False
        
        # 处理普通段落
        if stripped:
            # 如果是 HTML 标签，直接保留
            if stripped.startswith('<') and stripped.endswith('>'):
                html_lines.append(stripped)
                continue
            if stripped.startswith('<div') or stripped.startswith('</div') or stripped.startswith('<img'):
                html_lines.append(stripped)
                continue
            
            # 处理加粗
            para = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
            # 处理斜体
            para = re.sub(r'\*(.+?)\*', r'<em>\1</em>', para)
            # 处理行内代码
            para = re.sub(r'`(.+?)`', r'<code>\1</code>', para)
            html_lines.append(f'<p>{para}</p>')
        elif stripped == '':
            # 空行
            if in_blockquote:
                html_lines.append('</blockquote>')
                in_blockquote = False
    
    # 关闭未关闭的标签
    if in_blockquote:
        html_lines.append('</blockquote>')
    if in_list:
        html_lines.append('</ul>')
    if in_table:
        html_lines.append('</table>')
    
    return '\n'.join(html_lines)


def get_relative_path(image_path: str) -> str:
    """
    将图片路径转换为相对于 outputs/articles/ 的路径
    
    输入: outputs/images/memes/xxx.png
    输出: ../images/memes/xxx.png
    """
    if image_path.startswith("outputs/"):
        # 去掉 "outputs/" 前缀，加上 "../"
        return "../" + image_path[8:]  # 8 = len("outputs/")
    elif image_path.startswith("memes/"):
        # memes/images/xxx.png -> ../../memes/images/xxx.png
        return "../../" + image_path
    return image_path


def render_html(content: str, title: str, image_results: dict, 
                template_path: str = "templates/article.html") -> str:
    """
    将处理后的内容渲染为 HTML
    """
    # 替换表情包标记
    for tag, info in image_results["memes"].items():
        pattern = rf'\[MEME:\s*{re.escape(tag)}\]'
        if info["path"]:
            img_path = get_relative_path(info["path"])
            replacement = f'''<div class="meme-placeholder">
        <img src="{img_path}" alt="{tag}" class="meme-img">
      </div>'''
        else:
            # 使用 emoji 占位
            emoji_map = {
                "震惊": "😱", "目瞪口呆": "😱", "DNA动了": "🧬",
                "狗头": "🐶", "无语": "😑", "钞票": "💸",
                "危险": "⚠️", "警告": "⚠️", "蜡烛": "🕯️",
                "悼念": "🕯️", "破防": "😭", "泪目": "😭",
                "敬礼": "🫡", "致敬": "🫡", "叹气": "😮‍💨", "无奈": "😮‍💨"
            }
            first_key = tag.split('/')[0]
            emoji = emoji_map.get(first_key, "😀")
            replacement = f'''<div class="meme-placeholder">
        <span class="emoji">{emoji}</span>
        <span>{tag}</span>
      </div>'''
        content = re.sub(pattern, replacement, content)
    
    # 替换插图标记
    for tag, info in image_results["illustrations"].items():
        pattern = rf'\[IMG:\s*{re.escape(tag)}\]'
        if info["path"]:
            img_path = get_relative_path(info["path"])
            replacement = f'''<div class="img-placeholder">
        <img src="{img_path}" alt="{info['description']}" class="featured-img">
      </div>'''
        else:
            replacement = f'''<div class="img-placeholder">
        <div class="icon">🖼️</div>
        <p>{info['description']}<br><small>{info['style']}</small></p>
      </div>'''
        content = re.sub(pattern, replacement, content)
    
    # 加载模板
    if Path(template_path).exists():
        with open(template_path, 'r', encoding='utf-8') as f:
            html = f.read()
    else:
        # 使用简单模板
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>{{TITLE}}</title>
</head>
<body>
  <article>
    <h1>{{TITLE}}</h1>
    <div>{{CONTENT}}</div>
  </article>
</body>
</html>"""
    
    # 将 Markdown 转换为 HTML
    content_html = markdown_to_html(content)
    
    # 替换模板变量
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    rounds = str(image_results.get("workflow", {}).get("rounds", 1))
    score = image_results.get("workflow", {}).get("score", "N/A")
    clip_avg = image_results.get("clip_report", {}).get("average_score", "")
    score_display = f"{score}"
    if clip_avg:
        score_display += f" (CLIP: {clip_avg})"

    html = html.replace("{{TITLE}}", title)
    html = html.replace("{{TIMESTAMP}}", timestamp)
    html = html.replace("{{CONTENT}}", content_html)
    html = html.replace("{{WORD_COUNT}}", str(len(content)))
    html = html.replace("{{ROUNDS}}", rounds)
    html = html.replace("{{SCORE}}", score_display)
    html = html.replace("{{MEME_COUNT}}", str(image_results["stats"]["meme_count"]))
    html = html.replace("{{IMG_COUNT}}", str(image_results["stats"]["illust_count"]))
    html = html.replace("{{TAGS}}", "")

    return html


def render_markdown(content: str, image_results: dict) -> str:
    """
    将图片标记替换为 Markdown 图片语法，输出纯 Markdown 文件
    """
    for tag, info in image_results.get("memes", {}).items():
        pattern = rf'\[MEME:\s*{re.escape(tag)}\]'
        if info.get("path"):
            replacement = f'![{tag}]({info["path"]})'
        else:
            replacement = f'*[表情包: {tag}]*'
        content = re.sub(pattern, replacement, content)

    for tag, info in image_results.get("illustrations", {}).items():
        pattern = rf'\[IMG:\s*{re.escape(tag)}\]'
        desc = info.get("description", tag)
        if info.get("path"):
            replacement = f'![{desc}]({info["path"]})'
        else:
            replacement = f'*[插图: {desc}]*'
        content = re.sub(pattern, replacement, content)

    return content


def run_clip_evaluation(image_results: dict) -> Optional[dict]:
    """运行 CLIP Score 评估（如果模型可加载）"""
    try:
        from clip_score import CLIPScorer
        from dataclasses import asdict

        scorer = CLIPScorer()
        scorer.load()
        report = scorer.evaluate_article_images(image_results)
        report_dict = asdict(report)

        logger.info("CLIP Score 评估")
        logger.info("  评估图片: %d/%d", report.scored_images, report.total_images)
        logger.info("  平均分数: %.4f", report.average_score)
        logger.info("  归一化分: %.4f", report.average_normalized)
        logger.info("  整体质量: %s", report.overall_quality)

        return report_dict
    except ImportError:
        logger.warning("未安装 CLIP 依赖，跳过图文对齐评估")
        return None
    except Exception as e:
        logger.warning("CLIP Score 评估失败: %s", e)
        return None


def main():
    parser = argparse.ArgumentParser(description='渲染文章并处理图片')
    parser.add_argument('--input', type=str, help='输入的 Markdown 文件')
    parser.add_argument('--content', type=str, help='直接输入的文章内容')
    parser.add_argument('--title', type=str, default='文章', help='文章标题')
    parser.add_argument('--output', type=str, help='输出的 HTML 文件')
    parser.add_argument('--format', choices=['html', 'markdown', 'both'],
                        default='html', help='输出格式 (默认: html)')
    parser.add_argument('--skip-retrieval', action='store_true', help='跳过检索，直接生成')
    parser.add_argument('--skip-clip', action='store_true', help='跳过 CLIP Score 评估')

    args = parser.parse_args()

    if args.input:
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
    elif args.content:
        content = args.content
    else:
        logger.error("请提供 --input 或 --content 参数")
        return

    retriever = None
    if not args.skip_retrieval:
        retriever = MemeRetriever()
        retriever.load()

    logger.info("开始处理文章图片")

    image_results = process_article(content, retriever)

    if not args.skip_clip:
        clip_report = run_clip_evaluation(image_results)
        if clip_report:
            image_results["clip_report"] = clip_report

    logger.info("处理统计:")
    logger.info("  表情包数量: %d", image_results['stats']['meme_count'])
    logger.info("  插图数量: %d", image_results['stats']['illust_count'])
    logger.info("  检索成功: %d", image_results['stats']['retrieval_count'])
    logger.info("  生成成功: %d", image_results['stats']['generation_count'])

    if args.output:
        output_base = Path(args.output)

        if args.format in ('html', 'both'):
            html_path = output_base.with_suffix('.html') if args.format == 'both' else output_base
            html = render_html(content, args.title, image_results)
            html_path.parent.mkdir(parents=True, exist_ok=True)
            with open(html_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(html)
            logger.info("HTML 已保存到: %s", html_path)

        if args.format in ('markdown', 'both'):
            md_path = output_base.with_suffix('.md') if args.format == 'both' else output_base
            md_content = render_markdown(content, image_results)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            with open(md_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(md_content)
            logger.info("Markdown 已保存到: %s", md_path)

    logger.info("处理结果: %s", json.dumps(image_results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())
    main()
