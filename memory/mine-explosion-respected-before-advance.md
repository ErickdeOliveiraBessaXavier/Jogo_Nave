---
name: mine-explosion-respected-before-advance
description: Explosões de mina ativas seguram o avanço de fase até a animação/dano terminar
metadata: 
  node_type: memory
  type: project
  originSessionId: d0a47dad-e855-4dde-861f-cbeb61dfb91c
---

`_count_active_stage_hostiles` inclui `em.mine_explosions` ainda não-`finished()`
(e visíveis via `is_on_screen`) na contagem que segura o avanço de fase.

**Why:** `MineExplosion` (dur. 0,5s) é hazard real (causa dano durante a vida) e
fica numa lista separada de `enemies`. Sem contá-la, a fase avançava no meio da
explosão, cortando a animação. Pedido explícito do usuário: respeitar a animação
da mina e sua explosão antes de avançar.

**How to apply:** ao decidir "fase limpa?", hazards transitórios visíveis (como
explosões de mina) também contam, não só inimigos. Combina com a regra de
visibilidade estrita de [[level-progression-onscreen-visibility]].
