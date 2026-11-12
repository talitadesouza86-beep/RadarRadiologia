# Radar Radiologia

Radar de concursos, processos seletivos e vagas de emprego para Técnico em Radiologia na região de Campinas/SP.

## Cidades monitoradas
Campinas, Sumaré, Hortolândia, Paulínia, Valinhos, Vinhedo, Indaiatuba, Americana, Nova Odessa, Santa Bárbara d'Oeste, Monte Mor, Jaguariúna, Cosmópolis, Pedreira, Itatiba, Holambra, Limeira, Piracicaba e Jundiaí.

## O que procura
- Concursos públicos, processos seletivos, contratações temporárias e cadastro reserva.
- Vagas privadas em hospitais, clínicas, centros de diagnóstico por imagem e medicina ocupacional.
- Técnico em Radiologia, Técnico de Raio X e funções técnicas correlatas.
- Mamografia, tomografia, ressonância e radiodiagnóstico quando a formação técnica em Radiologia for aceita.

## Fontes configuradas
PCI Concursos, Concursos no Brasil, JC Concursos, FUNCAMP, FASCAMP, Prefeitura de Campinas, CISMETRO, VUNESP, Indeed, LinkedIn, Gupy, InfoJobs, Catho, Trabalha Brasil, Grupo Diagmed, Hospital Vera Cruz e Hospital PUC-Campinas. Há também pesquisa complementar por Bing RSS.

**Limitação importante:** os sites mudam, bloqueiam robôs e podem exigir JavaScript/login. Os agregadores são pistas; o anúncio original precisa ser conferido. Fonte indisponível é registrada como falha, não como ausência de vagas. PDFs digitalizados sem texto selecionável não são lidos por OCR nesta versão.

## Telegram
Secrets do GitHub:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_IDS` — IDs separados por vírgula.

Cada pessoa deve abrir o bot e enviar `/start`.

O sistema conserva histórico, evita duplicatas e só notifica itens classificados como verificados. Candidatas incertas ficam pendentes de revisão.

## Execução
```bash
python -m pip install -r requirements.txt
python radar.py
```

## Agendamento
O workflow principal executa três vezes ao dia (UTC), além de permitir execução manual.
