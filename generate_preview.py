#!/usr/bin/env python3
"""
预览图生成工具

自动扫描项目中所有宠物目录（包含 pet.json + spritesheet.webp），
从精灵图的第一行裁剪出站立动画帧，保存为 preview/<pet-id>/idle.png，
并自动更新 README.md 中的预览图部分。

用法:
    # 首次使用需安装依赖
    pip install Pillow numpy

    # 运行
    python generate_preview.py
"""

import json
import os
import sys

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("错误: 缺少依赖，请先运行: pip install Pillow numpy")
    sys.exit(1)

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PREVIEW_DIR = os.path.join(ROOT_DIR, "preview")
README_PATH = os.path.join(ROOT_DIR, "README.md")

# README 中预览区域的标记
PREVIEW_START = "<!-- PREVIEW_START -->"
PREVIEW_END = "<!-- PREVIEW_END -->"


def find_segments(has_content, min_gap=3):
    """在布尔数组中找出连续为 True 的区段，合并间距过小的段"""
    segments = []
    in_seg = False
    start = 0
    for i, v in enumerate(has_content):
        if v and not in_seg:
            start = i
            in_seg = True
        elif not v and in_seg:
            segments.append((start, i - 1))
            in_seg = False
    if in_seg:
        segments.append((start, len(has_content) - 1))

    if not segments:
        return []

    # 合并间距过小的段
    merged = [segments[0]]
    for s, e in segments[1:]:
        if s - merged[-1][1] <= min_gap:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def extract_first_row(spritesheet_path):
    """从精灵图中裁剪第一行，返回 PIL Image"""
    img = Image.open(spritesheet_path).convert("RGBA")
    data = np.array(img)
    alpha = data[:, :, 3]

    # 按行检测内容区域
    row_has_content = np.any(alpha > 10, axis=1)
    row_segments = find_segments(row_has_content)

    if not row_segments:
        return None

    y1, y2 = row_segments[0]

    # 找第一行的水平内容范围
    row_alpha = alpha[y1 : y2 + 1, :]
    col_content = np.any(row_alpha > 10, axis=0)
    cols = np.where(col_content)[0]

    if len(cols) == 0:
        return None

    x1, x2 = int(cols[0]), int(cols[-1])
    return img.crop((x1, y1, x2 + 1, y2 + 1))


def discover_pets():
    """扫描项目根目录，找到所有包含 pet.json 和 spritesheet.webp 的目录"""
    pets = []
    for entry in sorted(os.listdir(ROOT_DIR)):
        pet_dir = os.path.join(ROOT_DIR, entry)
        if not os.path.isdir(pet_dir):
            continue
        pet_json = os.path.join(pet_dir, "pet.json")
        spritesheet = os.path.join(pet_dir, "spritesheet.webp")
        if os.path.isfile(pet_json) and os.path.isfile(spritesheet):
            with open(pet_json, "r", encoding="utf-8") as f:
                config = json.load(f)
            pets.append(
                {
                    "id": config.get("id", entry),
                    "displayName": config.get("displayName", entry),
                    "description": config.get("description", ""),
                    "dir": entry,
                    "spritesheet": spritesheet,
                }
            )
    return pets


def generate_previews(pets):
    """为所有宠物生成预览图"""
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    results = []

    for pet in pets:
        pet_preview_dir = os.path.join(PREVIEW_DIR, pet["dir"])
        os.makedirs(pet_preview_dir, exist_ok=True)
        out_path = os.path.join(pet_preview_dir, "idle.png")

        print(f"  处理 {pet['displayName']}...", end=" ")
        row_img = extract_first_row(pet["spritesheet"])
        if row_img is None:
            print("⚠ 无法提取第一行，跳过")
            continue

        row_img.save(out_path, optimize=True)
        print(f"✓ {row_img.size[0]}x{row_img.size[1]}px")
        results.append(pet)

    return results


def update_readme(pets):
    """更新 README.md 中的预览图区域"""
    if not os.path.isfile(README_PATH):
        print("  ⚠ README.md 不存在，跳过更新")
        return

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 构建预览区域内容
    preview_lines = [PREVIEW_START, ""]
    for pet in pets:
        preview_lines.append(f"![{pet['displayName']}](preview/{pet['dir']}/idle.png)")
        preview_lines.append("")
    preview_lines.append(PREVIEW_END)
    preview_block = "\n".join(preview_lines)

    # 替换或插入预览区域
    if PREVIEW_START in content and PREVIEW_END in content:
        # 替换已有区域
        start_idx = content.index(PREVIEW_START)
        end_idx = content.index(PREVIEW_END) + len(PREVIEW_END)
        content = content[:start_idx] + preview_block + content[end_idx:]
    else:
        # 查找 ## Example 并在其后插入
        example_marker = "## Example"
        if example_marker in content:
            idx = content.index(example_marker) + len(example_marker)
            # 跳过紧跟的换行
            while idx < len(content) and content[idx] == "\n":
                idx += 1
            # 移除旧的预览图行（以 ![开头的行）
            lines = content[:idx].rstrip("\n").split("\n")
            rest_lines = content[idx:].split("\n")
            # 过滤掉旧的 preview 图片行
            rest_lines = [
                line
                for line in rest_lines
                if not (line.startswith("![") and "preview/" in line)
            ]
            rest_content = "\n".join(rest_lines).strip()
            content = "\n".join(lines) + "\n\n" + preview_block
            if rest_content:
                content += "\n\n" + rest_content
            content += "\n"
        else:
            # 直接追加到末尾
            content = content.rstrip("\n") + "\n\n## Example\n\n" + preview_block + "\n"

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    print("🔍 扫描宠物目录...")
    pets = discover_pets()

    if not pets:
        print("  未找到任何宠物目录（需包含 pet.json + spritesheet.webp）")
        sys.exit(0)

    print(f"  找到 {len(pets)} 个宠物: {', '.join(p['displayName'] for p in pets)}\n")

    print("🖼  生成预览图...")
    generated = generate_previews(pets)
    print()

    print("📝 更新 README.md...")
    update_readme(generated)
    print("  ✓ README.md 已更新\n")

    print(f"✅ 完成！共生成 {len(generated)} 个预览图")


if __name__ == "__main__":
    main()
