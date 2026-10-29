"""JUnit XML parsing into per-test results.

The XML comes from inside a challenge container and is therefore untrusted: it is always parsed
with ``defusedxml`` (DTDs forbidden outright, which also rules out entity-expansion and XXE
payloads) and only then handed to ``junitparser`` for the JUnit structure.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from enum import StrEnum
from typing import IO
from xml.etree.ElementTree import ElementTree, ParseError

import defusedxml
import defusedxml.ElementTree
from junitparser import Error, Failure, JUnitXml, JUnitXmlError, Skipped

from patchground.sandbox.errors import JUnitError


class TestStatus(StrEnum):
    """Outcome of a single test case."""

    __test__ = False  # not a pytest test class

    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class TestResult:
    """One ``<testcase>``; ``id`` is ``classname::name`` (or ``name`` without a classname)."""

    __test__ = False  # not a pytest test class

    id: str
    name: str
    classname: str
    status: TestStatus


def _safe_parse(source: IO[bytes]) -> ElementTree:
    return defusedxml.ElementTree.parse(source, forbid_dtd=True)


def parse_junit(data: bytes) -> tuple[TestResult, ...]:
    """Parse a JUnit XML document (``<testsuites>`` or ``<testsuite>`` root).

    Status precedence inside one test case: error > failure > skipped > passed.
    Raises :class:`JUnitError` if the document is malformed, unsafe or not JUnit.
    """
    try:
        xml = JUnitXml.fromfile(io.BytesIO(data), parse_func=_safe_parse)
        results: list[TestResult] = []
        for suite in xml:
            for case in suite:
                name = str(case.name or "")
                classname = str(case.classname or "")
                outcomes = case.result
                if any(isinstance(r, Error) for r in outcomes):
                    status = TestStatus.ERRORED
                elif any(isinstance(r, Failure) for r in outcomes):
                    status = TestStatus.FAILED
                elif any(isinstance(r, Skipped) for r in outcomes):
                    status = TestStatus.SKIPPED
                else:
                    status = TestStatus.PASSED
                test_id = f"{classname}::{name}" if classname else name
                results.append(TestResult(test_id, name, classname, status))
    except (ParseError, defusedxml.DefusedXmlException, JUnitXmlError) as exc:
        raise JUnitError(f"invalid JUnit XML: {exc}") from exc
    return tuple(results)
