#!/usr/bin/env python3
"""
构建表情包 CLIP 向量索引

使用 CLIP 模型将表情包编码为向量，用于后续的语义检索。
"""

import os
import json
import numpy as np
from pathlib import Path
from typing import Optional
from PIL import Image
import torch

from log_config import get_logger

logger = get_logger(__name__)

# 配置
MEME_DIR = Path("memes/images")
TAGS_FILE = Path("memes/tags.json")
EMBEDDINGS_FILE = Path("memes/embeddings.npy")
INDEX_FILE = Path("memes/index.json")

# CLIP 模型配置
CLIP_MODEL = "ViT-B/32"  # 可选: ViT-L/14 更精准但更慢


def load_clip_model():
    """加载 CLIP 模型"""
    try:
        import open_clip
        
        model, _, preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL.replace("/", "-"),
            pretrained="openai"
        )
        tokenizer = open_clip.get_tokenizer(CLIP_MODEL.replace("/", "-"))
        
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        model = model.to(device)
        model.eval()
        
        logger.info("CLIP 模型已加载: %s", CLIP_MODEL)
        logger.info("   设备: %s", device)
        
        return model, preprocess, tokenizer, device
        
    except ImportError:
        logger.error("请先安装 open_clip: pip install open-clip-torch")
        raise


def encode_images(model, preprocess, device, image_paths: list[Path]) -> np.ndarray:
    """编码图片为向量"""
    embeddings = []
    
    with torch.no_grad():
        for i, path in enumerate(image_paths):
            try:
                img = Image.open(path).convert("RGB")
                img_tensor = preprocess(img).unsqueeze(0).to(device)
                
                embedding = model.encode_image(img_tensor)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)
                
                embeddings.append(embedding.cpu().numpy()[0])
                
                if (i + 1) % 100 == 0:
                    logger.info("   已处理: %d/%d", i + 1, len(image_paths))
                    
            except Exception as e:
                logger.warning("   跳过 %s: %s", path.name, e)
                # 使用零向量作为占位
                embeddings.append(np.zeros(512))  # CLIP ViT-B/32 输出 512 维
    
    return np.array(embeddings)


def encode_texts(model, tokenizer, device, texts: list[str]) -> np.ndarray:
    """编码文本为向量"""
    with torch.no_grad():
        text_tokens = tokenizer(texts).to(device)
        embeddings = model.encode_text(text_tokens)
        embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
    
    return embeddings.cpu().numpy()


def search_meme(query: str, model, tokenizer, device, 
                image_embeddings: np.ndarray, image_paths: list[str],
                top_k: int = 5) -> list[tuple[str, float]]:
    """搜索最匹配的表情包"""
    query_embedding = encode_texts(model, tokenizer, device, [query])[0]
    
    # 计算余弦相似度
    similarities = np.dot(image_embeddings, query_embedding)
    
    # 获取 top-k
    top_indices = np.argsort(similarities)[::-1][:top_k]
    
    results = []
    for idx in top_indices:
        results.append((image_paths[idx], float(similarities[idx])))
    
    return results


def main():
    """主函数"""
    logger.info("构建 CLIP 向量索引")
    
    if not MEME_DIR.exists():
        logger.error("图片目录不存在: %s", MEME_DIR)
        logger.info("   请先运行 crawl_memes.py")
        return
    
    # 获取所有图片
    image_paths = []
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp"]:
        image_paths.extend(MEME_DIR.glob(ext))
    
    if not image_paths:
        logger.error("未找到图片文件")
        return
    
    logger.info("找到 %d 张图片", len(image_paths))
    
    # 加载 CLIP 模型
    model, preprocess, tokenizer, device = load_clip_model()
    
    # 编码图片
    logger.info("编码图片中...")
    embeddings = encode_images(model, preprocess, device, image_paths)
    
    np.save(EMBEDDINGS_FILE, embeddings)
    logger.info("向量已保存: %s", EMBEDDINGS_FILE)
    logger.info("   形状: %s", embeddings.shape)
    
    # 保存索引
    index = {
        "files": [str(p.name) for p in image_paths],
        "model": CLIP_MODEL,
        "embedding_dim": embeddings.shape[1],
    }
    with open(INDEX_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    logger.info("索引已保存: %s", INDEX_FILE)
    
    logger.info("测试搜索...")
    test_queries = ["震惊", "无语", "狗头", "开心"]
    
    for query in test_queries:
        results = search_meme(
            query, model, tokenizer, device,
            embeddings, [str(p.name) for p in image_paths],
            top_k=3
        )
        logger.info("   查询: %s", query)
        for filename, score in results:
            logger.info("      %s: %.3f", filename, score)
    
    logger.info("索引构建完成!")


if __name__ == "__main__":
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())
    main()
