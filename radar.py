import hashlib
import json
import logging
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from collectors.fascamp import collect as collect_fascamp
from collectors.web_sources import collect_source, collect_bing
from telegram_bot import send_notification

BASE = Path(__file__).resolve().parent
TZ = ZoneInfo("America/Sao_Paulo")
DATA = BASE / "data" / "opportunities.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("Radar")


def norm(value):
    value = str(value or "").lower().strip()
    value = unicodedata.normalize("NFD", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", value)


def load_yaml(path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings():
    cities = load_yaml(BASE / "config/cities.yml").get("cities", [])
    kw = load_yaml(BASE / "config/keywords.yml").get("keywords", {})
    src = load_yaml(BASE / "config/sources.yml")
    return {
        "cities": cities,
        "terms": list(dict.fromkeys(kw.get("exact_match", []) + kw.get("related_match", []))),
        "keywords": kw,
        "sources": src.get("sources", []),
        "search": src.get("search", {})
    }


def fingerprint(item):
    raw = "|".join(norm(item.get(k)) for k in ["source", "title", "city", "application_url"])
    return hashlib.sha256(raw.encode()).hexdigest()


def excluded(item, kw):
    title = norm(item.get("title"))
    body = norm(" ".join(item.get("matched_terms", [])))
    for phrase in kw.get("service_exclusions", []):
        if norm(phrase) in title or norm(phrase) in body:
            return True
    higher = [norm(x) for x in kw.get("excluded_when_exclusive", [])]
    if any(x in title for x in higher):
        return True
    return False


def collect_all(settings):
    all_items, runs = [], []
    try:
        items = collect_fascamp(settings)
        all_items.extend(items)
        runs.append({"source": "FASCAMP", "status": "success", "candidates": len(items)})
    except Exception as exc:
        log.exception("FASCAMP falhou: %s", exc)
        runs.append({"source": "FASCAMP", "status": "error", "error": str(exc)})

    for source in settings["sources"]:
        if not source.get("enabled", True) or source["name"] == "FASCAMP":
            continue
        try:
            items = collect_source(source, settings)
            all_items.extend(items)
            runs.append({"source": source["name"], "status": "success", "candidates": len(items)})
            log.info("%s: %s candidatas", source["name"], len(items))
        except Exception as exc:
            log.exception("%s falhou: %s", source["name"], exc)
            runs.append({"source": source["name"], "status": "error", "error": str(exc)})

    try:
        items = collect_bing(settings, settings["search"])
        all_items.extend(items)
        runs.append({"source": "Bing RSS", "status": "success", "candidates": len(items)})
    except Exception as exc:
        log.exception("Bing RSS falhou: %s", exc)
    return all_items, runs


def run():
    settings = load_settings()
    if DATA.exists():
        try:
            previous = json.loads(DATA.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
    else:
        previous = {}

    old_items = previous.get("opportunities", [])
    merged = {x.get("fingerprint") or fingerprint(x): x for x in old_items}
    now = datetime.now(TZ).isoformat()
    collected, runs = collect_all(settings)
    new_count = 0

    for item in collected:
        if excluded(item, settings["keywords"]):
            continue
        key = fingerprint(item)
        item["fingerprint"] = key
        item["first_seen"] = merged.get(key, {}).get("first_seen", now)
        item["last_seen"] = now
        old = merged.get(key, {})
        item["notified"] = old.get("notified", False)
        item["notified_at"] = old.get("notified_at")
        if old.get("status") == "approved":
            item["status"] = "approved"
        if key not in merged:
            new_count += 1
        merged[key] = item

    sent = 0
    for item in merged.values():
        eligible = (
            item.get("verification_status") == "verified"
            and item.get("deadline_status") != "expired"
            and item.get("status") != "pending_review"
            and not item.get("notified", False)
        )
        if eligible and send_notification(item):
            item["notified"] = True
            item["notified_at"] = now
            sent += 1

    opportunities = sorted(merged.values(), key=lambda x: x.get("first_seen", ""), reverse=True)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "last_update": now,
        "total_found": len(opportunities),
        "new_candidates_this_run": new_count,
        "notifications_sent": sent,
        "source_runs": runs,
        "opportunities": opportunities
    }
    DATA.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Radar concluído | novas: %s | acumuladas: %s | notificações: %s",
             new_count, len(opportunities), sent)


if __name__ == "__main__":
    run()

