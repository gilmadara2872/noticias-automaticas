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
│   ├── collect.py          # Coleta em 3 camadas (nome, tema, veículo)
│   ├── filtro_pagina.py    # Separa matéria real de menu/rodapé/lateral
│   ├── sentiment.py        # 05:30 BRT - Análise de sentimento (LLM, léxico só de reserva)
│   ├── send_summary.py     # 06:00 BRT - Envia resumo via Telegram
│   ├── requirements.txt    # Dependências Python
│   └── README.md           # Documentação do pipeline
└── painel-kenneth-7f3a9c.html  # Painel web com gráficos
```

## Pipeline (GitHub Actions)

| Horário (BRT) | Job | O que faz |
|---|---|---|
| 05:00 | `monitor` | Coleta em 3 camadas: nome exato, tema, veículo. Filtra matéria×página, checa duplicata, salva no Supabase (timeout 120 min) |
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
| `LLM_MODEL_RESERVA` | Modelos `:free` de reserva, separados por `;`. Tentados **na ordem**, só quando o principal falha. O principal é sempre tentado primeiro — quando volta, volta sozinha, sem configuração |
| `TG_TOKEN` | Token do bot Telegram |
| `TG_CHAT_ID` | ID do chat Telegram |

## Coleta em 3 camadas

Buscar só pelo nome **perde matéria**: foi assim que a matéria do O Globo
("Do destino ao restaurante...") escapou — o Kenneth aparecia 6 vezes no
corpo e **nenhum** no título. Por isso a coleta hoje é:

| Camada | Busca | Pega o quê |
|---|---|---|
| `nome` | nome exato da pessoa/empresa | matéria com o nome no título |
| `tema` | termos do assunto (IA, innovaçao, CiteCo, agro…) | matéria em que ele só é citado no corpo |
| `veiculo` | Folha, O Globo, Estadão, UOL, CNN, Valor, Canal Rural | outlet que ele publica e que não indexa por busca de nome |

Ordem de verificação de cada candidata, **antes** de gravar:

```
1. link já no banco (sem query string)?          → descarta
2. nome no título?
   ├─ título igual em outro veículo?            → descarta
   └─ senão                                     → aceita
3. senão, baixa o corpo da página
   ├─ filtro de matéria × página                → descarta se não for sobre ele
   ├─ recontido ≥ 0,55 em veículo distinto      → descarta como republicação
   └─ senão                                     → aceita
```

O passo 2 em diante **não é atalho**: nome no título é pista de descoberta,
não aceite automático. Sem as checagens de link e título (commits
`29dc681`), a matéria removida na limpeza voltava na coleta seguinte.

### O filtro de matéria × página (`filtro_pagina.py`)

Uma página de portal traz o nome do Kenneth no menu lateral, no rodapé ou
em "Notícias Relacionadas". Isso **não é** matéria sobre ele.

| Regra | O que exige |
|---|---|
| Pessoa | nome completo exato presente (normalizado: acento e caixa não contam) |
| Empresa | nome completo presente (`80 20 Marketing`, não `marketing` solto; `MedGuias` inteira) |
| Empresa, posição | primeira menção antes de **85%** do texto |

O corte de posição estava em 60% e **barrava matéria real**: em 2026-10-05
a matéria da Prefeitura de Campo Grande o lista entre 8 palestrantes
confirmados, a 62% do texto. Afrouxado para 85%.

Medido depois do ajuste: **32/32** matérias legítimas aceitas, **8/8**
ruídos barrados, o caso de 62% aceito.

## Análise de sentimento

O sistema usa duas abordagens:

### 0. O que se avalia é a PESSOA, não o assunto
Definido pelo Kenneth: *sentimento é a avaliação da participação dele,
não do tema da matéria.* Um acidente climático é negativo; ele não é.

**O modelo só recebe as frases em torno do nome.** A notícia inteira
ia nele e o modelo via "acusava", "processo" referidos a outra empresa
e marcava `NEGATIVA`. `frases_sobre_a_pessoa()` corta isso: 4262 chars
viram 426, o nome sobrevive em 41/41, e o termo fora de contexto
desaparece.

Exemplos que o Kenneth definiu (validados 6/6 na IA real):

| Situação | Resultado |
|---|---|
| Opinião boa como especialista, mesmo em assunto negativo | **POSITIVA** |
| Vítima de violência (não é culpa nem juízo sobre ele) | **NEUTRA** |
| Comentário que não agrega, nome em lista | **NEUTRA** |
| Citado perto de crime/investigação, sem acusação direta | **NEGATIVA** |
| Acusação, ataque, exposição reputacional **contra ele** | **NEGATIVA** |
| Acusação contra a empresa, processo contra terceiros | **NEGATIVA** de outro, não dele |

### 1. LLM (OpenRouter) — caminho principal
O modelo classifica **pelo papel que a pessoa exerce na matéria**, não pelo tema dela:

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

## Limites conhecidos

Registrados para ninguém descobrir tarde:

- **A coleta é heurística.** Google News, busca por tema e por veículo são
  camadas de tentativa, não cobertura garantida. Não há como provar que uma
  matéria não existe.
- **A cota gratuita é por conta, não por modelo.** `free-models-per-day`
  estoura junto para todos os modelos `:free`. Os modelos de reserva
  resolvem limite **do modelo**, não **da conta**. Uso normal gasta poucas
  chamadas por dia (só matéria nova); reclassificação completa, essa.
- **O fallback léxico nunca é silencioso.** Se a IA cair, o Telegram avisa
  e a matéria fica marcada como pendente.
- **Filtro de frase não confirmado pela IA em produção.** Validado por
  número (4262→426 chars, nome preservado em 41/41), mas a cota acabou
  antes da primeira classificação real. Se não funcionar bem, o sintoma é
  classificação com termo fora de contexto — visível e corrigível.
- **O filtro barra o que ele conhece.** Pode existir forma de o nome
  aparecer que ninguém viu ainda. Quem sustenta a proteção é a exigência de
  nome completo, não a posição no texto.
- **Carga dos segredos:** todos foram expostos em conversa. Rotacionei-os:
  `LLM_API_KEY`, `SUPABASE_KEY`, `TG_TOKEN`, token do GitHub.
