from __future__ import annotations

import multiprocessing
import os
import signal
from collections.abc import Callable
from typing import Any


class ProcessExecutionError(RuntimeError):
    pass


class ProcessExecutionTimeout(TimeoutError):
    pass


def _process_entry(connection, target: Callable, args: tuple, kwargs: dict) -> None:
    if os.name == "posix":
        os.setsid()

    try:
        connection.send(("ok", target(*args, **kwargs)))
    except BaseException as exc:
        connection.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        connection.close()


def _terminate_process_tree(process, cleanup_timeout: float) -> None:
    if not process.is_alive():
        process.join(timeout=cleanup_timeout)
        return

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            if process.is_alive():
                process.terminate()
    else:
        process.terminate()

    process.join(timeout=cleanup_timeout)
    if not process.is_alive():
        return

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            if process.is_alive():
                process.kill()
    else:
        process.kill()
    process.join(timeout=cleanup_timeout)


def run_in_process(
    target: Callable,
    *args: Any,
    timeout: float,
    cleanup_timeout: float = 5.0,
    **kwargs: Any,
) -> Any:
    """Run a callable with a wall-clock timeout that can kill child processes."""
    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_process_entry,
        args=(send_connection, target, args, kwargs),
    )
    process.start()
    send_connection.close()

    try:
        if not receive_connection.poll(timeout):
            _terminate_process_tree(process, cleanup_timeout)
            raise ProcessExecutionTimeout(
                f"process exceeded wall-clock timeout of {timeout:.1f}s"
            )

        try:
            status, payload = receive_connection.recv()
        except EOFError as exc:
            raise ProcessExecutionError(
                f"process exited without a result (exit code {process.exitcode})"
            ) from exc

        process.join(timeout=cleanup_timeout)
        if process.is_alive():
            _terminate_process_tree(process, cleanup_timeout)

        if status == "error":
            raise ProcessExecutionError(payload)
        return payload
    finally:
        receive_connection.close()
        if process.is_alive():
            _terminate_process_tree(process, cleanup_timeout)
