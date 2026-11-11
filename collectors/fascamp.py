import json
import logging
import re
import unicodedata

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests
import yaml

from bs4 import BeautifulSoup


# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

BASE_DIR = Path(__file__).resolve().parents[1]

KEYWORDS_FILE = BASE_DIR / "config" / "keywords.yml"
CITIES_FILE = BASE_DIR / "config" / "cities.yml"
OUTPUT_FILE = BASE_DIR / "data" / "fascamp_candidates.json"

FASCAMP_URL = "https://fascamp.org.br/processos-seletivos/"

TIMEZONE = ZoneInfo("America/Sao_Paulo")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; RadarRadiologia/1.0; "
        "+https://github.com/talitadesouza86-beep/RadarRadiologia)"
    )
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("FASCAMP")


# ==========================================================
# FUNÇÕES BÁSICAS
# ==========================================================

def normalize(text):
    text = str(text or "").lower().strip()

    text = unicodedata.normalize("NFD", text)

    text = "".join(
        char for char in text
        if unicodedata.category(char) != "Mn"
    )

    return re.sub(r"\s+", " ", text)


def load_yaml(path):
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def fetch_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


# ==========================================================
# CONFIGURAÇÕES DE BUSCA
# ==========================================================

def load_search_settings():
    keywords = load_yaml(KEYWORDS_FILE)
    cities = load_yaml(CITIES_FILE)

    keyword_config = keywords.get("keywords", {})

    terms = (
        keyword_config.get("exact_match", [])
        + keyword_config.get("related_match", [])
    )

    return {
        "terms": [normalize(term) for term in terms],
        "cities": cities.get("cities", [])
    }


def has_radiology_match(title, terms):
    normalized_title = normalize(title)

    return any(
        term in normalized_title
        for term in terms
    )


# ==========================================================
# FILTROS DE CONTRATAÇÃO
# ==========================================================

def is_service_contract(text):
    normalized = normalize(text)

    exclusion_terms = [
        "credenciamento",
        "contratacao de empresa",
        "empresa especializada",
        "contratacao de servicos",
        "prestacao de servicos",
        "pessoa juridica",
        "pessoa juridica especializada"
    ]

    return any(
        term in normalized
        for term in exclusion_terms
    )


def identify_city(text, cities):
    normalized_text = normalize(text)

    for city in cities:
        if normalize(city) in normalized_text:
            return city

    return "Não identificada"


# ==========================================================
# EXTRAÇÃO DE PRAZOS
# ==========================================================

def extract_application_date(text):
    normalized = normalize(text)

    patterns = [
        r"inscricoes.{0,100}?"
        r"(\d{2}/\d{2}/\d{4}\s*(?:a|ate|-)\s*\d{2}/\d{2}/\d{4})",

        r"prazo.{0,80}?"
        r"(\d{2}/\d{2}/\d{4}\s*(?:a|ate|-)\s*\d{2}/\d{2}/\d{4})",

        r"inscricoes.{0,100}?"
        r"(?:ate|até)\s*(\d{2}/\d{2}/\d{4})"
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized)

        if match:
            return match.group(1)

    return "Prazo não informado"


def check_deadline(application_date):
    """
    Retorna:
    - open: prazo futuro ou vigente identificado
    - expired: prazo encerrado identificado
    - review: prazo não identificado
    """

    if application_date == "Prazo não informado":
        return "review"

    dates = re.findall(
        r"\d{2}/\d{2}/\d{4}",
        application_date
    )

    if not dates:
        return "review"

    try:
        parsed_dates = [
            datetime.strptime(value, "%d/%m/%Y").date()
            for value in dates
        ]
    except ValueError:
        return "review"

    today = datetime.now(TIMEZONE).date()

    if len(parsed_dates) == 2:
        start, end = parsed_dates

        if end < today:
            return "expired"

        if start > end:
            return "review"

        return "open"

    deadline = parsed_dates[0]

    if deadline < today:
        return "expired"

    return "open"


# ==========================================================
# IDENTIFICAÇÃO DOS EDITAIS
# ==========================================================

def collect_listing_links(soup, terms):
    results = {}

    for anchor in soup.find_all("a", href=True):
        title = anchor.get_text(" ", strip=True)
        url = urljoin(FASCAMP_URL, anchor["href"])

        if not title or not url.startswith("https://"):
            continue

        if "fascamp.org.br" not in url:
            continue

        if not has_radiology_match(title, terms):
            continue

        if url.rstrip("/") == FASCAMP_URL.rstrip("/"):
            continue

        results[url] = title

    return results


def inspect_opportunity(url, title, settings):
    logger.info("Analisando: %s", title)

    soup = fetch_page(url)

    page_text = soup.get_text(" ", strip=True)

    if is_service_contract(page_text):
        logger.info("Descartado: contratação de serviços ou empresa.")
        return None

    normalized_page = normalize(page_text)

    if "processo seletivo" not in normalized_page:
        logger.info("Descartado: não foi identificado processo seletivo.")
        return None

    application_date = extract_application_date(page_text)

    deadline_status = check_deadline(application_date)

    if deadline_status == "expired":
        logger.info("Descartado: prazo encerrado.")
        return None

    city = identify_city(page_text, settings["cities"])

    classification = "needs_review"

    if city == "Não identificada":
        logger.info("Localidade não identificada. Exige revisão.")

    return {
        "source": "FASCAMP",
        "source_url": FASCAMP_URL,
        "title": title,
        "city": city,
        "state": "SP",
        "category": "processo_seletivo",
        "application_date": application_date,
        "application_url": url,
        "deadline_status": deadline_status,
        "classification": classification,
        "status": "pending_review",
        "collected_at": datetime.now(TIMEZONE).isoformat()
    }


# ==========================================================
# COLETA PRINCIPAL
# ==========================================================

def collect():
    settings = load_search_settings()

    logger.info("Consultando processos seletivos da FASCAMP...")

    soup = fetch_page(FASCAMP_URL)

    links = collect_listing_links(
        soup,
        settings["terms"]
    )

    logger.info(
        "Possíveis oportunidades encontradas: %s",
        len(links)
    )

    opportunities = []

    for url, title in links.items():
        try:
            result = inspect_opportunity(
                url,
                title,
                settings
            )

            if result:
                opportunities.append(result)

        except requests.RequestException as error:
            logger.error(
                "Erro ao acessar %s: %s",
                url,
                error
            )

        except Exception:
            logger.exception(
                "Erro ao analisar oportunidade: %s",
                title
            )

    return opportunities


# ==========================================================
# EXECUÇÃO
# ==========================================================

def main():
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    opportunities = collect()

    result = {
        "source": "FASCAMP",
        "last_update": datetime.now(TIMEZONE).isoformat(),
        "total_found": len(opportunities),
        "opportunities": opportunities
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    logger.info(
        "Coleta concluída. Candidatas encontradas: %s",
        len(opportunities)
    )

    logger.info(
        "Arquivo gerado: %s",
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()
