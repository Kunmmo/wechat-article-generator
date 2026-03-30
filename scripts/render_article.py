#!/usr/bin/env python3
"""
文章渲染脚本 - 处理表情包和插图，生成最终 HTML

流程：
1. 解析文章中的 [MEME: xxx] 和 [IMG: xxx] 标记
2. 表情包：先 CLIP 检索，失败则调用 Gemini 生成
3. 插图：直接调用 Gemini 生成
4. 替换标记为实际图片，生成 HTML
"""

import re
import json
import argparse
import hashlib
import base64
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False


def load_config():
    """加载 Gemini API 配置"""
    config_path = Path(__file__).parent.parent / 'config' / 'gemini.json'
    with open(config_path, 'r') as f:
        return json.load(f)


def generate_hash(text: str, length: int = 8) -> str:
    """生成短哈希"""
    return hashlib.md5(text.encode()).hexdigest()[:length]


# ============ 表情包检索 ============

class MemeRetriever:
    """表情包检索器（简化版）"""
    
    def __init__(self):
        self.embeddings = None
        self.filenames = []
        self.model = None
        self.tokenizer = None
        self.device = None
    
    def load(self):
        """加载模型和索引"""
        import numpy as np
        
        embeddings_file = Path("memes/embeddings.npy")
        index_file = Path("memes/index.json")
        
        if embeddings_file.exists() and index_file.exists():
            self.embeddings = np.load(embeddings_file)
            with open(index_file, "r") as f:
                index = json.load(f)
                self.filenames = index.get("files", [])
            print(f"✅ 加载了 {len(self.filenames)} 张表情包索引")
            
            # 加载 CLIP 模型
            try:
                import open_clip
                import torch
                
                self.model, _, _ = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
                self.tokenizer = open_clip.get_tokenizer("ViT-B-32")
                self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
                self.model = self.model.to(self.device)
                self.model.eval()
                print(f"✅ CLIP 模型加载成功 (device: {self.device})")
            except ImportError:
                print("⚠️ 未安装 open_clip，将直接使用生成模式")
        else:
            print("⚠️ 表情包索引不存在，将直接使用生成模式")
    
    def search(self, query: str, threshold: float = 0.25) -> Tuple[Optional[str], float]:
        """
        检索表情包
        
        Returns:
            (文件路径, 相似度) 或 (None, 0) 如果未找到
        """
        import numpy as np
        import torch
        
        if self.embeddings is None or self.model is None:
            return None, 0.0
        
        # 编码查询
        with torch.no_grad():
            text = self.tokenizer([query]).to(self.device)
            text_embedding = self.model.encode_text(text)
            text_embedding = text_embedding / text_embedding.norm(dim=-1, keepdim=True)
            text_embedding = text_embedding.cpu().numpy()[0]
        
        # 计算相似度
        similarities = np.dot(self.embeddings, text_embedding)
        top_idx = np.argmax(similarities)
        top_score = float(similarities[top_idx])
        
        if top_score >= threshold:
            filepath = f"memes/images/{self.filenames[top_idx]}"
            return filepath, top_score
        
        return None, top_score


# ============ 图片生成 ============

def generate_image(prompt: str, image_type: str = "meme") -> Optional[str]:
    """
    调用 Gemini API 生成图片
    
    Args:
        prompt: 生成提示词
        image_type: "meme" 或 "illustration"
    
    Returns:
        生成图片的路径，或 None
    """
    config = load_config()
    
    # 根据类型构造 prompt
    if image_type == "meme":
        full_prompt = f"""Generate a meme-style image:
- Theme/Emotion: {prompt}
- Style: Exaggerated expression, cartoon style, suitable for social media
- Requirements: No text in image, pure visual expression, square format
- Quality: High quality, clear details"""
        output_dir = "outputs/images/memes"
        prefix = "gen_meme"
    else:
        full_prompt = f"""Generate a professional illustration:
- Scene Description: {prompt}
- Style: Modern flat illustration or tech-style design
- Purpose: Article illustration for WeChat Official Account
- Aspect Ratio: 16:9 horizontal
- Quality: High quality, professional look, no text or watermarks"""
        output_dir = "outputs/images/illustrations"
        prefix = "gen_illust"
    
    # 构造 API 请求
    model = config.get('model', 'gemini-2.0-flash-exp-image-generation')
    url = f"{config['base_url']}/models/{model}:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": config['api_key']}
    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "temperature": 1,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 8192,
        }
    }
    
    try:
        print(f"  🎨 正在生成 {image_type}: {prompt[:30]}...")
        response = requests.post(url, headers=headers, params=params, json=payload, timeout=120)
        
        if response.status_code == 200:
            result = response.json()
            
            for candidate in result.get('candidates', []):
                for part in candidate.get('content', {}).get('parts', []):
                    if 'inlineData' in part:
                        img_data = base64.b64decode(part['inlineData']['data'])
                        
                        # 生成文件名
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        prompt_hash = generate_hash(prompt)
                        filename = f"{prefix}_{timestamp}_{prompt_hash}.png"
                        
                        # 保存
                        Path(output_dir).mkdir(parents=True, exist_ok=True)
                        filepath = f"{output_dir}/{filename}"
                        with open(filepath, "wb") as f:
                            f.write(img_data)
                        
                        print(f"  ✅ 生成成功: {filepath}")
                        return filepath
            
            print(f"  ⚠️ API 返回无图片数据")
        else:
            print(f"  ❌ API 错误: {response.status_code} - {response.text[:100]}")
        
    except Exception as e:
        print(f"  ❌ 生成失败: {e}")
    
    return None


# ============ 文章处理 ============

def parse_img_tag(tag: str) -> Tuple[str, str]:
    """
    解析 [IMG: xxx] 标记
    
    Returns:
        (描述, 风格)
    """
    # 尝试分割描述和风格
    if '，' in tag:
        parts = tag.rsplit('，', 1)
        if '风格' in parts[-1]:
            return parts[0].strip(), parts[-1].strip()
    if ',' in tag:
        parts = tag.rsplit(',', 1)
        if 'style' in parts[-1].lower() or '风格' in parts[-1]:
            return parts[0].strip(), parts[-1].strip()
    
    return tag.strip(), "科技扁平风格"


def process_article(content: str, retriever: Optional[MemeRetriever] = None) -> dict:
    """
    处理文章中的所有图片标记
    
    Args:
        content: 带有 [MEME: xxx] 和 [IMG: xxx] 标记的文章内容
        retriever: 表情包检索器（可选）
    
    Returns:
        {
            "memes": {"tag": {"path": "...", "source": "retrieval/generation"}},
            "illustrations": {"desc": {"path": "...", "style": "..."}},
            "stats": {"meme_count": x, "illust_count": y, "generated": z}
        }
    """
    results = {
        "memes": {},
        "illustrations": {},
        "stats": {
            "meme_count": 0,
            "illust_count": 0,
            "retrieval_count": 0,
            "generation_count": 0
        }
    }
    
    # 处理表情包 [MEME: xxx]
    meme_pattern = r'\[MEME:\s*([^\]]+)\]'
    meme_tags = set(re.findall(meme_pattern, content))
    
    for tag in meme_tags:
        tag = tag.strip()
        print(f"\n🔍 处理表情包: {tag}")
        
        # 先尝试检索
        if retriever and retriever.embeddings is not None:
            path, score = retriever.search(tag)
            if path:
                results["memes"][tag] = {
                    "path": path,
                    "score": score,
                    "source": "retrieval"
                }
                results["stats"]["retrieval_count"] += 1
                print(f"  ✅ 检索成功: {path} (score: {score:.3f})")
                continue
        
        # 检索失败，尝试生成
        gen_path = generate_image(tag, "meme")
        if gen_path:
            results["memes"][tag] = {
                "path": gen_path,
                "score": 1.0,
                "source": "generation"
            }
            results["stats"]["generation_count"] += 1
        else:
            results["memes"][tag] = {
                "path": None,
                "score": 0,
                "source": "failed"
            }
    
    results["stats"]["meme_count"] = len(meme_tags)
    
    # 处理插图 [IMG: xxx]
    img_pattern = r'\[IMG:\s*([^\]]+)\]'
    img_tags = set(re.findall(img_pattern, content))
    
    for tag in img_tags:
        description, style = parse_img_tag(tag)
        print(f"\n🖼️ 处理插图: {description} ({style})")
        
        # 插图直接生成
        full_prompt = f"{description}，{style}"
        gen_path = generate_image(full_prompt, "illustration")
        
        if gen_path:
            results["illustrations"][tag] = {
                "path": gen_path,
                "description": description,
                "style": style,
                "source": "generation"
            }
            results["stats"]["generation_count"] += 1
        else:
            results["illustrations"][tag] = {
                "path": None,
                "description": description,
                "style": style,
                "source": "failed"
            }
    
    results["stats"]["illust_count"] = len(img_tags)
    
    return results


def markdown_to_html(content: str) -> str:
    """
    将 Markdown 转换为 HTML
    """
    if HAS_MARKDOWN:
        # 使用 markdown 库
        md = markdown.Markdown(extensions=['tables', 'fenced_code'])
        html = md.convert(content)
        return html
    
    # 简单的 Markdown 转换（备选方案）
    lines = content.split('\n')
    html_lines = []
    in_blockquote = False
    in_list = False
    in_table = False
    
    for line in lines:
        stripped = line.strip()
        
        # 处理水平线
        if stripped == '---' or stripped == '***':
            if in_blockquote:
                html_lines.append('</blockquote>')
                in_blockquote = False
            html_lines.append('<div class="divider"></div>')
            continue
        
        # 处理标题
        if stripped.startswith('# '):
            html_lines.append(f'<h1>{stripped[2:]}</h1>')
            continue
        elif stripped.startswith('## '):
            html_lines.append(f'<h2>{stripped[3:]}</h2>')
            continue
        elif stripped.startswith('### '):
            html_lines.append(f'<h3>{stripped[4:]}</h3>')
            continue
        
        # 处理引用
        if stripped.startswith('> '):
            if not in_blockquote:
                html_lines.append('<blockquote>')
                in_blockquote = True
            quote_content = stripped[2:]
            # 处理引用内的加粗
            quote_content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', quote_content)
            html_lines.append(f'<p>{quote_content}</p>')
            continue
        elif in_blockquote and stripped == '':
            html_lines.append('</blockquote>')
            in_blockquote = False
            continue
        
        # 处理列表
        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            list_content = stripped[2:]
            list_content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', list_content)
            html_lines.append(f'<li>{list_content}</li>')
            continue
        elif stripped.startswith(('1. ', '2. ', '3. ', '4. ', '5. ')):
            if not in_list:
                html_lines.append('<ol>')
                in_list = True
            list_content = stripped[3:]
            list_content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', list_content)
            html_lines.append(f'<li>{list_content}</li>')
            continue
        elif in_list and stripped == '':
            if '<ol>' in ''.join(html_lines[-10:]):
                html_lines.append('</ol>')
            else:
                html_lines.append('</ul>')
            in_list = False
            continue
        
        # 处理表格
        if '|' in stripped and stripped.startswith('|'):
            if not in_table:
                html_lines.append('<table>')
                in_table = True
            if stripped.replace('|', '').replace('-', '').replace(' ', '') == '':
                continue  # 跳过分隔行
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            row_html = '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>'
            html_lines.append(row_html)
            continue
        elif in_table and '|' not in stripped:
            html_lines.append('</table>')
            in_table = False
        
        # 处理普通段落
        if stripped:
            # 如果是 HTML 标签，直接保留
            if stripped.startswith('<') and stripped.endswith('>'):
                html_lines.append(stripped)
                continue
            if stripped.startswith('<div') or stripped.startswith('</div') or stripped.startswith('<img'):
                html_lines.append(stripped)
                continue
            
            # 处理加粗
            para = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
            # 处理斜体
            para = re.sub(r'\*(.+?)\*', r'<em>\1</em>', para)
            # 处理行内代码
            para = re.sub(r'`(.+?)`', r'<code>\1</code>', para)
            html_lines.append(f'<p>{para}</p>')
        elif stripped == '':
            # 空行
            if in_blockquote:
                html_lines.append('</blockquote>')
                in_blockquote = False
    
    # 关闭未关闭的标签
    if in_blockquote:
        html_lines.append('</blockquote>')
    if in_list:
        html_lines.append('</ul>')
    if in_table:
        html_lines.append('</table>')
    
    return '\n'.join(html_lines)


def get_relative_path(image_path: str) -> str:
    """
    将图片路径转换为相对于 outputs/articles/ 的路径
    
    输入: outputs/images/memes/xxx.png
    输出: ../images/memes/xxx.png
    """
    if image_path.startswith("outputs/"):
        # 去掉 "outputs/" 前缀，加上 "../"
        return "../" + image_path[8:]  # 8 = len("outputs/")
    elif image_path.startswith("memes/"):
        # memes/images/xxx.png -> ../../memes/images/xxx.png
        return "../../" + image_path
    return image_path


def render_html(content: str, title: str, image_results: dict, 
                template_path: str = "templates/article.html") -> str:
    """
    将处理后的内容渲染为 HTML
    """
    # 替换表情包标记
    for tag, info in image_results["memes"].items():
        pattern = rf'\[MEME:\s*{re.escape(tag)}\]'
        if info["path"]:
            img_path = get_relative_path(info["path"])
            replacement = f'''<div class="meme-placeholder">
        <img src="{img_path}" alt="{tag}" class="meme-img">
      </div>'''
        else:
            # 使用 emoji 占位
            emoji_map = {
                "震惊": "😱", "目瞪口呆": "😱", "DNA动了": "🧬",
                "狗头": "🐶", "无语": "😑", "钞票": "💸",
                "危险": "⚠️", "警告": "⚠️", "蜡烛": "🕯️",
                "悼念": "🕯️", "破防": "😭", "泪目": "😭",
                "敬礼": "🫡", "致敬": "🫡", "叹气": "😮‍💨", "无奈": "😮‍💨"
            }
            first_key = tag.split('/')[0]
            emoji = emoji_map.get(first_key, "😀")
            replacement = f'''<div class="meme-placeholder">
        <span class="emoji">{emoji}</span>
        <span>{tag}</span>
      </div>'''
        content = re.sub(pattern, replacement, content)
    
    # 替换插图标记
    for tag, info in image_results["illustrations"].items():
        pattern = rf'\[IMG:\s*{re.escape(tag)}\]'
        if info["path"]:
            img_path = get_relative_path(info["path"])
            replacement = f'''<div class="img-placeholder">
        <img src="{img_path}" alt="{info['description']}" class="featured-img">
      </div>'''
        else:
            replacement = f'''<div class="img-placeholder">
        <div class="icon">🖼️</div>
        <p>{info['description']}<br><small>{info['style']}</small></p>
      </div>'''
        content = re.sub(pattern, replacement, content)
    
    # 加载模板
    if Path(template_path).exists():
        with open(template_path, 'r', encoding='utf-8') as f:
            html = f.read()
    else:
        # 使用简单模板
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>{{TITLE}}</title>
</head>
<body>
  <article>
    <h1>{{TITLE}}</h1>
    <div>{{CONTENT}}</div>
  </article>
</body>
</html>"""
    
    # 将 Markdown 转换为 HTML
    content_html = markdown_to_html(content)
    
    # 替换模板变量
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = html.replace("{{TITLE}}", title)
    html = html.replace("{{TIMESTAMP}}", timestamp)
    html = html.replace("{{CONTENT}}", content_html)
    html = html.replace("{{WORD_COUNT}}", str(len(content)))
    html = html.replace("{{ROUNDS}}", "1")
    html = html.replace("{{SCORE}}", "8.0/10")
    html = html.replace("{{MEME_COUNT}}", str(image_results["stats"]["meme_count"]))
    html = html.replace("{{IMG_COUNT}}", str(image_results["stats"]["illust_count"]))
    html = html.replace("{{TAGS}}", "")
    
    return html


def main():
    parser = argparse.ArgumentParser(description='渲染文章并处理图片')
    parser.add_argument('--input', type=str, help='输入的 Markdown 文件')
    parser.add_argument('--content', type=str, help='直接输入的文章内容')
    parser.add_argument('--title', type=str, default='文章', help='文章标题')
    parser.add_argument('--output', type=str, help='输出的 HTML 文件')
    parser.add_argument('--skip-retrieval', action='store_true', help='跳过检索，直接生成')
    
    args = parser.parse_args()
    
    # 获取内容
    if args.input:
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
    elif args.content:
        content = args.content
    else:
        print("请提供 --input 或 --content 参数")
        return
    
    # 初始化检索器
    retriever = None
    if not args.skip_retrieval:
        retriever = MemeRetriever()
        retriever.load()
    
    # 处理图片
    print("\n" + "="*50)
    print("开始处理文章图片")
    print("="*50)
    
    image_results = process_article(content, retriever)
    
    # 打印统计
    print("\n" + "="*50)
    print("处理统计")
    print("="*50)
    print(f"表情包数量: {image_results['stats']['meme_count']}")
    print(f"插图数量: {image_results['stats']['illust_count']}")
    print(f"检索成功: {image_results['stats']['retrieval_count']}")
    print(f"生成成功: {image_results['stats']['generation_count']}")
    
    # 渲染 HTML
    if args.output:
        html = render_html(content, args.title, image_results)
        
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"\n✅ HTML 已保存到: {args.output}")
    
    # 输出 JSON 结果
    print("\n处理结果:")
    print(json.dumps(image_results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
