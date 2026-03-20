#!/usr/bin/env python3
"""
表情包语义检索模块

基于 CLIP 向量索引进行表情包语义检索。
当检索失败时，调用生图 API 生成表情包。
"""

import os
import json
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

# 配置
MEME_DIR = Path("memes/images")
EMBEDDINGS_FILE = Path("memes/embeddings.npy")
INDEX_FILE = Path("memes/index.json")
TAGS_FILE = Path("memes/tags.json")

# 相似度阈值：低于此值触发生图
SIMILARITY_THRESHOLD = 0.25


class MemeRetriever:
    """表情包检索器"""
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.preprocess = None
        self.device = None
        self.embeddings: Optional[np.ndarray] = None
        self.filenames: list[str] = []
        self.tags: dict = {}
    
    def load(self):
        """加载模型和索引"""
        # 加载 CLIP 模型
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
        
        # 加载向量索引
        if EMBEDDINGS_FILE.exists() and INDEX_FILE.exists():
            self.embeddings = np.load(EMBEDDINGS_FILE)
            with open(INDEX_FILE, "r") as f:
                index = json.load(f)
                self.filenames = index.get("files", [])
            print(f"✅ 已加载 {len(self.filenames)} 张表情包索引")
        else:
            print("⚠️ 索引文件不存在，请先运行 build_meme_index.py")
        
        # 加载标签
        if TAGS_FILE.exists():
            with open(TAGS_FILE, "r") as f:
                self.tags = json.load(f)
    
    def search(self, query: str, top_k: int = 5) -> list[Tuple[str, float]]:
        """
        搜索最匹配的表情包
        
        Args:
            query: 搜索词，如 "震惊"、"无语"
            top_k: 返回数量
        
        Returns:
            [(文件名, 相似度分数), ...]
        """
        import torch
        
        if self.embeddings is None or len(self.filenames) == 0:
            return []
        
        # 编码查询文本
        with torch.no_grad():
            text = self.tokenizer([query]).to(self.device)
            text_embedding = self.model.encode_text(text)
            text_embedding = text_embedding / text_embedding.norm(dim=-1, keepdim=True)
            text_embedding = text_embedding.cpu().numpy()[0]
        
        # 计算相似度
        similarities = np.dot(self.embeddings, text_embedding)
        
        # 排序
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
        print(f"  ⚠️ 检索失败（相似度 < {SIMILARITY_THRESHOLD}），尝试生成...")
        
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
        """调用 Gemini API 生成表情包"""
        import requests
        import base64
        import hashlib
        from datetime import datetime
        
        # 加载配置
        config_path = Path(__file__).parent.parent / 'config' / 'gemini.json'
        if not config_path.exists():
            print("  ⚠️ 未找到 config/gemini.json，无法生成")
            return None
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        try:
            # 构造生图提示词
            full_prompt = f"""Generate a meme-style image:
- Theme/Emotion: {prompt}
- Style: Exaggerated expression, cartoon style, suitable for social media
- Requirements: No text in image, pure visual expression, square format
- Quality: High quality, clear details"""

            # 调用 Gemini API
            url = f"{config['base_url']}/models/{config['model']}:generateContent"
            headers = {"Content-Type": "application/json"}
            params = {"key": config['api_key']}
            payload = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}
            }
            
            response = requests.post(url, headers=headers, params=params, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                
                # 解析返回的图片
                for candidate in result.get('candidates', []):
                    for part in candidate.get('content', {}).get('parts', []):
                        if 'inlineData' in part:
                            img_data = base64.b64decode(part['inlineData']['data'])
                            
                            # 生成文件名
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            hash_name = hashlib.md5(prompt.encode()).hexdigest()[:8]
                            filename = f"gen_meme_{timestamp}_{hash_name}.png"
                            
                            # 保存到生成目录
                            gen_dir = Path("outputs/images/memes")
                            gen_dir.mkdir(parents=True, exist_ok=True)
                            filepath = gen_dir / filename
                            
                            with open(filepath, "wb") as f:
                                f.write(img_data)
                            
                            print(f"  ✅ 生成成功: {filepath}")
                            return str(filepath)
                
                print(f"  ⚠️ API 返回无图片数据")
                return None
            else:
                print(f"  ❌ API 错误: {response.status_code}")
                return None
            
        except Exception as e:
            print(f"  ❌ 生成失败: {e}")
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
        
        print(f"🔍 处理: [MEME: {tag}]")
        path, score, source = retriever.get_meme(tag)
        
        results[tag] = {
            "path": path,
            "score": score,
            "source": source,
        }
        
        print(f"   → {source}: {path} (score: {score:.3f})")
    
    return results


# 示例使用
if __name__ == "__main__":
    print("="*50)
    print("表情包检索测试")
    print("="*50)
    
    retriever = MemeRetriever()
    retriever.load()
    
    # 测试检索
    test_queries = ["震惊", "无语", "狗头", "开心", "难过"]
    
    for query in test_queries:
        print(f"\n🔍 查询: {query}")
        results = retriever.search(query, top_k=3)
        for filename, score in results:
            print(f"   {filename}: {score:.3f}")
    
    # 测试文章处理
    print("\n" + "="*50)
    print("文章表情包处理测试")
    print("="*50)
    
    test_content = """
    这个消息太劲爆了 [MEME: 震惊]
    
    看完之后我直接 [MEME: 无语]
    
    但是仔细想想，也没什么嘛 [MEME: 狗头]
    """
    
    results = process_article_memes(test_content, retriever)
    print("\n处理结果:")
    print(json.dumps(results, indent=2, ensure_ascii=False))
