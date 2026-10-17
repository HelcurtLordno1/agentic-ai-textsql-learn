"""Elapsed-time safety bounds independent of wall-clock steps and NTP tick slew."""

import time


def monotonic_seconds() -> float:
    if hasattr(time, "CLOCK_MONOTONIC_RAW"):
        return time.clock_gettime(time.CLOCK_MONOTONIC_RAW)
    return time.monotonic()


def sleep_seconds(seconds: float) -> None:
    if seconds < 0:
        raise ValueError("Sleep duration must be nonnegative")
    deadline = monotonic_seconds() + seconds
    while (remaining := deadline - monotonic_seconds()) > 0:
        time.sleep(min(0.05, remaining))
