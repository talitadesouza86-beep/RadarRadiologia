import logging
from urllib.parse import quote_plus

import feedparser
from bs4 import BeautifulSoup

from collectors.base import get_soup, page_text, links_from, make_record, matches

logger = logging.getLogger("WebSources")


def collect_source(source, settings):
    name, url = source["name"], source["url"]
    category = source.get("category", "emprego")
    try:
        soup = get_soup(url)
    except Exception as exc:
        logger.warning("%s indisponível: %s", name, exc)
        return []

    results = []
    for item in links_from(soup, url)[:220]:
        if not matches(item["title"], settings["terms"]):
            continue
        try:
            detail = get_soup(item["url"])
            record = make_record(name, item["title"], item["url"], page_text(detail),
                                 settings["terms"], settings["cities"], category)
            if record:
                # Agregadores são apenas pistas; revisão humana obrigatória.
                if source.get("source_type") != "official":
                    record["verification_status"] = "pending_review"
                    record["status"] = "pending_review"
                results.append(record)
        except Exception as exc:
            logger.debug("%s link falhou %s: %s", name, item["url"], exc)
    return results


def collect_bing(settings, search):
    if not search.get("bing_rss_enabled", False):
        return []
    results = []
    queries = search.get("queries", [])
    limit = int(search.get("max_results_per_query", 10))
    for city in settings["cities"]:
        for phrase in queries:
            q = f'{phrase} "{city}" SP'
            url = "https://www.bing.com/search?format=rss&q=" + quote_plus(q)
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:limit]:
                    title, link = entry.get("title", ""), entry.get("link", "")
                    summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True)
                    record = make_record("Pesquisa Bing RSS", title, link, summary,
                                         settings["terms"], [city], "emprego")
                    if record:
                        record["city"] = city
                        record["verification_status"] = "pending_review"
                        record["status"] = "pending_review"
                        results.append(record)
            except Exception as exc:
                logger.warning("Bing RSS falhou para %s: %s", q, exc)
    return results
