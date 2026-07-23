---
name: death-animations-respected-before-advance
description: "Avanço de fase espera animações de morte cosméticas (explosões/implosões) terminarem, sem tratá-las como hostis."
metadata: 
  node_type: memory
  type: project
  originSessionId: 7be3c0a8-500b-43ab-abb2-7949ea3e47a7
---

A transição de fase em `LevelProgressionController.check_level_progression`
**espera** as animações de morte cosméticas terminarem antes de concluir o
nível (ou iniciar o boss), via `_has_active_death_animations()`: cobre
`entity_manager.explosion_pool.active` (explosões comuns) e
`entity_manager.core_implosions` (implosão do Neon Sniper).

**Why:** sem isso, ao virar de fase (ex.: 1-1 → 1-2) o último abate tinha a
explosão cortada — `_count_active_stage_hostiles` zerava assim que o inimigo
morria e o `LEVEL_CLEARED` disparava imediatamente.

**How to apply:** animações cosméticas (sem dano) NÃO entram em
`_count_active_stage_hostiles` — se entrassem, disparariam o blink de cleanup
(`begin_cleanup`) à toa. Elas só retornam `ProgressionStatus.NONE` (segura)
quando a tela já está sem hostis reais. Isso difere das `mine_explosions`, que
causam dano e por isso CONTAM como hostil (ver [[mine-explosion-respected-before-advance]]).
Novo efeito de morte cosmético → adicione-o em `_has_active_death_animations`,
não na contagem de hostis. Relacionado: [[level-progression-onscreen-visibility]].
