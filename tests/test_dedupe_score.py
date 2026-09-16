from scraper.dedupe import dedupe, same_business
from scraper.models import Lead
from scraper.score import passes_filters, score


def test_same_phone_merges():
    a = Lead("Smile Dental", sources=["maps"], phone="+919876543210", rating=4.5, reviews=120)
    b = Lead("Smile Dental Clinic Andheri", sources=["justdial"], phone="+919876543210", reviews=300)
    merged = dedupe([a, b])
    assert len(merged) == 1
    assert merged[0].sources == ["maps", "justdial"]
    assert merged[0].rating == 4.5
    assert merged[0].reviews == 300


def test_same_website_host_merges_but_shared_hosts_do_not():
    a = Lead("A", sources=["maps"], website="https://www.smiledental.in/")
    b = Lead("B", sources=["search"], website="https://smiledental.in/contact")
    assert same_business(a, b)
    c = Lead("C", website="https://sites.google.com/view/c")
    d = Lead("D", website="https://sites.google.com/view/d")
    assert not same_business(c, d)


def test_chain_branches_with_different_addresses_stay_separate():
    a = Lead("Apollo Clinic", address="Andheri West, Mumbai 400058")
    b = Lead("Apollo Clinic", address="Vashi Sector 17, Navi Mumbai 400703")
    assert not same_business(a, b)


def test_short_generic_names_do_not_merge():
    assert not same_business(Lead("Dental"), Lead("Dental Care Centre"))


def test_score_full_and_empty():
    full = Lead("X", phone="+919876543210", emails=["a@b.in"], socials=["ig"],
                website="https://x.in", rating=4.2, reviews=50)
    assert score(full) == 100
    assert score(Lead("Y")) == 0
    assert score(Lead("Z", phone="+919876543210", emails=["a@b.in"])) == 60


def test_filters():
    lead = Lead("X", phone="+919876543210", rating=3.9, reviews=10)
    assert passes_filters(lead, require_phone=True)
    assert not passes_filters(lead, require_email=True)
    assert not passes_filters(lead, min_rating=4.0)
    assert not passes_filters(lead, min_reviews=20)
    assert passes_filters(lead, no_website_only=True)
    assert not passes_filters(Lead("Y"), min_rating=4.0)
