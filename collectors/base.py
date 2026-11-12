import re
import unicodedata
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarRadiologia/3.0)"}
TIMEOUT = 25


def normalize(value):
    value = str(value or "").lower().strip()
    value = unicodedata.normalize("NFD", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", value)


def get_soup(url):
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def page_text(soup):
    clone = BeautifulSoup(str(soup), "html.parser")
    for tag in clone.select("script,style,nav,footer,header,aside,form,noscript"):
        tag.decompose()
    main = clone.select_one("main") or clone.select_one("article") or clone.body or clone
    return main.get_text(" ", strip=True)


def links_from(soup, base_url):
    items = []
    seen = set()
    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        url = a["href"]
        from urllib.parse import urljoin
        url = urljoin(base_url, url)
        if not title or len(title) < 3 or url in seen:
            continue
        if urlparse(url).scheme not in ("http", "https"):
            continue
        seen.add(url)
        items.append({"title": title[:250], "url": url})
    return items


def matches(text, terms):
    value = normalize(text)
    return [term for term in terms if normalize(term) in value]


def city_from(text, cities):
    value = normalize(text)
    for city in cities:
        if normalize(city) in value:
            return city
    return "Não identificada"


def dates_from(text):
    value = normalize(text)
    patterns = [
        r"(?:inscricoes|periodo de inscricao|prazo de inscricao)[^0-9]{0,100}(\d{2}/\d{2}/\d{4})\s*(?:a|ate|-|–)\s*(\d{2}/\d{2}/\d{4})",
        r"(?:inscricoes|periodo de inscricao|prazo de inscricao)[^0-9]{0,100}ate\s*(\d{2}/\d{2}/\d{4})"
    ]
    for pattern in patterns:
        found = re.search(pattern, value)
        if found:
            return (f"{found.group(1)} a {found.group(2)}" if len(found.groups()) == 2
                    else f"Até {found.group(1)}")
    return "Prazo não informado"


def explicitly_expired(text):
    value = normalize(text)
    return any(x in value for x in [
        "inscricoes encerradas", "prazo de inscricao encerrado",
        "periodo de inscricao encerrado", "processo seletivo encerrado",
        "processo seletivo cancelado", "edital cancelado"
    ])


def make_record(source, title, url, body, terms, cities, category):
    found = matches(title + " " + body, terms)
    if not found:
        return None
    deadline = dates_from(body)
    expired = explicitly_expired(body)
    city = city_from(title + " " + body, cities)
    needs_review = (
        city == "Não identificada"
        or deadline == "Prazo não informado"
        or expired
        or category == "emprego"
    )
    return {
        "source": source,
        "title": title[:300],
        "city": city,
        "state": "SP",
        "category": category,
        "application_date": deadline,
        "application_url": url,
        "document_url": None,
        "matched_terms": found,
        "deadline_status": "expired" if expired else ("review" if deadline == "Prazo não informado" else "open"),
        "verification_status": "pending_review" if needs_review else "verified",
        "status": "pending_review" if needs_review else "new",
        "collected_at": datetime.now().astimezone().isoformat()
    }
