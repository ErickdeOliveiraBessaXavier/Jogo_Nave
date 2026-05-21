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

**Esforço:** 2–3 dias · **Risco:** Alto · **Status:** ⏳ Em andamento (Passo 2.1 ✅)

**Passo 2.1** ✅ Concluído. `_init_ship()` cria `Ship` localmente e popula
`self.roster = PlayerRoster.with_primary(PlayerSlot(...))`. `self.ship` virou
property → `self.roster.primary().ship`. `_sync_lives` agora também atualiza
`primary.lives`. Imports passam, todos os ~100 call sites de `self.ship.*`
continuam funcionando via property.

**Passos 2.2-2.4 pendentes** — convertem `_check_ship_damage` (~15 chamadas
de `X_vs_ship(self.ship, ...)`), `ship_vs_enemies`, `_check_boss_collisions`,
`_handle_ship_hit` (precisa receber slot) e cooldown de tiro do
`ShootingSystem` (hoje global, precisa ser per-ship). Com 1 slot, o
comportamento deve ser **idêntico** — loop de 1 = single path.

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

**Esforço:** 1 dia · **Risco:** Médio · **Status:** Pendente

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

**Esforço:** 0,5 dia · **Risco:** Baixo · **Status:** Pendente

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

**Esforço:** 2–4 horas · **Risco:** Baixo · **Status:** Pendente

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

**Esforço:** 1–1,5 dia · **Risco:** Médio · **Status:** Pendente

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

**Esforço:** 0,5 dia · **Risco:** Baixo · **Status:** Pendente

`game/render/hud.py` (ou onde estiver o HUD):
- Coluna P1 (atual) + coluna P2 ao lado, com ícone da nave
- Score continua centralizado (compartilhado)
- P2 morto: mostra "REVIVING... XX%" no lugar das vidas
- Power-up timers de P2 num canto separado (oposto ao de P1)

**Critério de aceite:** dois HUDs visíveis e não conflitantes.

---

### Fase 8 — Game over e fim de partida

**Esforço:** 0,5 dia · **Risco:** Baixo · **Status:** Pendente

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

**Esforço:** 0,5–1 dia · **Risco:** Médio · **Status:** Pendente

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
| 2 — Refatorar `self.ship` → `roster` | 2–3 dias | Alto | ⏳ Passo 2.1 ✅ |
| 3 — Fluxo de entrada P2 (modal) | 1 dia | Médio | Pendente |
| 4 — Power-ups e mini-naves per-player | 0,5 dia | Baixo | Pendente |
| 5 — Boss HP +40% | 2–4 h | Baixo | Pendente |
| 6 — Sistema de reviver (beacon) | 1–1,5 dia | Médio | Pendente |
| 7 — HUD dual | 0,5 dia | Baixo | Pendente |
| 8 — Game over rework | 0,5 dia | Baixo | Pendente |
| 9 — Edge cases | 0,5–1 dia | Médio | Pendente |

**Total estimado:** ~8–10 dias de trabalho concentrado.

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
