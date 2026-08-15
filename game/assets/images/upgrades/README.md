# Ícones dos aprimoramentos

Solte aqui um PNG por upgrade, nomeado com o **`icon_id`** dele (o mesmo campo
de `UPGRADES_META`, em `game/core/upgrades.py`):

```
shield_burst.png       heal.png            emp.png
homing_shot.png        orbital_discharge.png
explosive_shot.png     giant_shot.png      air_strike.png
black_hole.png         cannon_tower.png    blink_dash.png
gravity_bomb.png       chain_lightning.png orbital_shield.png
plasma_beam.png        wingman.png         berserk.png
link.png               implosion_shot.png  critical_core.png
cryo_shot.png          shockwave.png       corrosive_ammo.png
```

O arquivo é descoberto sozinho — **não há mapa para registrar em lugar nenhum**
(mesma ideia das pastas de música por tema/boss). Assim que o PNG existir, ele
substitui o medalhão de letra no grid, no slot equipado e na animação de voo,
que passam todos por `_draw_upgrade_art`.

**Formato:** quadrado, com fundo transparente. O jogo escala para o tamanho de
cada lugar, então um lado de 128px cobre desde a célula do grid (~80px em 720p)
até 1080p sem serrilhar. Pixel art: prefira múltiplos de 8.

**Enquanto não existir arte**, o upgrade cai no fallback (círculo colorido por
categoria + a letra de `get_upgrade_icon`) — não é erro, é o estado normal. Dá
para migrar um por vez.
