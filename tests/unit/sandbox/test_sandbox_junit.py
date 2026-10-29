from __future__ import annotations

import pytest

from patchground.sandbox import JUnitError, TestResult, TestStatus, parse_junit
from patchground.sandbox.run import RunOutcome, outcome_for

PYTEST_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
  <testsuite name="pytest" errors="1" failures="1" skipped="1" tests="4" time="0.1">
    <testcase classname="tests.test_app" name="test_ok" time="0.001" />
    <testcase classname="tests.test_app" name="test_bad" time="0.001">
      <failure message="assert 1 == 2">assert 1 == 2</failure>
    </testcase>
    <testcase classname="tests.test_app" name="test_broken" time="0.001">
      <error message="failed on setup with &quot;fixture 'x' not found&quot;">E</error>
    </testcase>
    <testcase classname="tests.test_app" name="test_later" time="0.000">
      <skipped type="pytest.skip" message="later">skip</skipped>
    </testcase>
  </testsuite>
</testsuites>
"""


def test_pytest_style_statuses() -> None:
    results = parse_junit(PYTEST_XML)
    assert [(r.id, r.status) for r in results] == [
        ("tests.test_app::test_ok", TestStatus.PASSED),
        ("tests.test_app::test_bad", TestStatus.FAILED),
        ("tests.test_app::test_broken", TestStatus.ERRORED),
        ("tests.test_app::test_later", TestStatus.SKIPPED),
    ]
    assert results[0] == TestResult(
        "tests.test_app::test_ok", "test_ok", "tests.test_app", TestStatus.PASSED
    )


def test_testsuite_root_and_missing_classname() -> None:
    xml = b'<testsuite><testcase name="alone"/><testcase classname="c" name="n"/></testsuite>'
    results = parse_junit(xml)
    assert [r.id for r in results] == ["alone", "c::n"]
    assert results[0].classname == ""


def test_nested_testsuites_are_included() -> None:
    xml = (
        b"<testsuites><testsuite name='outer'><testcase name='a'/>"
        b"<testsuite name='inner'><testcase name='b'><failure/></testcase></testsuite>"
        b"</testsuite></testsuites>"
    )
    results = parse_junit(xml)
    assert {r.id: r.status for r in results} == {"a": TestStatus.PASSED, "b": TestStatus.FAILED}


def test_error_wins_over_failure_and_skip() -> None:
    xml = b"<testsuite><testcase name='t'><skipped/><failure/><error/></testcase></testsuite>"
    assert parse_junit(xml)[0].status is TestStatus.ERRORED
    xml = b"<testsuite><testcase name='t'><skipped/><failure/></testcase></testsuite>"
    assert parse_junit(xml)[0].status is TestStatus.FAILED


def test_empty_suite_parses_to_no_tests() -> None:
    assert parse_junit(b"<testsuites/>") == ()


@pytest.mark.parametrize(
    "data",
    [b"", b"not xml at all", b"<testsuite><testcase>", b"<html><body/></html>", b"\xff\xfe\x00"],
)
def test_garbage_is_rejected(data: bytes) -> None:
    with pytest.raises(JUnitError):
        parse_junit(data)


BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
 <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
]>
<testsuite><testcase name="&lol4;"/></testsuite>
"""

XXE = b"""<?xml version="1.0"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<testsuite><testcase name="&xxe;"/></testsuite>
"""

DTD_ONLY = b"""<?xml version="1.0"?>
<!DOCTYPE testsuite SYSTEM "http://example.invalid/junit.dtd">
<testsuite><testcase name="t"/></testsuite>
"""


@pytest.mark.parametrize("data", [BILLION_LAUGHS, XXE, DTD_ONLY], ids=["laughs", "xxe", "dtd"])
def test_unsafe_xml_is_rejected(data: bytes) -> None:
    with pytest.raises(JUnitError):
        parse_junit(data)


def _t(status: TestStatus) -> TestResult:
    return TestResult(f"t_{status}", f"t_{status}", "", status)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([TestStatus.PASSED], RunOutcome.PASSED),
        ([TestStatus.PASSED, TestStatus.SKIPPED], RunOutcome.PASSED),
        ([TestStatus.SKIPPED], RunOutcome.PASSED),
        ([TestStatus.PASSED, TestStatus.FAILED], RunOutcome.FAILED),
        ([TestStatus.FAILED, TestStatus.ERRORED], RunOutcome.ERRORED),
    ],
)
def test_outcome_rules(statuses: list[TestStatus], expected: RunOutcome) -> None:
    outcome, note = outcome_for([_t(s) for s in statuses])
    assert outcome is expected
    assert note is None


def test_zero_tests_is_errored_with_note() -> None:
    outcome, note = outcome_for([])
    assert outcome is RunOutcome.ERRORED
    assert note is not None and "no test cases" in note
