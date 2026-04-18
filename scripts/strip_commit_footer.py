"""Remove an automated two-line footer from commit messages (git filter-branch --msg-filter)."""

from __future__ import annotations

import sys

_MARKER = "\n\nMade-with: Cursor"
_LINE = "Made-with: Cursor"


def strip_message(raw: str) -> str:
    if _MARKER in raw:
        return raw.split(_MARKER, 1)[0].rstrip("\n") + "\n"
    lines = raw.rstrip("\n").split("\n")
    if lines and lines[-1].strip() == _LINE:
        lines = lines[:-1]
        while lines and lines[-1] == "":
            lines.pop()
        if lines:
            return "\n".join(lines) + "\n"
        return ""
    return raw


if __name__ == "__main__":
    sys.stdout.write(strip_message(sys.stdin.read()))
