from aw_bot.lead import _clean_address


def test_hash_removed_from_unit():
    assert _clean_address("# A") == "A"
    assert _clean_address("#5") == "5"
    assert _clean_address("Apt #12") == "Apt 12"


def test_street_hash_removed():
    assert _clean_address("123 Main St #4") == "123 Main St 4"


def test_plain_values_unchanged():
    assert _clean_address("Apt 3") == "Apt 3"
    assert _clean_address("") == ""
    assert _clean_address(None) == ""
