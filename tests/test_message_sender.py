"""Tests for app.services.message_sender — message splitting logic."""

from app.services.message_sender import split_message


def test_short_message_no_split():
    result = split_message("Hello there!", 100)
    assert result == ["Hello there!"]


def test_split_on_double_newline():
    text = "A" * 80 + "\n\n" + "B" * 80
    result = split_message(text, 100)
    assert len(result) == 2
    assert result[0] == "A" * 80
    assert result[1] == "B" * 80


def test_split_on_single_newline():
    text = "A" * 80 + "\n" + "B" * 80
    result = split_message(text, 100)
    assert len(result) == 2
    assert result[0] == "A" * 80
    assert result[1] == "B" * 80


def test_split_at_hard_limit():
    text = "A" * 200
    result = split_message(text, 100)
    assert len(result) == 2
    assert len(result[0]) == 100
    assert len(result[1]) == 100


def test_split_preserves_content():
    lines = [f"Line {i}" for i in range(20)]
    text = "\n".join(lines)
    result = split_message(text, 50)
    reassembled = "\n".join(result)
    # All lines should be present
    for line in lines:
        assert line in reassembled


def test_empty_message():
    result = split_message("", 100)
    assert result == [""]


def test_exact_limit():
    text = "A" * 100
    result = split_message(text, 100)
    assert result == ["A" * 100]


def test_multiple_splits():
    text = ("A" * 40 + "\n\n") * 5
    result = split_message(text.strip(), 50)
    assert len(result) >= 3
    for chunk in result:
        assert len(chunk) <= 50
