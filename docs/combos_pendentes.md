# Combos de upgrades — backlog de ideias

Contexto: hoje só a **família de modificadores de tiro** combina de verdade
(HOMING + EXPLOSIVE + GIANT são flags/efeitos na mesma bala e empilham). O
trabalho de "combo" é dar **identidade** (visual + sinergia legível), não criar a
mecânica do zero.

## ✅ #1 — Chain Lightning na família (FEITO)
Implementado: halo elétrico azul no `_draw_power_pulse`; chain+explosive detona
uma mini-explosão a cada salto; chain+giant ganha 1 salto extra.
Arquivos: `game/entities/bullet.py`, `game/systems/collisions.py`.

---

## ⬜ #2 — Controle de área + Dano em área (o de maior "wow")
Peças já existem: **Black Hole** e **Gravity Bomb** (vórtices) agrupam inimigos;
**Explosive**, **Air Strike** e **Plasma Beam** despejam AoE.

Ideia: inimigo **dentro do raio de um vórtice/buraco negro** recebe marca de
"vulnerável" → **+X% de dano** de qualquer fonte. Assim, puxar o enxame para um
ponto e detonar o aglomerado multiplica o dano.

Onde mexer (esboço):
- `black_hole.py` / vórtices do `GravityBombUpgrade`: expor um raio de "campo de
  vulnerabilidade".
- Ponto único de aplicação de dano (`CollisionPhysics.apply_hit`): checar se o
  alvo está dentro de algum campo e escalar o dano.
- Cuidado de balance: começar com +25–40% e testar; talvez limitar a inimigos
  não-boss ou dar um teto contra boss.

## ⬜ #3 — Combo elétrico: EMP + Chain Lightning
Os dois são "elétricos". Enquanto o campo do **EMP** (lentidão) estiver ativo:
- Chain salta para **mais alvos** (ex.: +2 saltos) ou com **raio maior**, e/ou
- aplica um **micro-stun** nos inimigos encadeados.

Onde mexer: `_trigger_chain_shot` já recebe `entity_manager`; dá para ler
`getattr(em, "emp_active", False)` e ajustar `jumps_left`/`radius`.

## ⬜ #4 — EMP + qualquer ofensivo (genérico, barato)
Inimigo lento = alvo fácil. Conceder **bônus de dano em inimigo desacelerado**
(marca de EMP/linger), sem código por-par — combina com tudo.

Onde mexer: `CollisionPhysics.apply_hit` — se o alvo tem slow de EMP ativo,
escalar o dano. Sinergia natural com #2 (mesmo ponto de aplicação).

---

## Outras sementes (não priorizadas)
- **Giant + Plasma Beam / Laser**: engrossar o feixe/laser enquanto o Giant Shot
  dura.
- **Blink Dash + ofensivo**: dash deixa um rastro de dano curto.
- **Orbital Shield + Repulsion**: empurrão ao refletir tiros.
