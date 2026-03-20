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
        
        print(f"✅ CLIP 模型已加载: {CLIP_MODEL}")
        print(f"   设备: {device}")
        
        return model, preprocess, tokenizer, device
        
    except ImportError:
        print("❌ 请先安装 open_clip: pip install open-clip-torch")
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
                    print(f"   已处理: {i + 1}/{len(image_paths)}")
                    
            except Exception as e:
                print(f"   ⚠️ 跳过 {path.name}: {e}")
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
    print("="*50)
    print("构建 CLIP 向量索引")
    print("="*50)
    
    # 检查图片目录
    if not MEME_DIR.exists():
        print(f"❌ 图片目录不存在: {MEME_DIR}")
        print("   请先运行 crawl_memes.py")
        return
    
    # 获取所有图片
    image_paths = []
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp"]:
        image_paths.extend(MEME_DIR.glob(ext))
    
    if not image_paths:
        print(f"❌ 未找到图片文件")
        return
    
    print(f"📁 找到 {len(image_paths)} 张图片")
    
    # 加载 CLIP 模型
    model, preprocess, tokenizer, device = load_clip_model()
    
    # 编码图片
    print("\n🔄 编码图片中...")
    embeddings = encode_images(model, preprocess, device, image_paths)
    
    # 保存向量
    np.save(EMBEDDINGS_FILE, embeddings)
    print(f"💾 向量已保存: {EMBEDDINGS_FILE}")
    print(f"   形状: {embeddings.shape}")
    
    # 保存索引
    index = {
        "files": [str(p.name) for p in image_paths],
        "model": CLIP_MODEL,
        "embedding_dim": embeddings.shape[1],
    }
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"💾 索引已保存: {INDEX_FILE}")
    
    # 测试搜索
    print("\n🔍 测试搜索...")
    test_queries = ["震惊", "无语", "狗头", "开心"]
    
    for query in test_queries:
        results = search_meme(
            query, model, tokenizer, device,
            embeddings, [str(p.name) for p in image_paths],
            top_k=3
        )
        print(f"\n   查询: {query}")
        for filename, score in results:
            print(f"      {filename}: {score:.3f}")
    
    print("\n" + "="*50)
    print("✅ 索引构建完成！")
    print("="*50)


if __name__ == "__main__":
    main()
