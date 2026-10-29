import pytest

from catalog.pagination import PageOutOfRange, paginate

CHAIRS = [f"chair-{i}" for i in range(20)]


def test_page_past_the_end_is_out_of_range():
    with pytest.raises(PageOutOfRange):
        paginate(CHAIRS, page=3, per_page=10)


def test_last_page_of_exact_multiple():
    page = paginate(CHAIRS, page=2, per_page=10)
    assert page.items == CHAIRS[10:]
    assert page.has_next is False
