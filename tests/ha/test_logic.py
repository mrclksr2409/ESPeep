"""Pure helpers: barcode validation, name cleanup, API response parsing."""

import pytest

from custom_components.espeep.logic import (
    clean_name,
    compose_label,
    node_action_name,
    normalize_ean,
    parse_off_product,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3017620422003", "3017620422003"),
        ("5449000000996\r\n", "5449000000996"),
        (" 96385074 ", "96385074"),
        ("036000291452", "036000291452"),
        ("10036000291459", "10036000291459"),
        ("5449000000986", None),  # one digit corrupted
        ("5449000009096", None),  # transposed digits
        ("12345", None),
        ("", None),
        ("https://example.com", None),
        ("٣٠١٧٦٢٠٤٢٢٠٠٣", None),  # non-ASCII digits are not barcode digits
    ],
)
def test_normalize_ean(raw, expected):
    assert normalize_ean(raw) == expected


def test_clean_name():
    assert clean_name("  Milch\n 1,5 %\t") == "Milch 1,5 %"
    assert clean_name(None) == ""
    assert len(clean_name("x" * 500)) == 100


@pytest.mark.parametrize(
    ("name", "brand", "include", "expected"),
    [
        ("Nutella", "Ferrero", True, "Ferrero Nutella"),
        ("Nutella", "Ferrero", False, "Nutella"),
        ("Ferrero Nutella", "Ferrero", True, "Ferrero Nutella"),
        ("Milch", "", True, "Milch"),
    ],
)
def test_compose_label(name, brand, include, expected):
    assert compose_label(name, brand, include) == expected


def test_parse_off_product_prefers_language():
    payload = {
        "product": {
            "product_name": "Hazelnut spread",
            "product_name_de": "Nuss-Nougat-Creme",
            "brands": "Ferrero, Nutella",
            "quantity": "450 g",
        },
        "status": 1,
    }
    info = parse_off_product(payload, "de", "Open Food Facts")
    assert info is not None
    assert info.name == "Nuss-Nougat-Creme"
    assert info.brand == "Ferrero"
    assert info.quantity == "450 g"
    assert info.database == "Open Food Facts"


@pytest.mark.parametrize(
    "payload",
    [
        {"status": 0},
        {"product": {"product_name": ""}},
        {"product": None},
        [],
    ],
)
def test_parse_off_product_without_name(payload):
    assert parse_off_product(payload, "de") is None


def test_node_action_name():
    assert (
        node_action_name("espeep-kueche", "show_result") == "espeep_kueche_show_result"
    )
