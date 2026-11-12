import logging
from io import BytesIO
from urllib.parse import urljoin, urlparse

import requests
from pypdf import PdfReader

from collectors.base import get_soup, page_text, links_from, make_record, normalize

logger = logging.getLogger("FASCAMP")
BASE = "https://fascamp.org.br/processos-seletivos/"
MAX_PAGES = 12


def read_pdf(url):
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        if len(response.content) > 20 * 1024 * 1024:
            return ""
        reader = PdfReader(BytesIO(response.content))
        return " ".join((p.extract_text() or "") for p in reader.pages)
    except Exception as exc:
        logger.warning("PDF não lido %s: %s", url, exc)
        return ""


def collect(settings):
    links = {}
    for page in range(1, MAX_PAGES + 1):
        url = BASE if page == 1 else urljoin(BASE, f"page/{page}/")
        try:
            soup = get_soup(url)
        except requests.RequestException as exc:
            logger.warning("FASCAMP listagem falhou %s: %s", url, exc)
            continue
        anchors = soup.select("article h2 a[href], article h3 a[href], .entry-title a[href], h2 a[href], h3 a[href]")
        if not anchors:
            anchors = [a for a in soup.find_all("a", href=True)
                       if normalize(a.get_text(" ", strip=True)).startswith(("edital", "selecao de curriculos"))]
        count = 0
        for a in anchors:
            title = a.get_text(" ", strip=True)
            link = urljoin(url, a["href"])
            if title and urlparse(link).netloc.endswith("fascamp.org.br"):
                links[link] = title
                count += 1
        logger.info("FASCAMP página %s: %s links", page, count)
        if page > 1 and count == 0:
            break

    logger.info("FASCAMP total de editais listados: %s", len(links))
    results = []
    for link, title in links.items():
        try:
            soup = get_soup(link)
            body = page_text(soup)
            pdfs = [x["url"] for x in links_from(soup, link) if ".pdf" in x["url"].lower()][:4]
            full_text = body
            for pdf in pdfs:
                full_text += " " + read_pdf(pdf)

            title_norm, body_norm = normalize(title), normalize(full_text)
            if "credenciamento" in title_norm or (
                "pessoa juridica" in body_norm and
                any(p in body_norm for p in ["contratacao de empresa", "prestacao de servicos"])
            ):
                logger.info("FASCAMP excluído: contratação empresarial: %s", title)
                continue
            record = make_record("FASCAMP", title, link, full_text,
                                 settings["terms"], settings["cities"], "processo_seletivo")
            if record:
                record["document_url"] = pdfs[0] if pdfs else None
                results.append(record)
                logger.info("FASCAMP candidata: %s", title)
        except Exception as exc:
            logger.warning("FASCAMP erro %s: %s", title, exc)
    return results
