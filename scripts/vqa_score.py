#!/usr/bin/env python3
"""
VQA Score 图文对齐评估模块

基于 VQA (Visual Question Answering) 模型评估图片与文本的语义匹配。
使用 BLIP-2 或兼容模型，通过提问 "Does this image match: {text}?" 的方式
获取图文相关性得分。

作为 CLIP Score 的补充评估维度。
"""

import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from log_config import get_logger

logger = get_logger(__name__)


@dataclass
class VQAScoreResult:
    """单张图片的 VQA Score 结果"""
    image_path: str
    text: str
    question: str
    answer: str
    confidence: float
    score: float


class VQAScorer:
    """VQA Score 评估器"""

    def __init__(self, model_name: str = "Salesforce/blip2-opt-2.7b"):
        self.model_name = model_name
        self.model = None
        self.processor = None
        self.device = None

    def load(self):
        """加载 VQA 模型"""
        try:
            import torch
            from transformers import Blip2Processor, Blip2ForConditionalGeneration

            self.device = (
                "cuda" if torch.cuda.is_available()
                else "mps" if torch.backends.mps.is_available()
                else "cpu"
            )

            logger.info("加载 VQA 模型: %s ...", self.model_name)
            self.processor = Blip2Processor.from_pretrained(self.model_name)
            self.model = Blip2ForConditionalGeneration.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            ).to(self.device)
            self.model.eval()
            logger.info("VQA 模型加载成功 (device: %s)", self.device)
        except ImportError:
            raise ImportError(
                "VQA Score 需要安装 transformers: pip install transformers"
            )

    def compute_score(self, image_path: str, text: str) -> Optional[VQAScoreResult]:
        """
        计算单张图片与文本的 VQA Score

        通过向模型提问的方式评估图文匹配度
        """
        import torch
        from PIL import Image

        if self.model is None:
            raise RuntimeError("模型未加载，请先调用 load()")

        img_path = Path(image_path)
        if not img_path.exists():
            return None

        try:
            image = Image.open(img_path).convert("RGB")

            # Strategy 1: Ask relevance question
            question = f"Does this image represent or relate to: {text}? Answer yes or no."
            inputs = self.processor(image, question, return_tensors="pt").to(self.device)

            with torch.no_grad():
                outputs = self.model.generate(**inputs, max_new_tokens=10)
            answer = self.processor.decode(outputs[0], skip_special_tokens=True).strip().lower()

            # Strategy 2: Generate caption and compute overlap
            caption_inputs = self.processor(image, return_tensors="pt").to(self.device)
            with torch.no_grad():
                caption_ids = self.model.generate(**caption_inputs, max_new_tokens=50)
            caption = self.processor.decode(caption_ids[0], skip_special_tokens=True).strip()

            # Compute score based on answer and caption similarity
            if "yes" in answer:
                base_score = 0.8
            elif "no" in answer:
                base_score = 0.2
            else:
                base_score = 0.5

            # Bonus for caption overlap with text
            text_words = set(text.lower().split())
            caption_words = set(caption.lower().split())
            if text_words and caption_words:
                overlap = len(text_words & caption_words) / max(len(text_words), 1)
                base_score = base_score * 0.7 + overlap * 0.3

            confidence = 1.0 if "yes" in answer or "no" in answer else 0.5

            return VQAScoreResult(
                image_path=str(img_path),
                text=text,
                question=question,
                answer=answer,
                confidence=confidence,
                score=round(base_score, 4),
            )

        except Exception as e:
            logger.error("VQA Score 计算失败: %s", e)
            return None

    def evaluate_article_images(self, image_results: dict) -> dict:
        """评估文章中所有图片的 VQA Score"""
        results = []

        for tag, info in image_results.get("memes", {}).items():
            if info.get("path") and Path(info["path"]).exists():
                result = self.compute_score(info["path"], tag)
                if result:
                    results.append(asdict(result))

        for tag, info in image_results.get("illustrations", {}).items():
            desc = info.get("description", tag)
            if info.get("path") and Path(info["path"]).exists():
                result = self.compute_score(info["path"], desc)
                if result:
                    results.append(asdict(result))

        avg_score = 0.0
        if results:
            avg_score = sum(r["score"] for r in results) / len(results)

        return {
            "total_images": len(results),
            "average_score": round(avg_score, 4),
            "per_image_scores": results,
        }


if __name__ == "__main__":
    import argparse
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())

    parser = argparse.ArgumentParser(description='VQA Score 图文对齐评估')
    parser.add_argument('--image', type=str, help='图片路径')
    parser.add_argument('--text', type=str, help='文本描述')

    args = parser.parse_args()

    if args.image and args.text:
        scorer = VQAScorer()
        scorer.load()
        result = scorer.compute_score(args.image, args.text)
        if result:
            logger.info("结果: %s", json.dumps(asdict(result), indent=2, ensure_ascii=False))
    else:
        logger.info("VQA Score 评估工具")
        logger.info("用法: python vqa_score.py --image path/to/image.png --text '描述'")
        logger.info("需要安装: pip install transformers torch")
        logger.info("模型: Salesforce/blip2-opt-2.7b (首次运行需下载)")
