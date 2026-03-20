#!/usr/bin/env python3
"""
图片生成脚本 - 使用 Gemini API 生成表情包和插图
"""

import json
import base64
import requests
import argparse
import hashlib
from pathlib import Path
from datetime import datetime


def load_config():
    """加载 Gemini API 配置"""
    config_path = Path(__file__).parent.parent / 'config' / 'gemini.json'
    with open(config_path, 'r') as f:
        return json.load(f)


def generate_hash(text: str, length: int = 8) -> str:
    """生成短哈希用于文件名"""
    return hashlib.md5(text.encode()).hexdigest()[:length]


def generate_image(prompt: str, output_path: str, image_type: str = "meme") -> dict:
    """
    调用 Gemini API 生成图片
    
    Args:
        prompt: 生成提示词
        output_path: 输出文件路径
        image_type: 图片类型 (meme/illustration)
    
    Returns:
        dict: 包含状态和路径的结果
    """
    config = load_config()
    
    # 根据类型构造不同的 prompt
    if image_type == "meme":
        full_prompt = f"""Generate a meme-style image:
- Theme/Emotion: {prompt}
- Style: Exaggerated expression, cartoon style, suitable for social media
- Requirements: No text in image, pure visual expression, square format
- Quality: High quality, clear details"""
    else:
        full_prompt = f"""Generate a professional illustration:
- Scene Description: {prompt}
- Style: Modern flat illustration or tech-style design
- Purpose: Article illustration for social media
- Aspect Ratio: 16:9 horizontal
- Quality: High quality, professional look, no text or watermarks"""

    # 使用配置的图片生成模型
    model = config.get('model', 'gemini-2.5-flash-image')
    url = f"{config['base_url']}/models/{model}:generateContent"
    
    headers = {
        "Content-Type": "application/json",
    }
    params = {
        "key": config['api_key']
    }
    
    # Gemini 2.0 的图片生成请求格式
    payload = {
        "contents": [{
            "parts": [{"text": full_prompt}]
        }],
        "generationConfig": {
            "temperature": 1,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 8192,
        }
    }
    
    try:
        print(f"  🎨 正在生成 {image_type}: {prompt[:50]}...")
        response = requests.post(url, headers=headers, params=params, json=payload, timeout=120)
        
        if response.status_code == 200:
            result = response.json()
            
            # 检查是否有图片数据
            for candidate in result.get('candidates', []):
                for part in candidate.get('content', {}).get('parts', []):
                    # 检查 inlineData（base64 图片）
                    if 'inlineData' in part:
                        mime_type = part['inlineData'].get('mimeType', 'image/png')
                        image_data = base64.b64decode(part['inlineData']['data'])
                        
                        output_file = Path(output_path)
                        output_file.parent.mkdir(parents=True, exist_ok=True)
                        
                        with open(output_file, 'wb') as f:
                            f.write(image_data)
                        
                        print(f"  ✅ 生成成功: {output_file}")
                        return {
                            "status": "SUCCESS",
                            "path": str(output_file),
                            "type": image_type,
                            "prompt": prompt
                        }
                    
                    # 检查 fileData（URI 引用）
                    if 'fileData' in part:
                        file_uri = part['fileData'].get('fileUri', '')
                        print(f"  ⚠️ 返回了文件 URI: {file_uri}")
                        return {
                            "status": "SUCCESS",
                            "path": file_uri,
                            "type": image_type,
                            "prompt": prompt,
                            "note": "File URI returned, need to download separately"
                        }
            
            # 如果没有图片，返回文本内容（模型可能返回了描述而非图片）
            text_content = ""
            for candidate in result.get('candidates', []):
                for part in candidate.get('content', {}).get('parts', []):
                    if 'text' in part:
                        text_content += part['text']
            
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
        return {
            "status": "FAILED",
            "error": "Request timeout"
        }
    except Exception as e:
        return {
            "status": "FAILED",
            "error": str(e)
        }


def generate_meme(tag: str, output_dir: str = "outputs/images/memes") -> dict:
    """生成表情包"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_hash = generate_hash(tag)
    output_path = f"{output_dir}/gen_meme_{timestamp}_{tag_hash}.png"
    
    return generate_image(tag, output_path, "meme")


def generate_illustration(description: str, style: str = "科技扁平风", 
                         output_dir: str = "outputs/images/illustrations") -> dict:
    """生成插图"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    desc_hash = generate_hash(description)
    output_path = f"{output_dir}/gen_illust_{timestamp}_{desc_hash}.png"
    
    full_prompt = f"{description}，{style}"
    return generate_image(full_prompt, output_path, "illustration")


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
        # 批量生成模式
        items = json.loads(args.batch)
        results = batch_generate(items, args.type)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.prompt and args.output:
        # 单张生成模式（指定输出路径）
        result = generate_image(args.prompt, args.output, args.type)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.description:
        # 插图生成模式
        result = generate_illustration(args.description, args.style)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.prompt:
        # 表情包生成模式
        result = generate_meme(args.prompt)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
