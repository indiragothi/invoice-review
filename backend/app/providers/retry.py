"""Retry with backoff and the one error type the rest of the app sees from the providers.

Pure and SDK-free, so it can be tested without a model. The SDK exceptions are translated into
`ProviderError` in `providers/__init__.py`; nothing outside `providers/` imports them.
"""

import time
from collections.abc import Callable, Sequence


class ProviderError(Exception):
    """A provider call failed after the retries. `busy` = worth trying again later."""

    def __init__(self, message: str, *, busy: bool) -> None:
        super().__init__(message)
        self.busy = busy


def retry_with_backoff[T](
    call: Callable[[], T],
    delays: Sequence[float],
    is_retryable: Callable[[Exception], bool],
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run `call`; on a retryable error wait `delays[0]`, `delays[1]`, ... and try again.

    So there are `len(delays) + 1` attempts. The last error is raised unchanged; an error that is
    not retryable is raised at once.
    """
    for delay in delays:
        try:
            return call()
        except Exception as error:
            if not is_retryable(error):
                raise
            sleep(delay)
    return call()
