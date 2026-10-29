import pytest

from catalog.pagination import PageOutOfRange, paginate

CHAIRS = [f"chair-{i}" for i in range(25)]


def test_partial_last_page_is_reachable():
    page = paginate(CHAIRS, page=3, per_page=10)
    assert page.items == CHAIRS[20:]
    assert page.has_next is False


def test_total_pages_rounds_up():
    assert paginate(CHAIRS, page=1, per_page=10).total_pages == 3
    assert paginate(CHAIRS[:1], page=1, per_page=10).total_pages == 1
    assert paginate(CHAIRS[:11], page=1, per_page=10).total_pages == 2


def test_second_to_last_page_has_next():
    assert paginate(CHAIRS, page=2, per_page=10).has_next is True


def test_page_past_the_end_is_out_of_range():
    with pytest.raises(PageOutOfRange):
        paginate(CHAIRS, page=4, per_page=10)


def test_fewer_items_than_one_page():
    page = paginate(CHAIRS[:3], page=1, per_page=10)
    assert page.items == CHAIRS[:3]
    assert page.total_pages == 1
