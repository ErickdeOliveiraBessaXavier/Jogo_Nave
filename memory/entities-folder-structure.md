---
name: entities-folder-structure
description: Layout de game/entities/ por responsabilidade + tema; onde colocar arquivo novo
metadata:
  type: project
---

`game/entities/` é organizado por **responsabilidade**, e os inimigos por
**tema** dentro de `enemies/`. A raiz só tem `__init__.py` (antes tinha 94
arquivos soltos). Estrutura:

```
game/entities/
  player/        nave e escoltas: ship, ship_movement/renderer/powerups,
                 mini_ship, wingman, revival_beacon
  projectiles/   tudo que voa e causa dano: bullet(+pool), homing_bullet,
                 lasers (player/boss/eye/spike), mines, air_strike_bomb, plasma_beam
  effects/       visual/transiente: explosion(+pool), explosive_effect,
                 chain_lightning, emp_wave, zones (fire/ice/electric),
                 particles, floating_score, coop_link, cutting_storm, slime_drip
  bosses/        boss base + *_boss + *_pixel_map + boss_hit_mixin/state/cannon/
                 renderer/square + square_base + spike
    city/        chefes do tema CITY + satélites exclusivos: metropolis_overlord_boss
                 (nível 30) e triad_boss (nível 34), com metropolis_* e triad_*
                 (pixel maps, projéteis, feixes, segmentos, coreografia) + city_thruster
  pickups/       powerup, star
  _shared/       mixins/pools/utils cross-categoria: pool_stats_mixin, zone_base,
                 attraction_utils, draw_utils, impact_styles
  enemies/
    space/       alien, meteor(+pool), guided_meteor, black_hole, satellite,
                 eye_enemy, bot_elemental, orbital_*, stealth_fighter, cannon_tower,
                 repair_drone, formation, dreadnought, gravity_well (era Espaco)
    city/        (era Inimigos_Tema_Cidade — mundo 3 Neon)
    mountain/    mountain_*, stone_*, ice_golem, rock_glider(+pool)
    _shared/     enemy_hit_mixin
```

**Onde colocar arquivo novo:** inimigo → `enemies/<tema>/` (o tema de onde
aparece). Projétil (voa+dano) → `projectiles/`, independente de quem dispara.
Efeito cosmético/zona → `effects/`. Boss e seus pixel_maps → `bosses/`.
Mixin/pool/util usado por várias categorias → `_shared/`.

**Boss com muito satélite ganha subpasta por tema** (`bosses/city/`). O corte é
por USO, não por nome: módulo que só o boss consome vai junto com ele; módulo que
o tema também usa fica em `enemies/<tema>/`. Foi assim que `city_mine` ficou para
trás (o `levels/pipeline.py` também o spawna) enquanto `city_thruster` foi junto.
Os dois chefes do City nasceram (2026-08) dentro de `enemies/city/` porque
compartilhavam pasta com os inimigos do tema — corrigido depois, com `git mv`
(renames preservados) + reescrita mecânica dos imports.

**Reescrita de imports ao mover entre subpastas de mesma profundidade**
(`enemies/city/` → `bosses/city/`): a contagem até `game` NÃO muda (`....core`
continua igual), e `...effects`/`...projectiles`/`...pickups` também não, porque
`...` é `entities` nos dois casos. Mudam só os que apontavam para irmãos:
`...bosses.X` → `..X`, `.._shared.Y` → `...enemies._shared.Y`,
`.city_mine` → `...enemies.city.city_mine`.

**Imports relativos:** arquivos em subpasta simples (`player/`) usam `...core`
(3 pontos); em subpasta dupla (`enemies/space/`) usam `....core` (4 pontos).
Base: `..` = `entities`, então conte os níveis até `game`. Ver as notas de
migração: a reorg (2026-07) foi 100% mecânica via script AST, validada por
import-all (246 módulos) + pytest + ruff.

Sem imports dinâmicos/por-string de entities no projeto — mover arquivo é seguro
desde que os imports relativos sejam re-relativizados (profundidade muda).
