# Plano: Fase de Transição "Entering and Exiting the Atmosphere"

> Interstício jogável e **longo** entre dois mundos, representando a nave entrando
> ou saindo da atmosfera de um planeta. **Não é um nível numerado** — vive no fluxo
> de transição de mundo, entre duas cutscenes. Status: **planejado** (2026-05-26).

---

## 1. Conceito e decisões travadas

| Decisão | Valor |
|---|---|
| Estrutura | Interstício (fora de `FIXED_LEVELS` e da numeração de níveis) |
| Fluxo | `Mundo X → cutscene 1 → interstício → cutscene 2 → Mundo Y` |
| Quando dispara | Só quando **um dos lados é sideral** (`WorldTheme.STARFIELD`) |
| Direção | espaço→planeta = **Entering** (nave em cima, atira pra baixo, facing `south`); planeta→espaço = **Exiting** (nave embaixo, atira pra cima, facing `north`) |
| planeta→planeta | **Sem interstício** — só a cutscene normal de hoje |
| Inimigos | **Sem atiradores.** Objetivo: desviar + atirar. Meteoros + inimigos custom criados só pra essa fase |
| Fim da fase | **Medidor de altitude/distância** que enche ao longo do percurso (não por kills) |
| Morte (perder todas as vidas) | **Não é game over**: corta a barra de progresso **pela metade** e a fase continua |

Rotas reais na ordem atual de mundos:
- **M→S** (MOUNTAINS→STARFIELD): planeta→espaço = **Exiting**
- **S→C** (STARFIELD→CITY): espaço→planeta = **Entering**
- **C→V** (CITY→VOLCANIC): planeta→planeta = **cutscene normal, sem fase**

---

## 2. O que já existe no motor (reaproveitar)

- **Modo dual por tema** — `is_top_down_mode` / `is_side_scroll_mode` (`game/core/world_config.py`). STARFIELD = top-down vertical; resto = side-scroll.
- **Facing cardinal da nave** — `set_facing("north"/"south"/"east"/"west")`, `get_facing_vector`, e `shoot()` já ramifica por facing. **Atirar pra baixo (`south`) já está implementado.** `apply_world_mode` escolhe o facing default.
- **Spawner parametrizado por orientação** — todo `_spawn_*` em `spawner.py` já faz `if is_side_scroll:` para posicionar o inimigo na borda certa, e tem o ramp de `spawn_intensity`.
- **Hook de transição** — `playing.py`: `_on_advance_level(theme_changed, new_world)` → `_start_world_transition_cutscene` → `_apply_pending_world_transition`. `pending_world_transition` segura o Mundo Y durante toda a transição.

---

## 3. Onde plugar (state machine de transição)

Hoje (`playing.py`, `_on_advance_level` com `theme_changed=True`):

```
_start_world_transition_cutscene(new_world)   # cutscene
... depois ...
_apply_pending_world_transition()             # troca p/ Mundo Y
```

Novo fluxo — adicionar `TransitionPhase.INTERSTITIAL` (e um sub-estado pra cutscene 2):

```
theme_changed=True
  ├─ se rota NÃO qualifica (planeta→planeta):  fluxo atual intacto
  └─ se rota qualifica (um lado sideral):
       _start_world_transition_cutscene()        # cutscene 1 (sair do Mundo X)
       → _start_atmosphere_interstitial(route)    # [NOVO] fase jogável longa
       → _start_world_transition_cutscene()        # cutscene 2 (chegar no Mundo Y)
       → _apply_pending_world_transition()         # finaliza Mundo Y (INTACTO)
```

`pending_world_transition` continua segurando o Mundo Y; só **atraso** o `_apply_pending_world_transition` até interstício + cutscene 2 terminarem. **Zero mudança em numeração, world ranges, `get_world_for_level`, `validate_worlds`.**

---

## 4. Orientação invertida — escopo reduzido

O eixo hoje é binário (`is_side_scroll`). "Entering" é um 3º caso (vertical-invertido). Como os **inimigos da fase são custom**, a maior parte da orientação mora neles:

- **Tiro pra baixo (Entering):** `ship.set_facing("south")` — já funciona no `shoot()`.
- **Inimigos de baixo subindo:** ficam **dentro dos inimigos custom** (spawnam e se movem como quiserem). Não precisa generalizar `is_side_scroll` pelo codebase.
- **Meteoro invertido:** única reutilização hostil. Criar variante/flag de `Meteor` que spawna embaixo e usa `vy` negativo (Entering). No Exiting o meteoro padrão (top→down) serve.
- **Clamp da nave:** restringir à faixa **superior** no Entering / **inferior** no Exiting (ajuste local no movimento + posição de entrada, espelhando `_reset_ship_for_level_entry`).

> ⚠️ **Não registrar os inimigos custom no pipeline normal** (`spawner.py` caps, `core/levels/` allowlist/pressure). Eles são spawnados pelo loop do interstício, não pela progressão. O `GUIA_NOVOS_INIMIGOS.md` vale só para a **classe da entidade** (interface `rect`/`on_hit`/`update` + herdar `EnemyHitMixin`), **não** para as seções 2–5 (registro de progressão).

---

## 5. Modelo de conteúdo (registro por rota)

Fora de `FIXED_LEVELS`. Registro leve:

```python
# classificação: sideral = STARFIELD; planetário = resto
# planeta→espaço = "exiting"; espaço→planeta = "entering"
@dataclass(frozen=True)
class AtmospherePhaseConfig:
    facing: str                       # "south" (entering) | "north" (exiting)
    inverted_vertical: bool           # True no entering
    altitude_length: float            # "distância" total (fase longa)
    spawn_table: dict[type, float]    # {Meteor(variante): t, MeuInimigoEntering: t, ...}
    background: ...                    # background dedicado da fase

ATMOSPHERE_PHASES = {
    "entering": AtmospherePhaseConfig(facing="south", inverted_vertical=True,  ...),
    "exiting":  AtmospherePhaseConfig(facing="north", inverted_vertical=False, ...),
}
```

Durante o interstício, alimento o `spawner` com `spawn_table` em vez do `level_config` normal, reusando o ramp de `spawn_intensity` pra intensificar meteoros no meio do percurso.

---

## 6. Medidor de altitude (fim da fase) + pacing

- Barra de **altitude** (sobe no Entering, desce no Exiting) que enche ao longo de `altitude_length`. Progresso por tempo×velocidade de scroll, não por kills.
- Ao chegar a 100% → dispara **cutscene 2** → `_apply_pending_world_transition`.
- Ondas de meteoros intensificam via `spawn_intensity` na metade do percurso.

---

## 7. Penalidade de morte (regra própria da fase)

Interceptar o game-over **enquanto em `INTERSTITIAL`**:

- Perder **todas as vidas** **NÃO** vai pra `GameState.GAME_OVER`.
- Em vez disso: `progresso_altitude *= 0.5`, limpar hostis na tela, restaurar vidas e retomar a fase a partir do ponto reduzido.
- ⚠️ **Confirmar:** vidas restauradas para quanto? (sugestão: contagem padrão de vidas da run). E há piso da barra (ex.: nunca abaixo de 0%)?

---

## 8. Background (resolve o scroll invertido)

Os backgrounds atuais (`render/backgrounds.py`) têm a direção embutida (`update(dt, speed_mult)` é escalar). Em vez de inverter via `speed_mult` negativo, criar um **background dedicado da fase** (atmosfera: nuvens adensando no Entering, rareando no Exiting) que já rola na direção certa por modo. Mata o problema do scroll e dá identidade visual.

---

## 9. Arquivos a tocar

| Arquivo | Mudança |
|---|---|
| `game/scenes/playing.py` | `TransitionPhase.INTERSTITIAL` + sub-estado da cutscene 2; `_start_atmosphere_interstitial`; atrasar `_apply_pending_world_transition`; loop de update/draw do interstício; clamp/posição da nave; interceptar game-over (penalidade) |
| `game/core/world_config.py` (ou módulo novo `atmosphere_phase.py`) | classificação sideral/planetário; `ATMOSPHERE_PHASES`; função que escolhe a rota |
| `game/entities/meteor.py` | variante/flag `inverted_vertical` (spawn embaixo, `vy` negativo) |
| `game/entities/<inimigos_custom>.py` | novos inimigos da fase (interface mínima; herdar `EnemyHitMixin`) |
| `game/render/backgrounds.py` | background dedicado da atmosfera (entering/exiting) |
| `game/systems/spawner.py` | aceitar `spawn_table` do interstício (ou um caminho de spawn dedicado da fase) |
| HUD/render | medidor de altitude |

---

## 10. Ordem de execução sugerida

```
✅ 1. Classificação de rota + ATMOSPHERE_PHASES (decide entering/exiting)  [base]
✅ 2. Fluxo cutscene1 → fase → cutscene2 (via PLAYING + flag _in_atmosphere) [esqueleto do fluxo]
✅ 3. Fase jogável reusando o loop normal — Exiting (nave entra de baixo,    [gameplay base]
      facing north, meteoros caindo, colisões); fim por altitude → cutscene 2
✅ 4. Medidor de altitude + Barra no HUD: loop visual completo              [HUD]
✅ 5. Meteoros invertidos + Background de nuvens: imersão completa          [visual/entidades]
🟡 6. Inimigos custom da fase + Entering invertido (clamp topo, meteoros subindo)
   7. Penalidade de morte (barra pela metade)                               [regra de falha]
   8. Pacing/intensidade + polimento visual                                 [tuning]
```

Marcos jogáveis: passo 4 fecha o loop (entra/sai mesmo vazio); passo 5 dá um Exiting de verdade; passo 7 fecha a regra de morte.

---

## 11. Pontos a confirmar antes/durante a implementação

- Vidas restauradas após a penalidade de morte (quanto?) e piso da barra de progresso.
- `altitude_length` concreta ("bem longa" = quanto, em segundos/distância?).
- Quantos/quais inimigos custom além dos meteoros.
- Se cutscene 1 e cutscene 2 reutilizam a animação atual de lançamento ou ganham variação (entrar vs sair da atmosfera).

---

## 12. Progresso

### 2026-05-26 — Passos 1 e 2 (base + esqueleto do fluxo)

**Passo 1 ✅ — Classificação de rota.** Criado `game/core/atmosphere_phase.py`:
- `is_sideral(theme)` (STARFIELD = espaço), `classify_route(origin, dest)` →
  `"entering"` / `"exiting"` / `None`, `AtmospherePhaseConfig`, registro
  `ATMOSPHERE_PHASES` e `get_phase_config(route)`.
- Feature flag `ATMOSPHERE_PHASE_ENABLED` (default `True`) para ligar/desligar
  o interstício sem remover o wiring.
- Verificado: M→S = `exiting`, S→C = `entering`, C→V = `None`.

**Passo 2 ✅ — Esqueleto do fluxo `INTERSTITIAL`.**
- `TransitionPhase.INTERSTITIAL` adicionado em `systems/transition_controller.py`
  (+ gate `is_interstitial`).
- `scenes/playing.py`: estado (`_atmosphere_route/_progress/_phase_done`),
  injeção em `_finish_world_transition_cutscene` (se a rota qualifica e não é
  debug → entra no interstício em vez de abrir o painel), métodos
  `_start_atmosphere_interstitial` / `_update_atmosphere_interstitial` /
  `_finish_atmosphere_interstitial`, e dispatch no `update()`. `pending_world_transition`
  segura o Mundo Y; cutscene 2 reusa `_start_world_transition_cutscene`, que então
  segue para o painel → `_apply_pending_world_transition` (intacto).
- Reset do estado em `_on_advance_level` (início de cada troca de tema).
- ⚠️ **Placeholder:** hoje o interstício é só uma **pausa curta**
  (`_INTERSTITIAL_SKELETON_DURATION = 2.5s`, gameplay congelado) — prova o fluxo
  `cutscene1 → fase → cutscene2 → Mundo Y`. Sem orientação invertida real,
  spawns nem medidor de altitude (passos 3–6).
- Verificado: ruff limpo; `playing.py` importa; métodos e enum presentes.

**Como testar in-game (atalho F8):** `F8` foi repropósto — antes era só preview
visual (`debug_mode=True`, que o gate do interstício ignora); agora
`debug_force_world_transition()` força uma transição **real** escolhendo um
destino com rota qualificante (entering/exiting), disparando
`cutscene1 → interstício → cutscene2 → Mundo Y`. Funciona de qualquer nível.
Caveat: não passa por `_on_advance_level`, então só o tema/mundo muda (o número
do nível não avança) — é atalho de teste. Sem F8, também dispara naturalmente nas
fronteiras M→S e S→C. Desligar: `ATMOSPHERE_PHASE_ENABLED = False` em
`game/core/atmosphere_phase.py`.

**Arquivos tocados:** `game/core/atmosphere_phase.py` (novo),
`game/systems/transition_controller.py`, `game/scenes/playing.py`
(F8: `trigger_world_transition_debug_preview` → `debug_force_world_transition`),
`game/systems/gameplay_input_handler.py` (bind F8).

> **Nota de direção:** ir PARA o Espaço Sideral (STARFIELD) a partir de um planeta
> é **Exiting** (nave embaixo, atira pra cima), não Entering. Entering é
> espaço→planeta (ex.: S→C).

### 2026-05-26 — Passo 3 (fase jogável, Exiting)

A fase deixou de ser placeholder congelado. Agora **reaproveita o loop normal**:

- **Modelo:** dropei o `TransitionPhase.INTERSTITIAL` congelado. A fase roda como
  `PLAYING` com a flag `self._in_atmosphere`. `_update_level_logic` gateia a
  progressão (sem boss, sem `enemies_to_clear`) e, em PLAYING, avança o medidor
  de altitude; ao encher → `_finish_atmosphere_interstitial` → cutscene 2.
- **`_start_atmosphere_interstitial`:** seta `is_side_scroll=False`, dá ao
  `enemy_spawner` uma `LevelConfig` de atmosfera (`build_spawn_config` → chuva de
  `Meteor`), e chama `_begin_level_preparation` (nave entra de baixo via
  PREPARING→PLAYING). Exiting = `set_facing("north")`.
- **`_finish_atmosphere_interstitial`:** limpa os meteoros, **restaura o spawner
  para o nível destino** (a fase tinha sobrescrito), rebuild de mini-naves, e
  dispara a cutscene 2.
- **F8 refeito (fiel):** `debug_force_world_transition` agora pula o controller
  para o fim do mundo atual (`current_level_index = boss_level - 1`) e chama
  `_start_next_level()` — dispara o **fluxo real** (theme change → cutscene 1 →
  interstício → cutscene 2 → destino com spawner corretamente setado por
  `start_next_level`). Some o problema do destino stale/inimigos herdados.
  Removidos `_find_debug_atmosphere_target` e `_find_next_world_for_debug_preview`.

**Verificado:** ruff limpo; import ok; `build_spawn_config('exiting')` → `{Meteor: 0.9}`.

### 2026-05-26 — Passo 4 (barra de altitude no HUD)

Barra de progresso integrada ao HUD, fechando o loop visual:

- **RenderFrame:** Adicionados `in_atmosphere`, `atmosphere_progress` e
  `atmosphere_route`.
- **GameRenderer:** Implementado `_render_atmosphere_hud`. Barra centralizada
  com labels dinâmicos ("ALTITUDE" em Exiting / "RE-ENTRY" em Entering) e cores
  distintas (Ciano / Laranja). Exibe porcentagem e preenchimento proporcional.
- **PlayingScene:** Popula o `RenderFrame` com o estado real do interstício.

**Verificado:** HUD aparece apenas durante a fase; labels e cores mudam conforme
a rota; ruff limpo.

### 2026-05-26 — Passo 5 (meteoros invertidos e background dedicado)

Implementada a infraestrutura visual e hostil para a rota de Entering:

- **Meteoros Invertidos:** Adicionado suporte a `inverted_vertical` na classe
  `Meteor`, `MeteorPool` e `EnemySpawner`. No modo Entering, meteoros spawnam no
  fundo da tela e sobem com velocidade negativa.
- **AtmosphereBackground:** Novo background dinâmico com:
    - Gradiente de céu que transita entre Espaço (escuro) e Atmosfera (azul)
      conforme o progresso.
    - `VerticalCloud`: Nuvens procedurais que se movem verticalmente.
    - Direção de scroll inteligente: nuvens descem em Exiting e sobem em Entering.
- **Integração no Renderer:** `Renderer` ganhou `set_atmosphere_mode` e agora
  atualiza o progresso do background via `RenderFrame`.

**Verificado:** Transição de cores suave; scroll vertical consistente com a
direção da nave; meteoros subindo no Entering funcionam corretamente; ruff limpo.

**Pendências conhecidas (próximos passos):**
- **Passo 6:** Inimigos custom da fase + Entering real (nave no topo, clamp).
- Morte = game over normal (penalidade "barra pela metade" é o passo 7).
- `altitude_length = 40s` (em `atmosphere_phase.py`) — ajustável para teste.
