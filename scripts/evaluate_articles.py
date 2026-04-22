#!/usr/bin/env python3
"""
文章质量量化评估管线

对生成的文章进行多维度量化评估，输出 JSON 报告。
评估维度：
1. CLIP Score - 图文对齐质量
2. 结构指标 - 段落数、标题数、表情包/配图数量
3. 可读性 - 句长方差、词汇多样性
4. 深度指标 - 数据引用数、信息源数量
"""

import re
import json
import math
import argparse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import Optional
from collections import Counter

from log_config import get_logger

logger = get_logger(__name__)


@dataclass
class StructureMetrics:
    """结构指标"""
    word_count: int = 0
    paragraph_count: int = 0
    heading_count: int = 0
    h2_count: int = 0
    h3_count: int = 0
    meme_count: int = 0
    image_count: int = 0
    blockquote_count: int = 0
    list_count: int = 0
    table_count: int = 0


@dataclass
class ReadabilityMetrics:
    """可读性指标"""
    avg_sentence_length: float = 0.0
    sentence_length_variance: float = 0.0
    vocabulary_size: int = 0
    vocabulary_diversity: float = 0.0
    total_sentences: int = 0


@dataclass
class DepthMetrics:
    """深度指标"""
    data_citation_count: int = 0
    source_reference_count: int = 0
    technical_term_count: int = 0
    question_count: int = 0
    has_conclusion: bool = False


@dataclass
class CLIPMetrics:
    """CLIP Score 指标"""
    total_images: int = 0
    scored_images: int = 0
    average_score: float = 0.0
    average_normalized: float = 0.0
    overall_quality: str = "N/A"
    per_image_scores: list = field(default_factory=list)


@dataclass
class EvaluationReport:
    """完整评估报告"""
    article_path: str = ""
    evaluated_at: str = ""
    structure: StructureMetrics = field(default_factory=StructureMetrics)
    readability: ReadabilityMetrics = field(default_factory=ReadabilityMetrics)
    depth: DepthMetrics = field(default_factory=DepthMetrics)
    clip: CLIPMetrics = field(default_factory=CLIPMetrics)
    overall_score: float = 0.0
    quality_level: str = ""


def _split_sentences(text: str) -> list[str]:
    """将中文文本拆分为句子"""
    separators = r'[。！？!?\n]+'
    sentences = re.split(separators, text)
    return [s.strip() for s in sentences if len(s.strip()) > 1]


def _count_chinese_chars(text: str) -> int:
    """统计中文字符数"""
    return len(re.findall(r'[\u4e00-\u9fff]', text))


def _extract_words(text: str) -> list[str]:
    """简单分词（按标点和空格切分，适用于中文混合文本）"""
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    english_words = re.findall(r'[a-zA-Z]+', text)
    return chinese_chars + english_words


def evaluate_structure(content: str) -> StructureMetrics:
    """评估文章结构"""
    metrics = StructureMetrics()

    clean = re.sub(r'<[^>]+>', '', content)
    metrics.word_count = len(clean.replace('\n', '').replace(' ', ''))

    paragraphs = [p.strip() for p in clean.split('\n\n') if p.strip()]
    metrics.paragraph_count = len(paragraphs)

    metrics.h2_count = len(re.findall(r'^##\s', content, re.MULTILINE))
    metrics.h3_count = len(re.findall(r'^###\s', content, re.MULTILINE))
    metrics.heading_count = metrics.h2_count + metrics.h3_count
    # Also check for HTML headings
    metrics.heading_count += len(re.findall(r'<h[23][^>]*>', content))

    metrics.meme_count = len(re.findall(r'\[MEME:\s*[^\]]+\]', content))
    metrics.image_count = len(re.findall(r'\[IMG:\s*[^\]]+\]', content))
    # Also count rendered images
    metrics.image_count += len(re.findall(r'<img\s', content))

    metrics.blockquote_count = len(re.findall(r'^>\s', content, re.MULTILINE))
    metrics.blockquote_count += len(re.findall(r'<blockquote', content))

    metrics.list_count = len(re.findall(r'^[-*]\s|^\d+\.\s', content, re.MULTILINE))
    metrics.table_count = len(re.findall(r'<table|^\|.*\|.*\|', content, re.MULTILINE))

    return metrics


def evaluate_readability(content: str) -> ReadabilityMetrics:
    """评估可读性"""
    metrics = ReadabilityMetrics()

    clean = re.sub(r'<[^>]+>', '', content)
    clean = re.sub(r'\[MEME:[^\]]+\]|\[IMG:[^\]]+\]', '', clean)

    sentences = _split_sentences(clean)
    metrics.total_sentences = len(sentences)

    if not sentences:
        return metrics

    lengths = [len(s) for s in sentences]
    metrics.avg_sentence_length = sum(lengths) / len(lengths)

    if len(lengths) > 1:
        mean = metrics.avg_sentence_length
        variance = sum((l - mean) ** 2 for l in lengths) / (len(lengths) - 1)
        metrics.sentence_length_variance = round(math.sqrt(variance), 2)

    words = _extract_words(clean)
    metrics.vocabulary_size = len(set(words))

    if len(words) > 0:
        metrics.vocabulary_diversity = round(len(set(words)) / len(words), 4)

    metrics.avg_sentence_length = round(metrics.avg_sentence_length, 2)
    return metrics


def evaluate_depth(content: str) -> DepthMetrics:
    """评估内容深度"""
    metrics = DepthMetrics()

    clean = re.sub(r'<[^>]+>', '', content)

    # Data citations: numbers with units, percentages, years
    metrics.data_citation_count = len(re.findall(
        r'\d+%|\d+\.\d+|\d+亿|\d+万|\d{4}年|第\d+', clean
    ))

    # Source references: "据...报道", "来源:", URLs, "研究表明"
    source_patterns = [
        r'据.{2,10}报道', r'来源[:：]', r'https?://',
        r'研究表明', r'数据显示', r'报告指出',
        r'根据.{2,10}统计', r'引用', r'\[参考\]',
    ]
    for pattern in source_patterns:
        metrics.source_reference_count += len(re.findall(pattern, clean))

    # Technical terms (common AI/tech terms)
    tech_terms = [
        'AI', '人工智能', '大模型', 'LLM', 'GPT', 'CLIP', 'Transformer',
        'API', '算法', '神经网络', '深度学习', '机器学习', '自然语言处理',
        'NLP', '多模态', '向量', '嵌入', '检索', '生成', '微调',
        'token', 'prompt', '推理', '训练', '数据集', '参数',
    ]
    for term in tech_terms:
        count = len(re.findall(re.escape(term), clean, re.IGNORECASE))
        if count > 0:
            metrics.technical_term_count += 1

    metrics.question_count = len(re.findall(r'[？?]', clean))

    conclusion_patterns = [
        r'总结', r'结语', r'最后', r'综上', r'总的来说',
        r'写在最后', r'结尾', r'展望',
    ]
    for pattern in conclusion_patterns:
        if re.search(pattern, clean):
            metrics.has_conclusion = True
            break

    return metrics


def evaluate_clip_scores(image_results: Optional[dict]) -> CLIPMetrics:
    """评估 CLIP Score（需要图片处理结果）"""
    metrics = CLIPMetrics()

    if not image_results:
        return metrics

    # If clip_report already exists in image_results, use it
    clip_report = image_results.get("clip_report")
    if clip_report:
        metrics.total_images = clip_report.get("total_images", 0)
        metrics.scored_images = clip_report.get("scored_images", 0)
        metrics.average_score = clip_report.get("average_score", 0.0)
        metrics.average_normalized = clip_report.get("average_normalized", 0.0)
        metrics.overall_quality = clip_report.get("overall_quality", "N/A")
        all_scores = clip_report.get("meme_scores", []) + clip_report.get("illustration_scores", [])
        metrics.per_image_scores = all_scores
        return metrics

    # Otherwise try to compute from scratch
    try:
        from clip_score import CLIPScorer
        scorer = CLIPScorer()
        scorer.load()
        report = scorer.evaluate_article_images(image_results)
        metrics.total_images = report.total_images
        metrics.scored_images = report.scored_images
        metrics.average_score = report.average_score
        metrics.average_normalized = report.average_normalized
        metrics.overall_quality = report.overall_quality
        metrics.per_image_scores = report.meme_scores + report.illustration_scores
    except Exception as e:
        logger.warning("CLIP Score 评估跳过: %s", e)

    return metrics


def compute_overall_score(structure: StructureMetrics,
                          readability: ReadabilityMetrics,
                          depth: DepthMetrics,
                          clip: CLIPMetrics) -> tuple[float, str]:
    """
    计算综合得分（满分 100）

    权重分配：
    - 结构 25%: 字数适中、段落丰富、有标题层级
    - 可读性 20%: 句长适中、词汇多样
    - 深度 30%: 数据引用、信息源、技术术语
    - 图文 25%: CLIP Score、图片数量
    """
    score = 0.0

    # Structure (25 points)
    s = 0.0
    if 2000 <= structure.word_count <= 5000:
        s += 8
    elif 1000 <= structure.word_count < 2000 or 5000 < structure.word_count <= 8000:
        s += 5
    elif structure.word_count > 0:
        s += 2

    if structure.paragraph_count >= 8:
        s += 5
    elif structure.paragraph_count >= 4:
        s += 3

    if structure.heading_count >= 3:
        s += 5
    elif structure.heading_count >= 1:
        s += 3

    if structure.blockquote_count >= 1:
        s += 2
    if structure.list_count >= 2:
        s += 2
    if structure.table_count >= 1:
        s += 3
    score += min(s, 25)

    # Readability (20 points)
    r = 0.0
    if 15 <= readability.avg_sentence_length <= 40:
        r += 8
    elif readability.avg_sentence_length > 0:
        r += 4

    if readability.sentence_length_variance >= 5:
        r += 4
    elif readability.sentence_length_variance > 0:
        r += 2

    if readability.vocabulary_diversity >= 0.6:
        r += 8
    elif readability.vocabulary_diversity >= 0.4:
        r += 5
    elif readability.vocabulary_diversity > 0:
        r += 2
    score += min(r, 20)

    # Depth (30 points)
    d = 0.0
    if depth.data_citation_count >= 5:
        d += 10
    elif depth.data_citation_count >= 2:
        d += 6
    elif depth.data_citation_count >= 1:
        d += 3

    if depth.source_reference_count >= 3:
        d += 8
    elif depth.source_reference_count >= 1:
        d += 4

    if depth.technical_term_count >= 8:
        d += 6
    elif depth.technical_term_count >= 3:
        d += 4
    elif depth.technical_term_count >= 1:
        d += 2

    if depth.has_conclusion:
        d += 3
    if depth.question_count >= 2:
        d += 3
    elif depth.question_count >= 1:
        d += 1
    score += min(d, 30)

    # Visual/CLIP (25 points)
    v = 0.0
    total_imgs = structure.meme_count + structure.image_count
    if total_imgs >= 4:
        v += 8
    elif total_imgs >= 2:
        v += 5
    elif total_imgs >= 1:
        v += 3

    if clip.average_score >= 0.30:
        v += 12
    elif clip.average_score >= 0.25:
        v += 9
    elif clip.average_score >= 0.20:
        v += 6
    elif clip.average_score > 0:
        v += 3

    if clip.scored_images > 0 and clip.scored_images == clip.total_images:
        v += 5
    elif clip.scored_images > 0:
        v += 3
    score += min(v, 25)

    score = round(score, 1)
    if score >= 85:
        level = "A"
    elif score >= 70:
        level = "B"
    elif score >= 55:
        level = "C"
    else:
        level = "D"

    return score, level


def evaluate_article(content: str,
                     image_results: Optional[dict] = None,
                     article_path: str = "") -> EvaluationReport:
    """
    对文章进行完整评估

    Args:
        content: 文章内容（Markdown 或 HTML）
        image_results: process_article() 返回的图片处理结果（可选）
        article_path: 文章文件路径

    Returns:
        EvaluationReport
    """
    structure = evaluate_structure(content)
    readability = evaluate_readability(content)
    depth = evaluate_depth(content)
    clip = evaluate_clip_scores(image_results)

    overall_score, quality_level = compute_overall_score(
        structure, readability, depth, clip
    )

    return EvaluationReport(
        article_path=article_path,
        evaluated_at=datetime.now().isoformat(),
        structure=structure,
        readability=readability,
        depth=depth,
        clip=clip,
        overall_score=overall_score,
        quality_level=quality_level,
    )


def print_report(report: EvaluationReport):
    """打印评估报告"""
    print("\n" + "=" * 60)
    print("  文章质量评估报告")
    print("=" * 60)

    if report.article_path:
        print(f"\n  文件: {report.article_path}")
    print(f"  评估时间: {report.evaluated_at}")

    print(f"\n  📊 综合评分: {report.overall_score}/100 ({report.quality_level})")

    s = report.structure
    print(f"\n  📝 结构指标:")
    print(f"     字数: {s.word_count}")
    print(f"     段落: {s.paragraph_count}")
    print(f"     标题: {s.heading_count} (H2: {s.h2_count}, H3: {s.h3_count})")
    print(f"     表情包标记: {s.meme_count}")
    print(f"     配图: {s.image_count}")
    print(f"     引用块: {s.blockquote_count}")
    print(f"     列表: {s.list_count}")

    r = report.readability
    print(f"\n  📖 可读性指标:")
    print(f"     句子数: {r.total_sentences}")
    print(f"     平均句长: {r.avg_sentence_length}")
    print(f"     句长标准差: {r.sentence_length_variance}")
    print(f"     词汇量: {r.vocabulary_size}")
    print(f"     词汇多样性: {r.vocabulary_diversity}")

    d = report.depth
    print(f"\n  🔬 深度指标:")
    print(f"     数据引用: {d.data_citation_count}")
    print(f"     信息源: {d.source_reference_count}")
    print(f"     技术术语: {d.technical_term_count}")
    print(f"     提问数: {d.question_count}")
    print(f"     有结语: {'是' if d.has_conclusion else '否'}")

    c = report.clip
    if c.scored_images > 0:
        print(f"\n  🖼️ CLIP Score:")
        print(f"     评估图片: {c.scored_images}/{c.total_images}")
        print(f"     平均分数: {c.average_score:.4f}")
        print(f"     图文质量: {c.overall_quality}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description='文章质量量化评估')
    parser.add_argument('--input', type=str, required=True,
                        help='输入文章路径 (HTML 或 Markdown)')
    parser.add_argument('--image-results', type=str,
                        help='图片处理结果 JSON 文件路径')
    parser.add_argument('--output', type=str,
                        help='输出评估报告 JSON 路径')
    parser.add_argument('--compare', type=str,
                        help='与基线文章目录比较 (data/articles/)')

    args = parser.parse_args()

    # Read article
    with open(args.input, 'r', encoding='utf-8') as f:
        content = f.read()

    # Load image results if available
    image_results = None
    if args.image_results:
        with open(args.image_results, 'r', encoding='utf-8') as f:
            image_results = json.load(f)

    # Run evaluation
    report = evaluate_article(content, image_results, args.input)
    print_report(report)

    # Save report
    if args.output:
        report_dict = asdict(report)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)
        logger.info("报告已保存: %s", args.output)

    # Compare with baselines
    if args.compare:
        baseline_dir = Path(args.compare)
        if baseline_dir.exists():
            baseline_reports = []
            for f in baseline_dir.glob("*.json"):
                if f.name == "stats.json":
                    continue
                try:
                    with open(f, 'r', encoding='utf-8') as bf:
                        article_data = json.load(bf)
                    article_content = article_data.get("content", "")
                    if article_content:
                        br = evaluate_article(article_content, article_path=str(f))
                        baseline_reports.append(br)
                except Exception:
                    continue

            if baseline_reports:
                avg_baseline = sum(r.overall_score for r in baseline_reports) / len(baseline_reports)
                print(f"\n  📊 基线对比 ({len(baseline_reports)} 篇基线文章):")
                print(f"     基线平均分: {avg_baseline:.1f}/100")
                print(f"     本文得分:   {report.overall_score}/100")
                diff = report.overall_score - avg_baseline
                arrow = "↑" if diff > 0 else "↓" if diff < 0 else "="
                print(f"     差异:       {arrow} {abs(diff):.1f}")


if __name__ == "__main__":
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())
    main()
