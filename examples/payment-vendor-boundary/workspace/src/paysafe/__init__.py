"""Paysafe Python SDK 2.x (vendored). Third-party code: do not edit; upgrade by replacing it.

Response codes: "00" approved, "05" do not honour, "51" insufficient funds,
"91" issuer unavailable. Other codes may appear in future versions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Transport = Callable[[dict[str, Any]], dict[str, Any]]


class PsTimeout(Exception):
    """The gateway did not answer in time. The charge may or may not have happened."""


@dataclass(frozen=True)
class PsResponse:
    txn_ref: str
    amt_minor: int
    ccy: str
    rc: str
    ts_ms: int


class PaysafeClient:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def charge(self, merchant_ref: str, amt_minor: int, ccy: str) -> PsResponse:
        try:
            raw = self._transport({"op": "sale", "merchant_ref": merchant_ref, "amt_minor": amt_minor, "ccy": ccy})
        except TimeoutError as error:
            raise PsTimeout(str(error)) from error
        return PsResponse(raw["txn_ref"], raw["amt_minor"], raw["ccy"], raw["rc"], raw["ts_ms"])
