import time
import unittest

from core.process_timeout import (
    ProcessExecutionError,
    ProcessExecutionTimeout,
    run_in_process,
)


def return_value(value):
    return value


def sleep_for(seconds):
    time.sleep(seconds)


def raise_remote_error():
    raise ValueError("remote failure")


class ProcessTimeoutTest(unittest.TestCase):
    def test_returns_successful_result(self):
        self.assertEqual(run_in_process(return_value, "ok", timeout=2), "ok")

    def test_terminates_hung_process(self):
        started_at = time.monotonic()

        with self.assertRaises(ProcessExecutionTimeout):
            run_in_process(
                sleep_for,
                10,
                timeout=0.2,
                cleanup_timeout=0.5,
            )

        self.assertLess(time.monotonic() - started_at, 2)

    def test_surfaces_remote_exception(self):
        with self.assertRaisesRegex(ProcessExecutionError, "remote failure"):
            run_in_process(raise_remote_error, timeout=2)


if __name__ == "__main__":
    unittest.main()
