# Plano de Melhorias: Balanceamento e Game Feel

Este documento detalha as três propostas estruturais para aprimorar o balanceamento do jogo, focando na experiência multiplayer, na curva de tensão e no desafio em níveis avançados.

> **Auditoria 2026-05-24:** todos os 3 itens validados em runtime. 1 bug latente
> no Item 1 foi corrigido (`player_count` agora atualiza dinamicamente quando P2
> entra/sai). Item 3 teve sua propagação completada nesta data — antes só estava
> definido no `difficulty.py` mas não chegava às entidades (rodava em modo no-op).

---

## 1. Escalonamento do Multiplayer nas Fases Comuns (Curto Prazo / Urgente) - [IMPLEMENTADO ✅]

**O Problema Atual:**
Enquanto os chefes (Bosses) recebem um multiplicador de +40% de vida (`_COOP_BOSS_HP_PER_EXTRA_PLAYER`) para cada jogador extra, as fases comuns (ondas de inimigos) permanecem inalteradas. Como dois jogadores possuem o dobro do poder de fogo (dano), as fases normais no modo cooperativo tornam-se desproporcionalmente fáceis e terminam rápido demais.

**A Solução Proposta:**
Implementar modificadores no `LevelConfig` e no `Spawner` sensíveis à quantidade de jogadores ativos.
*   **Volume da Horda:** Aumentar a quantidade de inimigos necessários para passar de fase (`enemies_to_clear`) em um percentual fixo por jogador extra (ex: +35%).
*   **Frequência (Ponderado):** Reduzir levemente o `spawn_time` base aumentando o multiplicador de cadência (ex: +20% mais rápido) para que a tela não fique vazia rapidamente devido à alta taxa de abate da dupla.

**Validação runtime** (fase procedural nível 5, NORMAL):

| Métrica | Solo | Coop (2P) | Ratio |
|---|---|---|---|
| `enemies_to_clear` | 80 | 108 | **1.350×** (esperado 1.35) |
| `spawn_time` (RockGlider) | 1.540s | 1.284s | **-16.7%** (esperado -16.7% = 1/1.20) |

**Arquivos modificados:**
*   `game/scenes/playing.py` — calcula `player_count` e passa em 2 pontos
*   `game/core/levels/_legacy.py` — `coop_enemies_multiplier` + `coop_spawn_multiplier` aplicados em 3 caminhos (fixed level, force_meteor_storm, procedural)
*   `game/systems/level_progression_controller.py` — armazena `_player_count` e propaga em `get_adjusted_level_config`

**🔧 Bug corrigido em 2026-05-24:**
`_player_count` era congelado no `__init__` do controller. Quando P2 entrava
mid-game via `_join_p2` (ou saía via `_remove_p2_slot`), as próximas fases
continuavam sendo geradas com o valor antigo — sem rebalanceamento. Adicionado
método `LevelProgressionController.set_player_count(count)` que é chamado nos
2 pontos de entrada/saída do P2. A fase ATUAL mantém o valor anterior (mudar
inimigos vivos seria confuso); novo valor passa a valer na próxima transição.

---

## 2. Diretor de Ondas - Dinâmica de Tensão (Médio Prazo) - [IMPLEMENTADO ✅]

**O Problema Atual:**
O sistema procedural utiliza intervalos matemáticos rígidos (ex: tenta spawnar a cada 0.25s, com gaps fixos). Isso gera um fluxo de inimigos constante e monótono (uma "linha reta" de tensão). O jogador nunca tem um momento claro de alívio ou um pico extremo de adrenalina justificado.

**A Solução Proposta:**
Inspirado em sistemas como o "Diretor" de *Left 4 Dead*, implementar ciclos de "Pico e Descanso" (Pacing) no `Spawner`.
*   **Fase de Agressão (Ex: 15-20s):** O spawner ignora parcialmente os gaps globais e tenta saturar a tela até o cap máximo permitido.
*   **Fase de Respiro (Ex: 5-8s):** O spawner entra em "cooldown", reduzindo a taxa de spawn quase a zero. Isso permite que o jogador limpe a tela, colete powerups e recarregue a tensão mental antes da próxima onda.

**Implementação real** (FSM em `spawner.py:278-1017`):

| Estado | Duração (random) | `spawn_intensity` | `director_intensity_mult` |
|---|---|---|---|
| BUILDUP | 8–12s | rampa 0.2 → 1.0 | 1.0 |
| PEAK | 12–18s | 1.0 (saturação) | 1.10 |
| REST | 4–7s | 0.1 (quase zero) | 0.50 |

**Notas vs. plano original:**
*   PEAK ficou 12-18s (plano dizia 15-20s) — espírito preservado, range mais amplo
*   REST ficou 4-7s (plano dizia 5-8s) — espírito preservado
*   PEAK usa mult 1.10 (10% mais agressivo) — conservador; spawn_intensity=1.0 já é o teto, então o boost real vem do intensity
*   REST combina `spawn_intensity=0.1` × `intensity_mult=0.50` ≈ 5% do fluxo normal — bate com "quase zero"

**Arquivos modificados:**
*   `game/systems/spawner.py`

---

## 3. Escalonamento de Agressividade (Velocidade) (Médio/Longo Prazo) - [IMPLEMENTADO ✅]

**O Problema Atual:**
O escalonamento procedural e as dificuldades mais altas (NIGHTMARE) focam majoritariamente em aumentar a **quantidade** de inimigos (até o limite do cap) e o **HP** deles. Em níveis muito avançados (ex: mundo 3+, ou dificuldade pesadelo + loop 2), o jogo pode virar um "bullet hell" confuso visualmente ou os inimigos viram "esponjas de dano", tornando o combate maçante.

**A Solução Proposta:**
Introduzir o conceito de "Agressividade" (Aggressiveness) que escala com a dificuldade selecionada. Em vez de apenas mais inimigos com mais vida, os inimigos se tornam mais *letais*.
*   **Velocidade de Movimento:** Inimigos se movem mais rápido (Ex: +20% no Hardcore, +45% no Pesadelo).
*   **Velocidade de Projéteis:** Balas inimigas (como as do Alien) herdam a agressividade e viajam mais rápido.
*   **Cooldown de Ataque:** O tempo entre os tiros dos inimigos (ou tempo de mira do EyeEnemy) é reduzido.

**Valores efetivos por preset:**

| Preset | `aggressiveness_multiplier` | Exemplo: Alien `speed_y` (base 60) | Meteor `vy` (base 100) |
|---|---|---|---|
| CASUAL | 0.85 | 51 | 85 |
| NORMAL | 1.00 | 60 | 100 |
| HARDCORE | 1.20 | 72 | 120 |
| NIGHTMARE | 1.45 | **87** | **145** |

**🔧 Bug corrigido em 2026-05-24:**
Originalmente, o multiplier ESTAVA definido em `difficulty.py` e ERA passado ao
`Spawner`, mas **não chegava às entidades** — o Spawner criava `EyeEnemy(x, y)`,
`Meteor(...)`, `RockGlider(...)`, `GuidedMeteor(...)` e `Formation(Alien, ...)`
sem propagar o parâmetro. Resultado: o sistema rodava em modo no-op, todas as
entidades usavam o default `1.0` independente da dificuldade selecionada.

**Propagação completa agora** (cobertura end-to-end):
*   **Pools** (`MeteorPool`, `RockGliderPool`): armazenam multiplier no `__init__`, aplicam via `reset()` ou no constructor em todas as code paths (free-list, criação nova, fallback de pool cheio)
*   **EntityManager**: recebe via PlayingScene e propaga aos pools
*   **Spawner**: passa para `EyeEnemy`, `GuidedMeteor`; usa `enemy_kwargs={"aggressiveness_multiplier": ...}` ao criar `Formation(Alien, ...)`
*   **CloudArchmageBoss**: recebe via construtor e propaga aos RockGliders que invoca
*   **boss_fight_controller**: passa o multiplier do EntityManager ao criar o CloudArchmageBoss

**Arquivos modificados:**
*   `game/core/difficulty.py` (Adicionado `aggressiveness_multiplier`).
*   `game/scenes/playing.py` (Passa o multiplier ao criar EntityManager).
*   `game/systems/entity_manager.py` (Recebe e propaga aos pools).
*   `game/systems/spawner.py` (Propaga ao criar EyeEnemy, GuidedMeteor e Formation).
*   `game/systems/boss_fight_controller.py` (Passa ao criar CloudArchmageBoss).
*   `game/entities/alien.py` (Aplica em `speed_x`, `speed_y`, `shoot_timer` e `AlienBullet`).
*   `game/entities/eye_enemy.py` (Aplica em `speed_x`, `timer`, `aim_duration` e `charge_duration`).
*   `game/entities/meteor.py` (Aplica na velocidade de queda `vy`).
*   `game/entities/meteor_pool.py` (Armazena e propaga em `get()`).
*   `game/entities/rock_glider.py` (Override de `reset` aceita o parâmetro).
*   `game/entities/rock_glider_pool.py` (Armazena e propaga em `get()`).
*   `game/entities/guided_meteor.py` (Aceita e propaga via `super().__init__`).
*   `game/entities/formation.py` (Novo parâmetro `enemy_kwargs` para passar ao construtor de cada inimigo).
*   `game/entities/cloud_archmage_boss.py` (Aceita e usa nos RockGliders spawnados).

---
**Status Geral:** Todas as etapas de balanceamento propostas foram implementadas
e validadas em runtime. Bugs latentes (player_count estático, aggressiveness
sem propagação) foram identificados e corrigidos. Ver
`PLANO_PENDENCIAS_MULTIPLAYER.md` para o checklist completo de fixes
relacionados ao multiplayer.
