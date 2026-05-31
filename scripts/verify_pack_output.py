# scripts/verify_pack_output.py
"""
打包后检查 dist 目录关键资源是否落入 _internal。
用法：python scripts/verify_pack_output.py [dist目录名]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_NAME = sys.argv[1] if len(sys.argv) > 1 else "FGO因陀罗桌宠"


def _internal_root(dist_dir: Path) -> Path | None:
    internal = dist_dir / "_internal"
    if internal.is_dir():
        return internal
    # 旧版 PyInstaller 可能无 _internal
    return dist_dir if dist_dir.is_dir() else None


REQUIRED_IN_INTERNAL = [
    "assets/images/pet.png",
    "assets/images/bolt-eye.png",
    "assets/images/bolt-eye.ico",
    "assets/images/ui/temp_bubble.png",
    "assets/images/idle",
    "assets/images/emoji",
    "models/gte-multilingual-base/model.safetensors",
    "src/llm/knowledge_db/lore/default__vector_store.json",
    "src/llm/knowledge_db/style/default__vector_store.json",
    "src/llm/knowledge/lore",
    "src/llm/persona.txt",
    "config/settings.json",
    "config/prompts/memory_extract.md",
    "src/llm/providers/registry.json",
    "用户手册.html",
]


def main() -> int:
    dist_dir = ROOT / "dist" / DIST_NAME
    if not dist_dir.is_dir():
        print(f"[verify_pack_output] 未找到输出目录: {dist_dir}")
        return 1

    exe = dist_dir / f"{DIST_NAME}.exe"
    if not exe.is_file():
        print(f"[verify_pack_output] 未找到可执行文件: {exe}")
        return 1

    internal = _internal_root(dist_dir)
    if internal is None:
        print("[verify_pack_output] 无法定位 _internal 资源目录")
        return 1

    missing: list[str] = []
    for rel in REQUIRED_IN_INTERNAL:
        path = internal / Path(rel)
        if not path.exists():
            missing.append(rel)

    if missing:
        print("[verify_pack_output] _internal 缺少以下资源：")
        for m in missing:
            print(f"  - {m}")
        return 1

    print("[verify_pack_output] 打包输出检查通过")
    print(f"  exe: {exe}")
    print(f"  资源根: {internal}")
    print("  用户可写数据将落在 exe 同级 config/、screenshots/（首次运行自动创建）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
