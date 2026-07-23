---
name: level-progression-onscreen-visibility
description: "Progressão de fase só conta hostis VISÍVEIS na tela (teste estrito), não _is_enemy_off_screen"
metadata: 
  node_type: memory
  type: project
  originSessionId: d0a47dad-e855-4dde-861f-cbeb61dfb91c
---

A progressão de fase (`LevelProgressionController._count_active_stage_hostiles`)
deve contar apenas hostis **visíveis na tela**, usando `EntityManager.is_on_screen`
(teste estrito: o rect intersecta `[0,SW]×[0,SH]`) — **não** `_is_enemy_off_screen`.

**Why:** `_is_enemy_off_screen` deliberadamente NÃO considera "acima do topo"
(`y < -eh`) como fora da tela, porque inimigos normais entram por cima e não
devem ser ignorados pelo culling. Mas as **formações** (feature do mundo
VOLCANIC, junto com minas) estacionam seus inimigos em `y = -100` durante a
entrada. Com o check antigo, esses inimigos invisíveis (acima do topo) contavam
como ativos e a fase travava **vários segundos com a tela vazia** — sintoma que
aparecia "só no vulcão" (4-1→4-2). O `_ENEMY_CLEANUP_DURATION = 20s` é só o
backstop anti-softlock, NÃO era a causa.

**How to apply:** para "a fase está limpa?", pergunte "há hostil VISÍVEL?", não
"há hostil vivo em qualquer lugar?". `is_on_screen` é estrito de propósito;
`_is_enemy_off_screen` tem semântica de gameplay (mantém entrantes vivos) e não
serve para esse fim. Ver [[mine-explosion-respected-before-advance]].
