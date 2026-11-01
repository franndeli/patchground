"""Email delivery through the storefront's SMTP relay.

The relay is not reachable from developer machines, so this gateway writes each message to an
outbox file; production swaps in the real transport by configuration.
"""

from __future__ import annotations

import json
from pathlib import Path


class SmtpNotifier:
    def __init__(self, outbox: str | Path) -> None:
        self._outbox = Path(outbox)

    def send(self, to: str, subject: str, body: str) -> None:
        with self._outbox.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"to": to, "subject": subject, "body": body}) + "\n")
