import pytest

from app.providers.retry import ProviderError, retry_with_backoff


class Busy(Exception):
    pass


def flaky(failures: int):
    state = {"calls": 0}

    def call() -> str:
        state["calls"] += 1
        if state["calls"] <= failures:
            raise Busy("429")
        return "ok"

    return call, state


def test_returns_at_once_when_the_first_call_works():
    call, state = flaky(0)
    waits: list[float] = []
    assert retry_with_backoff(call, (1, 2), lambda e: True, waits.append) == "ok"
    assert state["calls"] == 1 and waits == []


def test_retries_with_the_given_waits_until_it_works():
    call, state = flaky(2)
    waits: list[float] = []
    assert (
        retry_with_backoff(call, (4, 12, 30), lambda e: isinstance(e, Busy), waits.append) == "ok"
    )
    assert state["calls"] == 3 and waits == [4, 12]


def test_gives_up_after_the_last_wait_and_raises_the_last_error():
    call, state = flaky(99)
    waits: list[float] = []
    with pytest.raises(Busy):
        retry_with_backoff(call, (1, 2), lambda e: True, waits.append)
    assert state["calls"] == 3 and waits == [1, 2]


def test_an_error_that_is_not_retryable_is_raised_without_waiting():
    call, state = flaky(99)
    waits: list[float] = []
    with pytest.raises(Busy):
        retry_with_backoff(call, (1, 2), lambda e: False, waits.append)
    assert state["calls"] == 1 and waits == []


def test_provider_error_remembers_whether_it_was_busy():
    assert ProviderError("later", busy=True).busy is True
    assert ProviderError("bad output", busy=False).busy is False
