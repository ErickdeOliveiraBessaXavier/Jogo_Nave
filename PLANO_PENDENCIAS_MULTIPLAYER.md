# Plano — Pendências Multiplayer + Balanceamento

Itens deixados em aberto na auditoria de multiplayer e na revisão do
`PLANO_BALANCEAMENTO.md`. Cada item lista **sintoma**, **root cause já
investigada**, **direção de fix** e **risco/esforço**.

---

## Status do que JÁ foi feito

✅ Bug 7 — Revive devolve 3 vidas (era 1)
✅ Bug 3 — Engenheiro mantém permanent mini ships em coop transitions
✅ Bug 4 — Caçador special funciona simultaneamente em coop
✅ Bug 2 — Teclado auto-suprime quando 2 gamepads conectados
✅ Bug 6 — Crash `SerpentBlock.collision_circle` em chain shot
✅ Bônus — Logging em arquivo (`%LOCALAPPDATA%\PixelPatrol\game.log`)
✅ Item 3 — Aggressiveness propagado a Meteor, RockGlider, EyeEnemy, Alien (via Formation),
   GuidedMeteor e RockGliders spawned pelo CloudArchmageBoss
✅ Item 5 — `collision_circle` formalizado: fallback no `EnemyHitMixin` e `BossHitMixin`;
   adicionado em `MountainStalagmite` e `MountainStalactite` (também faltava — bomba-relógio)
✅ Item 1 — Detecção de layout adiada pro 1º `JOYAXISMOTION` real (sem race do pump);
   `gp.slot_axis_lt(slot)` per-slot resolve charge/dash em coop com layouts diferentes
✅ Item 2 — Reverberador combo creditado per-projétil: `owner_ship` em Bullet/MiniShipBullet/
   BossLaser/HomingBullet, propagado via `ShootingSystem.fire` e MiniShip/Wingman shooting.
   Cada collision method (projectiles, lasers, homing, beams, chain shot, explosive) credita
   `_credit_kill(projectile)` no owner correto. P2 não rouba combo do P1.
✅ UX — Conflito `p1_prefers_keyboard` + 2 controles: 2º controle fica ocioso ao invés
   de preencher slot 0 e anular preferência. Toggles sensíveis (`gamepad_enabled`,
   `p1_prefers_keyboard`) bloqueados mid-coop com popup informativo. Status visual no
   label mostra contagem real de controles ativos / ociosos.

---

## Pendências

### 1. Bug 1 — Direcionais invertidos após reconectar gamepad

**Sintoma:** Após desconectar e reconectar um controle, eixos analógicos
às vezes ficam invertidos (cursor escorrega pra cima, stick direito vira
trigger, etc).

**Root cause investigada:**

1. **Race em `gamepad.py:_detect_axis_layout`** (linhas 234-280). Quando
   `JOYDEVICEADDED` dispara, `_claim_slot` chama `_detect_axis_layout`
   imediatamente. O `pygame.event.pump()` no início do método tenta
   flushar valores iniciais, mas os eventos `JOYAXISMOTION` iniciais
   (que reportam o repouso `-1` dos triggers) ainda não foram
   processados pelo SDL. Resultado:
   - `get_axis(2)` retorna `0.0` (default), não `-1.0` (trigger em repouso)
   - `get_axis(4)` retorna `0.0`
   - Cai no `else` final → assume XInput
   - Se o controle for PS4: `axis_right_y=4` mapeia pro LT (em repouso `-1`)
     → empurra cursor virtual pra cima constantemente
   - É intermitente porque às vezes o SDL flusha a tempo

2. **`gp.axis_lt` é global slot-0** (`gamepad.py:124`). Eventos do LT do
   P2 nunca casam em `axis != gp.axis_lt` no `gameplay_input_handler.py:276`
   se os dois controles têm layouts diferentes.

**Direção de fix:**

a. **Adiar `_detect_axis_layout`**: em vez de detectar no `_claim_slot`,
   marcar o slot como "layout pendente" e detectar no primeiro
   `JOYAXISMOTION` real que chegar dele. Mais robusto que tentar
   flushar pump.

b. **Expor `gp.slot_axis_lt(slot: int) -> int`** e usar em
   `gameplay_input_handler._handle_gamepad_axis` no lugar de `gp.axis_lt`
   global.

**Arquivos:** `game/core/gamepad.py`, `game/systems/gameplay_input_handler.py`

**Esforço:** 1-2h
**Risco:** Médio — precisa testar com hardware real (XInput + PS4-like).

---

### 2. Bug 5 — Reverberador combo cresce 2x em coop

**Sintoma:** Em coop, o combo do Reverberador escala mais rápido que o
esperado. Cada inimigo abatido conta como kill para TODOS os jogadores
vivos, mesmo quem não atirou.

**Root cause investigada:** `scenes/playing.py:1615-1617`:

```python
for slot in self.roster.alive_slots():
    for _ in range(destroyed):
        slot.ship.register_kill()
```

O comentário acima admite o problema: "Refinar atribuição por dano em
fase futura se preciso." — sabia que estava errado.

Consequências:
- P2 Reverberador ganha combo sem atirar (parasita)
- Em 2× Reverberadores, combo cresce o dobro da velocidade real
- Quebra a fantasia de "combo = recompensa por skill individual"

**Direção de fix:**

Rastrear o `owner_ship` em cada projétil/laser/AOE do jogador. Quando
o kill for confirmado em `CollisionPhysics.apply_hit`, atribuir o
`register_kill()` apenas ao ship dono do projétil.

Mudanças necessárias:
- `Bullet`, `HomingBullet`, `MiniShipBullet`, `PlayerLaser`, `BossLaser`
  ganham campo `owner_ship` (HomingBullet já tem `source_ship` do fix 4)
- `spawn_*` no `EntityManager` aceita e propaga `owner_ship`
- `ShootingSystem` passa `ship` em todos os spawns
- `CollisionPhysics.apply_hit` recebe `owner_ship` ou extrai do
  projétil; chama `owner_ship.register_kill()` em vez do loop global
- Remover o loop em `playing.py:1615-1617`

**Arquivos:** `entities/bullet.py`, `entities/homing_bullet.py`,
`entities/mini_ship_bullet.py`, `entities/player_laser.py`,
`systems/entity_manager.py`, `systems/shooting_system.py`,
`systems/collision_physics.py`, `scenes/playing.py`

**Esforço:** 2-3h
**Risco:** Alto — toca pipeline de dano inteiro. Vai aparecer warning de
`reportPrivateUsage` (`source_ship` no HomingBullet já caminha nessa
direção). Testar bem antes de mergear.

---

### 3. Aggressiveness multiplier não chega às entidades

**Contexto:** No `PLANO_BALANCEAMENTO.md`, o Item 3 está marcado como
`[IMPLEMENTADO]`, mas a propagação está incompleta. O `Spawner` recebe
o multiplicador mas **não passa** ao criar as entidades.

**Pontos quebrados (todos os call sites criam com default `1.0`):**

| Local | Linha | Entidade |
|-------|-------|----------|
| `systems/spawner.py` | 738 | `EyeEnemy(x, y)` |
| `systems/spawner.py` | 1178 | `Formation(Alien, count, ...)` |
| `systems/spawner.py` | 1208 | `GuidedMeteor(...)` |
| `entities/meteor_pool.py` | 86, 104 | `Meteor(...)` |
| `entities/rock_glider_pool.py` | 34, 59, 75 | `RockGlider(...)` |
| `entities/meteor.py` | 325 | `Meteor.create_*` (factory) |
| `entities/cloud_archmage_boss.py` | 1278 | `RockGlider()` spawned by boss |

Resultado: dificuldade Hardcore/Nightmare **não está mais letal** como
deveria — só o HP escala. O combate em níveis altos vira "esponjas de
dano" exatamente como o PLANO_BALANCEAMENTO queria evitar.

**Direção de fix:**

a. **Propagar via Pool** (escalável): `MeteorPool` e `RockGliderPool`
   recebem `aggressiveness_multiplier` no init e armazenam. Quando
   `get()` cria nova instância, passa. Quando reusa, faz
   `meteor.aggressiveness_multiplier = self.aggressiveness_multiplier`
   antes de devolver.

b. **Propagar via Spawner**: spawner recebe `aggressiveness_multiplier`
   no `__init__` (já recebe — só precisa USAR ao criar):
   - `EyeEnemy(x, y, aggressiveness_multiplier=self.aggressiveness_multiplier)`
   - `Formation(Alien, count, ..., enemy_kwargs={"aggressiveness_multiplier": ...})`
     → `Formation.__init__` precisa aceitar kwargs e passar pra `enemy_type(**kwargs)`
   - `GuidedMeteor(..., aggressiveness_multiplier=...)` (precisa adicionar suporte)

c. **CloudArchmageBoss spawned RockGlider**: o boss não tem acesso ao
   spawner. Opções: passar o multiplicador via construtor do boss, ou
   colocar como atributo de cena consultado.

**Arquivos:** `systems/spawner.py`, `entities/formation.py`,
`entities/meteor_pool.py`, `entities/rock_glider_pool.py`,
`entities/cloud_archmage_boss.py`, possivelmente
`entities/guided_meteor.py`

**Esforço:** 1-2h
**Risco:** Baixo-médio — mecânica. Testar que Hardcore/Nightmare ficam
de fato mais rápidos.

---

### 4. Reproduzir + diagnosticar outros crashes do MountainSerpentBoss

**Contexto:** O crash original do usuário (`SerpentBlock.collision_circle`)
foi corrigido. Mas a investigação revelou outros vetores que **podem**
crashar em condições raras:

- **Double-kill no mesmo frame**: P1 e P2 acertam o mesmo `SerpentBlock`
  no mesmo frame. `take_damage` tem guard `if self.dead: return`, mas
  `_apply_hit` chama `target.on_hit` 2x. Segundo `on_hit` em block morto
  retorna `HitResult(killed=False, explosion=10)`. Sem crash óbvio, mas
  vale validar com 2 Caçadores em fire-mode.

- **Pool de explosão estourado**: `spawn_explosion` cria via pool. Se o
  pool tem cap e o boss gera N shards × M players, pode haver pressão.

- **Outros bosses sem `collision_circle`**: replicar o fix em outros
  bosses/blocks que possam ser candidates do chain shot. Risco
  arquitetural — ver item 5 abaixo.

**Esforço:** ~30min se reproduzir; depende do que aparecer no `game.log`.

---

### 5. Tornar `collision_circle` parte explícita do protocolo `Enemy`

**Sintoma preventivo:** O crash do `SerpentBlock` foi um exemplo de
"entidade vai pra `enemies` mas não implementa todo o contrato esperado".
Outros bosses/entidades podem ter o mesmo problema dormente.

**Direção:** Em `systems/collision_protocols.py` (Protocol/Enemy), declarar
`collision_circle() -> tuple[float, float, float]` como método obrigatório.
Adicionar implementação padrão em `EnemyHitMixin` (fallback que usa
`rect.center` e `max(w, h) / 2` como raio) ou raise `NotImplementedError`
forçando explicitação.

Auditar todos os tipos que entram em `entity_manager.enemies`:
- Aliens, Meteoros, EyeEnemy, RockGlider — todos têm
- Bosses (boss.py, spike_boss, slime_boss, cloud_archmage, stone_golem,
  giant_meteor, square_minion, mountain_serpent) — verificar caso a caso
- SerpentBlock — **adicionado neste ciclo**
- BotElemental, ExplosiveMine, MountainGeode, MountainPropeller — todos têm

**Arquivos:** `systems/collision_protocols.py`, `entities/enemy_hit_mixin.py`

**Esforço:** 30min-1h
**Risco:** Baixo — só formaliza contrato existente.

---

## Prioridade sugerida

| # | Item | Valor | Esforço | Sugerido |
|---|------|-------|---------|----------|
| ~~3~~ | ~~Aggressiveness propagation~~ | — | — | ✅ Feito |
| ~~1~~ | ~~Gamepad reconnect~~ | — | — | ✅ Feito |
| ~~5~~ | ~~Formalizar collision_circle~~ | — | — | ✅ Feito |
| ~~2~~ | ~~Reverberador combo coop~~ | — | — | ✅ Feito |
| 4 | Reproduzir crashes restantes | Baixo (ninguém reportou) | 30min+ | 🟡 Quando aparecer log |

---

## Como capturar mais dados antes do próximo ciclo

1. **Rebuilde o exe** com os fixes atuais (`pyinstaller Pixel_Patrol.spec`)
2. **Jogue normalmente** algumas sessões coop, tentando reproduzir cada bug
3. **Anexe `%LOCALAPPDATA%\PixelPatrol\game.log`** quando for retomar —
   o `RotatingFileHandler` mantém histórico até 4 MB
4. Para o **Bug 1** especificamente: tentar desconectar/reconectar
   controles de layouts diferentes (XInput + PS4) e observar logs do
   `_detect_axis_layout` (`"layout XInput"` vs `"layout PS4-like"` vs
   `"layout indetectável"`)
