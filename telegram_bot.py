import json
import os
import urllib.parse
import urllib.request


def get_chat_ids():
    return [x.strip() for x in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if x.strip()]


def format_notification(item):
    if item.get("category") == "emprego":
        header, label = "💼 VAGA DE EMPREGO", "Prazo"
    else:
        header, label = "🩻 RADAR RADIOLOGIA", "Inscrições"
    date = item.get("application_date") or "Prazo não informado"
    city = item.get("city") or "Local não identificado"
    return (f"{header}\nVaga: {item.get('title', 'Técnico em Radiologia')}\n"
            f"Local: {city} – SP\n{label}: {date}\n🔗 {item.get('application_url', '')}")


def send_message(chat_id, message, token):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": message, "disable_web_page_preview": "true"
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        result = json.loads(response.read().decode())
    return bool(result.get("ok"))


def send_notification(item):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    ids = get_chat_ids()
    if not token or not ids:
        return False
    ok = True
    for chat_id in ids:
        try:
            ok = send_message(chat_id, format_notification(item), token) and ok
        except Exception as exc:
            print(f"Falha no Telegram: {exc}")
            ok = False
    return ok
