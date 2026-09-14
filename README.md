# Notícias Automáticas

Sistema de monitoramento automatizado de notícias via Google News, com análise de sentimento e envio de resumo diário via Telegram. Projeto de extensão da UNINASSAU.

## Stack
- **Coleta:** Python 3.12 + GitHub Actions (cron)
- **Banco:** Supabase (PostgreSQL)
- **Análise:** LLM (Hy3 free via OpenRouter) ou léxico PT-BR offline
- **Notificação:** Telegram Bot
- **Painel:** HTML/JS com Chart.js (estático, lê do Supabase)

## Estrutura
```
noticias-automaticas/
├── .github/workflows/
│   └── agenda.yml          # Pipeline cron (05:00, 05:30, 06:00 BRT)
├── github-actions/
│   ├── common.py           # Helpers compartilhados (stdlib only)
│   ├── monitor.py          # 05:00 BRT - Coleta notícias do Google News
│   ├── sentiment.py        # 05:30 BRT - Análise de sentimento
│   ├── send_summary.py     # 06:00 BRT - Envia resumo via Telegram
│   └── requirements.txt    # Dependências Python
└── painel-kenneth-7f3a9c.html  # Painel web com gráficos
```

## Pipeline (GitHub Actions)

| Horário (BRT) | Job | O que faz |
|---|---|---|
| 05:00 | `monitor` | Busca notícias no Google News (palavras-chave), dedup por link, salva no Supabase |
| 05:30 | `sentiment` | Lê notícias sem sentimento, abre conteúdo integral, classifica POSITIVA/NEGATIVA/NEUTRA |
| 06:00 | `send` | Lê notícias do dia alvo no Supabase, envia resumo único via Telegram |

## Variáveis de ambiente (GitHub Secrets)

| Variável | Descrição |
|---|---|
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_KEY` | Chave de API do Supabase |
| `KEYWORDS` | Palavras-chave monitoradas (separadas por `;`) |
| `LLM_API_KEY` | Chave do OpenRouter (opcional, fallback para léxico) |
| `LLM_MODEL` | Modelo LLM (padrão: `tencent/hy3:free`) |
| `TG_TOKEN` | Token do bot Telegram |
| `TG_CHAT_ID` | ID do chat Telegram |

## Banco de dados (Supabase)

Tabela: `monitored_news`

| Campo | Tipo | Descrição |
|---|---|---|
| `ts` | timestamp | Data/hora da coleta |
| `dia` | date | Dia da notícia (para filtro) |
| `quando` | timestamp | Data da notícia (quando disponível) |
| `source` | text | Veículo/fonte |
| `title` | text | Título da notícia |
| `link` | text | URL original (unique, dedup) |
| `sentimento` | text | POSITIVA / NEGATIVA / NEUTRA |

## Como rodar localmente

```bash
cd github-actions
pip install -r requirements.txt

# Configurar variáveis de ambiente
export SUPABASE_URL="..."
export SUPABASE_KEY="..."
export KEYWORDS="Palavra1;Palavra2;Palavra3"

# Executar manualmente
python monitor.py
python sentiment.py
python send_summary.py
```

## Painel web

O arquivo `painel-kenneth-7f3a9c.html` é uma página estática que lê diretamente do Supabase (chave anon, somente leitura) e exibe:

- Gráfico pizza: distribuição de sentimentos
- Gráfico barras: notícias por dia
- Tabela: últimas 500 notícias com data, veículo, título, link e sentimento

Para usar: abrir o arquivo no navegador ou hospedar em qualquer servidor estático.

## Análise de sentimento

Se `LLM_API_KEY` estiver configurada, usa LLM (Hy3 free) para classificar o conteúdo integral da notícia. Caso contrário, cai em um léxico PT-BR offline baseado em palavras positivas/negativas pré-definidas.

## Dedup e acúmulo

- Notícias são deduplicadas por URL (nunca repete)
- O banco acumula todas as notícias dos últimos N dias (nunca apaga)
- O resumo diário cobre todas as palavras-chave, mesmo as que não tiveram notícias (silêncio nunca é omissão)

## Equipe
Projeto de extensão — UNINASSAU Teresina-PI.
Aluno: Gilberto de Sousa Barbosa Filho.
Orientador: Kenneth Corrêa (mentor).

## Licença
Projeto acadêmico — uso livre.
