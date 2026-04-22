#!/usr/bin/env python3
"""
插图生成脚本 - 使用 Gemini API 生成文章插图

封装 gemini_client 的插图生成功能，提供独立 CLI 入口。
"""

import json
import argparse

from log_config import get_logger
from generate_image import generate_illustration, batch_generate

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Generate article illustrations using Gemini API')
    parser.add_argument('--description', type=str, required=False,
                        help='Scene description for the illustration')
    parser.add_argument('--style', type=str, default='科技扁平风',
                        help='Visual style (default: 科技扁平风)')
    parser.add_argument('--output-dir', type=str, default='outputs/images/illustrations',
                        help='Output directory')
    parser.add_argument('--batch', type=str,
                        help='JSON array of {description, style} objects for batch generation')

    args = parser.parse_args()

    if args.batch:
        items = json.loads(args.batch)
        results = batch_generate(items, image_type="illustration")
        logger.info("结果: %s", json.dumps(results, ensure_ascii=False, indent=2))
    elif args.description:
        result = generate_illustration(
            args.description, args.style, args.output_dir
        )
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
