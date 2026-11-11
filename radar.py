
import json
import logging
import re
import unicodedata
from pathlib import Path

import yaml


# ==========================================================
# CONFIGURAÇÕES DO PROJETO
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent

CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"

CITIES_FILE = CONFIG_DIR / "cities.yml"
KEYWORDS_FILE = CONFIG_DIR / "keywords.yml"
SOURCES_FILE = CONFIG_DIR / "sources.yml"
OPPORTUNITIES_FILE = DATA_DIR / "opportunities.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S"
)

logger = logging.getLogger("RadarRadiologia")


# ==========================================================
# FUNÇÕES DE LEITURA
# ==========================================================

def load_yaml(file_path):
    """Carrega um arquivo YAML."""

    if not file_path.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {file_path}"
        )

    with file_path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file)

    if not isinstance(content, dict):
        raise ValueError(
            f"Configuração inválida ou vazia: {file_path}"
        )

    return content


def load_json(file_path):
    """Carrega o banco de oportunidades."""

    if not file_path.exists():
        logger.warning(
            "Banco de oportunidades não encontrado. Criando estrutura inicial."
        )

        return {
            "opportunities": [],
            "last_update": None,
            "total_found": 0
        }

    with file_path.open("r", encoding="utf-8") as file:
        content = json.load(file)

    if not isinstance(content, dict):
        raise ValueError("O banco de oportunidades precisa ser um objeto JSON.")

    content.setdefault("opportunities", [])
    content.setdefault("last_update", None)
    content.setdefault("total_found", 0)

    return content


# ==========================================================
# NORMALIZAÇÃO DE TEXTOS
# ==========================================================

def normalize_text(value):
    """
    Remove acentos, converte para minúsculas
    e normaliza espaços.
    """

    if value is None:
        return ""

    text = str(value).strip().lower()

    text = unicodedata.normalize("NFD", text)

    text = "".join(
        character
        for character in text
        if unicodedata.category(character) != "Mn"
    )

    text = re.sub(r"\s+", " ", text)

    return text


# ==========================================================
# CARREGAMENTO DAS CONFIGURAÇÕES
# ==========================================================

def load_project_config():
    """Carrega todas as configurações do Radar."""

    logger.info("Carregando configurações...")

    cities = load_yaml(CITIES_FILE)
    keywords = load_yaml(KEYWORDS_FILE)
    sources = load_yaml(SOURCES_FILE)
    database = load_json(OPPORTUNITIES_FILE)

    return {
        "cities": cities,
        "keywords": keywords,
        "sources": sources,
        "database": database
    }


# ==========================================================
# VALIDAÇÃO DAS CONFIGURAÇÕES
# ==========================================================

def validate_config(config):
    """Verifica se os dados essenciais estão disponíveis."""

    errors = []

    cities = config["cities"].get("cities", [])
    sources = config["sources"].get("sources", [])
    keywords = config["keywords"].get("keywords", {})

    if not cities:
        errors.append("Nenhuma cidade cadastrada.")

    if not sources:
        errors.append("Nenhuma fonte cadastrada.")

    if not keywords.get("exact_match"):
        errors.append("Nenhuma palavra-chave de correspondência exata.")

    if not isinstance(config["database"].get("opportunities"), list):
        errors.append("O banco de oportunidades está em formato inválido.")

    for source in sources:
        if not source.get("name"):
            errors.append("Existe uma fonte sem nome.")

        if not source.get("url"):
            errors.append(
                f"Existe uma fonte sem endereço: {source.get('name', 'desconhecida')}"
            )

    if errors:
        for error in errors:
            logger.error(error)

        return False

    return True


# ==========================================================
# RESUMO DO RADAR
# ==========================================================

def show_summary(config):
    """Exibe um resumo das configurações carregadas."""

    cities = config["cities"].get("cities", [])
    sources = config["sources"].get("sources", [])
    keywords = config["keywords"].get("keywords", {})
    database = config["database"]

    enabled_sources = [
        source for source in sources
        if source.get("enabled", True)
    ]

    public_sources = [
        source for source in enabled_sources
        if source.get("category") in (
            "concurso",
            "processo_seletivo"
        )
    ]

    employment_sources = [
        source for source in enabled_sources
        if source.get("category") == "emprego"
    ]

    exact_terms = keywords.get("exact_match", [])
    related_terms = keywords.get("related_match", [])

    print()
    print("=" * 55)
    print("             RADAR RADIOLOGIA")
    print("=" * 55)

    print(f"Cidades monitoradas: {len(cities)}")
    print(f"Fontes cadastradas: {len(sources)}")
    print(f"Fontes habilitadas: {len(enabled_sources)}")

    print(f"Fontes públicas: {len(public_sources)}")
    print(f"Fontes de emprego: {len(employment_sources)}")

    print(f"Termos exatos: {len(exact_terms)}")
    print(f"Termos relacionados: {len(related_terms)}")

    print(
        "Oportunidades no banco: "
        f"{len(database.get('opportunities', []))}"
    )

    print("=" * 55)
    print("Configurações carregadas com sucesso.")
    print("Modo atual: validação, sem coleta ou notificações.")
    print("=" * 55)
    print()


# ==========================================================
# EXECUÇÃO
# ==========================================================

def main():

    logger.info("Iniciando Radar Radiologia...")

    try:
        config = load_project_config()

        if not validate_config(config):
            logger.error("Existem problemas nas configurações.")
            return

        show_summary(config)

        logger.info("Inicialização concluída.")

    except Exception as error:
        logger.exception(
            "Falha ao iniciar o Radar: %s",
            error
        )


if __name__ == "__main__":
    main()
