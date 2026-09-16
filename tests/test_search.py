from pathlib import Path

from scraper.search import clean_title, is_blocked, parse_results

FIXTURE = Path(__file__).parent / "fixtures" / "ddg_lite.html"


def test_parse_results_from_real_page():
    results, next_form = parse_results(FIXTURE.read_text(encoding="utf-8"))
    assert len(results) == 10
    title, url = results[0]
    assert url == "https://www.practo.com/mumbai/dentist"
    assert "Practo" in title
    assert next_form is not None
    assert next_form["q"] == "dentists in Mumbai"
    assert next_form["s"] == "10"
    assert next_form["vqd"]


def test_blocks_directories_and_listicles():
    assert is_blocked("https://www.practo.com/mumbai/dentist")
    assert is_blocked("https://m.justdial.com/Mumbai/x")
    assert is_blocked("https://someblog.in/x", "Top 10 Dentists in Mumbai")
    assert is_blocked("/relative/link")
    assert is_blocked("https://bestmumbai.in/", "BestMumbai")
    assert is_blocked("https://www.top10dentists.com/")
    assert not is_blocked("https://smiledental.in/", "Smile Dental Clinic | Andheri")


def test_clean_title_picks_business_name():
    assert clean_title("Smile Dental Clinic | Best Dentist in Mumbai", "Mumbai") == "Smile Dental Clinic"
    assert clean_title("Best Dentist in Andheri - Smile Dental", "Mumbai") == "Smile Dental"
    assert clean_title("Home - Pearl Dental Care", "Mumbai") == "Pearl Dental Care"
    assert clean_title("Dentist in Mumbai", "Mumbai") == "Dentist in Mumbai"
