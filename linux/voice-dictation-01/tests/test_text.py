import pytest

from whisper_dictate.text import clean


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("hello world", "hello world"),
        ("line one\nline two", "line one line two"),
        ("carriage\rreturn", "carriage return"),
        ("windows\r\nending", "windows ending"),
        ("tab\there", "tab here"),
        ("  padded  ", "padded"),
        ("many   spaces", "many spaces"),
        ("nul\x00byte", "nul byte"),
        ("c1\x85control", "c1 control"),
        ("delete\x7fchar", "delete char"),
        ("café — naïve “quotes”", "café — naïve “quotes”"),
        ("", ""),
        ("\n\r\t", ""),
    ],
)
def test_clean(raw, expected):
    assert clean(raw) == expected


def test_clean_never_leaves_a_key_that_presses_enter():
    cleaned = clean("first\nsecond\r\nthird\rfourth")
    assert "\n" not in cleaned
    assert "\r" not in cleaned
