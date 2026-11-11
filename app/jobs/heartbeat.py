from __future__ import annotations

import threading

from app.services.errors import OwnershipLostError


class OperationHeartbeat:
    """Each pulse opens its own short transaction with the same owner fence."""

    def __init__(self, sessions, lease, interval):
        self.sessions, self.lease, self.interval = sessions, lease, interval
        self.stopped = threading.Event()
        self.lost = threading.Event()
        self._thread = None

    def pulse(self):
        try:
            self.sessions.renew(self.lease)
        except Exception:
            self.lost.set()
            self.stopped.set()
            return False
        return True

    def check(self):
        if self.lost.is_set():
            raise OwnershipLostError("Ownership heartbeat failed; output will not be published")

    def _run(self):
        while not self.stopped.wait(self.interval):
            if not self.pulse():
                return

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="skillbridge-lease-heartbeat")
        self._thread.start()
        return self

    def __exit__(self, *args):
        self.stopped.set()
        self._thread.join(timeout=6)
