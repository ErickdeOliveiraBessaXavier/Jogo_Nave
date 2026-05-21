# Plano — Multiplayer Local Cooperativo

Implementação de coop local para o Space Shooter. Documento vivo: marcar
status conforme cada fase é concluída.

---

## Visão geral

P2 entra mid-game ao apertar Start em um segundo controle. Modal aparece para
escolher nave entre as desbloqueadas pelo perfil de P1. Score é compartilhado;
vidas e power-ups são individuais. Quando um morre, o outro pode reviver
chegando perto da posição da morte e segurando Y por 5 segundos.

---

## Decisões de design (travadas)

| Item | Decisão |
|---|---|
| **Pré-requisito de coop** | **Multiplayer só ativa com 2 gamepads conectados.** Teclado não é dividido entre jogadores (inviável). P1 pode usar teclado ou gamepad; P2 **obrigatoriamente** gamepad |
| Vidas P2 | Mesma quantidade configurada pela dificuldade (igual P1) |
| Power-ups | Quem coleta fica com o efeito — **não compartilhado** |
| Score | **Compartilhado** (continua em `self.score` único) |
| Boss HP em coop | **+40%** com 2 players ativos no momento do spawn |
| Beacon timer | **5 segundos**, **reseta a 0** se o vivo sair do raio |
| Botão de reviver | **Y / Triangle** |
| Beacon radius | 70px |
| Vidas pós-revive | 1 vida + 2s de invuln |
| Game over | Só quando ambos sem vidas **e** sem beacon ativo |
| P2 upgrades permanentes | **Nenhum** — stats base do perfil escolhido |
| Câmera | Continua centrada em P1 |
| HP do boss já spawnado | Não reescala se P2 entrar mid-fight — escaling vale para o próximo boss |

---

## Fases

### Fase 0 — Tipos base (`PlayerSlot`, `PlayerRoster`)

**Esforço:** 0,5 dia · **Risco:** Baixo · **Status:** ✅ Concluída

Arquivo: `game/systems/player_slot.py`. Importável sem erros, sem uso ainda.

Criar `game/systems/player_slot.py`:

```python
@dataclass
class PlayerSlot:
    ship: Ship
    gamepad_slot: int | None         # índice no GamepadManager; None = teclado
    lives: int
    is_dead: bool = False
    revival_beacon: "RevivalBeacon | None" = None
    apply_permanent_upgrades: bool = True   # False para P2

class PlayerRoster:
    def __init__(self, primary: PlayerSlot): ...
    def primary(self) -> PlayerSlot: ...
    def all(self) -> list[PlayerSlot]: ...
    def alive(self) -> list[PlayerSlot]: ...
    def dead(self) -> list[PlayerSlot]: ...
    def add(self, slot: PlayerSlot) -> None: ...
    def remove(self, slot: PlayerSlot) -> None: ...
    def count(self) -> int: ...
```

**Critério de aceite:** módulo criado, importável, sem uso ainda. Build verde.

---

### Fase 1 — Input multi-controle

**Esforço:** 1–2 dias · **Risco:** Médio · **Status:** ✅ Concluída

Arquivos: `game/core/gamepad.py`, `game/core/input.py`.

- `GamepadManager` refatorado para multi-slot (até 2 controles)
- API legada preservada 100% (propriedades `_joystick`, `axis_lt`, `is_active`, `connected` continuam funcionando, todas resolvendo para slot 0)
- Novo: `is_slot_connected(slot)`, `is_slot_active(slot)`, `slot_instance_id(slot)`, `slot_of_instance_id(iid)`, `secondary_connected`
- Read methods (`get_axis`, `get_stick`, `get_trigger`, `is_button_pressed`, `get_dpad`, `rumble`) aceitam `slot` opcional (default 0)
- `JOYDEVICEADDED/REMOVED` agora preenche/libera qualquer slot vazio
- `_detect_axis_layout` agora é por-slot (cada gamepad pode ter layout diferente)
- `Input.poll_held_for(slot)` adicionado — slot 0 inclui teclado, demais slots só gamepad
- `Input.gamepad_movement_vector_for(slot)` adicionado
- Smoke test de boot e API compat passa.

Arquivos: `game/core/gamepad.py`, `game/core/input.py`.

**Mudanças:**
- `GamepadManager` passa a manter `dict[int, pygame.joystick.Joystick]` por
  `instance_id` em vez de um único joystick
- Detectar `pygame.JOYDEVICEADDED` e `JOYDEVICEREMOVED` (hoje ignorados)
- API nova: `gamepad_movement_vector(slot)`, `is_button_pressed(slot, button)`,
  `is_button_held(slot, button)`
- Atribuição de slots: P1 = primeiro controle conectado (ou teclado se nenhum);
  segundo controle vira candidato a P2 mas só ativa após fluxo da Fase 3
- `Input.poll_held_for(slot)` adicionado em paralelo a `poll_held()` (legacy =
  slot 0). Não quebrar caminho single-player
- **Importante:** D-pad de upgrades em `playing.py` continua exclusivo do
  slot P1 (não pode vazar pro P2)

**Critério de aceite:** com 2 controles plugados, console loga
`"P1=instance_id=X, candidato P2=Y"`. Gameplay single-player idêntico.

---

### Fase 2 — Refatorar `self.ship` → `self.roster` 🔥

**Esforço:** 2–3 dias · **Risco:** Alto · **Status:** ✅ Concluída

**Passo 2.1** ✅ `_init_ship()` cria `Ship` localmente e popula
`self.roster = PlayerRoster.with_primary(PlayerSlot(...))`. `self.ship` virou
property → `self.roster.primary().ship`. `gamepad_slot=0` por padrão para P1.

**Passo 2.3** ✅ Conversão das funções de colisão per-player:
- `_check_ship_damage(slot)` — usa `slot.ship` em todas as 11+ chamadas de `X_vs_ship`
- `_check_stone_golem_sweep(em, slot)` — feixe sweep contra slot específico
- `_handle_ship_hit(slot=None)` — opera em `slot.ship` para invuln/shield/combo; decrementa via `_change_lives_for(slot, -1)`; game over checa `slot.lives <= 0` (em Fase 6 vira lógica de beacon)
- Orquestrador `_handle_collisions`: loop `for slot in self.roster.alive_slots()` para `ship_vs_enemies`, `_check_ship_damage`, e `register_kill` do reverberador
- `_sync_lives_for(slot, lives)` e `_change_lives_for(slot, delta)` — primário mirror em `self.lives` para HUD legado

Pendências documentadas para Fase 3+: `mine_explosions`, `fire_zones`,
`ice_poison_zones` e `slime_drip_damage` hoje checam só contra P1 (`self.roster.primary()`).
Refatorar essas pra per-slot exige dedupe de score (cada chamada compartilha
o cômputo de dano a inimigos). Não bloqueia Phase 3.

**Passo 2.4** ✅ `ShootingSystem` per-ship:
- `shoot_cd: float` → `_cooldowns: dict[int, float]` keyed por `id(ship)`
- `is_ready` → `is_ready(ship)` (parametrizado)
- `update(dt)` decrementa todos os cooldowns; `reset()` limpa
- Loop sobre `self.roster.alive_slots()` em `playing.py:_apply_gameplay_actions` para input/move/fire per-slot (`poll_held_for(slot)`, `gamepad_movement_vector_for(slot)`)
- Call site em `gameplay_input_handler.py` atualizado para `is_ready(ship)`

**Critério de aceite (1 slot = idêntico ao single-player):** smoke tests
de import + boot passam. Validação manual de gameplay fica para o usuário.

Esta é a fase mais cara. Estratégia incremental, **commits pequenos**, manter
single-player 100% funcional a cada commit.

**Passo 2.1** — Em `PlayingScene.__init__`, criar
`self.roster = PlayerRoster(PlayerSlot(ship=self.ship, ...))`. Manter
`self.ship` como **property** que retorna `self.roster.primary().ship`.

**Passo 2.2** — Categorizar os ~100 usos de `self.ship`:
- Queries de "nave principal" (HUD, câmera, fundo) → mantêm `self.ship`
- Colisões e damage → loop sobre `self.roster.alive()`
- `_sync_lives` → vira `_sync_lives_for(slot)`
- Spawn de mini-naves, balas, lasers → saber de qual ship parte

**Passo 2.3** — Refatorar `Collisions._handle_collisions()`:
```python
for slot in self.roster.alive():
    self.collisions.ship_vs_enemies(slot.ship, ...)
    self.collisions.enemy_projectiles_vs_ship(slot.ship, ..., grid=...)
```
Score vai pro `self.score` global. Damage afeta `slot.lives` individual.

**Passo 2.4** — `ShootingSystem`: cooldown precisa virar **per-ship**, não
global. Extrair `ShotCooldown` por slot, ou mover `shoot_cd` pro próprio
`Ship`. Decidir quando chegar lá.

**Critério de aceite:** P1 sozinho joga **idêntico** ao single-player atual.
Regressão zero é o critério.

---

### Fase 3 — Fluxo de entrada do P2

**Esforço:** 1 dia · **Risco:** Médio · **Status:** ✅ Concluída

**Arquivos novos:** `game/scenes/p2_ship_select.py` — modal de seleção.

**Fluxo implementado:**
- `PlayingScene.handle_event` intercepta JOYBUTTONDOWN com `event.button == START`
- Verifica via `gamepad.slot_of_instance_id(event.instance_id) == 1` se é o
  segundo controle, `roster.count() < 2` e `gamepad.secondary_connected`
- Se todos True: abre `P2ShipSelectScene` empurrado no states stack
- Modal mostra carrossel filtrado por `player_profile.unlocked_ships`
- Navegação: D-pad ⬅/➡, LS X, A confirma, B cancela
- `_spawn_p2(profile)`: cria `Ship` ao lado de P1, sem entry animation, com
  invuln inicial; adiciona `PlayerSlot(gamepad_slot=1, apply_permanent_upgrades=False)`
  ao roster
- Vidas iniciais = mesma quantidade da dificuldade (decisão travada)

**Render multiplayer:**
- `RenderFrame` ganhou `extra_ships: tuple[Ship, ...]` (default vazio)
- `GameRenderer` desenha P1 e depois itera `extra_ships`
- `_build_render_frame` filtra slots mortos do extra_ships

**Lógica de game-over ajustada (preparação parcial pra Fase 6):**
- `_handle_ship_hit(slot)`: quando `slot.lives <= 0`, marca `slot.is_dead = True`
  (em vez de game-over imediato)
- Game-over real só dispara quando `all(s.lives <= 0 for s in roster.all_slots())`
- Single-player: 1 slot, comportamento idêntico

**Limitações reconhecidas, a tratar em fases seguintes:**
- P2 não pode disparar ações especiais via botões (dash, charge, cycle, cofre) —
  gameplay_input_handler ainda é P1-only. Movement + shoot funcionam por
  `poll_held_for(slot)` da Fase 2
- Powerups ainda vão pra P1 (Fase 4 vai rotear por colisão)
- HUD não mostra P2 (Fase 7)
- Sem beacon de revive (Fase 6) — P2 morto fica permanentemente fora até fim de partida ou level transition

**Trigger:** durante `PlayingScene.update()`, se `roster.count() < 2` **e**
`gamepad.secondary_connected` for True **e** algum controle não-P1 pressionar
Start, abrir modal. Sem segundo gamepad conectado, qualquer tentativa
(teclado ou outro botão) é ignorada — coop exige 2 controles.

**Modal `game/ui/p2_ship_select_modal.py`:**
- Overlay sobre a partida — jogo **pausa**
- Carrossel horizontal de naves desbloqueadas (`profile.unlocked_ships`)
- D-pad/setas navegam, A confirma, B cancela
- Reusar preview de nave de `ship_selection.py` se possível

**Spawn P2:**
- Posição: ao lado de P1, mesma altura
- `Ship(x, y, mouse_control=False, auto_fire=False, profile=selected_profile)`
- **Sem aplicar upgrades permanentes** — flag `apply_permanent_upgrades=False`
  no slot, consultada no `Ship` para skipar bônus de `MetaProgression`
- Auditar `Ship.__init__` linha-a-linha pra garantir stats base limpos
- Vidas: mesma quantidade da dificuldade atual

**Critério de aceite:** com 2 controles plugados, Start no segundo abre modal,
A confirma, P2 spawna ao lado de P1 e se movimenta.

---

### Fase 4 — Power-ups e mini-naves per-player

**Esforço:** 0,5 dia · **Risco:** Baixo · **Status:** ✅ Concluída

**`PowerupSystem` refatorado para receber slot:**
- `apply(kind, slot)` — assinatura agora exige o slot coletor
- `process_collection()` itera `roster.alive_slots()`; primeiro slot a tocar
  no powerup fica com o efeito (`ship_vs_powerups` muta a lista in-place)
- `_apply_life(slot)` → `_change_lives_for(slot, +1)`
- `_apply_shield/double_shot/speed/piercing/damage_boost/chain_shot/repulsion_shield` →
  operam em `slot.ship` (efeito per-coletor)
- `_apply_score_bonus`/`_apply_time_stop` continuam globais (efeito coletivo)
- `_apply_rainbow` thread o slot em todos os subefeitos

**Mini-naves per-slot (follow-up integrado depois):**
- `_build_mini_ships(slot=None)` e `_build_permanent_mini_ships(slot=None)`
  aceitam slot. Filtragem por `MiniShip.player is slot.ship` substitui apenas
  as mini-naves do slot, preservando as de outros
- `_update_ship`: novo loop por slot detecta expiração de `mini_ships_timer`
  e troca temporárias pelas permanentes só desse slot (bloco legado removido)
- `_apply_mini_ships(slot)`: agora opera na nave do coletor
- `_spawn_p2`: chama `_build_permanent_mini_ships(p2_slot)` se profile do P2
  for Engenheiro
- Death/revive: ao morrer, mini-naves do slot são removidas (não orbitam ship
  fantasma); revive restaura as permanentes via `_build_permanent_mini_ships`
- `_remove_p2_slot`: limpa mini-naves do P2 saída voluntária/desconexão

**`_apply_powerup(kind, slot=None)`** atualizado em PlayingScene com default
no primário — preserva o caminho do Cofre (`_activate_stored_powerup`) sem
mudança de comportamento.

- Coleta de `Powerup`: loop sobre roster, primeiro player a tocar fica com o
  efeito (`apply_to(slot.ship)`)
- `MiniShip` recebe `Ship` no construtor — cada player tem seu par
- Magnet/charge-shot/shield: timers já são per-`Ship`, funcionam isolados
- **Sinergia com backlog item #6:** extrair `targeting` compartilhado entre
  Ship e MiniShip facilita aqui

**Critério de aceite:** P2 pega power-up e só ele ganha o efeito. P1 não vê
mudança.

---

### Fase 5 — Boss HP scaling

**Esforço:** 2–4 horas · **Risco:** Baixo · **Status:** ✅ Concluída

`PlayingScene._start_boss_fight` calcula `coop_hp_scale = 1.0 + 0.40 * (player_count - 1)`
no momento do spawn e multiplica `self.enemy_health_multiplier` por ele
antes de passar para `BossFightController.start`. Bosses já em campo não
reescalam — escala vale só pro próximo spawn (decisão travada).

Constante `_COOP_BOSS_HP_PER_EXTRA_PLAYER = 0.40` na classe para fácil
ajuste futuro.

`BossController.spawn_boss(...)` (ou equivalente) consulta
`len(roster.alive())` no momento do spawn:

```python
multiplier = 1.0 + 0.4 * (player_count - 1)
health = base_health * multiplier
```

Passar `max_health` ajustado pro construtor. Barra de vida do boss recalcula
sozinha. **Não reescalar boss já em campo** se P2 entrar mid-fight.

**Critério de aceite:** boss com 2 players ativos nasce com +40% HP. Boss
single-player mantém HP original.

---

### Fase 6 — Sistema de reviver (beacon)

**Esforço:** 1–1,5 dia · **Risco:** Médio · **Status:** ✅ Concluída

**Nova entidade:** `game/entities/revival_beacon.py`:
- `RevivalBeacon(x, y, for_slot)` com `HOLD_TIME_REQUIRED=5.0s`, `RADIUS=70px`
- `tick_hold(dt)`, `reset_progress()`, `update_visual(dt)`, `is_complete`, `contains_point(px,py)`
- `draw(surface)`: círculo translúcido com anel de progresso (preenche em sentido horário) + cruz central + pulso visual

**Integração em `PlayingScene`:**
- `_handle_ship_hit`: quando `slot.lives <= 0`, chama `_spawn_revival_beacon(slot)` (no-op em single-player com 1 slot)
- `_spawn_revival_beacon(slot)`: cria beacon em `(ship.rect.centerx, ship.rect.centery)` e atribui em `slot.revival_beacon`
- `_update_revival_beacons(dt)`: para cada slot morto com beacon, busca um vivo dentro do raio segurando Y; se sim, `tick_hold(dt)`; senão, `reset_progress()`; se `is_complete`, chama `_revive_slot`
- `_find_revive_helper(beacon, alive)`: primeiro vivo dentro do raio com Y segurado
- `_is_revive_button_held(slot)`: gamepad Y do slot + fallback teclado Y para P1
- `_revive_slot(slot)`: reposiciona ship no centro do beacon, `invuln = 2000ms`, `is_dead = False`, vidas = 1, limpa beacon

**Render multiplayer:**
- `RenderFrame`: adicionados `revival_beacons: tuple[RevivalBeacon, ...]` e `primary_alive: bool`
- `GameRenderer`: pula `frame.ship.draw()` quando `primary_alive=False`; renderiza beacons como overlay
- Slots mortos sem beacon (single-player, ou após game over consolidado) ficam invisíveis automaticamente

**Bidirecional:** P1 revive P2 ou P2 revive P1 — qualquer vivo segurando Y dentro do raio do beacon do morto avança o timer.

**Game over:** mantém `all(s.lives <= 0 for s in roster.all_slots())`. Se ambos morrem antes de qualquer revive, game over fecha o ciclo (impossível ativar beacon sem ninguém vivo).

**Defensivo:** `_handle_ship_hit` checa `slot.is_dead` no topo e ignora — protege mine/slime/fire zones ainda P1-only de re-spawnar beacon num slot já morto.

**Novo arquivo: `game/entities/revival_beacon.py`**

```python
class RevivalBeacon:
    HOLD_TIME_REQUIRED: Final[float] = 5.0
    RADIUS: Final[float] = 70.0

    def __init__(self, x: float, y: float, for_slot: PlayerSlot): ...

    def update(self, dt: float, alive_players: list[PlayerSlot],
               button_held_by_slot: dict[PlayerSlot, bool]) -> None:
        # Para cada alive_player dentro do raio E com botão segurado:
        #   hold_progress += dt
        # Se ninguém qualifica neste frame:
        #   hold_progress = 0.0   (RESETA, não pausa)
        # Se hold_progress >= HOLD_TIME_REQUIRED:
        #   emit PlayerRevived(for_slot); marcar para remoção
        ...

    def draw(self, surface: pygame.Surface) -> None:
        # Ícone fantasma + barra circular de progresso + partículas suaves
        ...
```

**Trigger de criação:** em `_on_player_hit(slot)`, se `slot.lives <= 0`:
- `slot.is_dead = True`
- Cria `RevivalBeacon(ship.x, ship.y, slot)`
- Salva em `slot.revival_beacon`
- Esconde sprite e para colisões da nave morta

**Botão de reviver:** **Y / Triangle**. Distinto de tiro/dash.

**Trigger de revive:** ao receber `PlayerRevived(slot)`:
- `slot.lives = 1`
- `slot.is_dead = False`
- Respawn ship em `(beacon.x, beacon.y)` com `invuln = 2.0s`
- `slot.revival_beacon = None`

**Visual:**
- Beacon emite partículas suaves (cor da nave do morto)
- Vivo no raio: anel ao redor preenche conforme progresso
- Vivo sai do raio: anel zera imediatamente

**Critério de aceite:** P2 morre, P1 chega perto, segura Y por 5s, P2 volta
com 1 vida. Se P1 sai do raio antes dos 5s, progresso zera.

---

### Fase 7 — HUD dual

**Esforço:** 0,5 dia · **Risco:** Baixo · **Status:** ✅ Concluída

**Novo dataclass `P2HudInfo`** em `render_frame.py`: `lives`, `is_dead`,
`ship`, `beacon_progress`. `RenderFrame.p2_hud: Optional[P2HudInfo]`.

**`PlayingScene._build_p2_hud_info()`** monta o snapshot. None em
single-player (1 slot só).

**`GameRenderer._render_p2_hud(p2_hud, surface)`**:
- Canto superior direito, abaixo das vidas do P1
- Label "JOGADOR 2" em ciano
- Se vivo: "Vidas: N" e timers de Escudo/Tiro Duplo/Velocidade alinhados à direita
- Se morto: "REVIVE XX%" com cor que pulsa de cinza para ciano conforme `beacon_progress`

`game/render/hud.py` (ou onde estiver o HUD):
- Coluna P1 (atual) + coluna P2 ao lado, com ícone da nave
- Score continua centralizado (compartilhado)
- P2 morto: mostra "REVIVING... XX%" no lugar das vidas
- Power-up timers de P2 num canto separado (oposto ao de P1)

**Critério de aceite:** dois HUDs visíveis e não conflitantes.

---

### Fase 8 — Game over e fim de partida

**Esforço:** 0,5 dia · **Risco:** Baixo · **Status:** ✅ Concluída (junto com 3+6)

A lógica de game over consolidou-se em `_handle_ship_hit`:

```python
is_game_over = all(s.lives <= 0 for s in self.roster.all_slots())
```

**Por que esta condição é suficiente:**
- Single-player (1 slot): equivale ao comportamento original (lives<=0 = game over)
- Coop: se algum slot ainda tem `lives > 0`, ele está vivo (ou poderia ser revivido). Game over só fecha quando todos zeraram
- Beacon sem helper vivo é inerte: se todos zeraram, ninguém ativa o beacon, então game over é o desfecho correto
- A regra `if slot.is_dead: return` no topo de `_handle_ship_hit` evita re-spawn de beacons em slots já marcados como mortos

**Ordem dos efeitos garantida:** dentro de `_handle_ship_hit`, o
`_spawn_revival_beacon(slot)` acontece **antes** do check `is_game_over` —
beacons nascem na morte mesmo no frame do game over, mas se ninguém vivo, a
GameOverScene assume o controle e o beacon nunca é renderizado/ativado.

```python
def _check_game_over(self) -> bool:
    if any(s.lives > 0 and not s.is_dead for s in self.roster.all()):
        return False
    if any(s.revival_beacon is not None for s in self.roster.dead()):
        # Mas só se houver alguém vivo pra ativar o beacon — caso contrário,
        # beacon é inútil e game over imediato
        if any(not s.is_dead for s in self.roster.all()):
            return False
    return True
```

**Crítico:** se P1 morre com beacon ativo e P2 morre antes de reviver,
game over **imediato** (sem alguém vivo, beacon não tem como avançar).

**Critério de aceite:** game over respeita ambas as condições.

---

### Fase 9 — Edge cases e polimento

**Esforço:** 0,5–1 dia · **Risco:** Médio · **Status:** ✅ Concluída (core)

**Tratamentos implementados em `PlayingScene.handle_event`:**

- **`_is_p2_leave_trigger(event)`**: BACK no controle do slot 1 remove P2
  voluntariamente. Score compartilhado preserva (P1 fica com o total).
- **`_is_p2_disconnect(event)`**: JOYDEVICEREMOVED do gamepad do slot 1
  remove P2 automaticamente — evita nave parada na tela sem input.
- **`_remove_p2_slot(reason)`**: descarta beacon ativo se houver e tira o slot
  do roster. Loga o motivo.

**Pause já compatível** com qualquer controle: `_handle_gamepad_button(button)`
em `gameplay_input_handler.py` ignora `instance_id`, então START de P1 ou P2
abre o pause. `PausedScene.handle_event` igualmente aceita qualquer controle
para fechar.

**Boss HP scaling correto na transição P2 sair durante boss:**
- `_start_boss_fight()` lê `roster.all_slots()` no spawn — se P2 sair durante
  boss fight, boss já está em campo e não reescala (decisão travada)
- Próximo boss usa o count atual

**Não-bloqueantes (limitações conhecidas, podem virar polish futuro):**
- Modal de P2 não detecta JOYDEVICEREMOVED — se controle cair durante
  seleção, ESC do teclado cancela
- Mine/fire/ice/slime zones ainda checam apenas P1 — P2 atravessa sem dano
  nessas armadilhas específicas
- Câmera/shake centrados em P1 sempre (sem split-screen — coop é colocalizado)

| Caso | Tratamento |
|---|---|
| Controle de P2 desconecta mid-partida | Pausa modal: "Reconecte ou X para sair"; se sair, ship explode |
| P2 sai voluntariamente | Botão Select/Back → ship explode dignamente, score mantido |
| P2 morre exatamente na hora do boss spawn | Boss escala pra count de `roster.all()` (P2 só temporariamente fora) |
| Câmera/shake | Centrada em P1 sempre |
| Pause | Qualquer player pausa; ambos veem mesmo menu |
| Restart pós game over | Limpa roster, volta pro fluxo single-player |

---

## Ordem de execução recomendada

1. **Fase 0** → **Fase 2** (refatoração-base é pré-requisito de tudo)
2. **Fase 1** em paralelo com Fase 2 (arquivos independentes)
3. **Fase 5** pode ser feita após Fase 2, a qualquer momento
4. **Fases 3, 4, 6, 7, 8** em sequência
5. **Fase 9** ao final

---

## Resumo de esforço

| Fase | Esforço | Risco | Status |
|---|---|---|---|
| 0 — Tipos base (`PlayerSlot`/`PlayerRoster`) | 0,5 dia | Baixo | ✅ Concluída |
| 1 — Input multi-controle | 1–2 dias | Médio | ✅ Concluída |
| 2 — Refatorar `self.ship` → `roster` | 2–3 dias | Alto | ✅ Concluída |
| 3 — Fluxo de entrada P2 (modal) | 1 dia | Médio | ✅ Concluída |
| 4 — Power-ups e mini-naves per-player | 0,5 dia | Baixo | ✅ Concluída |
| 5 — Boss HP +40% | 2–4 h | Baixo | ✅ Concluída |
| 6 — Sistema de reviver (beacon) | 1–1,5 dia | Médio | ✅ Concluída |
| 7 — HUD dual | 0,5 dia | Baixo | ✅ Concluída |
| 8 — Game over rework | 0,5 dia | Baixo | ✅ Concluída |
| 9 — Edge cases | 0,5–1 dia | Médio | ✅ Concluída (core) |

**Total estimado:** ~8–10 dias de trabalho concentrado.

---

## Pós-Fase 9 — Polish entregue

### Per-slot button routing no gameplay_input_handler

`handle(event)` agora propaga `event.instance_id` para os subhandlers de
JOYBUTTON/JOYHAT/JOYAXIS. Novo `_slot_for_instance_id(instance_id)` resolve
qual `PlayerSlot` emitiu o evento.

**Resultado:**
- A/X/Y do controle do P2 → ativam Cofre/cycle_facing **da nave do P2**
- LT do controle do P2 → dash/charge_shot **da nave do P2** (Fantasma/Caçador/Magneto agora funcionais pra P2)
- LB/RB e D-pad ↑ continuam exclusivos do P1 (upgrade select é do perfil dele)
- START de qualquer controle pausa (mantido)
- Estado de calibração e "pressionado" do LT virou dict per slot do gamepad — controles com layouts diferentes calibram independentemente

**Conflito Y vs revive resolvido:** `_slot_inside_any_beacon(slot)` checa se
o jogador está no raio de algum beacon de morto ativo; se sim, o botão Y
**não** ativa Cofre slot 0 (deixa a precedência para o revive contínuo).

### HUD do Cofre — 4 caixas em coop

`_render_storage_slots_hud(p1_ship, surface, p2_ship=None)`:
- Single-player ou só P1 com Cofre: 2 caixas centralizadas (comportamento original)
- Apenas P2 com Cofre: 2 caixas centralizadas com labels Y/A
- Ambos com Cofre: 4 caixas centralizadas com pequena separação visual e labels "P1"/"P2" acima dos grupos
- Hints de tecla: P1 mostra Q/E (teclado), P2 mostra Y/A (gamepad)

---

## Princípios

- **Regressão zero no single-player a cada commit.** Se for impossível
  preservar single-player em um commit intermediário, marcar `WIP` no commit
  e estabilizar no próximo.
- **Commits pequenos por fase.** Cada passo numerado dentro de uma fase
  idealmente vira um commit.
- **Testar manualmente single-player ao fim de cada fase.** Pelo menos: começa
  partida, joga 1 minuto, morre, restart, sai pro menu.
- **Não otimizar prematuramente.** Algumas fases mexem em hot paths
  (colisões, shooting). Otimização vem depois de funcionar.
