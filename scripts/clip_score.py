#!/usr/bin/env python3
"""
CLIP Score 图文对齐评估模块

基于 CLIPScore (Hessel et al., 2021) 评估图片与文本描述之间的语义对齐质量。
用于：
1. 评估表情包检索/生成结果与原始标记的匹配度
2. 评估插图与场景描述的一致性
3. 作为文章整体图文质量的量化指标
"""

import json
import numpy as np
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from log_config import get_logger

logger = get_logger(__name__)


@dataclass
class CLIPScoreResult:
    """单张图片的 CLIP Score 结果"""
    image_path: str
    text: str
    score: float
    normalized_score: float
    quality_level: str


@dataclass
class ArticleCLIPReport:
    """文章级别的 CLIP Score 报告"""
    total_images: int
    scored_images: int
    average_score: float
    average_normalized: float
    meme_scores: list
    illustration_scores: list
    overall_quality: str


class CLIPScorer:
    """CLIP Score 评估器"""

    QUALITY_THRESHOLDS = {
        "excellent": 0.30,
        "good": 0.25,
        "fair": 0.20,
        "poor": 0.0,
    }

    def __init__(self):
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        self.device = None

    def load(self):
        """加载 CLIP 模型"""
        import open_clip
        import torch

        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="openai"
        )
        self.tokenizer = open_clip.get_tokenizer("ViT-B-32")
        self.device = (
            "cuda" if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available()
            else "cpu"
        )
        self.model = self.model.to(self.device)
        self.model.eval()
        logger.info("CLIP Score 模型加载成功 (device: %s)", self.device)

    def _classify_quality(self, score: float) -> str:
        """根据分数判定质量等级"""
        for level, threshold in self.QUALITY_THRESHOLDS.items():
            if score >= threshold:
                return level
        return "poor"

    def compute_score(self, image_path: str, text: str) -> Optional[CLIPScoreResult]:
        """
        计算单张图片与文本之间的 CLIP Score

        Args:
            image_path: 图片文件路径
            text: 文本描述

        Returns:
            CLIPScoreResult 或 None（图片无法加载时）
        """
        import torch
        from PIL import Image

        if self.model is None:
            raise RuntimeError("模型未加载，请先调用 load()")

        img_path = Path(image_path)
        if not img_path.exists():
            logger.warning("图片不存在: %s", image_path)
            return None

        try:
            image = Image.open(img_path).convert("RGB")
            image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)

            with torch.no_grad():
                image_features = self.model.encode_image(image_tensor)
                text_tokens = self.tokenizer([text]).to(self.device)
                text_features = self.model.encode_text(text_tokens)

                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

                # Cosine similarity as CLIP Score
                raw_score = float((image_features @ text_features.T).squeeze())

            # CLIPScore 通常使用 max(score, 0) * 2.5 归一化到 ~[0,1]
            normalized = max(raw_score, 0) * 2.5
            quality = self._classify_quality(raw_score)

            return CLIPScoreResult(
                image_path=str(image_path),
                text=text,
                score=round(raw_score, 4),
                normalized_score=round(normalized, 4),
                quality_level=quality,
            )

        except Exception as e:
            logger.error("CLIP Score 计算失败 (%s): %s", image_path, e)
            return None

    def evaluate_article_images(self, image_results: dict) -> ArticleCLIPReport:
        """
        评估文章中所有图片的 CLIP Score

        Args:
            image_results: process_article() 返回的结果字典

        Returns:
            ArticleCLIPReport
        """
        meme_scores = []
        illustration_scores = []

        # 评估表情包
        for tag, info in image_results.get("memes", {}).items():
            if info.get("path") and Path(info["path"]).exists():
                result = self.compute_score(info["path"], tag)
                if result:
                    meme_scores.append(asdict(result))

        # 评估插图
        for tag, info in image_results.get("illustrations", {}).items():
            desc = info.get("description", tag)
            if info.get("path") and Path(info["path"]).exists():
                result = self.compute_score(info["path"], desc)
                if result:
                    illustration_scores.append(asdict(result))

        all_scores = meme_scores + illustration_scores
        total = len(image_results.get("memes", {})) + len(image_results.get("illustrations", {}))
        scored = len(all_scores)

        if scored > 0:
            avg_score = np.mean([s["score"] for s in all_scores])
            avg_norm = np.mean([s["normalized_score"] for s in all_scores])
        else:
            avg_score = 0.0
            avg_norm = 0.0

        overall = self._classify_quality(avg_score)

        return ArticleCLIPReport(
            total_images=total,
            scored_images=scored,
            average_score=round(float(avg_score), 4),
            average_normalized=round(float(avg_norm), 4),
            meme_scores=meme_scores,
            illustration_scores=illustration_scores,
            overall_quality=overall,
        )


def main():
    """CLI 测试入口"""
    import argparse

    parser = argparse.ArgumentParser(description='CLIP Score 图文对齐评估')
    parser.add_argument('--image', type=str, help='图片路径')
    parser.add_argument('--text', type=str, help='文本描述')
    parser.add_argument('--article-results', type=str,
                        help='process_article() 输出的 JSON 文件路径')

    args = parser.parse_args()

    scorer = CLIPScorer()
    scorer.load()

    if args.image and args.text:
        result = scorer.compute_score(args.image, args.text)
        if result:
            logger.info("结果: %s", json.dumps(asdict(result), indent=2, ensure_ascii=False))
        else:
            logger.error("评估失败")
    elif args.article_results:
        with open(args.article_results, 'r', encoding='utf-8') as f:
            image_results = json.load(f)
        report = scorer.evaluate_article_images(image_results)
        logger.info("报告: %s", json.dumps(asdict(report), indent=2, ensure_ascii=False))
    else:
        logger.info("用法:")
        logger.info("  python clip_score.py --image path/to/image.png --text '描述文本'")
        logger.info("  python clip_score.py --article-results results.json")


if __name__ == "__main__":
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())
    main()
