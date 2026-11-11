import json
import logging
import re
import unicodedata

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
import yaml

from bs4 import BeautifulSoup
from pypdf import PdfReader


# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

BASE_DIR = Path(__file__).resolve().parents[1]

KEYWORDS_FILE = BASE_DIR / "config" / "keywords.yml"
CITIES_FILE = BASE_DIR / "config" / "cities.yml"

OUTPUT_FILE = BASE_DIR / "data" / "fascamp_candidates.json"

FASCAMP_URL = "https://fascamp.org.br/processos-seletivos/"

TIMEZONE = ZoneInfo("America/Sao_Paulo")

# Quantidade de páginas recentes da listagem que serão analisadas.
MAX_LISTING_PAGES = 8

# Quantidade máxima de PDFs consultados por edital.
MAX_PDFS_PER_ARTICLE = 3

# Tamanho máximo de cada PDF.
MAX_PDF_SIZE = 20 * 1024 * 1024

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; RadarRadiologia/2.0; "
        "+https://github.com/talitadesouza86-beep/RadarRadiologia)"
    )
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("FASCAMP")


# ==========================================================
# FUNÇÕES GERAIS
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


def fetch_binary(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=40
    )

    response.raise_for_status()

    if len(response.content) > MAX_PDF_SIZE:
        logger.warning("PDF ignorado por tamanho: %s", url)
        return None

    return response.content


# ==========================================================
# CONFIGURAÇÕES DE PESQUISA
# ==========================================================

def load_search_settings():
    keyword_config = load_yaml(KEYWORDS_FILE).get("keywords", {})
    city_config = load_yaml(CITIES_FILE)

    exact_terms = keyword_config.get("exact_match", [])
    related_terms = keyword_config.get("related_match", [])

    terms = list(dict.fromkeys(exact_terms + related_terms))

    return {
        "terms": [normalize(term) for term in terms if term],
        "cities": city_config.get("cities", [])
    }


def find_role_matches(text, terms):
    normalized_text = normalize(text)

    return [
        term for term in terms
        if term in normalized_text
    ]


# ==========================================================
# IDENTIFICAÇÃO DAS OPORTUNIDADES
# ==========================================================

def is_service_contract(title, text):
    normalized_title = normalize(title)
    normalized_text = normalize(text)

    title_exclusions = [
        "credenciamento",
        "pregao eletronico",
        "pregao presencial",
        "licitacao"
    ]

    if any(term in normalized_title for term in title_exclusions):
        return True

    exclusion_phrases = [
        "edital de credenciamento",
        "contratacao de empresa especializada",
        "contratacao de empresa para prestacao",
        "contratacao de servicos especializados",
        "prestacao de servicos por pessoa juridica",
        "fornecimento de mao de obra por empresa"
    ]

    return any(
        term in normalized_text
        for term in exclusion_phrases
    )


def is_cancelled(title, text):
    normalized_title = normalize(title)
    normalized_text = normalize(text)

    if "cancelado" in normalized_title:
        return True

    cancellation_phrases = [
        "processo seletivo cancelado",
        "edital de cancelamento do processo seletivo",
        "processo seletivo revogado"
    ]

    return any(
        phrase in normalized_text
        for phrase in cancellation_phrases
    )


def is_selection_process(text):
    normalized_text = normalize(text)

    indicators = [
        "processo seletivo",
        "selecao de curriculos",
        "contratacao de pessoal"
    ]

    return any(
        term in normalized_text
        for term in indicators
    )


# ==========================================================
# IDENTIFICAÇÃO DA CIDADE
# ==========================================================

def identify_city(title, text, cities):
    normalized_title = normalize(title)

    # Primeiro verifica o título, que costuma indicar a unidade.
    for city in cities:
        if normalize(city) in normalized_title:
            return city

    normalized_text = normalize(text)

    # Procura a cidade próxima de expressões de local de trabalho.
    location_indicators = [
        "local de trabalho",
        "local de atuacao",
        "lotacao",
        "unidade de trabalho",
        "hospital regional de",
        "ame ",
        "municipio de"
    ]

    for indicator in location_indicators:
        start = 0

        while True:
            position = normalized_text.find(indicator, start)

            if position == -1:
                break

            excerpt = normalized_text[
                position:position + 250
            ]

            for city in cities:
                if normalize(city) in excerpt:
                    return city

            start = position + len(indicator)

    return "Não identificada"


# ==========================================================
# DATAS DE INSCRIÇÃO
# ==========================================================

def extract_application_date(text):
    normalized_text = normalize(text)

    # Procura a seção de inscrições do edital.
    section_markers = [
        "das inscricoes",
        "periodo de inscricao",
        "periodo das inscricoes",
        "inscricoes:"
    ]

    section_position = -1

    for marker in section_markers:
        position = normalized_text.find(marker)

        if position != -1:
            section_position = position
            break

    if section_position == -1:
        return "Prazo não informado"

    section = normalized_text[
        section_position:section_position + 1800
    ]

    dates = re.findall(
        r"\b\d{2}/\d{2}/\d{4}\b",
        section
    )

    if len(dates) >= 2:
        return f"{dates[0]} a {dates[1]}"

    if len(dates) == 1:
        return f"Até {dates[0]}"

    return "Prazo não informado"


def check_deadline(application_date):
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
            datetime.strptime(
                value,
                "%d/%m/%Y"
            ).date()
            for value in dates
        ]
    except ValueError:
        return "review"

    today = datetime.now(TIMEZONE).date()

    # Para um intervalo, considera a data final.
    if len(parsed_dates) >= 2:
        start, end = parsed_dates[0], parsed_dates[1]

        if start > end:
            return "review"

        if end < today:
            return "expired"

        return "open"

    # Uma data isolada só é considerada vencida
    # quando o texto indica expressamente um prazo final.
    if application_date.lower().startswith("até"):
        if parsed_dates[0] < today:
            return "expired"

        return "open"

    return "review"


# ==========================================================
# EXTRAÇÃO DE TEXTO DOS EDITAIS
# ==========================================================

def extract_article_content(soup):
    # Remove elementos que não fazem parte do edital.
    for element in soup.select(
        "script, style, nav, footer, header, aside, form"
    ):
        element.decompose()

    selectors = [
        ".entry-content",
        ".post-content",
        ".article-content",
        "article",
        "main"
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if element:
            content = element.get_text(" ", strip=True)

            if len(content) > 200:
                return content

    return soup.get_text(" ", strip=True)


def collect_pdf_links(soup, article_url):
    links = []

    for anchor in soup.find_all("a", href=True):
        url = urljoin(
            article_url,
            anchor["href"]
        )

        normalized_url = normalize(url)

        if ".pdf" not in normalized_url:
            continue

        if urlparse(url).netloc not in (
            "fascamp.org.br",
            "www.fascamp.org.br"
        ):
            continue

        if url not in links:
            links.append(url)

    return links[:MAX_PDFS_PER_ARTICLE]


def extract_pdf_text(pdf_url):
    try:
        content = fetch_binary(pdf_url)

        if not content:
            return ""

        reader = PdfReader(BytesIO(content))

        pages_text = []

        for page in reader.pages:
            text = page.extract_text() or ""

            if text:
                pages_text.append(text)

        return " ".join(pages_text)

    except Exception as error:
        logger.warning(
            "Não foi possível ler o PDF %s: %s",
            pdf_url,
            error
        )

        return ""


# ==========================================================
# LEITURA DA LISTAGEM
# ==========================================================

def extract_listing_links(soup):
    results = {}

    selectors = [
        "article h2 a[href]",
        "article h3 a[href]",
        ".entry-title a[href]",
        "h2 a[href]",
        "h3 a[href]"
    ]

    anchors = []

    for selector in selectors:
        anchors.extend(soup.select(selector))

    # Plano alternativo para alterações no HTML do site.
    if not anchors:
        for anchor in soup.find_all("a", href=True):
            title = anchor.get_text(" ", strip=True)
            normalized_title = normalize(title)

            if (
                normalized_title.startswith("edital")
                or normalized_title.startswith("selecao de curriculos")
            ):
                anchors.append(anchor)

    for anchor in anchors:
        title = anchor.get_text(" ", strip=True)

        if not title:
            continue

        url = urljoin(
            FASCAMP_URL,
            anchor["href"]
        )

        parsed = urlparse(url)

        if parsed.netloc not in (
            "fascamp.org.br",
            "www.fascamp.org.br"
        ):
            continue

        if url.rstrip("/") == FASCAMP_URL.rstrip("/"):
            continue

        if "/page/" in parsed.path:
            continue

        results[url] = title

    return results


def collect_listing_pages():
    all_links = {}

    for page_number in range(1, MAX_LISTING_PAGES + 1):
        if page_number == 1:
            url = FASCAMP_URL
        else:
            url = urljoin(
                FASCAMP_URL,
                f"page/{page_number}/"
            )

        logger.info(
            "Consultando listagem %s de %s: %s",
            page_number,
            MAX_LISTING_PAGES,
            url
        )

        try:
            soup = fetch_page(url)

            links = extract_listing_links(soup)

            if not links:
                logger.info(
                    "Nenhum edital encontrado na página %s.",
                    page_number
                )

                break

            all_links.update(links)

            logger.info(
                "Editais identificados nesta página: %s",
                len(links)
            )

        except requests.RequestException as error:
            logger.error(
                "Erro ao consultar página %s: %s",
                page_number,
                error
            )

            # Não interrompe a coleta das páginas seguintes.
            continue

    return all_links


# ==========================================================
# ANÁLISE DE CADA EDITAL
# ==========================================================

def inspect_opportunity(url, title, settings):
    logger.info("Analisando edital: %s", title)

    soup = fetch_page(url)

    page_text = extract_article_content(soup)

    if is_service_contract(title, page_text):
        logger.info("Descartado: contratação de serviços.")
        return None

    if is_cancelled(title, page_text):
        logger.info("Descartado: processo cancelado.")
        return None

    if not is_selection_process(page_text):
        logger.info("Descartado: não é processo seletivo.")
        return None

    document_url = None

    role_matches = find_role_matches(
        page_text,
        settings["terms"]
    )

    # Se o conteúdo da página não identificar a função,
    # verifica os PDFs vinculados ao edital.
    if not role_matches:
        pdf_links = collect_pdf_links(
            soup,
            url
        )

        for pdf_url in pdf_links:
            logger.info(
                "Verificando documento PDF: %s",
                pdf_url
            )

            pdf_text = extract_pdf_text(pdf_url)

            if not pdf_text:
                continue

            pdf_matches = find_role_matches(
                pdf_text,
                settings["terms"]
            )

            if pdf_matches:
                role_matches = pdf_matches
                document_url = pdf_url
                page_text += " " + pdf_text
                break

    if not role_matches:
        logger.info(
            "Descartado: nenhuma função de Radiologia identificada."
        )

        return None

    application_date = extract_application_date(page_text)

    deadline_status = check_deadline(
        application_date
    )

    if deadline_status == "expired":
        logger.info("Descartado: prazo de inscrição encerrado.")
        return None

    city = identify_city(
        title,
        page_text,
        settings["cities"]
    )

    return {
        "source": "FASCAMP",
        "source_url": FASCAMP_URL,
        "title": title,
        "matched_terms": role_matches,
        "city": city,
        "state": "SP",
        "category": "processo_seletivo",
        "application_date": application_date,
        "application_url": url,
        "document_url": document_url,
        "deadline_status": deadline_status,
        "classification": "needs_review",
        "status": "pending_review",
        "collected_at": datetime.now(TIMEZONE).isoformat()
    }


# ==========================================================
# COLETA PRINCIPAL
# ==========================================================

def collect():
    settings = load_search_settings()

    logger.info("=" * 55)
    logger.info("INICIANDO COLETA FASCAMP")
    logger.info("=" * 55)

    listing_links = collect_listing_pages()

    logger.info(
        "Total de editais identificados nas listagens: %s",
        len(listing_links)
    )

    opportunities = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(
                inspect_opportunity,
                url,
                title,
                settings
            ): (url, title)
            for url, title in listing_links.items()
        }

        for future in as_completed(futures):
            url, title = futures[future]

            try:
                result = future.result()

                if result:
                    opportunities.append(result)

                    logger.info(
                        "OPORTUNIDADE IDENTIFICADA: %s",
                        title
                    )

            except requests.RequestException as error:
                logger.error(
                    "Erro ao acessar edital %s: %s",
                    title,
                    error
                )

            except Exception:
                logger.exception(
                    "Erro ao analisar edital: %s",
                    title
                )

    # Remove duplicidades por URL.
    unique_opportunities = {}

    for opportunity in opportunities:
        unique_opportunities[
            opportunity["application_url"]
        ] = opportunity

    return list(unique_opportunities.values())


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

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    logger.info("=" * 55)
    logger.info("COLETA FASCAMP CONCLUÍDA")
    logger.info("Total de candidatas: %s", len(opportunities))
    logger.info("Arquivo: %s", OUTPUT_FILE)
    logger.info("=" * 55)


if __name__ == "__main__":
    main()

