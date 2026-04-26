"""
Confirmation Gate — thread-safe asyncio gate for run_command user approval.

When run_command needs user confirmation, it calls gate.request(command).
The executor detects the sentinel, yields a command_confirmation_required event,
then awaits gate.wait_for_decision(). The CLI handles the event, prompts the
user (without blocking the event loop), and calls gate.approve() or gate.deny().
The gate signals, the executor resumes, and execution continues.

The session timeout is PAUSED while waiting for confirmation — user think time
should not count against the 10-minute query limit.
"""

import asyncio
from typing import Optional


class ConfirmationGate:
    """
    Asyncio event gate for CLI-level command confirmation.

    Thread-safe between the event loop and Rich's console.input()
    which runs in a thread pool executor.
    """

    def __init__(self) -> None:
        self._event: Optional[asyncio.Event] = None
        self._approved: bool = False
        self._pending_command: Optional[str] = None

    def request(self, command: str) -> None:
        """
        Mark a command as pending confirmation.

        Called by run_command BEFORE returning the sentinel dict.
        Creates a new asyncio.Event on the running event loop.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._event = asyncio.Event()
            else:
                self._event = None  # No loop — gate is a no-op
        except RuntimeError:
            self._event = None
        self._approved = False
        self._pending_command = command

    async def wait_for_decision(self) -> bool:
        """
        Wait indefinitely until approve() or deny() is called.

        Returns True if approved, False if denied.
        Called by execute_stream() after yielding command_confirmation_required.
        """
        if self._event is None:
            # No event loop at request time — auto-approve (shouldn't happen in prod)
            return True
        await self._event.wait()
        return self._approved

    def approve(self) -> None:
        """Signal approval. Called by CLI after user types 'y'."""
        self._approved = True
        if self._event:
            self._event.set()

    def deny(self) -> None:
        """Signal denial. Called by CLI after user types 'n'."""
        self._approved = False
        if self._event:
            self._event.set()

    def reset(self) -> None:
        """
        Clear all state from the previous query.

        Call this at the start of each new query in REPL mode.
        If a previous query ended abnormally while the gate was pending
        (e.g. Ctrl-C), the stale _event is never .set() and any code that
        was await-ing it is leaked. reset() ensures the next query starts
        from a clean slate.
        """
        if self._event and not self._event.is_set():
            # Unblock any leaked awaiter with a deny so it exits cleanly
            self._approved = False
            self._event.set()
        self._event = None
        self._approved = False
        self._pending_command = None

    @property
    def pending_command(self) -> Optional[str]:
        return self._pending_command


# Module-level singleton — shared between run_command (tool) and execute_stream (executor)
_gate = ConfirmationGate()


def get_confirmation_gate() -> ConfirmationGate:
    """Get the module-level singleton gate."""
    return _gate
