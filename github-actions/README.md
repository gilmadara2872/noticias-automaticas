# Monitor de Notícias — Pipeline Automatizado

Pipeline 100% gratuito que monitora notícias sobre o cliente nas fontes abertas
(Google News), classifica o sentimento de cada matéria e envia um resumo diário
via Telegram — tudo rodando na nuvem, sem depender de nenhum servidor local.

## O que o projeto faz

Todo dia, em horário agendado (Brasília), três etapas rodam automaticamente:

| Horário (BRT) | Etapa | O que acontece |
|---------------|-------|----------------|
| 05:00 | **Monitorar** | Busca notícias das últimas 48h no Google News para as palavras-chave do cliente e salva no banco. |
| 05:30 | **Sentimento** | Lê as notícias ainda não analisadas, abre o conteúdo e classifica como POSITIVA / NEGATIVA / NEUTRA. |
| 06:00 | **Resumo** | Envia pelo Telegram um resumo das notícias do dia com data/hora, veículo, título, URL e sentimento. |

O banco **acumula todas as notícias** (nunca apaga) para gerar gráficos e
indicadores ao longo do tempo.

## Stack

- **Python 3** (biblioteca padrão apenas — sem dependências externas)
- **Google News RSS** como fonte de notícias
- **Supabase** (Postgres gratuito) como banco de dados persistente
- **Telegram Bot API** para envio do resumo
- **GitHub Actions** como agendador (cron) e runtime — roda na nuvem, 24/7
- **LLM**: Qwen/Qwen2.5-7B-Instruct via OpenRouter para análise de sentimento

## Arquitetura

```
GitHub Actions (cron 05:00/05:30/06:00 BRT)
   │
   ├─ monitor.py      → Google News RSS → Supabase (INSERT/UPSERT, sem duplicar)
   ├─ sentiment.py    → Supabase (lê sem sentimento) → classifica → grava
   └─ send_summary.py → Supabase (lê do dia) → Telegram (resumo único do dia)
```

## Análise de sentimento

### Modelo LLM (principal)
Usa o modelo **Qwen/Qwen2.5-7B-Instruct** via OpenRouter para classificar o conteúdo integral da notícia.

O LLM recebe contexto especial sobre o mentor **Kennedy Corrêa**: quando Kennedy aparece como palestrante, moderador ou coordenador, o sistema analisa ESTRICTAMENTE o contexto da participação. Se ele é palestrante = POSITIVA; se é criticado = NEGATIVA; se apenas citado = NEUTRA.

### Léxico PT-BR (fallback)
Se o LLM não estiver disponível, usa um léxico com 200+ palavras em português brasileiro, incluindo regras de negação (ex: "não é bom" = negativo).

### Modo reclassificação
Para reclassificar todas as notícias existentes com o novo modelo:
```bash
python sentiment.py --force
```
Isso busca TODAS as 37+ notícias no banco e as reclassifica com o LLM Qwen.

## Segurança

- Nenhuma chave (Supabase, Telegram) está no código. Tudo vem de
  **GitHub Secrets** (`Settings → Secrets and variables → Actions`).
- O banco não expõe dados sensíveis do cliente; as palavras-chave de produção
  são configuráveis e neste repositório estão como *placeholders* ("Cliente Nome",
  "Marca A", "Empresa B").
- As notícias nunca são removidas do banco (apenas inseridas/atualizadas).
- Para reclassificação, o workflow `reclassify.yml` usa `secrets.LLM_API_KEY`
  para acessar o OpenRouter e processa todas as notícias.

## Como usar

1. Fork/clona este repositório.
2. Em `Settings → Secrets and variables → Actions`, adiciona:
   - `SUPABASE_URL` — URL do projeto Supabase
   - `SUPABASE_KEY` — chave `service_role` (grava no banco)
   - `LLM_API_KEY` — chave do OpenRouter (obrigatório para LLM)
   - `LLM_MODEL` — modelo LLM (padrão: `Qwen/Qwen2.5-7B-Instruct`)
   - `TG_TOKEN` — token do Bot do Telegram
   - `TG_CHAT_ID` — chat de destino do resumo
   - `KEYWORDS` — palavras-chave do cliente
3. Ajusta as `KEYWORDS` em `monitor.py` para os termos do seu cliente.
4. O workflow roda sozinho todos os dias. Para testar na hora, use
   **Actions → Run workflow → Reclassificar Sentimentos** (para reprocessar tudo).

## Estrutura

```
github-actions/
  common.py           # helpers: Supabase + LLM API
  monitor.py          # 05:00 - coleta e salva notícias
  sentiment.py        # 05:30 - classifica sentimento (LLM Qwen ou léxico PT-BR)
  send_summary.py     # 06:00 - envia resumo via Telegram
  requirements.txt    # dependências
  README.md           # esta documentação
.github/workflows/agenda.yml    # agendamento (cron BRT) + dispatch manual
.github/workflows/reclassify.yml # reclassifica TODAS as noticias com LLM
painel-kenneth-7f3a9c.html      # painel web com gráficos
```

## Pipeline agendado

| Horário (BRT) | Job | Descrição |
|---|---|---|
| 05:00 | `agenda.yml` → monitor | Busca notícias do Google News |
| 05:30 | `agenda.yml` → sentiment | Classifica sentimento das novas notícias |
| 06:00 | `agenda.yml` → send | Envia resumo via Telegram |
| (manual) | `reclassify.yml` → reclassify | Reclassifica TODAS com o modelo Qwen |

## Notas

- O envio é **único por dia** (06:00). As etapas 05:00 e 05:30 processam em
  silêncio e só alimentam o banco.
- O filtro de resumo considera "o dia" como o dia anterior à execução
  (`RESUMO_DIAS_ATRAS = 1`), configurável em `send_summary.py`.
- O modelo LLM Qwen/Qwen2.5-7B-Instruct foi escolhido por ter melhor suporte
  a português brasileiro e contexto de 128k tokens.
- A reclassificação (`sentiment.py --force`) processa todas as notícias do banco,
  incluindo as que já tinham sentimento atribuído.
