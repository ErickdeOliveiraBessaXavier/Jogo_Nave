---
name: swarm-base-and-combination-history
description: "Filosofia \"SWARM (base) + N complementares\" no teto de variedade + anti-repetição do triângulo entre fases vizinhas (pipeline.py)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6b3b4046-db28-4ea1-84bc-5312107fe81b
---

Ajuste no sistema procedural (jun/2026) em `game/core/levels/pipeline.py`:

**SWARM = base do tema.** Não há classe `Swarm`; o "swarm" é conceitual = o base
por tema (Meteor/RockGlider/CityDrone, papel `volume`), já a massa mais frequente
(menor `spawn_time`; MOUNTAINS via `THEME_ENEMY_REPLACEMENTS[Meteor→RockGlider]`,
CITY injeta CityDrone direto em `_configure_city_spawn`). `_select_variety_subset`
adiciona o base primeiro → nenhuma fase sai "só de specials".

**Teto = swarm + N complementares.** `VARIETY_CAP_MAX_BY_DIFFICULTY` (e FLOOR)
agora **3/3/4/4** (Casual/Normal/Hardcore/Pesadelo). Como o base ocupa 1 slot:
Normal/Casual = swarm + 2; Hardcore/Pesadelo = swarm + 3. Isto **reverteu** o
override CITY=4/5 do `PLANO_BALANCEAMENTO.md` e re-alinhou com o que o CLAUDE.md §11
já declarava (3/4). `VARIETY_CAP_POOL_FRACTION` virou vestigial (FLOOR==MAX).

**Triangulação escalonada.** `ROLE_REPEAT_PENALTY` (0.18) agora é `PENALTY ** nº
do mesmo papel já no encontro` (era binário/set) — empurra mais forte contra
empilhar a mesma função. `chosen_roles` é `dict[str,int]`. Premissa documentada:
base usa papel exclusivo (`volume`), então não penaliza nenhum special.

**Histórico de combinação (novo).** Constantes `COMBINATION_HISTORY=3`,
`COMBINATION_RESHUFFLE_ATTEMPTS=16`. O conjunto de specials (triângulo SEM o swarm)
não repete a fase anterior (proibição dura via re-sorteio com `seed_salt` em
`_select_variety_subset`) e evita as 3 fases recentes em best-effort. Implementado
em `_resolve()` dentro de `_apply_enemy_variety_cap`: **recursivo e memoizado**,
ancorado em `world.start_level`, comparando contra conjuntos FINAIS já resolvidos
(não pré-histórico — isso falhava quando a fase anterior re-sorteava). Helper
extraído: `_recency_penalty_for_level`.

**Resíduos conhecidos (validados por sweep de 159 níveis):** zero "true-miss"
(pool igual). Repeats restantes são (a) **forçados** — pool de specials ≤ vagas,
ex.: Vulcão só tem Alien+EyeEnemy como specials → triângulo fixo o mundo inteiro
(é **gap de conteúdo**, precisa de inimigos novos no tema, não é bug); (b)
**gate-drift** — boundary onde um special acabou de desbloquear e o pool cresceu
(stateless usa o pool atual p/ reconstruir o vizinho). Determinismo por nível
preservado; ~2ms/geração (one-time no load).

Relacionado: [[city-variety-pyramid-rotation]], [[new-theme-specials-gate-after-trio]],
[[variety-cap-exclui-specials-raros]].
