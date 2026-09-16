from pathlib import Path

from scraper.maps import parse_place, parse_place_links

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_place_links_from_real_feed():
    links = parse_place_links((FIXTURES / "maps_list.html").read_text(encoding="utf-8"))
    assert len(links) == 7
    assert all("/maps/place/" in link for link in links)
    assert "SmyleXL" in links[0]


def test_parse_place_from_real_page():
    url = "https://www.google.com/maps/place/SmyleXL+Dental+Clinic+Mumbai+Central/data=!4m7?hl=en"
    lead = parse_place((FIXTURES / "maps_place.html").read_text(encoding="utf-8"), url)
    assert lead is not None
    assert lead.name == "SmyleXL Dental Clinic Mumbai Central"
    assert lead.sources == ["maps"]
    assert lead.phone == "+917420963040"
    assert lead.website == "https://smylexl.com/dental-clinic-in-mumbai-central/"
    assert lead.rating == 4.9
    assert lead.reviews == 510
    assert lead.category == "Dental clinic"
    assert lead.address.startswith("Anand Rao, C-01")
    assert lead.listing_url == url.split("?")[0]


def test_parse_place_without_title_returns_none():
    assert parse_place("<html><body></body></html>", "u") is None


def test_social_link_is_not_treated_as_website():
    html = """<h1 class="DUwDvf">Cafe</h1>
    <a data-item-id="authority" href="https://www.instagram.com/cafe">IG</a>"""
    lead = parse_place(html, "u")
    assert lead.website == ""
    assert lead.socials == ["https://www.instagram.com/cafe"]


def test_website_tracking_params_stripped():
    html = """<h1 class="DUwDvf">Clinic</h1>
    <a data-item-id="authority" href="https://clinic.in/?utm_source=gmb">Site</a>"""
    assert parse_place(html, "u").website == "https://clinic.in/"
