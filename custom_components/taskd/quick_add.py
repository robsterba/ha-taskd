"""Pure helpers mirroring taskd's GUI quick-add parsing.

taskd's GUI (frontend/src/pages/TaskList.jsx ``parseQuickAdd``) recognizes:

- ``#tag`` tokens (multiple allowed, no whitespace inside a tag)
- a single ``!priority`` token (``!urgent``, ``!high``, ``!medium``, ``!low``)
- everything left over is the task name

No date syntax is supported by the GUI, so none is parsed here either.
"""

from __future__ import annotations

import re
from typing import Any, Final

_PRIORITY_RE: Final = re.compile(r"!(\w+)")
_TAG_RE: Final = re.compile(r"#(\S+)")
_VALID_PRIORITIES: Final = {"urgent", "high", "medium", "low"}


def parse_quick_add(text: str) -> dict[str, Any]:
    """Parse quick-add syntax from a summary string.

    Returns a dict with ``name``, ``tags`` (list[str]) and ``priority``
    (str | None) keys. If the name ends up empty (e.g. the user typed
    only tokens), the original text is used as the name, matching the
    taskd GUI fallback behaviour.
    """
    name = text.strip()
    tags: list[str] = []
    priority: str | None = None

    priority_match = _PRIORITY_RE.search(name)
    if priority_match and priority_match[1].lower() in _VALID_PRIORITIES:
        priority = priority_match[1].lower()
        name = name.replace(priority_match[0], "", 1).strip()

    tag_match = _TAG_RE.search(name)
    while tag_match:
        tags.append(tag_match[1])
        name = name.replace(tag_match[0], "", 1).strip()
        tag_match = _TAG_RE.search(name)

    if not name:
        name = text.strip()

    return {"name": name, "tags": tags or None, "priority": priority}
