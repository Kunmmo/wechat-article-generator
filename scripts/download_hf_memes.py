#!/usr/bin/env python3
"""
从 Hugging Face 下载中文表情包数据集

数据集: YZhao09/meme_chn
- 5,329 张中文表情包
- 带中文描述（可直接用作标签）
- 1.39 GB

使用方法:
    python scripts/download_hf_memes.py

备选方案（如果 HF 也无法访问）:
    1. 使用镜像: export HF_ENDPOINT=https://hf-mirror.com
    2. 手动下载后运行: python scripts/download_hf_memes.py --local /path/to/dataset
"""

import os
import re
import json
import shutil
import argparse
from pathlib import Path
from typing import Optional

from log_config import get_logger

logger = get_logger(__name__)

# 配置
MEME_DIR = Path("memes/images")
TAGS_FILE = Path("memes/tags.json")
HF_DATASET = "YZhao09/meme_chn"
MAX_MEMES = 1000  # 限制下载数量，可调整


def extract_tags_from_description(description: str) -> list[str]:
    """
    从中文描述中提取标签
    
    描述示例: "一个熊猫头表情包，表情是无语的样子，眼睛上翻，嘴角下撇"
    提取: ["熊猫头", "无语", "表情包"]
    """
    # 常见情绪词
    emotion_keywords = {
        "震惊": ["震惊", "惊讶", "吃惊", "目瞪口呆"],
        "无语": ["无语", "白眼", "翻白眼", "眼睛上翻"],
        "笑": ["笑", "哈哈", "开心", "高兴", "搞笑", "大笑", "微笑"],
        "哭": ["哭", "难过", "伤心", "流泪", "泪"],
        "愤怒": ["愤怒", "生气", "怒", "火大"],
        "可爱": ["可爱", "萌", "卖萌"],
        "狗头": ["狗头", "狗", "柴犬", "doge"],
        "熊猫头": ["熊猫头", "熊猫"],
        "蘑菇头": ["蘑菇头"],
        "猫": ["猫", "猫咪", "喵"],
        "思考": ["思考", "沉思", "疑惑", "困惑"],
        "得意": ["得意", "骄傲", "嘚瑟"],
        "尴尬": ["尴尬", "社死", "害羞"],
        "无奈": ["无奈", "摊手", "叹气"],
        "加油": ["加油", "鼓励", "支持"],
        "OK": ["ok", "好的", "没问题", "可以"],
        "拒绝": ["拒绝", "不", "不行", "不要"],
    }
    
    tags = []
    desc_lower = description.lower()
    
    for tag, keywords in emotion_keywords.items():
        for kw in keywords:
            if kw in desc_lower:
                tags.append(tag)
                break
    
    # 添加通用标签
    tags.append("中文")
    tags.append("表情包")
    
    return list(set(tags))


def download_from_huggingface(max_count: int = MAX_MEMES) -> list[dict]:
    """从 Hugging Face 下载数据集"""
    logger.info("正在从 Hugging Face 下载数据集: %s", HF_DATASET)
    logger.info("   限制数量: %d 张", max_count)
    
    try:
        from datasets import load_dataset
        
        hf_endpoint = os.getenv("HF_ENDPOINT", "")
        if hf_endpoint:
            logger.info("   使用镜像: %s", hf_endpoint)
        
        logger.info("   正在加载数据集（首次需要下载，约 1.4GB）...")
        dataset = load_dataset(HF_DATASET, split="train")
        
        logger.info("   数据集大小: %d 条", len(dataset))
        
        # 创建输出目录
        MEME_DIR.mkdir(parents=True, exist_ok=True)
        
        # 处理数据
        memes = []
        count = 0
        
        for item in dataset:
            if count >= max_count:
                break
            
            try:
                # 获取图片和描述
                image = item.get("image")
                description = item.get("description", "")
                filename_orig = item.get("file_name", f"meme_{count}.jpg")
                
                if image is None:
                    continue
                
                # 生成文件名
                ext = Path(filename_orig).suffix or ".jpg"
                filename = f"hf_{count:05d}{ext}"
                filepath = MEME_DIR / filename
                
                # 保存图片
                image.save(filepath)
                
                # 提取标签
                tags = extract_tags_from_description(description)
                
                memes.append({
                    "filename": filename,
                    "description": description,
                    "tags": tags,
                })
                
                count += 1
                
                if count % 100 == 0:
                    logger.info("   已处理: %d/%d", count, max_count)
                    
            except Exception as e:
                logger.warning("   处理失败: %s", e)
                continue
        
        logger.info("下载完成: %d 张", len(memes))
        return memes
        
    except ImportError:
        logger.error("请先安装 datasets: pip install datasets")
        raise
    except Exception as e:
        logger.error("下载失败: %s", e)
        logger.info("如果是网络问题，可以尝试:")
        logger.info("  Linux/macOS: export HF_ENDPOINT=https://hf-mirror.com")
        logger.info("  Windows CMD: set HF_ENDPOINT=https://hf-mirror.com")
        logger.info("  PowerShell:  $env:HF_ENDPOINT='https://hf-mirror.com'")
        logger.info("  或使用代理 / 手动下载后使用 --local 参数")
        raise


def process_local_dataset(local_path: str, max_count: int = MAX_MEMES) -> list[dict]:
    """处理本地已下载的数据集"""
    logger.info("处理本地数据集: %s", local_path)
    
    local_dir = Path(local_path)
    if not local_dir.exists():
        raise FileNotFoundError(f"目录不存在: {local_path}")
    
    # 创建输出目录
    MEME_DIR.mkdir(parents=True, exist_ok=True)
    
    memes = []
    count = 0
    
    # 查找图片文件
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    
    for img_path in local_dir.rglob("*"):
        if count >= max_count:
            break
        
        if img_path.suffix.lower() not in image_extensions:
            continue
        
        try:
            # 复制图片
            filename = f"local_{count:05d}{img_path.suffix}"
            filepath = MEME_DIR / filename
            shutil.copy2(img_path, filepath)
            
            # 从目录名提取标签
            parent_name = img_path.parent.name
            tags = extract_tags_from_description(parent_name)
            
            memes.append({
                "filename": filename,
                "description": parent_name,
                "tags": tags,
            })
            
            count += 1
            
            if count % 100 == 0:
                logger.info("   已处理: %d/%d", count, max_count)
                
        except Exception as e:
            logger.warning("   处理失败 %s: %s", img_path, e)
            continue
    
    logger.info("处理完成: %d 张", len(memes))
    return memes


def clone_chinesebqb(max_count: int = MAX_MEMES) -> list[dict]:
    """从 GitHub 克隆 ChineseBQB 仓库"""
    import subprocess
    
    logger.info("正在克隆 ChineseBQB 仓库...")
    
    bqb_dir = Path("memes/ChineseBQB")
    
    if not bqb_dir.exists():
        try:
            subprocess.run([
                "git", "clone", "--depth", "1",
                "https://github.com/zhaoolee/ChineseBQB.git",
                str(bqb_dir)
            ], check=True, timeout=300)
            logger.info("克隆完成")
        except subprocess.CalledProcessError as e:
            logger.error("克隆失败: %s", e)
            logger.info("可以手动下载: https://github.com/zhaoolee/ChineseBQB")
            raise
    else:
        logger.info("   仓库已存在，跳过克隆")
    
    # 处理图片
    return process_local_dataset(str(bqb_dir), max_count)


def save_tags(memes: list[dict]):
    """保存标签索引"""
    tags_dict = {}
    for meme in memes:
        tags_dict[meme["filename"]] = meme["tags"]
    
    TAGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TAGS_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(tags_dict, f, ensure_ascii=False, indent=2)
    
    logger.info("标签索引已保存: %s", TAGS_FILE)
    
    full_file = TAGS_FILE.parent / "metadata.json"
    with open(full_file, "w", encoding="utf-8", newline="\n") as f:
        json.dump(memes, f, ensure_ascii=False, indent=2)
    logger.info("完整元数据已保存: %s", full_file)


def main():
    parser = argparse.ArgumentParser(description="下载中文表情包数据集")
    parser.add_argument("--local", type=str, help="使用本地已下载的数据集路径")
    parser.add_argument("--git", action="store_true", help="从 GitHub 克隆 ChineseBQB")
    parser.add_argument("--max", type=int, default=MAX_MEMES, help=f"最大下载数量 (默认: {MAX_MEMES})")
    args = parser.parse_args()
    
    logger.info("中文表情包数据集下载工具")
    
    try:
        if args.local:
            memes = process_local_dataset(args.local, args.max)
        elif args.git:
            memes = clone_chinesebqb(args.max)
        else:
            memes = download_from_huggingface(args.max)
        
        if memes:
            save_tags(memes)
            
            tag_counts = {}
            for meme in memes:
                for tag in meme["tags"]:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            
            logger.info("标签分布 (Top 10):")
            sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:10]
            for tag, count in sorted_tags:
                logger.info("   %s: %d", tag, count)
            
            logger.info("下载完成!")
            logger.info("   - 图片数量: %d", len(memes))
            logger.info("   - 图片目录: %s", MEME_DIR)
            logger.info("   - 标签文件: %s", TAGS_FILE)
            logger.info("下一步: python scripts/build_meme_index.py")
        else:
            logger.error("未获取到任何图片")
            
    except Exception as e:
        logger.error("执行失败: %s", e)
        logger.info("备选方案:")
        logger.info("  1. Linux/macOS: export HF_ENDPOINT=https://hf-mirror.com")
        logger.info("     Windows CMD: set HF_ENDPOINT=https://hf-mirror.com")
        logger.info("     PowerShell:  $env:HF_ENDPOINT='https://hf-mirror.com'")
        logger.info("  2. 使用 Git 克隆: python scripts/download_hf_memes.py --git")
        logger.info("  3. 手动下载后: python scripts/download_hf_memes.py --local /path/to/images")
        return 1
    
    return 0


if __name__ == "__main__":
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())
    exit(main())
