# tests/test_memory_extract_sampling.py
"""聊天长期记忆取样单元测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm.memory_extract_sampling import (
    SCREEN_COMMENT_PREFIX,
    MemoryRoundBuffer,
    build_chat_extract_slice,
    is_screen_comment_message,
)


def _round(user_text: str, assistant_text: str) -> tuple[dict, dict]:
    return (
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_text},
    )


def test_n2_four_rounds_two_slices_no_overlap():
    buf = MemoryRoundBuffer()
    n = 2
    slices = []
    for i in range(1, 5):
        u, a = _round(f"用户消息{i}", f"助手回复{i}")
        buf.append_round(u, a)
        while buf.pending_count() >= n:
            sl = buf.pending_slice(n)
            assert sl is not None
            slices.append(sl)
            buf.commit(n)
    assert len(slices) == 2
    assert all(len(s) == 4 for s in slices)
    assert "用户消息1" in slices[0][0]["content"]
    assert "用户消息2" in slices[0][2]["content"]
    assert "用户消息3" in slices[1][0]["content"]
    assert "用户消息4" in slices[1][2]["content"]
    assert buf.pending_count() == 0


def test_screen_comment_not_appended_to_buffer():
    buf = MemoryRoundBuffer()
    screen = {
        "role": "assistant",
        "content": f"{SCREEN_COMMENT_PREFIX}\n你在写代码",
    }
    u, a = _round("正常聊天", "正常回复")
    buf.append_round(u, a)
    buf.append_round(u, screen)
    assert len(buf.rounds) == 1
    assert is_screen_comment_message(screen)


def test_build_chat_extract_slice_returns_none_when_insufficient():
    rounds = [[_round("a", "b")[0], _round("a", "b")[1]]]
    assert build_chat_extract_slice(rounds, 0, 2) is None
    assert build_chat_extract_slice(rounds, 0, 1) is not None


def test_cursor_commit_trims_committed_rounds():
    buf = MemoryRoundBuffer()
    for i in range(3):
        u, a = _round(f"u{i}", f"a{i}")
        buf.append_round(u, a)
    assert len(buf.rounds) == 3
    sl = buf.pending_slice(2)
    assert sl is not None
    buf.commit(2)
    assert len(buf.rounds) == 1
    assert buf.pending_count() == 1


if __name__ == "__main__":
    test_n2_four_rounds_two_slices_no_overlap()
    test_screen_comment_not_appended_to_buffer()
    test_build_chat_extract_slice_returns_none_when_insufficient()
    test_cursor_commit_trims_committed_rounds()
    print("all tests passed")
