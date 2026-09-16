from dataclasses import dataclass, field


@dataclass
class Lead:
    name: str
    sources: list[str] = field(default_factory=list)
    phone: str = ""
    extra_phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    whatsapp: str = ""
    socials: list[str] = field(default_factory=list)
    website: str = ""
    rating: float | None = None
    reviews: int | None = None
    address: str = ""
    category: str = ""
    listing_url: str = ""
    https: bool | None = None
    mobile_friendly: bool | None = None
    score: int = 0
