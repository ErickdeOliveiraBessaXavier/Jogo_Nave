---
name: ship-impact-identity
description: "Impacto por nave só em hits NÃO-letais (morte fica intacta); giro de matiz do tiro do P2 é pequeno (0.08), NÃO o 0.5 dos sprites"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8f579ccf-a7d9-4f66-b075-41102b17a84f
---

Identidade visual de tiro/impacto por nave (`game/entities/_shared/impact_styles.py`),
adicionada em 2026-07-15. `SHIP_IMPACT_STYLES` mapeia nave → (pattern, palette).

**O estilo da nave só vale em hits NÃO-letais** (`CollisionPhysics.apply_hit`); a
explosão de MORTE fica intacta, é a que o inimigo pede. **Why:** decisão explícita
do usuário — a identidade de tema dos hostis (ALIEN/SLIME/CYBER/ICE_CORE) não deve
ser tocada. Consequência ACEITA de propósito, não é bug: `Alien.on_hit` e
`Meteor.on_hit` setam `dead = True` incondicionalmente, ignorando dano e vida, e
por isso nunca geram chip hit — nesses dois o efeito da nave não aparece. Chegamos
a implementar "forma da nave + cor do inimigo na morte" para cobri-los e o usuário
reverteu; **não reintroduzir**. **How to apply:** nave nova = 1 entrada em
`SHIP_IMPACT_STYLES` + (se precisar de forma nova) um spawner
em `_SPAWNERS` e, se a física fugir do burst, uma entrada em `_MOTION`
(`explosion.py`). Os padrões reusam o `ExplosionPool` de propósito — não criar
sistema de partículas paralelo, que exigiria replumbar update/draw/clear e o
gate de progressão.

**O tiro do P2 usa `P2_SHOT_HUE_SHIFT = 0.08`, não o `P2_HUE_SHIFT = 0.5` dos
sprites** (`core/player_tint.py`). **Why:** o 0.5 funciona no casco porque toda
nave parte do mesmo vermelho e todas caem no mesmo ciano. Os tiros já nascem em
cores distintas entre si, então meia volta manda cada um para um lugar diferente
e destrói a identidade por nave — verificado renderizando: o Magneto do P2 caía
no amarelo do Padrão e o Reverberador do P2 no verde do Estilete. **How to
apply:** para cor de tiro/partícula use `player_shot_color`, nunca o giro dos
sprites. Cores abaixo de `_SAT_FLOOR` (o prata do Caçador) não têm matiz para
girar e ficariam idênticas nos dois jogadores — por isso levam um cast frio.

Gotcha herdado: `Explosion._get_color` indexa a paleta por `life_ratio` e estoura
(IndexError) se uma partícula viver mais que `self.time`. Os spawners mantêm
vida <= time; há clamp como rede. Paletas vão de [morte → nascimento].

Ver [[visual-quality-system]] (a contagem de partículas passa por `vq.particles()`
em todo padrão) e [[city-mine-neon-residue]].
