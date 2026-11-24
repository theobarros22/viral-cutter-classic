# Loop de Dados — Score Viral Calibrado com Instagram

> Especificação v1 — 03/07/2026
> Objetivo: transformar o score viral de heurística em modelo calibrado com desempenho real.

## O problema

Hoje o score (1-10) é opinião do Claude + heurísticas por nicho. Ninguém sabe se um clipe score 9 performa melhor que um score 6. Sem medição, o score é decoração.

## Arquitetura — 3 componentes

### 1. Registro de publicação (no Viralume)

Ao exportar, cada clipe grava uma linha em `%LOCALAPPDATA%\ViralCutter\dados\clipes.jsonl`:

```json
{"clipe_id": "a1b2", "data": "2026-07-03", "video_origem": "podcast_ep12.mp4",
 "nicho": "podcast", "score_previsto": 8, "duracao_s": 47,
 "hook_aplicado": true, "titulo": "...", "instagram_media_id": null}
```

Quando o clipe for publicado, associa-se o `instagram_media_id` (via comando simples ou campo na UI). Sem associação, o clipe fica fora do loop — sem problema.

### 2. Coletor de métricas (script agendável)

`coletar_metricas.py` roda 7 e 30 dias após cada publicação, via Meta Graph API
(credenciais que você já usa no relatório de Instagram):

- `views`, `reach`, `likes`, `comments`, `shares`, `saved`
- retenção média (`ig_reels_avg_watch_time`) quando disponível

Grava em `metricas.jsonl` vinculado ao `clipe_id`. Custo de API: desprezível.

### 3. Recalibrador (a partir de ~30 clipes medidos)

Com dados suficientes, por nicho:

- correlação score previsto × desempenho real (a métrica-mestre é **retenção**, não views — views dependem do algoritmo, retenção depende do corte)
- fatores mensuráveis: duração ótima, hook sim/não (teste A/B natural), template de legenda
- saída: ajustes nos pesos de `ajustar_score_por_nicho` + exemplos reais
  (few-shot) no prompt do Claude: "clipes assim performaram no top 20%"

## Métricas de sucesso do próprio loop

| Indicador | Meta |
|---|---|
| Correlação score × retenção | > 0.5 (hoje: desconhecida) |
| Clipes com métricas coletadas | 30 em 60 dias |
| Uplift de retenção com hook vs. sem | mensurado (hipótese: +15%) |

## Fases

1. **MVP (1 sessão):** registro de exportação + script de coleta manual.
2. **Automação (0,5 sessão):** tarefa agendada semanal de coleta.
3. **Recalibração (1 sessão, após 30 clipes):** análise + ajuste de pesos.

## Decisões que são suas

1. Qual conta business do Instagram entra no loop (a sua? a de clientes?).
2. Clipes de clientes entram no dataset? (agrega volume, mas mistura nichos)
3. Consentimento: se dados de clientes entram, o contrato precisa prever.
