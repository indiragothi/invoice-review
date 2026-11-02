from app.auth.session import is_valid_token, make_token, password_matches

SECRET = "a-long-test-secret"


def test_fresh_token_is_valid() -> None:
    assert is_valid_token(SECRET, make_token(SECRET, 60, now=1000), now=1030)


def test_expired_token_is_rejected() -> None:
    assert not is_valid_token(SECRET, make_token(SECRET, 60, now=1000), now=1061)


def test_token_signed_with_another_secret_is_rejected() -> None:
    assert not is_valid_token(SECRET, make_token("other-secret", 60, now=1000), now=1030)


def test_tampered_expiry_is_rejected() -> None:
    _, _, signature = make_token(SECRET, 60, now=1000).partition(".")
    assert not is_valid_token(SECRET, f"99999999999.{signature}", now=1030)


def test_garbage_tokens_are_rejected() -> None:
    for token in (None, "", "abc", "123.", ".abc", "x.y"):
        assert not is_valid_token(SECRET, token, now=1030)


def test_password_compare() -> None:
    assert password_matches("demo-pass", "demo-pass")
    assert not password_matches("demo-pass", "demo-pas")
    assert not password_matches("demo-pass", "")
