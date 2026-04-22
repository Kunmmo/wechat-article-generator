#!/usr/bin/env python3
"""
表情包爬虫脚本 v2

使用可靠的 API 服务爬取表情包：
- Giphy API (免费，需要 API key)
- Tenor API (Google 旗下)
- 本地备选：从 GitHub 开源表情包仓库下载
"""

import os
import json
import time
import hashlib
import requests
import urllib3
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor

from log_config import get_logger

logger = get_logger(__name__)

# 禁用 SSL 警告（仅用于国内网站 SSL 问题）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置
MEME_DIR = Path("memes/images")
TAGS_FILE = Path("memes/tags.json")
MAX_MEMES = 1000

# API Keys（可选，有 key 爬得更多）
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY", "")
TENOR_API_KEY = os.getenv("TENOR_API_KEY", "")

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


@dataclass
class Meme:
    """表情包数据结构"""
    filename: str
    url: str
    source: str
    tags: list[str]


class MemeCrawler:
    """表情包爬虫基类"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.downloaded = set()
        self._load_existing()
    
    def _load_existing(self):
        """加载已下载的文件"""
        for f in self.output_dir.glob("*"):
            if f.is_file():
                self.downloaded.add(f.stem)
    
    def _get_file_hash(self, content: bytes) -> str:
        """计算文件哈希"""
        return hashlib.md5(content).hexdigest()[:12]
    
    def download_image(self, url: str, tags: list[str], source: str, 
                       verify_ssl: bool = True) -> Optional[Meme]:
        """下载单张图片"""
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15, verify=verify_ssl)
            resp.raise_for_status()
            
            content = resp.content
            if len(content) < 1000:  # 太小的图片跳过
                return None
                
            file_hash = self._get_file_hash(content)
            
            if file_hash in self.downloaded:
                return None
            
            # 确定文件扩展名
            content_type = resp.headers.get("Content-Type", "")
            if "gif" in content_type or url.endswith(".gif"):
                ext = ".gif"
            elif "png" in content_type or url.endswith(".png"):
                ext = ".png"
            elif "webp" in content_type or url.endswith(".webp"):
                ext = ".webp"
            else:
                ext = ".jpg"
            
            filename = f"{file_hash}{ext}"
            filepath = self.output_dir / filename
            
            with open(filepath, "wb") as f:
                f.write(content)
            
            self.downloaded.add(file_hash)
            
            return Meme(
                filename=filename,
                url=url,
                source=source,
                tags=tags,
            )
        except Exception as e:
            return None


class GiphyCrawler(MemeCrawler):
    """Giphy API 爬虫"""
    
    # 中英文情绪关键词映射
    KEYWORDS = {
        "shocked": ["震惊", "shocked", "surprised"],
        "annoyed": ["无语", "annoyed", "facepalm"],
        "laughing": ["笑死", "laughing", "lol", "haha"],
        "crying": ["哭", "crying", "sad"],
        "happy": ["开心", "happy", "joy"],
        "angry": ["愤怒", "angry", "rage"],
        "confused": ["困惑", "confused", "what"],
        "thinking": ["思考", "thinking", "hmm"],
        "cool": ["酷", "cool", "sunglasses"],
        "love": ["爱", "love", "heart"],
        "thumbs up": ["点赞", "thumbs up", "nice"],
        "eye roll": ["白眼", "eye roll", "whatever"],
        "mind blown": ["DNA动了", "mind blown", "wow"],
        "sarcastic": ["狗头", "sarcastic", "ironic"],
        "tired": ["累", "tired", "exhausted"],
        "excited": ["激动", "excited", "yay"],
        "nervous": ["紧张", "nervous", "anxious"],
        "shrug": ["摊手", "shrug", "idk"],
        "clap": ["鼓掌", "clap", "applause"],
        "dance": ["跳舞", "dance", "celebration"],
    }
    
    def crawl(self, limit: int = 400) -> list[Meme]:
        """爬取 Giphy 表情包"""
        logger.info("开始爬取 Giphy...")
        memes = []
        
        # 使用公开 API（无需 key，但有限制）
        base_url = "https://api.giphy.com/v1/gifs/search"
        api_key = GIPHY_API_KEY or "dc6zaTOxFJmzC"  # Giphy 公开测试 key
        
        per_keyword = limit // len(self.KEYWORDS)
        
        for eng_key, tags in self.KEYWORDS.items():
            if len(memes) >= limit:
                break
            
            logger.info("  搜索: %s", eng_key)
            
            try:
                params = {
                    "api_key": api_key,
                    "q": eng_key,
                    "limit": min(per_keyword, 25),
                    "rating": "g",
                    "lang": "en",
                }
                
                resp = requests.get(base_url, params=params, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    gifs = data.get("data", [])
                    
                    for gif in gifs:
                        # 获取小尺寸版本
                        images = gif.get("images", {})
                        fixed_height = images.get("fixed_height", {})
                        img_url = fixed_height.get("url", "")
                        
                        if not img_url:
                            continue
                        
                        meme = self.download_image(
                            url=img_url,
                            tags=tags,
                            source="giphy"
                        )
                        if meme:
                            memes.append(meme)
                            logger.debug("    下载: %s", meme.filename)
                
                time.sleep(0.3)
                
            except Exception as e:
                logger.warning("  搜索 %s 失败: %s", eng_key, e)
                continue
        
        logger.info("  Giphy 爬取完成: %d 张", len(memes))
        return memes


class TenorCrawler(MemeCrawler):
    """Tenor API 爬虫"""
    
    KEYWORDS = {
        "reaction": ["反应", "reaction"],
        "meme": ["梗图", "meme"],
        "funny face": ["搞笑表情", "funny"],
        "anime reaction": ["动漫表情", "anime"],
        "cat meme": ["猫咪表情", "cat"],
        "dog meme": ["狗狗表情", "dog"],
        "surprised pikachu": ["震惊皮卡丘", "pikachu", "shocked"],
        "facepalm": ["捂脸", "facepalm"],
        "ok": ["好的", "ok", "agree"],
        "no": ["拒绝", "no", "disagree"],
    }
    
    def crawl(self, limit: int = 300) -> list[Meme]:
        """爬取 Tenor 表情包"""
        logger.info("开始爬取 Tenor...")
        memes = []
        
        base_url = "https://tenor.googleapis.com/v2/search"
        api_key = TENOR_API_KEY
        if not api_key:
            logger.warning("未设置 TENOR_API_KEY，跳过 Tenor 爬取")
            return []
        
        per_keyword = limit // len(self.KEYWORDS)
        
        for eng_key, tags in self.KEYWORDS.items():
            if len(memes) >= limit:
                break
            
            logger.info("  搜索: %s", eng_key)
            
            try:
                params = {
                    "key": api_key,
                    "q": eng_key,
                    "limit": min(per_keyword, 20),
                    "media_filter": "gif,tinygif",
                    "contentfilter": "medium",
                }
                
                resp = requests.get(base_url, params=params, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    
                    for result in results:
                        media = result.get("media_formats", {})
                        tinygif = media.get("tinygif", {})
                        img_url = tinygif.get("url", "")
                        
                        if not img_url:
                            gif = media.get("gif", {})
                            img_url = gif.get("url", "")
                        
                        if not img_url:
                            continue
                        
                        meme = self.download_image(
                            url=img_url,
                            tags=tags,
                            source="tenor"
                        )
                        if meme:
                            memes.append(meme)
                            logger.debug("    下载: %s", meme.filename)
                
                time.sleep(0.3)
                
            except Exception as e:
                logger.warning("  搜索 %s 失败: %s", eng_key, e)
                continue
        
        logger.info("  Tenor 爬取完成: %d 张", len(memes))
        return memes


class GitHubMemeCrawler(MemeCrawler):
    """从 GitHub 开源仓库下载表情包"""
    
    # 开源表情包仓库
    REPOS = [
        # 熊猫头表情包
        {
            "url": "https://api.github.com/repos/zhaoolee/ChineseBQB/contents/000熊猫头BQB",
            "tags": ["熊猫头", "panda", "中文"],
        },
        # 蘑菇头表情包
        {
            "url": "https://api.github.com/repos/zhaoolee/ChineseBQB/contents/001蘑菇头BQB",
            "tags": ["蘑菇头", "mushroom", "中文"],
        },
        # 金馆长表情包
        {
            "url": "https://api.github.com/repos/zhaoolee/ChineseBQB/contents/003金馆长BQB",
            "tags": ["金馆长", "kim", "中文"],
        },
        # 滑稽表情包
        {
            "url": "https://api.github.com/repos/zhaoolee/ChineseBQB/contents/005滑稽BQB",
            "tags": ["滑稽", "funny", "中文"],
        },
        # 兔斯基
        {
            "url": "https://api.github.com/repos/zhaoolee/ChineseBQB/contents/018兔斯基BQB",
            "tags": ["兔斯基", "tuzki", "中文"],
        },
    ]
    
    def crawl(self, limit: int = 400) -> list[Meme]:
        """从 GitHub 下载表情包"""
        logger.info("开始从 GitHub 下载表情包...")
        memes = []
        
        per_repo = limit // len(self.REPOS)
        
        for repo in self.REPOS:
            if len(memes) >= limit:
                break
            
            logger.info("  下载: %s", repo['tags'][0])
            
            try:
                # 获取目录内容
                resp = requests.get(
                    repo["url"],
                    headers={
                        **HEADERS,
                        "Accept": "application/vnd.github.v3+json",
                    },
                    timeout=15
                )
                
                if resp.status_code == 200:
                    files = resp.json()
                    count = 0
                    
                    for file in files:
                        if count >= per_repo:
                            break
                        
                        name = file.get("name", "")
                        download_url = file.get("download_url", "")
                        
                        # 只下载图片
                        if not any(name.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                            continue
                        
                        if not download_url:
                            continue
                        
                        meme = self.download_image(
                            url=download_url,
                            tags=repo["tags"],
                            source="github"
                        )
                        if meme:
                            memes.append(meme)
                            count += 1
                            logger.debug("    下载: %s", meme.filename)
                
                time.sleep(0.5)
                
            except Exception as e:
                logger.warning("  下载失败: %s", e)
                continue
        
        logger.info("  GitHub 爬取完成: %d 张", len(memes))
        return memes


class DoutulaCrawler(MemeCrawler):
    """斗图网爬虫（禁用 SSL 验证）"""
    
    KEYWORDS = ["震惊", "无语", "狗头", "捂脸", "笑死", "破防", 
                "社死", "摆烂", "躺平", "内卷", "可爱", "沙雕"]
    
    def crawl(self, limit: int = 200) -> list[Meme]:
        """爬取斗图网"""
        logger.info("开始爬取斗图网（禁用 SSL 验证）...")
        memes = []
        
        per_keyword = limit // len(self.KEYWORDS)
        
        for keyword in self.KEYWORDS:
            if len(memes) >= limit:
                break
            
            logger.info("  搜索: %s", keyword)
            
            try:
                url = f"https://www.doutula.com/api/search?keyword={keyword}&page=1"
                resp = requests.get(url, headers=HEADERS, timeout=10, verify=False)
                
                if resp.status_code == 200:
                    data = resp.json()
                    images = data.get("data", {}).get("list", [])
                    
                    for img in images[:per_keyword]:
                        img_url = img.get("image_url", "")
                        if img_url:
                            meme = self.download_image(
                                url=img_url,
                                tags=[keyword, "中文", "表情包"],
                                source="doutula",
                                verify_ssl=False
                            )
                            if meme:
                                memes.append(meme)
                                logger.debug("    下载: %s", meme.filename)
                
                time.sleep(0.5)
                
            except Exception as e:
                logger.warning("  搜索 %s 失败: %s", keyword, e)
                continue
        
        logger.info("  斗图网爬取完成: %d 张", len(memes))
        return memes


def save_tags(memes: list[Meme], output_file: Path):
    """保存标签索引"""
    tags_dict = {}
    for meme in memes:
        tags_dict[meme.filename] = meme.tags
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8", newline="\n") as f:
        json.dump(tags_dict, f, ensure_ascii=False, indent=2)
    
    logger.info("标签索引已保存: %s", output_file)


def main():
    """主函数"""
    logger.info("表情包爬虫 v2")
    logger.info("目标数量: %d 张", MAX_MEMES)
    logger.info("输出目录: %s", MEME_DIR)
    
    all_memes = []
    
    # 1. 从 GitHub 开源仓库下载（最可靠）
    github = GitHubMemeCrawler(MEME_DIR)
    all_memes.extend(github.crawl(limit=400))
    
    # 2. Giphy API
    giphy = GiphyCrawler(MEME_DIR)
    all_memes.extend(giphy.crawl(limit=400))
    
    # 3. Tenor API
    tenor = TenorCrawler(MEME_DIR)
    all_memes.extend(tenor.crawl(limit=300))
    
    # 4. 斗图网（备选，可能 SSL 问题）
    if len(all_memes) < MAX_MEMES:
        doutula = DoutulaCrawler(MEME_DIR)
        all_memes.extend(doutula.crawl(limit=200))
    
    # 保存标签
    save_tags(all_memes, TAGS_FILE)
    
    # 统计
    source_stats = {}
    for meme in all_memes:
        source = meme.source
        source_stats[source] = source_stats.get(source, 0) + 1
    
    logger.info("爬取完成!")
    logger.info("  - 总数量: %d 张", len(all_memes))
    logger.info("  - 来源分布:")
    for source, count in source_stats.items():
        logger.info("      %s: %d 张", source, count)
    logger.info("  - 图片目录: %s", MEME_DIR)
    logger.info("  - 标签文件: %s", TAGS_FILE)
    logger.info("下一步: 运行 python scripts/build_meme_index.py 构建 CLIP 向量索引")


if __name__ == "__main__":
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())
    main()
