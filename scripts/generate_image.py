#!/usr/bin/env python3
"""
图片生成脚本 - 使用 Gemini API 生成表情包和插图

CLI 入口，底层调用 gemini_client 统一模块。
"""

import json
import argparse
from datetime import datetime

from log_config import get_logger
from gemini_client import generate_hash, generate_image_detailed

logger = get_logger(__name__)


def generate_meme(tag: str, output_dir: str = "outputs/images/memes") -> dict:
    """生成表情包"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_hash = generate_hash(tag)
    output_path = f"{output_dir}/gen_meme_{timestamp}_{tag_hash}.png"
    return generate_image_detailed(tag, output_path, "meme")


def generate_illustration(description: str, style: str = "科技扁平风",
                          output_dir: str = "outputs/images/illustrations") -> dict:
    """生成插图"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    desc_hash = generate_hash(description)
    output_path = f"{output_dir}/gen_illust_{timestamp}_{desc_hash}.png"
    full_prompt = f"{description}, {style}"
    return generate_image_detailed(full_prompt, output_path, "illustration")


def batch_generate(items: list, image_type: str = "meme") -> list:
    """批量生成图片"""
    results = []
    for item in items:
        if image_type == "meme":
            result = generate_meme(item)
        else:
            if isinstance(item, dict):
                result = generate_illustration(
                    item.get('description', ''),
                    item.get('style', '科技扁平风')
                )
            else:
                result = generate_illustration(item)
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description='Generate images using Gemini API')
    parser.add_argument('--prompt', type=str, help='Generation prompt')
    parser.add_argument('--output', type=str, help='Output file path')
    parser.add_argument('--type', default='meme', choices=['meme', 'illustration'],
                        help='Image type to generate')
    parser.add_argument('--description', type=str, help='Scene description for illustration')
    parser.add_argument('--style', type=str, default='科技扁平风', help='Style for illustration')
    parser.add_argument('--batch', type=str, help='JSON array for batch generation')

    args = parser.parse_args()

    if args.batch:
        items = json.loads(args.batch)
        results = batch_generate(items, args.type)
        logger.info("结果: %s", json.dumps(results, ensure_ascii=False, indent=2))
    elif args.prompt and args.output:
        result = generate_image_detailed(args.prompt, args.output, args.type)
        logger.info("结果: %s", json.dumps(result, ensure_ascii=False, indent=2))
    elif args.description:
        result = generate_illustration(args.description, args.style)
        logger.info("结果: %s", json.dumps(result, ensure_ascii=False, indent=2))
    elif args.prompt:
        result = generate_meme(args.prompt)
        logger.info("结果: %s", json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    from log_config import setup_logging
    from compat import ensure_utf8_env, get_platform_info

    ensure_utf8_env()
    setup_logging()
    logger.info("Platform: %s", get_platform_info())
    main()
