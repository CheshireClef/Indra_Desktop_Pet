# src/llm/memory_extract_sampling.py
"""
聊天长期记忆取样：独立于 chat_history，按用户聊天轮缓冲、游标提交。
屏幕评论 assistant 消息不进入 buffer。
"""
from __future__ import annotations

import copy
from typing import Any

# 与 chat_manager 屏幕评论前缀保持一致
SCREEN_COMMENT_PREFIX = "【刚刚对屏幕的评论】"


def is_screen_comment_message(msg: dict[str, Any]) -> bool:
    """assistant 消息以屏幕评论前缀开头则判定为屏幕评论，不计入聊天轮。"""
    if not isinstance(msg, dict):
        return False
    if msg.get("role") != "assistant":
        return False
    content = str(msg.get("content") or "").strip()
    return content.startswith(SCREEN_COMMENT_PREFIX)


def flatten_rounds(rounds: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """将多轮 [[user, assistant], ...] 扁平化为 messages 列表。"""
    out: list[dict[str, Any]] = []
    for pair in rounds:
        for msg in pair:
            out.append(copy.deepcopy(msg))
    return out


def build_chat_extract_slice(
    rounds: list[list[dict[str, Any]]],
    cursor: int,
    n: int,
) -> list[dict[str, Any]] | None:
    """
    若 rounds[cursor:cursor+n] 存在，返回扁平化 slice；否则 None。
    不修改 cursor（由 MemoryRoundBuffer.commit 负责）。
    """
    if n < 1 or cursor < 0:
        return None
    if len(rounds) - cursor < n:
        return None
    chunk = rounds[cursor : cursor + n]
    return flatten_rounds(chunk)


class MemoryRoundBuffer:
    """
    用户聊天轮缓冲：每轮为 [user_msg, assistant_msg]。
    cursor 表示已提交抽取的轮数；commit 后 trim 已提交部分以释放内存。
    """

    def __init__(self) -> None:
        self.rounds: list[list[dict[str, Any]]] = []
        self.cursor: int = 0

    def append_round(
        self,
        user_msg: dict[str, Any],
        assistant_msg: dict[str, Any],
    ) -> None:
        """追加一轮用户聊天（不含屏幕评论）。"""
        if is_screen_comment_message(assistant_msg):
            return
        self.rounds.append(
            [copy.deepcopy(user_msg), copy.deepcopy(assistant_msg)]
        )

    def pending_count(self) -> int:
        """尚未提交抽取的轮数。"""
        return len(self.rounds) - self.cursor

    def pending_slice(self, n: int) -> list[dict[str, Any]] | None:
        """若待提交轮数 >= n，返回 rounds[cursor:cursor+n] 扁平化 slice。"""
        return build_chat_extract_slice(self.rounds, self.cursor, n)

    def commit(self, n: int) -> None:
        """标记 n 轮已提交，并丢弃已提交部分。"""
        if n < 1:
            return
        self.cursor += n
        if self.cursor > 0:
            del self.rounds[: self.cursor]
            self.cursor = 0
