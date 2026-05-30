# scripts/verify_pack_inputs.py
"""
打包前检查：嵌入模型、预构建向量库、关键资源是否齐全。
用法：python scripts/verify_pack_inputs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FILES = [
  # 嵌入模型（离线 RAG + 长期记忆）
  "models/gte-multilingual-base/model.safetensors",
  "models/gte-multilingual-base/config.json",
  "models/gte-multilingual-base/tokenizer.json",
  # 预构建向量索引（随包分发，避免测试用户首次重建）
  "src/llm/knowledge_db/lore/default__vector_store.json",
  "src/llm/knowledge_db/lore/docstore.json",
  "src/llm/knowledge_db/style/default__vector_store.json",
  "src/llm/knowledge_db/style/docstore.json",
  # 程序入口与配置模板
  "src/main.py",
  "config/settings.json",
  "config/prompts/memory_extract.md",
  "src/llm/providers/registry.json",
  "assets/images/pet.png",
  "assets/images/bolt-eye.png",
  "assets/images/bolt-eye.ico",
  "FGO因陀罗桌宠.spec",
]


def main() -> int:
    missing: list[str] = []
    for rel in REQUIRED_FILES:
        path = ROOT / rel.replace("/", "\\") if "\\" not in rel else ROOT / rel
        path = ROOT / Path(rel)
        if not path.is_file():
            missing.append(rel)

    if missing:
        print("[verify_pack_inputs] 缺少以下打包必需文件：")
        for m in missing:
            print(f"  - {m}")
        print("\n提示：嵌入模型请运行 python src/download_model.py；")
        print("向量库需在开发环境完成索引构建后再打包。")
        return 1

    model_mb = (ROOT / "models/gte-multilingual-base/model.safetensors").stat().st_size / (1024 * 1024)
    lore_mb = (ROOT / "src/llm/knowledge_db/lore/default__vector_store.json").stat().st_size / (1024 * 1024)
    style_mb = (
        ROOT / "src/llm/knowledge_db/style/default__vector_store.json"
    ).stat().st_size / (1024 * 1024)
    print("[verify_pack_inputs] 打包输入检查通过")
    print(f"  嵌入模型 model.safetensors: {model_mb:.1f} MB")
    print(f"  lore 向量库: {lore_mb:.1f} MB")
    print(f"  style 向量库: {style_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
