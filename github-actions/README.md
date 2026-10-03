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
- **LLM**: `qwen/qwen3.8-27b:free` via OpenRouter para análise de sentimento

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
Usa `qwen/qwen3.8-27b:free` via OpenRouter (tier gratuito, custo zero) para
ler a notícia inteira e classificar **pelo papel que a pessoa exerce na
matéria**, não pelo tema dela:

| Situação | Resultado |
|---|---|
| Palestrante, especialista citado como fonte, anfitrião, organizador, elogiado | **POSITIVA** |
| Acusado, negatively citado, vítima de violência, contexto de crime | **NEGATIVA** |
| Apenas citado de passagem (nota de rodapé, lista) ou o assunto não é sobre ela | **NEUTRA** |

Vale para qualquer pessoa monitorada — não há caso especial por nome.

### Léxico PT-BR (reserva)
200+ palavras com regras de negação. Só entra **se a IA falhar**, e nesse
caso o sistema **avisa no Telegram** dizendo quais notícias saíram do léxico.

### Checagem de saúde
`checa_llm()` testa a chave e o modelo **antes** de classificar. Sem isso,
uma chave vazia ou um modelo renomeado gera um workflow "verde" com 100% das
classificações vindo do léxico — foi o que aconteceu em 26/09 e ninguém
percebeu.

### Modo reclassificação
```bash
python sentiment.py --force
```
⚠️ Consome ~40 das 50 requisições gratuitas do dia. Rode uma vez pela manhã.

## Coleta em 2 camadas

Buscar só pelo nome **não pega matéria de veículo com paywall**: o Google
não indexa o corpo, e o nome costuma estar no meio do artigo. O filtro de
corpo (`cita()`) aceitaria a matéria — ela é que nunca chegava até ele.

Por isso o `collect.py` coleta em duas camadas:

1. **Por nome** — barata e precisa
2. **Por tema**, sempre com 2+ termos — com 1 termo o Google News satura em
   100 itens e a matéria escorre; com 2 ela volta completa e vem no topo

O filtro de corpo continua sendo o portão final nas duas camadas.

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
   - `LLM_MODEL` — modelo LLM (padrão: ``qwen/qwen3.8-27b:free``)
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
- O modelo LLM `qwen/qwen3.8-27b:free` foi escolhido por ter melhor suporte
  a português brasileiro e contexto de 128k tokens.
- A reclassificação (`sentiment.py --force`) processa todas as notícias do banco,
  incluindo as que já tinham sentimento atribuído.
