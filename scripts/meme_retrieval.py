#!/usr/bin/env python3
"""
表情包语义检索模块

基于 CLIP 向量索引进行表情包语义检索。
支持 OpenCLIP (ViT-B-32) 和 Chinese-CLIP (CN-CLIP) 双模型。
当检索失败时，调用生图 API 生成表情包。
"""

import os
import json
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

from log_config import get_logger

logger = get_logger(__name__)

# 配置
MEME_DIR = Path("memes/images")
EMBEDDINGS_FILE = Path("memes/embeddings.npy")
CN_EMBEDDINGS_FILE = Path("memes/cn_embeddings.npy")
INDEX_FILE = Path("memes/index.json")
TAGS_FILE = Path("memes/tags.json")

# 相似度阈值：低于此值触发生图
SIMILARITY_THRESHOLD = 0.25

# 模型选择: "openclip" 或 "cn-clip"
DEFAULT_CLIP_MODEL = os.getenv("CLIP_MODEL", "openclip")


class MemeRetriever:
    """表情包检索器（OpenCLIP 后端）"""
    
    def __init__(self, clip_model: Optional[str] = None):
        self.clip_model = clip_model or DEFAULT_CLIP_MODEL
        self.model = None
        self.tokenizer = None
        self.preprocess = None
        self.device = None
        self.embeddings: Optional[np.ndarray] = None
        self.filenames: list[str] = []
        self.tags: dict = {}
    
    def load(self):
        """加载模型和索引"""
        if self.clip_model == "cn-clip":
            self._load_cn_clip()
        else:
            self._load_openclip()

        self._load_index()

    def _load_openclip(self):
        """加载 OpenCLIP ViT-B-32 模型"""
        import open_clip
        import torch
        
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32",
            pretrained="openai"
        )
        self.tokenizer = open_clip.get_tokenizer("ViT-B-32")
        
        self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = self.model.to(self.device)
        self.model.eval()
        logger.info("OpenCLIP 模型加载成功 (device: %s)", self.device)

    def _load_cn_clip(self):
        """加载 Chinese-CLIP 模型（更好的中文语义理解）"""
        import torch

        try:
            import cn_clip.clip as clip
            from cn_clip.clip import load_from_name

            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model, self.preprocess = load_from_name(
                "ViT-B-16", device=self.device, download_root="./models"
            )
            self.tokenizer = clip.tokenize
            self.model.eval()
            self.clip_model = "cn-clip"
            logger.info("Chinese-CLIP 模型加载成功 (device: %s)", self.device)
        except ImportError:
            logger.warning("cn-clip 未安装，回退到 OpenCLIP (安装: pip install cn_clip)")
            self._load_openclip()

    def _load_index(self):
        """加载向量索引"""
        embeddings_file = CN_EMBEDDINGS_FILE if self.clip_model == "cn-clip" else EMBEDDINGS_FILE

        if embeddings_file.exists() and INDEX_FILE.exists():
            self.embeddings = np.load(embeddings_file)
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                index = json.load(f)
                self.filenames = index.get("files", [])
            logger.info("已加载 %d 张表情包索引", len(self.filenames))
        elif EMBEDDINGS_FILE.exists() and INDEX_FILE.exists():
            # Fallback to standard embeddings
            self.embeddings = np.load(EMBEDDINGS_FILE)
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                index = json.load(f)
                self.filenames = index.get("files", [])
            logger.info("已加载 %d 张表情包索引 (标准索引)", len(self.filenames))
        else:
            logger.warning("索引文件不存在，请先运行 build_meme_index.py")

        if TAGS_FILE.exists():
            with open(TAGS_FILE, "r", encoding="utf-8") as f:
                self.tags = json.load(f)
    
    def _encode_text(self, query: str):
        """编码文本为向量（适配不同后端）"""
        import torch

        with torch.no_grad():
            if self.clip_model == "cn-clip":
                text = self.tokenizer([query]).to(self.device)
                text_embedding = self.model.encode_text(text)
            else:
                text = self.tokenizer([query]).to(self.device)
                text_embedding = self.model.encode_text(text)

            text_embedding = text_embedding / text_embedding.norm(dim=-1, keepdim=True)
            return text_embedding.cpu().numpy()[0]

    def search(self, query: str, top_k: int = 5) -> list[Tuple[str, float]]:
        """
        搜索最匹配的表情包
        
        Args:
            query: 搜索词，如 "震惊"、"无语"
            top_k: 返回数量
        
        Returns:
            [(文件名, 相似度分数), ...]
        """
        if self.embeddings is None or len(self.filenames) == 0:
            return []
        
        text_embedding = self._encode_text(query)
        similarities = np.dot(self.embeddings, text_embedding)
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            results.append((self.filenames[idx], float(similarities[idx])))
        
        return results
    
    def get_meme(self, query: str) -> Tuple[Optional[str], float, str]:
        """
        获取表情包：优先检索，失败则生成
        
        Args:
            query: 表情包描述，如 "震惊"
        
        Returns:
            (文件路径, 相似度, 来源: "retrieval" 或 "generation")
        """
        # 先尝试检索
        results = self.search(query, top_k=1)
        
        if results and results[0][1] >= SIMILARITY_THRESHOLD:
            filename, score = results[0]
            filepath = str(MEME_DIR / filename)
            return filepath, score, "retrieval"
        
        # 检索失败，尝试生成
        logger.info("检索失败（相似度 < %s），尝试生成...", SIMILARITY_THRESHOLD)
        
        generated_path = self._generate_meme(query)
        if generated_path:
            return generated_path, 1.0, "generation"
        
        # 生成也失败，返回最佳检索结果
        if results:
            filename, score = results[0]
            filepath = str(MEME_DIR / filename)
            return filepath, score, "retrieval_fallback"
        
        return None, 0.0, "not_found"
    
    def _generate_meme(self, prompt: str) -> Optional[str]:
        """调用 Gemini API 生成表情包（通过 gemini_client 统一模块）"""
        try:
            from gemini_client import generate_image
            return generate_image(prompt, image_type="meme")
        except FileNotFoundError:
            logger.warning("未找到 config/gemini.json，无法生成")
            return None
        except Exception as e:
            logger.error("生成失败: %s", e)
            return None


def process_article_memes(content: str, retriever: MemeRetriever) -> dict:
    """
    处理文章中的所有表情包标记
    
    Args:
        content: 带有 [MEME: xxx] 标记的文章内容
        retriever: 表情包检索器
    
    Returns:
        {
            "meme_tag": {
                "path": "文件路径",
                "score": 相似度,
                "source": "retrieval/generation"
            },
            ...
        }
    """
    import re
    
    # 提取所有 MEME 标记
    meme_pattern = r'\[MEME:\s*([^\]]+)\]'
    meme_tags = re.findall(meme_pattern, content)
    
    results = {}
    
    for tag in meme_tags:
        tag = tag.strip()
        if tag in results:
            continue
        
        logger.info("处理: [MEME: %s]", tag)
        path, score, source = retriever.get_meme(tag)
        
        results[tag] = {
            "path": path,
            "score": score,
            "source": source,
        }
        
        logger.info("   -> %s: %s (score: %.3f)", source, path, score)
    
    return results


# 示例使用
if __name__ == "__main__":
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())

    logger.info("表情包检索测试")
    
    retriever = MemeRetriever()
    retriever.load()
    
    test_queries = ["震惊", "无语", "狗头", "开心", "难过"]
    
    for query in test_queries:
        logger.info("查询: %s", query)
        results = retriever.search(query, top_k=3)
        for filename, score in results:
            logger.info("   %s: %.3f", filename, score)
    
    logger.info("文章表情包处理测试")
    
    test_content = """
    这个消息太劲爆了 [MEME: 震惊]
    
    看完之后我直接 [MEME: 无语]
    
    但是仔细想想，也没什么嘛 [MEME: 狗头]
    """
    
    results = process_article_memes(test_content, retriever)
    logger.info("处理结果: %s", json.dumps(results, indent=2, ensure_ascii=False))
