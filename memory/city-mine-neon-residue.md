---
name: city-mine-neon-residue
description: CityMine (mina temática Neon City) = subclasse de ExplosiveMine + flag spawns_neon_residue; secundárias reusam ExplosiveEffect com delay/color.
metadata: 
  node_type: memory
  type: project
  originSessionId: 9172b5af-11c9-477a-9068-3475e2b9614f
---

A mina da Neon City (`game/entities/Inimigos_Tema_Cidade/city_mine.py`, classe
`CityMine`) segue o MESMO padrão da `MountainGeode`: subclasse de `ExplosiveMine`,
herda todo o fluxo de explosão de `Collisions.check_mine_explosions` (MineExplosion
+ dano à nave via `handle_mine_explosion` + dano a inimigos). Explosão principal
idêntica em lógica/dano/alcance (radius 30, explosion_radius 240).

**Gancho temático:** flag `spawns_neon_residue = True` (espelha o `spawns_ice_zone`
da geode), lido em `check_mine_explosions`. Quando a mina detona, chama
`mine.residue_bursts(cx, cy, explosion_radius)` (a própria mina calcula 3 posições
aleatórias DENTRO do raio principal, `dist + sub_r ≤ R`) e dá spawn em cada uma via
`EntityManager.spawn_explosive_effect(**spec)`. collisions só orquestra; os números
ficam na CityMine.

**Reuso das secundárias:** `ExplosiveEffect` foi estendido (retrocompatível) com
`delay` (acende sozinho após N s — encadeamento sem scheduler), `color` (tinta
temática) e `lifetime` exposto em `spawn_explosive_effect`. Os resíduos = 3
ExplosiveEffects neon, dano 12 (vs 50 da principal), raio ~0.16–0.24× do principal,
delays 0.12/0.19/0.26 (cadeia), vida 0.22 (rápido). `ExplosiveEffect` dá dano só a
INIMIGOS (`explosive_effects_vs_enemies`), não à nave — a principal já puniu a nave.

**Registro:** `THEME_ENEMY_REPLACEMENTS[(WorldTheme.CITY, ExplosiveMine)] = CityMine`
em pipeline.py (igual à geode em MOUNTAINS). O `_update_mine_spawner` usa
`_get_theme_mine_type()`, então a substituição é automática. Sprites próprios (4
frames: idle 01/02, explodindo 01/02) em `assets/images/Mine_City/`, animados em
`CityMine.draw` (sem mutar estado — frame derivado dos timers). Preload via
`sprite_loader.register("CityMine", ...)`.
