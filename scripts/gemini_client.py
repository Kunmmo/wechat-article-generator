#!/usr/bin/env python3
"""
Gemini API 统一客户端

集中管理所有 Gemini API 调用，提供一致的参数和错误处理。
支持图片生成（表情包/插图）和文本生成。
"""

import json
import base64
import hashlib
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional

from log_config import get_logger

logger = get_logger(__name__)


def load_config() -> dict:
    """加载 Gemini API 配置"""
    config_path = Path(__file__).parent.parent / 'config' / 'gemini.json'
    if not config_path.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {config_path}\n"
            "请复制 config/gemini.example.json 为 config/gemini.json 并填入 API Key"
        )
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_hash(text: str, length: int = 8) -> str:
    """生成短哈希用于文件名"""
    return hashlib.md5(text.encode()).hexdigest()[:length]


# ============ Prompt 模板 ============

MEME_PROMPT_TEMPLATE = """Generate a meme-style image:
- Theme/Emotion: {prompt}
- Style: Exaggerated expression, cartoon style, suitable for social media
- Requirements: No text in image, pure visual expression, square format
- Quality: High quality, clear details"""

ILLUSTRATION_PROMPT_TEMPLATE = """Generate a professional illustration:
- Scene Description: {prompt}
- Style: Modern flat illustration or tech-style design
- Purpose: Article illustration for WeChat Official Account
- Aspect Ratio: 16:9 horizontal
- Quality: High quality, professional look, no text or watermarks"""


def _build_image_payload(full_prompt: str) -> dict:
    """构建图片生成的统一请求 payload"""
    return {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "temperature": 1,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 8192,
        }
    }


def _extract_image_from_response(result: dict) -> Optional[bytes]:
    """从 Gemini API 响应中提取图片数据"""
    for candidate in result.get('candidates', []):
        for part in candidate.get('content', {}).get('parts', []):
            if 'inlineData' in part:
                return base64.b64decode(part['inlineData']['data'])
    return None


def _extract_text_from_response(result: dict) -> str:
    """从 Gemini API 响应中提取文本"""
    texts = []
    for candidate in result.get('candidates', []):
        for part in candidate.get('content', {}).get('parts', []):
            if 'text' in part:
                texts.append(part['text'])
    return '\n'.join(texts)


def generate_image(prompt: str, image_type: str = "meme",
                   output_path: Optional[str] = None) -> Optional[str]:
    """
    调用 Gemini API 生成图片

    Args:
        prompt: 生成提示词
        image_type: "meme" 或 "illustration"
        output_path: 自定义输出路径（可选，默认自动生成）

    Returns:
        生成图片的文件路径，失败返回 None
    """
    config = load_config()

    if image_type == "meme":
        full_prompt = MEME_PROMPT_TEMPLATE.format(prompt=prompt)
        default_dir = "outputs/images/memes"
        prefix = "gen_meme"
    else:
        full_prompt = ILLUSTRATION_PROMPT_TEMPLATE.format(prompt=prompt)
        default_dir = "outputs/images/illustrations"
        prefix = "gen_illust"

    model = config.get('model', 'gemini-2.5-flash-image')
    url = f"{config['base_url']}/models/{model}:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": config['api_key']}
    payload = _build_image_payload(full_prompt)

    try:
        logger.info("正在生成 %s: %s...", image_type, prompt[:50])
        response = requests.post(
            url, headers=headers, params=params, json=payload, timeout=120
        )

        if response.status_code == 200:
            result = response.json()
            img_data = _extract_image_from_response(result)

            if img_data:
                if output_path is None:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    prompt_hash = generate_hash(prompt)
                    filename = f"{prefix}_{timestamp}_{prompt_hash}.png"
                    output_path = f"{default_dir}/{filename}"

                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(img_data)

                logger.info("生成成功: %s", output_path)
                return output_path

            logger.warning("API 返回无图片数据")
        else:
            logger.error("API 错误: %d - %s", response.status_code, response.text[:200])

    except requests.exceptions.Timeout:
        logger.error("请求超时")
    except Exception as e:
        logger.error("生成失败: %s", e)

    return None


def generate_image_detailed(prompt: str, output_path: str,
                            image_type: str = "meme") -> dict:
    """
    调用 Gemini API 生成图片（返回详细结果字典）

    用于 generate_image.py CLI 脚本，需要丰富的状态信息。

    Returns:
        dict: 包含 status, path, type, prompt 等字段
    """
    config = load_config()

    if image_type == "meme":
        full_prompt = MEME_PROMPT_TEMPLATE.format(prompt=prompt)
    else:
        full_prompt = ILLUSTRATION_PROMPT_TEMPLATE.format(prompt=prompt)

    model = config.get('model', 'gemini-2.5-flash-image')
    url = f"{config['base_url']}/models/{model}:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": config['api_key']}
    payload = _build_image_payload(full_prompt)

    try:
        logger.info("正在生成(详细) %s: %s...", image_type, prompt[:50])
        response = requests.post(
            url, headers=headers, params=params, json=payload, timeout=120
        )

        if response.status_code == 200:
            result = response.json()
            img_data = _extract_image_from_response(result)

            if img_data:
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with open(output_file, 'wb') as f:
                    f.write(img_data)

                logger.info("生成成功: %s", output_file)
                return {
                    "status": "SUCCESS",
                    "path": str(output_file),
                    "type": image_type,
                    "prompt": prompt
                }

            # Check for fileData URI
            for candidate in result.get('candidates', []):
                for part in candidate.get('content', {}).get('parts', []):
                    if 'fileData' in part:
                        file_uri = part['fileData'].get('fileUri', '')
                        return {
                            "status": "SUCCESS",
                            "path": file_uri,
                            "type": image_type,
                            "prompt": prompt,
                            "note": "File URI returned, need to download separately"
                        }

            text_content = _extract_text_from_response(result)
            if text_content:
                return {
                    "status": "NO_IMAGE",
                    "error": "Model returned text instead of image",
                    "text": text_content[:500],
                    "prompt": prompt
                }

            return {
                "status": "FAILED",
                "error": "No image data in response",
                "response": str(result)[:500]
            }
        else:
            return {
                "status": "FAILED",
                "error": f"API returned status {response.status_code}",
                "response": response.text[:500]
            }

    except requests.exceptions.Timeout:
        return {"status": "FAILED", "error": "Request timeout"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _generate_image_stable_diffusion(prompt: str, output_path: str) -> Optional[str]:
    """
    使用 Stability AI API 生成图片（Stable Diffusion 后端）

    需要设置环境变量 STABILITY_API_KEY
    """
    import os

    api_key = os.getenv("STABILITY_API_KEY", "")
    if not api_key:
        logger.warning("STABILITY_API_KEY 未设置，跳过 Stable Diffusion")
        return None

    url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "text_prompts": [{"text": prompt, "weight": 1}],
        "cfg_scale": 7,
        "height": 1024,
        "width": 1024,
        "samples": 1,
        "steps": 30,
    }

    try:
        logger.info("正在使用 Stable Diffusion 生成...")
        response = requests.post(url, headers=headers, json=payload, timeout=120)

        if response.status_code == 200:
            result = response.json()
            for artifact in result.get("artifacts", []):
                if artifact.get("finishReason") == "SUCCESS":
                    img_data = base64.b64decode(artifact["base64"])
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(img_data)
                    logger.info("Stable Diffusion 生成成功: %s", output_path)
                    return output_path
        else:
            logger.warning("Stability API 错误: %d", response.status_code)

    except Exception as e:
        logger.warning("Stable Diffusion 生成失败: %s", e)

    return None


def generate_image_with_fallback(prompt: str, image_type: str = "meme",
                                 output_path: Optional[str] = None) -> Optional[str]:
    """
    带降级链的图片生成：Gemini -> Stable Diffusion -> None

    使用配置中的 image_provider 字段决定首选后端。
    """
    config = load_config()
    provider = config.get("image_provider", "gemini")

    if provider == "stable-diffusion":
        # 首选 SD，降级到 Gemini
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prompt_hash = generate_hash(prompt)
            prefix = "gen_meme" if image_type == "meme" else "gen_illust"
            default_dir = "outputs/images/memes" if image_type == "meme" else "outputs/images/illustrations"
            output_path = f"{default_dir}/{prefix}_{timestamp}_{prompt_hash}.png"

        template = MEME_PROMPT_TEMPLATE if image_type == "meme" else ILLUSTRATION_PROMPT_TEMPLATE
        full_prompt = template.format(prompt=prompt)
        result = _generate_image_stable_diffusion(full_prompt, output_path)
        if result:
            return result
        logger.info("降级到 Gemini...")
        return generate_image(prompt, image_type, output_path)
    else:
        # 首选 Gemini（默认），降级到 SD
        result = generate_image(prompt, image_type, output_path)
        if result:
            return result

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prompt_hash = generate_hash(prompt)
            prefix = "gen_meme" if image_type == "meme" else "gen_illust"
            default_dir = "outputs/images/memes" if image_type == "meme" else "outputs/images/illustrations"
            output_path = f"{default_dir}/{prefix}_{timestamp}_{prompt_hash}.png"

        template = MEME_PROMPT_TEMPLATE if image_type == "meme" else ILLUSTRATION_PROMPT_TEMPLATE
        full_prompt = template.format(prompt=prompt)
        logger.info("降级到 Stable Diffusion...")
        return _generate_image_stable_diffusion(full_prompt, output_path)


def generate_text(prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
    """
    调用 Gemini API 生成文本

    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词（可选）

    Returns:
        生成的文本，失败返回 None
    """
    config = load_config()
    model = config.get('text_model', 'gemini-2.0-flash')
    url = f"{config['base_url']}/models/{model}:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": config['api_key']}

    contents = [{"parts": [{"text": prompt}]}]
    payload = {"contents": contents}

    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{"text": system_prompt}]
        }

    try:
        response = requests.post(
            url, headers=headers, params=params, json=payload, timeout=60
        )
        if response.status_code == 200:
            return _extract_text_from_response(response.json())
        else:
            logger.error("API 错误: %d", response.status_code)
            return None
    except Exception as e:
        logger.error("文本生成失败: %s", e)
        return None
