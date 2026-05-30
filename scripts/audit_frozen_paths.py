# scripts/audit_frozen_paths.py
"""
扫描源码中的资源路径用法，并在 dist 存在时对照 _internal 校验。
用法：python scripts/audit_frozen_paths.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DIST_INTERNAL = ROOT / "dist" / "FGO因陀罗桌宠" / "_internal"

# 代码中引用的只读资源（目录或文件）
BUNDLED_REFERENCES = [
    "assets/images/pet.png",
    "assets/images/bolt-eye.png",
    "assets/images/ui/temp_bubble.png",
    "assets/images/idle",
    "assets/images/emoji",
    "config/settings.json",
    "config/prompts/memory_extract.md",
    "models/gte-multilingual-base/model.safetensors",
    "models/gte-multilingual-base/config.json",
    "src/llm/persona.txt",
    "src/llm/providers/registry.json",
    "src/llm/knowledge/lore",
    "src/llm/knowledge/style",
    "src/llm/knowledge_db/lore/default__vector_store.json",
    "src/llm/knowledge_db/style/default__vector_store.json",
    "用户手册.html",
]

# 危险模式：frozen 下 __file__ 与 datas 路径常不一致
DANGEROUS_PATTERNS = [
    (re.compile(r"Path\s*\(\s*__file__\s*\)"), "Path(__file__) 定位资源"),
    (re.compile(r"__file__\s*\)\.parent\s*/"), "__file__.parent / 文件"),
    (re.compile(r"dirname\s*\(\s*__file__\s*\).*\.(?:json|md|txt|png)"), "dirname(__file__) 拼接资源扩展名"),
]


def _scan_py_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _find_dangerous_lines() -> list[tuple[str, int, str, str]]:
    hits: list[tuple[str, int, str, str]] = []
    for py in _scan_py_files():
        text = py.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            for pat, label in DANGEROUS_PATTERNS:
                if pat.search(line):
                    # utils.py / settings_manager.py 用 __file__ 算项目根（非读资源）可忽略
                    rel = py.relative_to(ROOT).as_posix()
                    if rel in ("src/utils.py", "src/settings_manager.py"):
                        if "resource" not in line.lower() and ".json" not in line:
                            continue
                    hits.append((rel, i, label, line.strip()))
    return hits


def _find_resource_path_literals() -> set[str]:
    found: set[str] = set()
    pat = re.compile(r"""resource_path\s*\(\s*['"]([^'"]+)['"]\s*\)""")
    for py in _scan_py_files():
        for m in pat.finditer(py.read_text(encoding="utf-8")):
            found.add(m.group(1).replace("\\", "/"))
    return found


def _check_dist(paths: list[str]) -> list[str]:
    if not DIST_INTERNAL.is_dir():
        return []
    missing: list[str] = []
    for rel in paths:
        p = DIST_INTERNAL / Path(rel)
        if not p.exists():
            missing.append(rel)
    return missing


def main() -> int:
    ok = True

    print("[audit_frozen_paths] 1/3 扫描危险 __file__ 用法…")
    dangerous = _find_dangerous_lines()
    if dangerous:
        ok = False
        print("  发现可疑行（请改用 resource_path / user_data_path）：")
        for rel, line_no, label, snippet in dangerous:
            print(f"    {rel}:{line_no} [{label}]")
            print(f"      {snippet[:100]}")
    else:
        print("  未发现 __file__ 读资源模式")

    print("[audit_frozen_paths] 2/3 汇总 resource_path 字面量…")
    literals = sorted(_find_resource_path_literals())
    for s in literals:
        print(f"  - {s}")

    print("[audit_frozen_paths] 3/3 对照 dist/_internal…")
    missing = _check_dist(BUNDLED_REFERENCES)
    if not DIST_INTERNAL.is_dir():
        print(f"  跳过（未找到 {DIST_INTERNAL}，请先打包）")
    elif missing:
        ok = False
        print("  _internal 缺少：")
        for m in missing:
            print(f"    - {m}")
    else:
        print(f"  已校验 {len(BUNDLED_REFERENCES)} 项，全部存在")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
