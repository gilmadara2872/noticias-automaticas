# Notícias Automáticas

Sistema de monitoramento automatizado de notícias via Google News, com análise de sentimento e envio de resumo diário via Telegram. Projeto de extensão da UNINASSAU.

## Stack
- **Coleta:** Python 3.12 + GitHub Actions (cron)
- **Banco:** Supabase (PostgreSQL)
- **Análise:** LLM (Qwen/Qwen2.5-7B-Instruct via OpenRouter) ou léxico PT-BR offline com 200+ palavras + regra de negação
- **Notificação:** Telegram Bot
- **Painel:** HTML/JS com Chart.js (estático, lê do Supabase)

## Estrutura
```
noticias-automaticas/
├── .github/workflows/
│   ├── agenda.yml          # Pipeline cron (05:00, 05:30, 06:00 BRT)
│   └── reclassify.yml      # Reclassifica todas as notícias com LLM (workflow_dispatch)
├── reclassificar.py        # Script de reclassificação (standalone)
├── github-actions/
│   ├── common.py           # Helpers compartilhados (Supabase + LLM)
│   ├── monitor.py          # 05:00 BRT - Coleta notícias do Google News
│   ├── sentiment.py        # 05:30 BRT - Análise de sentimento (LLM Qwen ou léxico)
│   ├── send_summary.py     # 06:00 BRT - Envia resumo via Telegram
│   ├── requirements.txt    # Dependências Python
│   └── README.md           # Documentação do pipeline
└── painel-kenneth-7f3a9c.html  # Painel web com gráficos
```

## Pipeline (GitHub Actions)

| Horário (BRT) | Job | O que faz |
|---|---|---|
| 05:00 | `monitor` | Busca notícias no Google News (palavras-chave), dedup por link, salva no Supabase |
| 05:30 | `sentiment` | Lê notícias sem sentimento, abre conteúdo integral, classifica POSITIVA/NEGATIVA/NEUTRA |
| 06:00 | `send` | Lê notícias do dia alvo no Supabase, envia resumo único via Telegram |
| (manual) | `reclassify` | **Reclassifica TODAS as notícias com o modelo Qwen e regra do Kennedy** |

## Variáveis de ambiente (GitHub Secrets)

| Variável | Descrição |
|---|---|
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_KEY` | Chave `service_role` do Supabase (grava no banco) |
| `KEYWORDS` | Palavras-chave monitoradas (separadas por `;`) |
| `LLM_API_KEY` | Chave do OpenRouter (obrigatório para LLM; fallback para léxico se não configurado) |
| `LLM_MODEL` | Modelo LLM (padrão: `Qwen/Qwen2.5-7B-Instruct`) |
| `TG_TOKEN` | Token do bot Telegram |
| `TG_CHAT_ID` | ID do chat Telegram |

## Análise de sentimento

O sistema usa duas abordagens:

### 1. LLM (Qwen/Qwen2.5-7B-Instruct)
Se `LLM_API_KEY` estiver configurado, usa o modelo Qwen para classificar o conteúdo integral da notícia. O LLM recebe contexto especial sobre o mentor **Kennedy Corrêa** (palestrante/coordenador) — se ele participa como palestrante, a notícia tende a ser POSITIVA; se é criticado, é NEGATIVA.

### 2. Léxico PT-BR offline (fallback)
Se `LLM_API_KEY` não estiver configurado, usa um léxico com 200+ palavras em português brasileiro, incluindo regras de negação (ex: "não é bom" = negativo).

## Reclassificação

Para reclassificar todas as notícias já existentes no banco com o novo modelo:

**Via GitHub Actions (recomendado):**
- Vá em **Actions → Reclassificar Sentimentos → Run workflow**
- Todas as 37 notícias serão reprocessadas com o modelo Qwen

**Localmente:**
```bash
cd github-actions
export SUPABASE_URL="https://uirvzlxhuyaentizyden.supabase.co"
export SUPABASE_KEY="<service_role_key>"
export LLM_API_KEY="<openrouter_key>"
export LLM_MODEL="Qwen/Qwen2.5-7B-Instruct"
python sentiment.py --force
```

Ou use `python reclassificar.py` para apenas zerar os sentimentos (o pipeline faz a reclassificação no próximo ciclo).

## Regra Kennedy Corrêa

Quando Kennedy Corrêa aparece na notícia (como palestrante, moderador ou coordenador do evento), o LLM recebe um prompt especial que analisa ESTRITAMENTE o contexto da participação dele. Isso garante que notícias sobre eventos onde ele participou sejam classificadas corretamente (POSITIVA se ele estava como palestrante, NEGATIVA se fosse criticado, NEUTRA se apenas citado).

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
export LLM_API_KEY="..."
export LLM_MODEL="Qwen/Qwen2.5-7B-Instruct"

# Executar manualmente
python monitor.py
python sentiment.py           # Analisa pendentes
python sentiment.py --force   # Analisa TODAS (reclassifica)
python send_summary.py
```

## Painel web

O arquivo `painel-kenneth-7f3a9c.html` é uma página estática que lê diretamente do Supabase (chave anon, somente leitura) e exibe:

- Gráfico pizza: distribuição de sentimentos
- Gráfico barras: notícias por dia
- Tabela: últimas 500 notícias com data, veículo, título, link e sentimento

Para usar: abrir o arquivo no navegador ou hospedar em qualquer servidor estático.

## Equipe
Projeto de extensão — UNINASSAU Teresina-PI.
Aluno: Gilberto de Sousa Barbosa Filho.
Orientador: Kenneth Corrêa (mentor).

## Licença
Projeto acadêmico — uso livre.
