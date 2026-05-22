# Plano de Melhorias: Balanceamento e Game Feel

Este documento detalha as três propostas estruturais para aprimorar o balanceamento do jogo, focando na experiência multiplayer, na curva de tensão e no desafio em níveis avançados.

## 1. Escalonamento do Multiplayer nas Fases Comuns (Curto Prazo / Urgente) - [IMPLEMENTADO]

**O Problema Atual:**
Enquanto os chefes (Bosses) recebem um multiplicador de +40% de vida (`_COOP_BOSS_HP_PER_EXTRA_PLAYER`) para cada jogador extra, as fases comuns (ondas de inimigos) permanecem inalteradas. Como dois jogadores possuem o dobro do poder de fogo (dano), as fases normais no modo cooperativo tornam-se desproporcionalmente fáceis e terminam rápido demais.

**A Solução Proposta:**
Implementar modificadores no `LevelConfig` e no `Spawner` sensíveis à quantidade de jogadores ativos.
*   **Volume da Horda:** Aumentar a quantidade de inimigos necessários para passar de fase (`enemies_to_clear`) em um percentual fixo por jogador extra (ex: +35%).
*   **Frequência (Ponderado):** Reduzir levemente o `spawn_time` base aumentando o multiplicador de cadência (ex: +20% mais rápido) para que a tela não fique vazia rapidamente devido à alta taxa de abate da dupla.

**Arquivos modificados:**
*   `game/scenes/playing.py`
*   `game/core/levels/_legacy.py`
*   `game/systems/level_progression_controller.py`

---

## 2. Diretor de Ondas - Dinâmica de Tensão (Médio Prazo) - [IMPLEMENTADO]

**O Problema Atual:**
O sistema procedural utiliza intervalos matemáticos rígidos (ex: tenta spawnar a cada 0.25s, com gaps fixos). Isso gera um fluxo de inimigos constante e monótono (uma "linha reta" de tensão). O jogador nunca tem um momento claro de alívio ou um pico extremo de adrenalina justificado.

**A Solução Proposta:**
Inspirado em sistemas como o "Diretor" de *Left 4 Dead*, implementar ciclos de "Pico e Descanso" (Pacing) no `Spawner`.
*   **Fase de Agressão (Ex: 15-20s):** O spawner ignora parcialmente os gaps globais e tenta saturar a tela até o cap máximo permitido.
*   **Fase de Respiro (Ex: 5-8s):** O spawner entra em "cooldown", reduzindo a taxa de spawn quase a zero. Isso permite que o jogador limpe a tela, colete powerups e recarregue a tensão mental antes da próxima onda.

**Arquivos modificados:**
*   `game/systems/spawner.py`

---

## 3. Escalonamento de Agressividade (Velocidade) (Médio/Longo Prazo) - [IMPLEMENTADO]

**O Problema Atual:**
O escalonamento procedural e as dificuldades mais altas (NIGHTMARE) focam majoritariamente em aumentar a **quantidade** de inimigos (até o limite do cap) e o **HP** deles. Em níveis muito avançados (ex: mundo 3+, ou dificuldade pesadelo + loop 2), o jogo pode virar um "bullet hell" confuso visualmente ou os inimigos viram "esponjas de dano", tornando o combate maçante.

**A Solução Proposta:**
Introduzir o conceito de "Agressividade" (Aggressiveness) que escala com a dificuldade selecionada. Em vez de apenas mais inimigos com mais vida, os inimigos se tornam mais *letais*.
*   **Velocidade de Movimento:** Inimigos se movem mais rápido (Ex: +20% no Hardcore, +45% no Pesadelo).
*   **Velocidade de Projéteis:** Balas inimigas (como as do Alien) herdam a agressividade e viajam mais rápido.
*   **Cooldown de Ataque:** O tempo entre os tiros dos inimigos (ou tempo de mira do EyeEnemy) é reduzido.

**Arquivos modificados:**
*   `game/core/difficulty.py` (Adicionado `aggressiveness_multiplier`).
*   `game/systems/spawner.py` (Propaga o multiplicador).
*   `game/entities/alien.py` (Aplica em `speed_x`, `speed_y`, `shoot_timer` e `AlienBullet`).
*   `game/entities/eye_enemy.py` (Aplica em `speed_x`, `timer`, `aim_duration` e `charge_duration`).
*   `game/entities/meteor.py` (Aplica na velocidade de queda `vy`).

---
**Status Geral:** Todas as etapas de balanceamento propostas foram implementadas com sucesso!
