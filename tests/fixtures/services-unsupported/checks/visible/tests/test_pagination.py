import pytest

from catalog.pagination import PageOutOfRange, paginate

LAMPS = [f"lamp-{i}" for i in range(40)]


def test_first_page_has_per_page_items():
    page = paginate(LAMPS, page=1, per_page=10)
    assert page.items == LAMPS[:10]
    assert page.number == 1
    assert page.has_previous is False
    assert page.has_next is True


def test_exact_multiple_has_expected_page_count():
    page = paginate(LAMPS, page=4, per_page=10)
    assert page.items == LAMPS[30:]
    assert page.total_pages == 4
    assert page.has_next is False


def test_empty_results_are_one_empty_page():
    page = paginate([], page=1, per_page=10)
    assert page.items == []
    assert page.total_pages == 1
    assert page.has_next is False


def test_page_zero_is_out_of_range():
    with pytest.raises(PageOutOfRange):
        paginate(LAMPS, page=0, per_page=10)


def test_per_page_must_be_positive():
    with pytest.raises(ValueError):
        paginate(LAMPS, page=1, per_page=0)
