"""Tests for the scheduler's _parse_schedule function."""

from opencompany.company.scheduler import _parse_schedule


def test_parse_hours():
    result = _parse_schedule("every 6h")
    assert result == {"trigger": "interval", "hours": 6}


def test_parse_minutes():
    result = _parse_schedule("every 30m")
    assert result == {"trigger": "interval", "minutes": 30}


def test_parse_days():
    result = _parse_schedule("every 2d")
    assert result == {"trigger": "interval", "days": 2}


def test_parse_single_hour():
    result = _parse_schedule("every 1h")
    assert result == {"trigger": "interval", "hours": 1}


def test_parse_with_extra_whitespace():
    result = _parse_schedule("  every  6h  ")
    assert result == {"trigger": "interval", "hours": 6}


def test_parse_case_insensitive():
    result = _parse_schedule("Every 12H")
    assert result == {"trigger": "interval", "hours": 12}


def test_parse_invalid_falls_back_to_1h():
    result = _parse_schedule("something invalid")
    assert result == {"trigger": "interval", "hours": 1}


def test_parse_empty_string_falls_back():
    result = _parse_schedule("")
    assert result == {"trigger": "interval", "hours": 1}


def test_parse_every_no_unit_falls_back():
    result = _parse_schedule("every ")
    assert result == {"trigger": "interval", "hours": 1}
