# Monitor de Notícias — Pipeline Automatizado

Pipeline 100% gratuito que monitora notícias sobre um cliente nas fontes abertas
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

## Arquitetura

```
GitHub Actions (cron 05:00/05:30/06:00 BRT)
   │
   ├─ monitor.py      → Google News RSS → Supabase (INSERT/UPSERT, sem duplicar)
   ├─ sentiment.py    → Supabase (lê sem sentimento) → classifica → grava
   └─ send_summary.py → Supabase (lê do dia) → Telegram (resumo único do dia)
```

## Por que GitHub Actions e não um servidor

O agendador fica na nuvem da Microsoft. Não importa se o computador do dono
está ligado ou desligado: o resumo chega na hora certa. O tier gratuito de
repositórios privados cobre o uso com folga (alguns minutos por dia).

## Segurança

- Nenhuma chave (Supabase, Telegram) está no código. Tudo vem de
  **GitHub Secrets** (`Settings → Secrets and variables → Actions`).
- O banco não expõe dados sensíveis do cliente; as palavras-chave de produção
  são configuráveis e neste repositório estão como *placeholders* ("Cliente Nome",
  "Marca A", "Empresa B").
- As notícias nunca são removidas do banco (apenas inseridas/atualizadas).

## Como usar

1. Fork/clona este repositório.
2. Em `Settings → Secrets and variables → Actions`, adiciona:
   - `SUPABASE_URL` — URL do projeto Supabase
   - `SUPABASE_KEY` — chave `service_role` (grava no banco)
   - `TG_TOKEN` — token do Bot do Telegram
   - `TG_CHAT_ID` — chat de destino do resumo
   - (opcional) `LLM_API_KEY` — se quiser análise de sentimento por LLM em vez do léxico offline
3. Ajusta as `KEYWORDS` em `monitor.py` para os termos do seu cliente.
4. O workflow roda sozinho todos os dias. Para testar na hora, use
   **Actions → Run workflow**.

## Estrutura

```
github-actions/
  common.py        # helpers: acesso ao Supabase e Telegram
  monitor.py       # 05:00 - coleta e salva notícias
  sentiment.py     # 05:30 - classifica sentimento (LLM ou léxico PT-BR)
  send_summary.py  # 06:00 - envia resumo via Telegram
  requirements.txt # vazio (só stdlib)
.github/workflows/agenda.yml  # agendamento (cron BRT) + dispatch manual
```

## Notas

- O envio é **único por dia** (06:00). As etapas 05:00 e 05:30 processam em
  silêncio e só alimentam o banco.
- O filtro de resumo considera "o dia" como o dia anterior à execução
  (`RESUMO_DIAS_ATRAS = 1`), configurável em `send_summary.py`.
