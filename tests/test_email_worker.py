import pytest

from app.email_worker import render_email


@pytest.mark.parametrize(
    ("template", "expected"),
    [("reset_password", "비밀번호 재설정")],
)
def test_render_email_contains_token_and_expiration(template, expected):
    subject, text, body = render_email(template, {"token": "test-token"})
    assert expected in subject
    assert "test-token" in text
    assert "test-token" in body
    assert "1시간 후 만료" in text
    assert '<html lang="ko">' in body


def test_render_email_rejects_unknown_template():
    with pytest.raises(ValueError):
        render_email("unknown", {"token": "test-token"})
