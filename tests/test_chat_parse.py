# tests/test_chat_parse.py
"""聊天 JSON 解析单元测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm.parsers.json_extract import extract_json_object
from llm.parsers.chat_response import parse_chat_output


def test_incomplete_json_no_fulltext_fallback():
    prose = "因陀罗：不妨说说看" * 20
    bad = prose + '\n```json\n{"reply":"短","emotion":"干杯","memory_to_save": null,'
    r = extract_json_object(bad)
    assert r.payload is None
    assert r.incomplete_fence
    p = parse_chat_output(bad, allow_tag_fallback=False)
    assert not p.ok
    assert p.parse_mode == "json_incomplete"


def test_pure_json_ok():
    p = parse_chat_output('{"reply":"你好","emotion":"开心"}', allow_tag_fallback=False)
    assert p.ok
    assert p.reply == "你好"
    assert p.emotion == "开心"
