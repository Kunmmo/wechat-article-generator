#!/usr/bin/env python3
"""
优质文章采集脚本

从 WeRSS 系统采集 AI/互联网资讯类公众号的优质文章，
作为训练数据集用于评价体系优化。
"""

import os
import json
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, asdict

# 配置
WERSS_API = os.getenv("WERSS_API", "http://localhost:8001/api/v1/wx")
WERSS_USERNAME = os.getenv("WERSS_USERNAME", "admin")
WERSS_PASSWORD = os.getenv("WERSS_PASSWORD", "admin123")
OUTPUT_DIR = Path("data/articles")

# AI/互联网资讯类公众号（推荐订阅）
RECOMMENDED_ACCOUNTS = [
    {"name": "机器之心", "description": "AI行业深度报道"},
    {"name": "量子位", "description": "AI技术与产业"},
    {"name": "AI科技评论", "description": "AI学术与工业"},
    {"name": "虎嗅", "description": "互联网商业评论"},
    {"name": "36氪", "description": "创投与科技"},
    {"name": "极客公园", "description": "科技创新"},
    {"name": "InfoQ", "description": "技术社区"},
    {"name": "深灵.Tech", "description": "AI技术解读"},
    {"name": "硅星人", "description": "硅谷科技"},
    {"name": "晚点LatePost", "description": "科技深度报道"},
]


@dataclass
class Article:
    """文章数据结构"""
    id: str
    title: str
    content: str
    author: str
    mp_name: str
    publish_time: str
    url: str
    tags: list[str]
    word_count: int


class WeRSSClient:
    """WeRSS API 客户端"""
    
    def __init__(self, api_url: str = WERSS_API):
        self.api_url = api_url.rstrip("/")
        self.token: Optional[str] = None
        self.session = requests.Session()
    
    def login(self, username: str, password: str) -> bool:
        """登录获取 token"""
        try:
            # WeRSS 使用 form-urlencoded 格式
            resp = self.session.post(
                f"{self.api_url}/auth/login",
                data={"username": username, "password": password}
            )
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("access_token") or data.get("token")
                if self.token:
                    self.session.headers["Authorization"] = f"Bearer {self.token}"
                print(f"✅ 登录成功")
                return True
            else:
                print(f"❌ 登录失败: {resp.text}")
                return False
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False
    
    def get_mps(self) -> list[dict]:
        """获取已订阅的公众号列表"""
        try:
            resp = self.session.get(f"{self.api_url}/mps")
            if resp.status_code == 200:
                data = resp.json()
                return data.get("items", data.get("data", []))
            return []
        except Exception as e:
            print(f"⚠️ 获取公众号失败: {e}")
            return []
    
    def get_articles(self, mp_id: Optional[str] = None, 
                     page: int = 1, page_size: int = 50) -> list[dict]:
        """获取文章列表"""
        try:
            params = {"page": page, "page_size": page_size}
            if mp_id:
                params["mp_id"] = mp_id
            
            resp = self.session.get(f"{self.api_url}/articles", params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("items", data.get("data", []))
            return []
        except Exception as e:
            print(f"⚠️ 获取文章失败: {e}")
            return []
    
    def get_article_content(self, article_id: str) -> Optional[dict]:
        """获取文章详情"""
        try:
            resp = self.session.get(f"{self.api_url}/articles/{article_id}")
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            print(f"⚠️ 获取文章详情失败: {e}")
            return None


def clean_content(content: str) -> str:
    """清洗文章内容"""
    import re
    
    # 移除 HTML 标签
    content = re.sub(r'<[^>]+>', '', content)
    
    # 移除多余空白
    content = re.sub(r'\s+', ' ', content)
    
    # 移除特殊字符
    content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)
    
    return content.strip()


def analyze_article(article: dict) -> dict:
    """分析文章特征"""
    content = article.get("content", "")
    clean = clean_content(content)
    
    # 计算特征
    word_count = len(clean)
    paragraph_count = len([p for p in clean.split('\n') if p.strip()])
    
    # 检测是否有数据引用
    import re
    has_numbers = len(re.findall(r'\d+%|\d+\.\d+|第\d+|\d+亿|\d+万', clean)) > 0
    
    # 检测情感词汇
    emotion_words = ["震惊", "惊人", "重磅", "突破", "颠覆", "逆袭"]
    has_emotion = any(word in clean for word in emotion_words)
    
    return {
        "word_count": word_count,
        "paragraph_count": paragraph_count,
        "has_numbers": has_numbers,
        "has_emotion": has_emotion,
    }


def save_article(article: Article, output_dir: Path):
    """保存文章"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成文件名
    safe_title = "".join(c for c in article.title if c.isalnum() or c in (' ', '-', '_'))[:50]
    filename = f"{article.id}_{safe_title}.json"
    filepath = output_dir / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(article), f, ensure_ascii=False, indent=2)
    
    return filepath


def main():
    """主函数"""
    print("="*50)
    print("优质文章采集")
    print("="*50)
    print(f"WeRSS API: {WERSS_API}")
    print(f"输出目录: {OUTPUT_DIR}")
    print("="*50)
    
    # 创建客户端
    client = WeRSSClient()
    
    # 登录
    if not client.login(WERSS_USERNAME, WERSS_PASSWORD):
        print("\n❌ 无法连接 WeRSS，请确保：")
        print("   1. WeRSS 已启动 (运行 setup_werss.sh)")
        print("   2. 环境变量已配置 (WERSS_USERNAME, WERSS_PASSWORD)")
        return
    
    # 获取公众号列表
    mps = client.get_mps()
    print(f"\n📰 已订阅 {len(mps)} 个公众号")
    
    if not mps:
        print("\n⚠️ 未订阅任何公众号，请先在 WeRSS 中添加订阅")
        print("\n推荐订阅的 AI/互联网资讯类公众号：")
        for acc in RECOMMENDED_ACCOUNTS:
            print(f"   - {acc['name']}: {acc['description']}")
        return
    
    # 采集文章
    all_articles = []
    
    for mp in mps:
        mp_name = mp.get("mp_name", "未知")
        mp_id = mp.get("id")
        
        print(f"\n📁 {mp_name}")
        
        # 获取文章列表
        articles = client.get_articles(mp_id=mp_id, page_size=50)
        print(f"   找到 {len(articles)} 篇文章")
        
        for art in articles:
            # 获取详情
            detail = client.get_article_content(art.get("id"))
            if not detail:
                continue
            
            # 分析文章
            features = analyze_article(detail)
            
            # 过滤：只保留字数 > 500 的文章
            if features["word_count"] < 500:
                continue
            
            # 构建文章对象
            article = Article(
                id=str(detail.get("id")),
                title=detail.get("title", ""),
                content=clean_content(detail.get("content", "")),
                author=detail.get("author", ""),
                mp_name=mp_name,
                publish_time=detail.get("publish_time", ""),
                url=detail.get("url", ""),
                tags=detail.get("tags", []),
                word_count=features["word_count"],
            )
            
            # 保存
            filepath = save_article(article, OUTPUT_DIR)
            all_articles.append(article)
            print(f"   ✅ {article.title[:30]}...")
        
        time.sleep(0.5)  # 避免请求过快
    
    # 生成统计
    stats = {
        "total_articles": len(all_articles),
        "total_words": sum(a.word_count for a in all_articles),
        "mp_distribution": {},
        "collected_at": datetime.now().isoformat(),
    }
    
    for article in all_articles:
        mp = article.mp_name
        if mp not in stats["mp_distribution"]:
            stats["mp_distribution"][mp] = 0
        stats["mp_distribution"][mp] += 1
    
    # 保存统计
    stats_file = OUTPUT_DIR / "stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*50)
    print("✅ 采集完成！")
    print(f"   - 文章数量: {stats['total_articles']}")
    print(f"   - 总字数: {stats['total_words']:,}")
    print(f"   - 输出目录: {OUTPUT_DIR}")
    print("="*50)
    print("\n下一步: 使用这些文章优化评价体系")


if __name__ == "__main__":
    main()
