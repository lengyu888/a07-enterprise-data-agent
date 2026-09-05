import unittest

from app.core.retry import run_with_retry


class RetryTests(unittest.TestCase):
    def test_returns_after_transient_failures(self) -> None:
        calls = 0
        sleeps: list[float] = []

        def operation() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ConnectionError("database is starting")
            return "ready"

        result = run_with_retry(
            operation,
            attempts=4,
            delay_seconds=0.25,
            retryable_errors=(ConnectionError,),
            sleep=sleeps.append,
        )

        self.assertEqual(result, "ready")
        self.assertEqual(calls, 3)
        self.assertEqual(sleeps, [0.25, 0.25])

    def test_raises_last_error_after_bound(self) -> None:
        with self.assertRaisesRegex(ConnectionError, "still unavailable"):
            run_with_retry(
                lambda: (_ for _ in ()).throw(ConnectionError("still unavailable")),
                attempts=2,
                delay_seconds=0,
                retryable_errors=(ConnectionError,),
                sleep=lambda _: None,
            )

    def test_does_not_retry_non_retryable_errors(self) -> None:
        with self.assertRaises(ValueError):
            run_with_retry(
                lambda: (_ for _ in ()).throw(ValueError("bad migration")),
                attempts=3,
                delay_seconds=0,
                retryable_errors=(ConnectionError,),
                sleep=lambda _: None,
            )


if __name__ == "__main__":
    unittest.main()
