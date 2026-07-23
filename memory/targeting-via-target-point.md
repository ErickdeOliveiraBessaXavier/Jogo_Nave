---
name: targeting-via-target-point
description: Toda seleção/mira de inimigo deve usar target_point + is_targetable (systems/targeting.py), nunca x+w/2
metadata:
  type: project
---

Qualquer código que **mira ou seleciona inimigos** (escoltas, auto-aim,
teleguiados, charge shot) tem que usar os utilitários puros de
`game/systems/targeting.py`:

- **`target_point(enemy)`** para o ponto de mira — prefere `collision_circle()`,
  não `x + w/2, y + h/2`.
- **`is_targetable(enemy)`** para filtrar alvos — checa `dead` **e**
  `can_take_damage()`, não só `dead`.

**Por quê:** o `MountainSerpentBoss` expõe `(x, y, w, h)` como um *bound fixo de
tela inteira*; só o `collision_circle` segue a cabeça móvel. Mirar em `x + w/2`
manda o tiro para um **ponto invisível no topo central da tela**. E a cabeça
fica invulnerável enquanto os blocos laterais estão de pé — `is_targetable`
evita travar nela. Esse mesmo bug já apareceu e foi corrigido em sequência no
**Wingman** (`entities/wingman.py`), no **auto-aim do MiniShip** e no
**HOMING_SHOT** (`entities/homing_bullet.py`).

**Como aplicar:** ao acrescentar uma fonte de dano que mira/persegue, NÃO
recalcular o centro do alvo na mão. Importar `target_point`/`is_targetable` (ou
`enemy_center`, que combina os dois) de `..systems.targeting`. Para alvos com
trava (`locked_target`), re-adquirir quando `not is_targetable(target)` — não só
quando `dead`. Padrão de referência: `entities/wingman.py::_target_center`.

Relacionado ao princípio §5 do [[CLAUDE.md]] (geometria por contrato, não
heurística de bounds).
