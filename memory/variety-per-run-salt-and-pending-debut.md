---
name: variety-per-run-salt-and-pending-debut
description: "Semente de variedade por-partida (implementada) + estreia garantida por assinatura (IMPLEMENTADA jul/2026)"
metadata: 
  node_type: memory
  type: project
  originSessionId: bf80c383-04f4-4f9f-847f-b8490bc6c14f
---

Seleção de inimigos por nível era **determinística por seed = f(nível, tema)** → um tipo que perdia o sorteio ficava com **0% para sempre, para todos** (IceGolem no Mundo 1; MirrorPylon no City tinham o mesmo bug).

**Implementado (jul/2026):** `_RUN_VARIETY_SALT` global em `pipeline.py` + `set_run_variety_salt()`, somado à seed de `_select_variety_subset`. Sorteado 1x por sessão em `PlayingScene._init_systems` (antes de gerar fases). Constante durante a run → anti-repetição entre fases preservada; varia entre runs → todo tipo ganha chance real. Default 0 = legado determinístico (análise/testes). Cobertura resultante: IceGolem ~73%, MirrorPylon ~51% das runs (era 0%).

**Implementado (jul/2026) — "estreia garantida por assinatura":** `_signature_debut_levels(world)` + `_force_signature()` em `pipeline.py`, aplicados no fim de `_apply_enemy_variety_cap` (só ao nível ATUAL, pós-loteria). Cada assinatura recebe um SLOT determinístico = os últimos `k` níveis NÃO-FIXOS do mundo (k = nº de assinaturas), um por nível, mapeando a mais antiga ao slot mais cedo e a mais nova ao mais tarde. No seu slot, se estiver DISPONÍVEL no pool (`sig in composition`), é fixada substituindo um special NÃO-assinatura (não infla o teto, não toca na base). Evitou o problema de arquitetura (detectar estreia comparando pools de níveis vizinhos): não usa histórico nem reconstrução — a garantia é um slot fixo por nível. Cordilheiras: StoneEagle→1-7, CuttingStorm→1-8, IceGolem→1-9; cobertura das 3 assinaturas foi de 67-93% p/ **100% em 400/400 runs** (e IceGolem passou de 0%→presente na campanha salt=0). STARFIELD/CITY também ganham slots (guard `sig in composition` torna no-op os slots antes do desbloqueio). Relaciona-se a [[new-theme-specials-gate-after-trio]], [[swarm-base-and-combination-history]], [[variety-cap-exclui-specials-raros]].

Nota: `TEST_ARENA_ENABLED` em `fixed_levels.py` estava commitado como `True` (travava tudo em modo arena de teste) — corrigido para `False`.
