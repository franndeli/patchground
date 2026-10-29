"""Exceptions raised by the verify module."""

from __future__ import annotations


class VerifyEnvironmentError(Exception):
    """The host cannot run validation (engine unreachable, git missing, engine failure).

    This is not a verdict on the challenge: no step failed, validation could not proceed.
    """
