---
name: cryo-bomb-cycle
description: Cryo Shot fecha em bomba de gelo (cargas → cristalizar → estouro → fragmentos) e atira um TRIO maior/mais forte; boss cristaliza e detona mas NUNCA é freado (regra no _cryo_multiplier, não no guard da marca).
metadata:
  type: project
---

O **Cryo Shot** deixou de ser só controle. O ciclo completo é
**aplicar cargas → cristalizar → estouro → fragmentos**, e o congelamento é o
**pavio**: `cryo_slow_timer` com a escada cheia conta o tempo até a bomba.

## O tiro enquanto o upgrade dura

Trio (`CRYO_SHOT_ANGLES`, ±9°), área 1,6× (pelo `size_multiplier` do Giant Shot,
que compõe por multiplicação) e dano 1,35× por cristal. Ordem dos leques:
**Spread (5) > trio do Cryo (3) > tiro único** — eles não se multiplicam, mesma
regra do leque sobre as bocas do Double Shot; `apply_spread=False` (charge shots)
desliga os dois.

O leque é APERTADO de propósito: o Cryo é upgrade de **alvo único** (a escada só
sobe insistindo no mesmo inimigo), então espalhar as cargas por três alvos
trabalharia contra a própria mecânica. Consequência medida: uma salva que conecta
inteira enche a escada de uma vez (3 balas × 1 carga) — congelar virou coisa de
uma puxada de gatilho, não de três. Se algum dia isso pesar demais, o botão é
limitar as cargas por salva em `projectiles_vs_enemies`, não estreitar o leque.

O leque do Berserk não passa por `bullet_spawn`: ele recebe só o multiplicador de
dano do Cryo (o trio ali viraria 12 projéteis).

## Os dois gatilhos do estouro

1. **Pavio queimado** (alvo vivo) — `EntityManager._update_cryo_linger` devolve
   `True`, `_tick_cryo` chama `queue_cryo_detonation`, e
   `Collisions.cryo_bombs_vs_enemies` consome a fila **no mesmo frame**. Precisa
   passar pelo passe de colisão porque o estouro aplica dano, e dano vai pelo
   roteador único (§8).
2. **Morte cristalizado** — `CollisionPhysics.apply_hit`/`apply_ship_contact`
   chamam `entity_manager.burst_cryo_bomb(target)` na hora. Alvo morto não tem
   dano a receber, então é só efeito + leque, e o `EntityManager` resolve
   sozinho. **De propósito não enfileira:** o alvo morre DURANTE o passe de
   colisão, e um item enfileirado ali só seria lido no frame seguinte — depois
   de o `cleanup` (que roda dentro do `update`) já poder tê-lo devolvido ao pool.
   O dano cairia no inimigo que herdou o slot.

`_consume_cryo_marks` zera as marcas no instante do estouro: é o que garante
**uma detonação por alvo** e faz os cristais sumirem no mesmo frame. A fila
`cryo_detonations` também é limpa no INÍCIO de todo `update` — nenhum item
atravessa o frame em que nasceu (frame sem passe de colisão: fim de fase,
transição).

## Boss e miniboss: cristalizam, nunca congelam

A regra mora em **`EntityManager._cryo_multiplier`** (devolve 1.0 para
`is_boss`), **não** no guard da marca. Por isso existe `accepts_cryo` ao lado de
`can_be_controlled` em `control_marks.py`: são iguais menos o opt-out de boss.

É a lentidão que dessincroniza padrão roteirizado e peça coreografada — a marca
em si não faz mal. Assim o chefe acumula cargas, ganha os cristais, detona e
paga o dano (com o `BOSS_UPGRADE_DAMAGE_MULTIPLIER` global), sem que a IA ou o
ritmo da luta sejam tocados.

## Os fragmentos são `Bullet`, não entidade nova

`ice_shard=True` numa bala do pool: reusa pool, colisão, crédito de kill e
gravity wells de graça. O que muda por flag:

- geometria/velocidade próprias (não herda `bullet_speed_mult` nem Giant Shot);
- `shard_life` (0.4s) — o alcance é por TEMPO, senão o estouro vira salva grátis;
- sem perfuração (`_owner_pierce_count`);
- **não propaga upgrades do dono** — gate em `projectiles_vs_enemies` e
  `_project_into_boss`. Sem isso o caco herdaria o Cryo e a cascata seria
  infinita (gela → bomba → cacos → gela...), além de disparar cadeia/implosão
  oito vezes por estouro;
- `shard_source_id` — o alvo que estilhaçou não é atingido pelos próprios cacos
  (num boss, de raio largo, o leque inteiro voltaria para dentro do corpo).

O dono das cargas (`cryo_owner`, marca de controle) sobrevive no alvo para o
leque sair com a cor do jogador certo e creditar o kill a ele em coop.

## Cristais

`cryo_crystals.py` continua sem entidade nem buffer. A dissolução por alpha
saiu (gelo não dissolve mais, ele detona) e virou **carga**: na janela final
(`CRYO_CRYSTAL_CHARGE`) clareia rumo ao branco, incha e cintila mais rápido — o
tell do estouro. Como não há mais alpha parcial, sumiu o `Surface` SRCALPHA por
alvo por frame.

Para alvo grande (boss) o gelo cresce em **número**, não em tamanho: tetos em
pixels (`CRYO_CRYSTAL_MAX_LENGTH/WIDTH`) + `crystal_count` pelo perímetro. Sem
isso, 0.5×raio num boss de 90px vira lâmina de 45px cobrindo a arena.

Testes: `tests/test_cryo_shot.py` (`TestBombaDeGelo` cobre o ciclo, as travas de
cascata e a fila que não atravessa o frame).
