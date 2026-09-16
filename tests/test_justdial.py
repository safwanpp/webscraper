from pathlib import Path

from scraper.justdial import BASE_URL, parse_listing, search_url

FIXTURE = Path(__file__).parent / "fixtures" / "jd_list.html"


def test_search_url():
    assert search_url("dentists", "Mumbai") == f"{BASE_URL}/Mumbai/Dentists"
    assert search_url(" interior designers ", "navi mumbai") == f"{BASE_URL}/Navi-Mumbai/Interior-Designers"


def test_parse_listing_from_real_page():
    leads, next_url = parse_listing(FIXTURE.read_text(encoding="utf-8"))
    assert len(leads) == 10
    first = leads[0]
    assert first.name == "Ranjan Gupta Dental Clinic"
    assert first.sources == ["justdial"]
    assert first.rating == 4.0
    assert first.reviews == 6
    assert first.address == "Sakinaka, Mumbai, 400072"
    assert first.listing_url.startswith(f"{BASE_URL}/Mumbai/Ranjan-Gupta-Dental-Clinic-Sakinaka/")
    assert "?" not in first.listing_url
    assert leads[1].address.startswith("Shop No 1, Patel Apartment")
    assert next_url == f"{BASE_URL}/Mumbai/Dentists/nct-10156331/page-2"


def test_parse_listing_empty_page():
    assert parse_listing("<html><title>Access Denied</title></html>") == ([], None)
