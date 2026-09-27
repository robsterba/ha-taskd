"""Tests for the quick-add parser (mirrors taskd's GUI behaviour)."""

from custom_components.taskd.quick_add import parse_quick_add


def test_plain_text() -> None:
    assert parse_quick_add("Fix the wireguard tunnel") == {
        "name": "Fix the wireguard tunnel",
        "tags": None,
        "priority": None,
    }


def test_tags_and_priority() -> None:
    assert parse_quick_add("Fix wg on boxy #network #vpn !urgent") == {
        "name": "Fix wg on boxy",
        "tags": ["network", "vpn"],
        "priority": "urgent",
    }


def test_priority_only() -> None:
    assert parse_quick_add("!high Buy milk") == {
        "name": "Buy milk",
        "tags": None,
        "priority": "high",
    }


def test_tags_only() -> None:
    assert parse_quick_add("#homelab patch moxy") == {
        "name": "patch moxy",
        "tags": ["homelab"],
        "priority": None,
    }


def test_invalid_priority_kept_in_name() -> None:
    parsed = parse_quick_add("!foo Fix thing")
    assert parsed == {"name": "!foo Fix thing", "tags": None, "priority": None}


def test_only_first_priority_token() -> None:
    """The GUI only honours the first !priority token."""
    assert parse_quick_add("!high !low mixed") == {
        "name": "!low mixed",
        "tags": None,
        "priority": "high",
    }


def test_tokens_only_falls_back_to_original() -> None:
    """Only tokens typed: the GUI falls back to the raw text as name."""
    assert parse_quick_add("#tag") == {
        "name": "#tag",
        "tags": ["tag"],
        "priority": None,
    }


def test_whitespace_normalized() -> None:
    assert parse_quick_add("  Trim   me  !low ") == {
        "name": "Trim   me",
        "tags": None,
        "priority": "low",
    }
