import os
from telegram_bot import send_message, get_chat_ids

token = os.getenv("TELEGRAM_BOT_TOKEN")
ids = get_chat_ids()
if not token:
    raise SystemExit("Secret TELEGRAM_BOT_TOKEN não configurado.")
if not ids:
    raise SystemExit("Secret TELEGRAM_CHAT_IDS não configurado.")

message = "🩻 RADAR RADIOLOGIA\nTeste de conexão concluído!"
success = 0
for chat_id in ids:
    try:
        success += int(send_message(chat_id, message, token))
    except Exception as exc:
        print(f"Falha no envio: {exc}")

print(f"Mensagens entregues: {success} de {len(ids)}")
if success != len(ids):
    raise SystemExit("Um ou mais envios falharam.")
