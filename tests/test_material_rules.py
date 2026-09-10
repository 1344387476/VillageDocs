from housebook.constants import BOOK_ORDER, MATERIALS


def test_material_12_is_excluded() -> None:
    assert "12" not in BOOK_ORDER
    assert all(material.code != "12" for material in MATERIALS)


def test_fixed_book_order() -> None:
    assert BOOK_ORDER == ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "13", "14")

