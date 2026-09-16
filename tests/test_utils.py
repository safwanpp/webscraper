from scraper.utils import find_phones, host_of, is_social, normalize_phone, parse_float, parse_int


def test_normalize_phone_indian_mobile_formats():
    assert normalize_phone("098765 43210") == "+919876543210"
    assert normalize_phone("+91-98765-43210") == "+919876543210"
    assert normalize_phone("9876543210") == "+919876543210"


def test_normalize_phone_rejects_garbage():
    assert normalize_phone("") == ""
    assert normalize_phone("Show Number") == ""
    assert normalize_phone("12345") == ""
    assert normalize_phone("+61 3 8376 6284") == ""  # foreign (theme demo) number


def test_find_phones_skips_foreign_numbers():
    assert find_phones("Demo: +61 3 8376 6284. Real: 98765 43210") == ["+919876543210"]


def test_find_phones_in_text():
    text = "Call us at +91 98765 43210 or 022 2345 6789. Est. 1998."
    assert find_phones(text) == ["+919876543210", "+912223456789"]


def test_host_of():
    assert host_of("https://www.Smile-Dental.in/contact") == "smile-dental.in"
    assert host_of("smiledental.in") == "smiledental.in"
    assert host_of("") == ""


def test_is_social():
    assert is_social("https://www.instagram.com/smiledental")
    assert is_social("https://m.facebook.com/page")
    assert not is_social("https://notfacebook.com.in/")


def test_parse_numbers():
    assert parse_int("(1,234)") == 1234
    assert parse_int("") is None
    assert parse_float("4.6 stars") == 4.6
    assert parse_float("none") is None
