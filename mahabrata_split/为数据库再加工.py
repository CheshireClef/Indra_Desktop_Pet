import os
import yaml
import requests
from pathlib import Path

# ---------- config ----------
BASE_DIR = Path(__file__).resolve().parents[2]
LORE_DIR = BASE_DIR / r"C:\Users\AOELu\Documents\摩诃婆罗多脱水处理\第一部切片"

CONFIG_PATH = BASE_DIR / r"C:\Users\AOELu\Documents\摩诃婆罗多脱水处理\config.yaml"
CHARACTER_PATH = BASE_DIR / r"C:\Users\AOELu\Documents\Github\Indra_Desktop_Pet\src\llm\knowledge\lore\译名对照表.yaml"

# ---------- load config ----------
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

llm_cfg = config["llm"]

API_BASE = llm_cfg["api_base"].rstrip("/")
API_KEY = llm_cfg["api_key"]
MODEL = llm_cfg["model"]
TIMEOUT = llm_cfg.get("timeout", 60)

# ---------- load characters ----------
with open(CHARACTER_PATH, "r", encoding="utf-8") as f:
    char_data = yaml.safe_load(f)["characters"]

def build_character_context():
    lines = ["【角色别称对照表】"]
    for name, data in char_data.items():
        aliases = data.get("aliases", [])
        if aliases:
            lines.append(f"{name}：别称包括 {', '.join(aliases)}")
    return "\n".join(lines)

CHARACTER_CONTEXT = build_character_context()

# ---------- prompt ----------
SYSTEM_PROMPT = """你是一名文本分析助手，任务是将史诗叙事文本转换为适合RAG检索的事实文本。

要求：
1. 使用“事件”为单位
2. 明确写出：参与角色、立场关系、具体行为、因陀罗对其他角色的态度及原因
3. 使用规范角色名（不要使用别称）
4. 保留情节细节，但避免修辞和夸张
5. 输出为纯文本，不使用Markdown列表符号
"""

def build_user_prompt(story_text: str) -> str:
    return f"""
{CHARACTER_CONTEXT}

【原文】
{story_text}

请根据以上原文生成 facts 文本。
"""

# ---------- llm call ----------
def call_llm(prompt: str) -> str:
    url = f"{API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

# ---------- main ----------
def process_file(txt_path: Path):
    facts_path = txt_path.with_suffix(".facts.txt")
    if facts_path.exists():
        print(f"跳过已存在：{facts_path.name}")
        return

    story = txt_path.read_text(encoding="utf-8")
    prompt = build_user_prompt(story)
    facts = call_llm(prompt)

    facts_path.write_text(facts, encoding="utf-8")
    print(f"生成：{facts_path.name}")

def main():
    for txt in LORE_DIR.glob("*.txt"):
        if txt.name.endswith(".facts.txt"):
            continue
        process_file(txt)

if __name__ == "__main__":
    main()
