---
name: boss-single-source-roadmap
description: A classe do boss tem fonte única — WORLD_BOSS_ROADMAP via get_boss_for_level; nunca em WorldConfig nem FIXED_LEVELS.
metadata: 
  node_type: memory
  type: project
  originSessionId: bdc331f3-34fa-4d8b-9b5e-1d066f346d8b
---

A CLASSE do boss de qualquer nível (mid e final, nomeado e procedural) é definida
**só** em `WORLD_BOSS_ROADMAP` (`game/core/world_config.py`) e resolvida por
`get_boss_for_level(level)`. `WorldConfig` **não** tem mais `boss_type` —
`boss_level` ali é só o nível FINAL do mundo (transição de mundo, ex.: `playing.py`).
`FIXED_LEVELS` define **só o layout** handcrafted (inimigos/score/nome) das fases;
a classe do boss é injetada pelo pipeline a partir do roadmap.

**Why:** antes a classe morava em 3 lugares (WorldConfig, FIXED_LEVELS, roadmap)
que podiam discordar — havia 4 padrões de "boss final" e o `FIXED_LEVELS[10]` era
código morto. Refatoração Fase 1/2 (commits dccfa55/318c1b8) unificou isso.

**How to apply:** adicionar/trocar um boss = editar um `BossSlot` no roadmap, nunca
mexer em `WorldConfig` nem pôr `boss_type` em `FIXED_LEVELS`. Bosses procedurais
(setor) saem de `_get_procedural_sector_boss` + `get_procedural_midboss_for_level`,
também via `get_boss_for_level`. A cascata de CONSTRUÇÃO do boss em
`boss_fight_controller._spawn_boss` é separada e fica como está (§5, construtores
divergem). Plano e Fase 3 (ThemeProfile, adiada) em `PLANO_REORGANIZACAO_PROGRESSAO.md`.
Ver também [[city-variety-pyramid-rotation]].
