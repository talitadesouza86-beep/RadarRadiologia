
import logging
import os

from telegram_bot import get_chat_ids, send_message


logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_IDS = get_chat_ids()


def main():
    if not TOKEN:
        raise RuntimeError("Secret TELEGRAM_BOT_TOKEN não encontrado.")

    if len(CHAT_IDS) < 2:
        raise RuntimeError(
            "Esperados pelo menos dois IDs em TELEGRAM_CHAT_IDS."
        )

    message = (
        "🩻 RADAR RADIOLOGIA\n\n"
        "Teste de conexão realizado com sucesso!\n\n"
        "Este é o canal oficial de notificações de concursos "
        "e vagas de emprego para Técnico em Radiologia.\n\n"
        "Em breve, vocês receberão as novas oportunidades por aqui! 🚀"
    )

    successes = 0

    for chat_id in CHAT_IDS:
        if send_message(chat_id, message, TOKEN):
            successes += 1
            print(f"Mensagem enviada com sucesso para o ID {chat_id}.")
        else:
            print(f"Falha no envio para o ID {chat_id}.")

    if successes != len(CHAT_IDS):
        raise RuntimeError(
            f"Somente {successes} de {len(CHAT_IDS)} envios tiveram sucesso."
        )

    print("Todos os testes foram concluídos com sucesso!")


if __name__ == "__main__":
    main()
