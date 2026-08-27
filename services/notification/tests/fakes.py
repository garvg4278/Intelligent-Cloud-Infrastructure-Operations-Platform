from app.sender import SenderError


class FakeSender:
    """Configure fail_times to make the first N send() calls raise, then
    succeed -- lets tests exercise "fails twice, succeeds on the third
    attempt" without any real delivery mechanism."""

    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.calls: list[tuple[str, str, str]] = []

    def send(self, target: str, subject: str, body: str) -> None:
        self.calls.append((target, subject, body))
        if len(self.calls) <= self.fail_times:
            raise SenderError(f"simulated failure #{len(self.calls)}")


def no_sleep(_seconds: float) -> None:
    """Drop-in replacement for time.sleep in tests -- retry logic runs
    the same code path, just without actually waiting through backoff."""
