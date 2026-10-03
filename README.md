# Notícias Automáticas

Sistema de monitoramento automatizado de notícias via Google News, com análise de sentimento e envio de resumo diário via Telegram. Projeto de extensão da UNINASSAU.

## Stack
- **Coleta:** Python 3.12 + GitHub Actions (cron)
- **Banco:** Supabase (PostgreSQL)
- **Análise:** LLM via OpenRouter (padrão `qwen/qwen3.8-27b:free`, custo zero) com léxico PT-BR de 200+ palavras apenas como reserva
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
│   ├── collect.py          # Coleta em 2 camadas (por nome + por tema)
│   ├── sentiment.py        # 05:30 BRT - Análise de sentimento (LLM, léxico só de reserva)
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
| (manual) | `reclassify` | **Reclassifica TODAS as notícias pela IA** (regra da participação) |

## Variáveis de ambiente (GitHub Secrets)

| Variável | Descrição |
|---|---|
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_KEY` | Chave `service_role` do Supabase (grava no banco) |
| `KEYWORDS` | Palavras-chave monitoradas (separadas por `;`) |
| `LLM_API_KEY` | Chave do OpenRouter. **Obrigatória** — sem ela o léxico assume e o Telegram avisa |
| `LLM_MODEL` | Modelo LLM (padrão: `qwen/qwen3.8-27b:free`) |
| `TG_TOKEN` | Token do bot Telegram |
| `TG_CHAT_ID` | ID do chat Telegram |

## Análise de sentimento

O sistema usa duas abordagens:

### 1. LLM (OpenRouter) — caminho principal
O modelo lê a notícia inteira e classifica **pelo papel que a pessoa exerce na matéria**, não pelo tema dela:

| Situação na notícia | Resultado |
|---|---|
| Palestrante, especialista citado como fonte, anfitrião, organizador, elogiado | **POSITIVA** |
| Acusado, negativamente citado, vitima de violencia, contexto de crime | **NEGATIVA** |
| Apenas citado de passagem (nota de rodapé, lista) ou assunto não é sobre a pessoa | **NEUTRA** |

Vale para qualquer pessoa monitorada — não há caso especial por nome.

O tier gratuito do OpenRouter dá 50 requisições/dia por conta (custo zero). O sistema usa ~2 para checagem de saúde + 1 por notícia.

### 2. Léxico PT-BR — apenas reserva
Com 200+ palavras e regras de negação. Só entra **se a IA falhar**, e nesse caso o sistema **avisa no Telegram** dizendo quais notícias saíram do léxico. Nunca classifica em silêncio.

### Checagem de saúde (por que existe)
Antes de classificar, `sentiment.py` testa a chave e o modelo de verdade. Sem isso, uma chave vazia ou um modelo renomeado produz um workflow "verde" com 100% das classificações vindas do léxico — foi exatamente o que aconteceu em 26/09 e ninguém percebeu.

## Coleta em 2 camadas

Buscar apenas pelo nome **não pega matéria de veículo grande**. Medido: `"Kenneth Corrêa" when:365d` devolve 30 resultados e nenhum é a matéria do O Globo, porque o paywall impede o Google de indexar o corpo — e no O Globo o nome está no meio do artigo. O filtro aceitaria a matéria (o nome aparece 6 vezes no texto), mas ela nunca chegava até ele.

Por isso o `collect.py` coleta em duas camadas:

1. **Por nome** — barata e precisa
2. **Por tema**, usando sempre 2+ termos — porque com 1 termo o Google News satura em 100 itens e a matéria escorre; com 2 termos ela volta completa e aparece no topo (medido: `"inteligência artificial" viagem when:7d` → 37 itens, matéria na posição #1)

O filtro de corpo (`cita()`) continua sendo o portão final nas duas camadas, então a camada 2 não infla o banco.

## Reclassificação

**Via GitHub Actions (recomendado):** Actions → *Reclassificar Sentimentos* → Run workflow.
⚠️ Consome ~40 das 50 requisições gratuitas do dia. Rode uma vez pela manhã.

**Localmente:**
```bash
cd github-actions
export SUPABASE_URL="https://uirvzlxhuyaentizyden.supabase.co"
export SUPABASE_KEY="<service_role_key>"
export LLM_API_KEY="<chave_openrouter>"
export LLM_MODEL="qwen/qwen3.8-27b:free"
python sentiment.py --force
```

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
export LLM_MODEL="qwen/qwen3.8-27b:free"

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