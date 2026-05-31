# tests/test_memory_extract_parse.py
"""记忆抽取 JSON 解析单元测试（嵌套 memories 数组）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm.clients.text_sanitize import extract_json_payload
from llm.parsers.json_extract import extract_json_object


def _parse_memories(raw: str) -> list[tuple[str, str | None]]:
    """与 parse_extract_response 相同的核心解析路径（避免导入 memory_extract → PySide6）。"""
    payload = extract_json_payload(raw.strip(), brace_preference="first")
    if not payload:
        return []
    obj = json.loads(payload)
    if not isinstance(obj, dict):
        return []
    memories = obj.get("memories")
    if not isinstance(memories, list):
        return []
    out: list[tuple[str, str | None]] = []
    for item in memories:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        topic = item.get("topic")
        t = topic.strip() if isinstance(topic, str) and topic.strip() else None
        out.append((content.strip(), t))
    return out


def test_nested_memories_unfenced_first_brace():
    raw = (
        '{ "memories": [ { "content": "用户近期饮酒过量，正计划控制酒精摄入。", '
        '"topic": "健康习惯" }, { "content": "用户正在备考会计考试。", "topic": "学习备考" } ] }'
    )
    items = _parse_memories(raw)
    assert len(items) == 2
    assert items[0][1] == "健康习惯"
    assert items[1][1] == "学习备考"


def test_nested_memories_fenced():
    raw = """```json
{"memories":[{"content":"用户正在从事 AI 助手记忆模块开发","topic":"工作项目"}]}
```"""
    items = _parse_memories(raw)
    assert len(items) == 1
    assert "记忆模块" in items[0][0]


def test_last_brace_strategy_breaks_nested_but_first_works():
    raw = '{"memories":[{"content":"a","topic":"x"},{"content":"b","topic":"y"}]}'
    broken = extract_json_object(raw, brace_preference="last")
    fixed = extract_json_object(raw, brace_preference="first")
    assert broken.payload is not None
    assert fixed.payload is not None
    assert "memories" not in json.loads(broken.payload)
    assert "memories" in json.loads(fixed.payload)


def test_chat_last_brace_still_works_for_trailing_json():
    prose = "一些说明文字\n"
    raw = prose + '{"reply":"你好","emotion":"开心"}'
    r = extract_json_object(raw, brace_preference="last")
    assert r.payload is not None
    obj = json.loads(r.payload)
    assert obj["reply"] == "你好"


if __name__ == "__main__":
    test_nested_memories_unfenced_first_brace()
    test_nested_memories_fenced()
    test_last_brace_strategy_breaks_nested_but_first_works()
    test_chat_last_brace_still_works_for_trailing_json()
    print("all tests passed")
