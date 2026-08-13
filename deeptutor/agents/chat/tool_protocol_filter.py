"""Chunk-safe filter for leaked internal tool-call protocol.

Providers can split protocol tags at arbitrary byte/token boundaries. A regex
that cleans each emitted buffer independently can therefore leak parameter
payloads (for example the answer text inside ``<parameter=answer>``) before a
closing ``</function>`` arrives. This parser keeps protocol state across
chunks and suppresses the entire internal block.
"""

from __future__ import annotations

import re

_PROTOCOL_TAG_RE = re.compile(
    r"^<\s*(?P<close>/?)\s*(?P<name>tool_call|function|parameter)\b",
    re.IGNORECASE,
)


class ToolProtocolFilter:
    """Incrementally remove internal tool protocol without leaking payloads."""

    def __init__(self) -> None:
        self._buffer = ""
        self._stack: list[str] = []

    @staticmethod
    def _protocol_tag(tag: str) -> tuple[str, bool, bool] | None:
        match = _PROTOCOL_TAG_RE.match(tag)
        if match is None:
            return None
        name = str(match.group("name") or "").lower()
        closing = bool(match.group("close"))
        self_closing = tag.rstrip().endswith("/>")
        return name, closing, self_closing

    def _consume_protocol_tag(self, tag: str) -> bool:
        parsed = self._protocol_tag(tag)
        if parsed is None:
            return False
        name, closing, self_closing = parsed
        if closing:
            if name in self._stack:
                reverse_index = self._stack[::-1].index(name)
                index = len(self._stack) - 1 - reverse_index
                del self._stack[index:]
            return True
        if not self_closing:
            self._stack.append(name)
        return True

    def feed(self, chunk: str) -> str:
        """Consume one stream chunk and return only user-visible text."""
        if not chunk:
            return ""
        self._buffer += chunk
        emitted: list[str] = []

        while self._buffer:
            if self._stack:
                # While suppressed, plain payload text is safe to discard
                # immediately. Only retain a trailing partial tag so a closing
                # tag split across chunks can be recognized on the next feed.
                tag_start = self._buffer.find("<")
                if tag_start < 0:
                    self._buffer = ""
                    break
                if tag_start > 0:
                    self._buffer = self._buffer[tag_start:]
                tag_end = self._buffer.find(">")
                if tag_end < 0:
                    break
                tag = self._buffer[: tag_end + 1]
                self._buffer = self._buffer[tag_end + 1 :]
                self._consume_protocol_tag(tag)
                continue

            tag_start = self._buffer.find("<")
            if tag_start < 0:
                emitted.append(self._buffer)
                self._buffer = ""
                break
            if tag_start > 0:
                emitted.append(self._buffer[:tag_start])
                self._buffer = self._buffer[tag_start:]

            tag_end = self._buffer.find(">")
            if tag_end < 0:
                break
            tag = self._buffer[: tag_end + 1]
            self._buffer = self._buffer[tag_end + 1 :]
            if not self._consume_protocol_tag(tag):
                emitted.append(tag)

        return "".join(emitted)

    def flush(self) -> str:
        """Finish the stream, discarding any unfinished internal block."""
        if self._stack:
            self._buffer = ""
            self._stack.clear()
            return ""
        if not self._buffer:
            return ""

        remaining = self._buffer
        self._buffer = ""
        # A stream may end in a split internal tag such as ``<tool_ca``.
        # Suppress only protocol-looking partials; preserve ordinary text like
        # mathematical ``x < 5``.
        last_lt = remaining.rfind("<")
        if last_lt >= 0:
            tail = remaining[last_lt:]
            lowered = re.sub(r"\s+", "", tail.lower())
            protocol_prefixes = (
                "<tool_call",
                "</tool_call",
                "<function",
                "</function",
                "<parameter",
                "</parameter",
            )
            if any(
                prefix.startswith(lowered) or lowered.startswith(prefix)
                for prefix in protocol_prefixes
            ):
                remaining = remaining[:last_lt]
        return remaining


__all__ = ["ToolProtocolFilter"]
