---
name: new-theme-specials-gate-after-trio
description: "Ao adicionar inimigos novos a um tema existente, gatear depois do trio de introdução e registrar na ordem de introdução; o resto é automático (config global centralizada)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9172b5af-11c9-477a-9068-3475e2b9614f
---

Em 2026-06-06 adicionei 3 inimigos por tema ao Espaço (STARFIELD) e às
Cordilheiras (MOUNTAINS):
- STARFIELD: `StealthFighter` (rush), `OrbitalTurret` (sniper), `RepairDrone` (support).
- MOUNTAINS: `StoneEagle` (rush), `CuttingStorm` (area_denial), `IceGolem` (tank).

**Regra ao adicionar special novo a um tema existente:**
1. **Gatear DEPOIS do trio de introdução** (estágio absoluto `>=4` ou
   `stage_progress` tardio nos `_configure_*_spawn` de `procedural.py`). Senão rouba
   o slot do 2º/3º tipo e quebra a curva de introdução X-1→1, X-2→2, X-3→3.
2. **Registrar em `THEME_SIGNATURE_ENEMIES`** (pipeline.py) na ORDEM DE DESBLOQUEIO
   — é a fonte declarativa da ordem; o spotlight usa o rank.
3. Usar **spawn_time DIRETO** (sem `2/weight`) no gate (evita estourar o tempo).
4. `ENEMY_ARCHETYPE` (papel) + allowlist do tema. **Não** há mais tabelas de
   balanceamento por tema para mexer.

**Arquitetura GLOBAL de composição de encontros (refeita em 2026-06-06, focada):**
Tudo num único bloco "ENCOUNTER COMPOSITION CONFIG" em `pipeline.py`, sem exceção
por tema (substituiu `MAX_ENEMY_VARIETY_BY_DIFFICULTY` e `THEME_VARIETY_CAP_OVERRIDE`,
ambos REMOVIDOS):
- **Teto global dirigido pelo pool**: `_global_variety_ceiling(|pool|, dif)` =
  `clamp(round(0.5*|pool|), FLOOR, MAX)`. Mais tipos → mais vagas. Pool 7→4 (Normal),
  12→4/5 (CITY, sem override). Adicionar inimigos eleva o teto sozinho.
- **Spotlight BRANDO e aditivo**: peso = `1 + GAIN(2.0)*DECAY(0.5)**(ranks desde o
  mais novo presente)` → ×3.0→×2.0→×1.5→…→~×1.0. Dá cobertura na estreia sem dominar.
- **Recência é o motor de rotação**: janela 3, `{1:0.12,2:0.30,3:0.55}`, aplicada a
  TODOS (antes a assinatura ignorava). Quem aparece cai abaixo do campo por ~2-3
  níveis → ninguém se repete em excesso.
- **`ROLE_REPEAT_PENALTY=0.18`**: encontros complementares (não empilha mesmo papel).
- **`VETERAN_RESERVE=1`**: ≥1 vaga (além da base) barrada a specials "frescos" →
  garante veterano/antigo por encontro grande.

Validado: CITY (12 tipos) rotaciona as 11 assinaturas de forma equilibrada (2–6×
em 15 níveis); STARFIELD/MOUNTAINS mantêm antigos em ~todos os níveis pós-introdução.
Supersede o modelo de dominância permanente por rank descrito em
[[city-variety-pyramid-rotation]] e [[variety-cap-exclui-specials-raros]].

Infra adicionada: buffer `new_ice_zones` em `EnemyUpdateContext` (drenado pelo
`EntityManager` via `spawn_ice_poison_zone`), padrão de `new_explosions`, para o
`IceGolem` criar zona no slam. `CuttingStorm` reusa `ctx.new_area_blasts`.
