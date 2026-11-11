
import json
import logging
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


logger = logging.getLogger("RadarRadiologia.Telegram")


def get_chat_ids():
    """Retorna todos os IDs autorizados para receber notificações."""

    raw_ids = os.getenv("TELEGRAM_CHAT_IDS", "")

    return [
        chat_id.strip()
        for chat_id in raw_ids.split(",")
        if chat_id.strip()
    ]


def format_notification(opportunity):
    """Monta a mensagem no padrão oficial do Radar."""

    category = opportunity.get("category", "emprego")

    if category in ("concurso", "processo_seletivo"):
        header = "🩻 RADAR RADIOLOGIA"
    else:
        header = "💼 VAGA DE EMPREGO"

    title = opportunity.get("title", "Não informado")
    city = opportunity.get("city", "Não informado")
    state = opportunity.get("state", "SP")
    application_date = opportunity.get(
        "application_date",
        "Prazo não informado"
    )
    link = opportunity.get("application_url", "")

    if not link:
        raise ValueError("Oportunidade sem link direto de candidatura ou edital.")

    message = (
        f"{header}\n\n"
        f"Vaga: {title}\n"
        f"Local: {city} – {state}\n"
        f"Inscrições: {application_date}\n"
        f"🔗 {link}"
    )

    return message


def send_message(chat_id, message, token):
    """Envia uma mensagem para um usuário do Telegram."""

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = urlencode({
        "chat_id": chat_id,
        "text": message
    }).encode("utf-8")

    request = Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST"
    )

    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))

        if not result.get("ok"):
            logger.error("Telegram recusou a mensagem: %s", result)
            return False

        return True

    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        logger.error(
            "Erro ao enviar mensagem para %s: %s",
            chat_id,
            error
        )
        return False


def send_notification(opportunity):
    """Envia uma oportunidade para todos os usuários cadastrados."""

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_ids = get_chat_ids()

    if not token:
        logger.warning("Token do Telegram não configurado.")
        return False

    if not chat_ids:
        logger.warning("Nenhum usuário do Telegram configurado.")
        return False

    try:
        message = format_notification(opportunity)
    except (ValueError, TypeError) as error:
        logger.error("Oportunidade inválida: %s", error)
        return False

    results = []

    for chat_id in chat_ids:
        success = send_message(chat_id, message, token)
        results.append(success)

        if success:
            logger.info("Notificação enviada para um usuário.")

    return all(results)
