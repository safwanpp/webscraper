from scraper.enrich import clean_email, decode_cfemail, parse_page


def encode_cfemail(email: str, key: int = 0x42) -> str:
    return f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in email)


PAGE = f"""
<html><head>
  <meta name="viewport" content="width=device-width">
  <meta property="og:site_name" content="Smile Dental Clinic">
  <script>var x = "tracking@sentry.io 9876543210";</script>
</head><body>
  <a href="mailto:Info@SmileDental.in?subject=hi">Email</a>
  <a href="tel:+91-98765-43210">Call</a>
  <a href="https://wa.me/919812345678">WhatsApp</a>
  <a href="https://www.instagram.com/smiledental/?hl=en">IG</a>
  <a href="/contact-us">Contact</a>
  <a href="https://other.com/about">Other about</a>
  <a href="/cdn-cgi/l/email-protection#{encode_cfemail('appointments@smiledental.in')}">x</a>
  <span data-cfemail="{encode_cfemail('dr.shah@gmail.com')}"></span>
  <p>Landline: 022 2345 6789. Write to hello@smiledental.in.</p>
  <img src="logo@2x.png">
</body></html>
"""


def test_parse_page_extracts_contacts():
    info = parse_page(PAGE, "https://smiledental.in/")
    assert set(info.emails) == {
        "info@smiledental.in", "appointments@smiledental.in",
        "dr.shah@gmail.com", "hello@smiledental.in",
    }
    assert info.emails[-1] == "dr.shah@gmail.com"  # own-domain emails sorted first
    assert info.phones == ["+919876543210", "+912223456789"]
    assert info.whatsapp == "+919812345678"
    assert info.socials == ["https://www.instagram.com/smiledental"]
    assert info.contact_links == ["https://smiledental.in/contact-us"]
    assert info.mobile_friendly is True
    assert info.site_name == "Smile Dental Clinic"


def test_script_contents_ignored():
    info = parse_page(PAGE, "https://smiledental.in/")
    assert not any("sentry" in e for e in info.emails)


def test_decode_cfemail_roundtrip():
    assert decode_cfemail(encode_cfemail("a.b@c.in")) == "a.b@c.in"
    assert decode_cfemail("zz") == ""


def test_clean_email_rejects_junk():
    assert clean_email("logo@2x.png") == ""
    assert clean_email("user@example.com") == ""
    assert clean_email("noreply@gmail.com") == ""
    assert clean_email("support@envato.com") == ""
    assert clean_email("Sales@Shop.in.") == "sales@shop.in"
