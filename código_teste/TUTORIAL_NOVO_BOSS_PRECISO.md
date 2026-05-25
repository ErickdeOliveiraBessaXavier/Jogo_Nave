# Tutorial: Criando um Novo Boss para o Jogo (Versão Polimórfica)

> **Versão Atualizada (2026-05-25)**: Refatoração polimórfica concluída — adicionar
> um boss novo **não exige mais editar cascata `isinstance`** em `EntityManager`
> nem em `BossFightController._cache_boss_type`. O contrato é o `BossProtocol`
> em `game/systems/boss_context.py`. Este tutorial reflete a arquitetura real
> após a conclusão dos itens 1 e 2 do `NOVO_PLANO_DE_REVISÃO.MD`.

## Padrões Arquiteturais

### ✅ O Que Você Precisa Saber

1. **Sem herança forçada** — cada boss é uma classe independente, podendo opcionalmente
   herdar de `BossHitMixin` (`game/entities/boss_hit_mixin.py`) para ganhar o contrato
   de colisão (`take_damage`, `on_hit`, `collision_circle`, `is_boss = True`).
2. **Protocolo unificado** — todo boss implementa o `BossProtocol`:
   - Atributos: `is_boss: bool`, `BOSS_TYPE_NAME: str`, `dead`, `health`, `max_health`, `w`, `h`, `x`, `y`.
   - Método: `update_boss(dt: float, ctx: BossUpdateContext) -> BossUpdateResult`.
3. **Dispatch polimórfico** — `EntityManager._update_boss` (e o caminho de slow-motion)
   chamam `boss.update_boss(dt, ctx)` e roteiam o `BossUpdateResult` via
   `_consume_boss_result()`. Não há mais cascata de `isinstance`.
4. **Identificação por nome** — `BossFightController` consulta `BOSS_TYPE_NAME`
   via `getattr(type(boss), "BOSS_TYPE_NAME", "normal")`. Sem cascata.
5. **Visual** — `SlimeBoss` e `MountainSerpentBoss` usam sprites; os demais
   (`Boss`, `SpikeBoss`, `GiantMeteorBoss`, `StoneGolemBoss`, `CloudArchmageBoss`)
   desenham proceduralmente com `pygame.draw` + pixel maps em ASCII (paletas e
   layouts ficam em arquivos `*_pixel_map.py` dedicados).
6. **Sistema EMP** — aplicado automaticamente via multiplicador em
   `entity_manager._emp_multiplier()`. Nenhuma ação extra no boss.

---

## 📊 Bosses Existentes (Estado Atual)

| Boss | `BOSS_TYPE_NAME` | Mixin | Visual | Especificidade |
|------|------------------|-------|--------|----------------|
| `Boss` | `"normal"` | `BossHitMixin` | Pixel-map procedural | Squares orbitais + laser |
| `SpikeBoss` | `"spike"` | `BossHitMixin` | Pixel-map procedural | Espinhos nas laterais |
| `SlimeBoss` | `"slime"` | (próprio `is_boss`) | Sprite animado | Slime drips + serpent move |
| `GiantMeteorBoss` | `"giant_meteor"` | (próprio `is_boss`) | Procedural | Meteoro que cai |
| `StoneGolemBoss` | `"stone_golem"` | `BossHitMixin` | Pixel-map + FSM | Boulders + debris orbital |
| `MountainSerpentBoss` | `"mountain_serpent"` | `BossHitMixin` | Pixel-map | Blocos laterais + rock bullets |
| `CloudArchmageBoss` | `"cloud_archmage"` | (próprio `is_boss`) | Pixel-map (HAT/BODY/ARM) | Orbes + spawn de RockGlider/Propeller |

---

## 🧩 O Contrato `BossProtocol`

Definido em `game/systems/boss_context.py`:

```python
@dataclass
class BossUpdateContext:
    dt: float
    player_x: float
    player_y: float | None
    entity_manager: EntityManager

@dataclass
class BossUpdateResult:
    new_serpent_bullets: list[Any] = ...  # → em.serpent_bullets
    new_lasers: list[Any] = ...           # → em.boss_lasers
    new_squares: list[Any] = ...          # → em.boss_squares
    new_mines: list[Any] = ...            # → em.boulders   (StoneGolem)
    new_shards: list[Any] = ...           # → em.attack_debris (StoneGolem)
    new_spikes: list[Any] = ...           # → em.spikes     (SpikeBoss)
    spawned_enemies: list[Any] = ...      # → em.enemies
    sound_events: list[str] = ...         # → _dispatch_boss_sound_events

class BossProtocol(Protocol):
    is_boss: bool
    dead: bool
    health: int
    max_health: int
    w: float
    h: float
    x: float
    y: float
    BOSS_TYPE_NAME: str

    def update_boss(self, dt: float, ctx: BossUpdateContext) -> BossUpdateResult: ...
```

### Regras de roteamento

- Cada lista do `BossUpdateResult` vai para um grupo específico do `EntityManager`.
- Se precisar de uma rota nova (ex.: lista nova de `fireballs`), adicione um campo
  a `BossUpdateResult` e estenda `EntityManager._consume_boss_result()`.
- Para mutações fora desse padrão (ex.: sincronizar `orbital_debris` do StoneGolem,
  rotear `RockGlider` para o pool no CloudArchmage), o boss acessa
  `ctx.entity_manager` diretamente dentro do `update_boss` — preferindo,
  porém, manter as listas no resultado quando dá.

---

## 🔌 Sistema EMP (sem mudanças)

EMP continua automático: `EntityManager._emp_multiplier(entity, ...)` multiplica
o `dt` antes de chamar `update_in_context` (inimigos comuns) ou `update_boss`
(bosses). O `ctx.dt` que chega ao seu boss já vem ajustado em slow-motion / EMP /
ice. Não toque nesse caminho.

---

## Passo 1: Criar o Novo Boss

### 1.1 Estrutura Base

Crie `game/entities/fire_boss.py`:

```python
"""FireBoss — boss de fogo procedural.

Adere ao BossProtocol: implementa update_boss(dt, ctx) e devolve um
BossUpdateResult com fireballs em `spawned_enemies` (são entidades — vão para
em.enemies). Se quisesse roteá-las para uma lista dedicada, adicionaria um
campo `new_fireballs` em BossUpdateResult + tratamento em
EntityManager._consume_boss_result.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, List

import pygame

from ..core.config import config as Config
from .boss_hit_mixin import BossHitMixin

if TYPE_CHECKING:
    from ..systems.boss_context import BossUpdateContext, BossUpdateResult


class FireBoss(BossHitMixin):
    """Boss de fogo. Move lateralmente, dispara fireballs em padrões alternados."""

    # === Contrato BossProtocol ===
    BOSS_TYPE_NAME: str = "fire"
    # is_boss vem de BossHitMixin = True

    # Constantes class-level (visíveis externamente, ex.: para HUD ou hit-detect).
    WIDTH: int = 100
    HEIGHT: int = 80
    DEFAULT_HEALTH: int = 400

    def __init__(
        self,
        x: float,
        y: float,
        health: int | None = None,
        difficulty_multiplier: float = 1.0,
        aggressiveness_multiplier: float = 1.0,
    ) -> None:
        # Geometria
        self.w = self.WIDTH
        self.h = self.HEIGHT
        self.x = x
        self.y = -self.h  # entra de cima
        self.target_y = y

        # Saúde
        base = health if health is not None else self.DEFAULT_HEALTH
        self.max_health = int(base * difficulty_multiplier)
        self.health = self.max_health
        self.dead = False

        # Aggressiveness afeta cadência/velocidade de spawn (modos Hardcore/Nightmare).
        self.aggressiveness_multiplier = aggressiveness_multiplier

        # Movimento
        self.speed = 120.0
        self.direction = 1
        self.entry_speed = 150.0

        # Ataque
        self.state = "entering"  # entering | normal
        self.attack_timer = 0.0
        self.attack_cooldown = 1.5 / max(0.5, aggressiveness_multiplier)
        self.attack_pattern = 0

        # rect lazy (BossHitMixin.collision_circle usa o property `rect`)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.dead = True

    # ============================================================
    # CONTRATO BossProtocol
    # ============================================================
    def update_boss(
        self, dt: float, ctx: "BossUpdateContext"
    ) -> "BossUpdateResult":
        """Adaptador polimórfico chamado por EntityManager._update_boss."""
        from ..systems.boss_context import BossUpdateResult

        player_y = ctx.player_y if ctx.player_y is not None else 0.0
        fireballs = self._tick(dt, ctx.player_x, player_y)

        # Fireballs são inimigos do ponto de vista do EntityManager — vão para em.enemies.
        # Se preferir uma lista dedicada, adicione `new_fireballs` em BossUpdateResult
        # e estenda _consume_boss_result.
        return BossUpdateResult(spawned_enemies=list(fireballs))

    # ============================================================
    # Lógica interna (poderia estar inline no update_boss, separamos para clareza)
    # ============================================================
    def _tick(self, dt: float, player_x: float, player_y: float) -> List["Fireball"]:
        from .fireball import Fireball  # import local evita ciclo

        fireballs: List[Fireball] = []
        if self.state == "entering":
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self.state = "normal"
            return fireballs

        # Movimento lateral.
        self.x += self.speed * self.direction * dt
        if self.x <= Config.SCREEN_WIDTH * 0.1:
            self.direction = 1
        elif self.x >= Config.SCREEN_WIDTH * 0.9 - self.w:
            self.direction = -1

        # Tiro com padrões alternados.
        self.attack_timer += dt
        if self.attack_timer >= self.attack_cooldown:
            self.attack_timer = 0.0
            cx = self.x + self.w / 2
            cy = self.y + self.h
            if self.attack_pattern == 0:
                fireballs.append(Fireball(cx, cy, player_x, player_y))
            elif self.attack_pattern == 1:
                for ang in (-20, 0, 20):
                    fireballs.append(
                        Fireball(cx, cy, player_x, player_y, angle_offset=ang)
                    )
            else:  # 2: spread 4-cardeal
                for ang in (0, 90, 180, 270):
                    fireballs.append(
                        Fireball(cx, cy, player_x, player_y, fixed_angle=ang)
                    )
            self.attack_pattern = (self.attack_pattern + 1) % 3

        return fireballs

    def draw(self, surface: pygame.Surface) -> None:
        """Procedural: corpo vermelho + 2 olhos + barra de HP."""
        pygame.draw.rect(surface, (200, 50, 30), self.rect)
        pygame.draw.circle(surface, (255, 230, 80), (int(self.x + 25), int(self.y + 25)), 8)
        pygame.draw.circle(surface, (255, 230, 80), (int(self.x + self.w - 25), int(self.y + 25)), 8)

        # HUD
        bw, bh = self.w, 6
        bx, by = self.x, self.y - 12
        pygame.draw.rect(surface, (40, 40, 40), (bx, by, bw, bh))
        if self.max_health > 0:
            pct = self.health / self.max_health
            pygame.draw.rect(surface, (220, 60, 40), (bx, by, bw * pct, bh))
        pygame.draw.rect(surface, (255, 255, 255), (bx, by, bw, bh), 1)
```

> **Observação importante.** Bosses com pixel-map ASCII em vários parts (como
> `Boss`, `SpikeBoss`, `StoneGolemBoss`, `CloudArchmageBoss`) seguem a
> convenção de externar pixel maps + paletas em `*_pixel_map.py`. Se o seu boss
> usar pixel-map, faça o mesmo: crie `fire_boss_pixel_map.py` com `PIXEL_MAP`,
> `PALETTE`, `CHAR_TO_KEY`, etc.

### 1.2 (Opcional) Constantes em `config.py`

Se quiser parametrizar via `Config`, registre no `ConfigurationManager`. Como o
ciclo anterior migrou `config.py` para dataclasses `frozen=True`, evite
constantes soltas — coloque dentro do dataclass apropriado (`BossConfig` ou
crie um `FireBossConfig` no mesmo padrão).

---

## Passo 2: Entidades de Ataque (Fireball)

Crie `game/entities/fireball.py`:

```python
import math

import pygame

from ..core.config import config as Config


class Fireball:
    """Bola de fogo do FireBoss. Trata-se como inimigo (vai para em.enemies)."""

    is_boss: bool = False

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        damage: int = 20,
        angle_offset: float = 0.0,
        fixed_angle: float | None = None,
    ) -> None:
        self.x = x
        self.y = y
        self.w = self.h = 12
        self.speed = 250.0
        self.damage = damage
        self.dead = False
        self.lifetime = 10.0

        if fixed_angle is not None:
            rad = math.radians(fixed_angle)
        else:
            base = math.atan2(target_y - y, target_x - x)
            rad = base + math.radians(angle_offset)
        self.vx = math.cos(rad) * self.speed
        self.vy = math.sin(rad) * self.speed

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 6), int(self.y - 6), self.w, self.h)

    # Inimigos comuns ganham EMP/ice via update_in_context — implemente se quiser
    # que a fireball desacelere quando o jogador usar EMP.
    def update_in_context(self, ctx) -> None:
        self.update(ctx.sdt)

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.lifetime -= dt
        off = (
            self.x < -50
            or self.x > Config.SCREEN_WIDTH + 50
            or self.y < -50
            or self.y > Config.SCREEN_HEIGHT + 50
        )
        if off or self.lifetime <= 0:
            self.dead = True

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.circle(surface, (255, 100, 0), (int(self.x), int(self.y)), 7)
        pygame.draw.circle(surface, (255, 230, 60), (int(self.x), int(self.y)), 3)
```

---

## Passo 3: Integração com `EntityManager`

### 3.1 Atualizar o union type de `self.boss`

Em `game/systems/entity_manager.py`, expanda a anotação do `self.boss`:

```python
self.boss: Union[
    Boss,
    SpikeBoss,
    SlimeBoss,
    GiantMeteorBoss,
    StoneGolemBoss,
    MountainSerpentBoss,
    CloudArchmageBoss,
    FireBoss,            # ← novo
    None,
] = None
```

E importe `FireBoss` no topo.

### 3.2 Cascata `_update_boss`? **Nada a fazer.**

Esse era o passo doloroso antes. Agora `_update_boss` é polimórfico:

```python
def _update_boss(self, enemy_dt, player_x, player_y) -> None:
    if not self.boss:
        return
    ctx = BossUpdateContext(
        dt=enemy_dt, player_x=player_x, player_y=player_y, entity_manager=self,
    )
    self._consume_boss_result(self.boss.update_boss(enemy_dt, ctx))
```

Como o seu `FireBoss.update_boss` devolve `spawned_enemies=[fireballs]`, o
`_consume_boss_result` já roteia para `self.enemies.extend(...)`. **Zero
edição** em `EntityManager` para o caso comum.

### 3.3 Quando precisar de uma rota nova

Se quisesse manter as fireballs em uma lista **separada** (`em.fireballs` em
vez de misturar com `em.enemies`):

1. Em `EntityManager.__init__`: `self.fireballs: list[Fireball] = []`.
2. Em `EntityManager.cleanup()`: `self._filter_dead_inplace(self.fireballs)`.
3. Em `EntityManager.clear_for_level_transition()`: `self.fireballs.clear()`.
4. Em `BossUpdateResult` (em `boss_context.py`):

   ```python
   new_fireballs: list[Any] = field(default_factory=_empty_any_list)
   ```

5. Em `EntityManager._consume_boss_result`:

   ```python
   if result.new_fireballs:
       self.fireballs.extend(result.new_fireballs)
   ```

6. Em `FireBoss.update_boss`, devolva via o campo novo:

   ```python
   return BossUpdateResult(new_fireballs=list(fireballs))
   ```

7. Atualize o roteamento de roteamento no docstring do `BossUpdateResult`.

### 3.4 `draw()` do EntityManager

Se as fireballs ficarem em `em.enemies`, o `draw()` já lida — `Fireball.draw()`
é chamado pelo loop genérico de inimigos. Se virem uma lista dedicada
`em.fireballs`, adicione um loop de draw no método `draw()` apropriado de
`EntityManager`.

---

## Passo 4: Spawn — `BossFightController._spawn_boss`

A cascata de **identificação por tipo** foi eliminada, mas a de **construção
no spawn** ainda existe (cada boss tem assinatura de construtor diferente). Em
`game/systems/boss_fight_controller.py`, no método `_spawn_boss`, adicione um
ramo:

```python
elif boss_type == FireBoss:
    boss = FireBoss(
        Config.SCREEN_WIDTH / 2 - 50,
        50,
        difficulty_multiplier=enemy_health_multiplier,
        aggressiveness_multiplier=agg,
    )
    self._em.boss = boss
```

E importe `FireBoss` no topo do arquivo (ou no import local no início de
`_spawn_boss`).

### `_cache_boss_type`? **Nada a fazer.**

`_cache_boss_type` consulta `getattr(type(boss), "BOSS_TYPE_NAME", "normal")`
e seu `FireBoss.BOSS_TYPE_NAME = "fire"` já cuida disso.

---

## Passo 5: Colisões (`collisions.py`)

Bosses com `BossHitMixin` herdam `take_damage`/`on_hit`/`collision_circle`, e
o pipeline genérico `projectiles_vs_enemies` em `collisions.py` já trata bosses
quando `entity_manager.boss` é exposto via os mesmos sistemas de hit. Para
**ataques de boss vs nave**:

- Se a fireball está em `em.enemies` e implementa `rect`, o caminho existente
  `enemies_vs_ship` já cobre.
- Para listas dedicadas (`em.fireballs`), adicione um método `fireballs_vs_ship`
  espelhando o padrão `enemy_projectiles_vs_ship`, e chame-o no `playing.py`.

> **Não duplique a verificação de boss `is_boss`** — o `apply_hit` em
> `collision_physics.py` já consulta `getattr(target, "is_boss", False)` e
> suprime `EnemyDestroyed` corretamente.

---

## Passo 6: `PlayingScene` — Caches e Colisões

### 6.1 `_check_boss_collisions`

`PlayingScene` consulta `entity_manager.boss` e despacha colisões. Como o
`BossFightController.boss_type` é setado via `BOSS_TYPE_NAME`, você pode
ramificar pelo string:

```python
if self.boss_controller.boss_type == "fire":
    fire_boss = cast(FireBoss, self.entity_manager.boss)
    # rotear colisões específicas se houver
```

Mas, na maioria dos casos, `projectiles_vs_enemies` + `BossHitMixin.on_hit` já
cobre o hit do jogador no boss. Adicione um ramo aqui só se o boss tiver
hitbox custom (caso do MountainSerpent, com blocos laterais).

### 6.2 Dano da nave por fireballs

Se as fireballs vão para `em.enemies`, o caminho `enemies_vs_ship` já trata.
Se você criou `em.fireballs` separado, chame `fireballs_vs_ship` em
`_check_ship_damage`.

---

## Passo 7: Configurar Level (`core/levels/fixed_levels.py`)

> ⚠️ Após o split do item 4, `core/levels.py` virou `core/levels/` (pacote).
> `FIXED_LEVELS` e `LevelConfig` vivem em **`core/levels/fixed_levels.py`**.

### 7.1 Atualizar o union type do `LevelConfig.boss_type`

Em `game/core/levels/fixed_levels.py`:

```python
boss_type: (
    Type[
        Boss
        | SpikeBoss
        | SlimeBoss
        | GiantMeteorBoss
        | StoneGolemBoss
        | MountainSerpentBoss
        | CloudArchmageBoss
        | FireBoss              # ← novo
    ]
    | None
) = None
```

E importe `FireBoss`:

```python
from ...entities.fire_boss import FireBoss
```

### 7.2 Adicionar entrada em `FIXED_LEVELS`

```python
30: LevelConfig(
    level_number=30,
    enemy_spawn_config={
        Meteor: 1.0,
        Alien: 2.5,
        EyeEnemy: 4.0,
    },
    enemies_to_clear=400,
    boss_type=FireBoss,
    mines_enabled=True,
    formations_enabled=False,
    theme_name="Vulcao Infernal",
    score_multiplier=1.8,
),
```

> Cuidado: os níveis 1, 3, 6, 10, 12, 16, 20 e 25 já têm bosses fixos.
> Escolha um número livre.

---

## Passo 8: Sprites? (Opcional)

A maioria dos bosses desenha proceduralmente. Se o seu boss usa sprite sheet
(como `SlimeBoss`), siga o padrão:

1. Coloque `sprite_boss_fire.png` em `game/assets/images/`.
2. Carregue via `sprite_loader.load_animation_frames(...)` em
   `@classmethod load_animation_frames`.
3. Registre no preload: `sprite_loader.register("fire_boss", cls.load_frames_for_preload)`.

Se for procedural (recomendado para começar), pule este passo.

---

## Passo 9: Validação

### 9.1 Sintaxe + imports

```bash
python -c "from game.entities.fire_boss import FireBoss; print('ok')"
python -c "from game.entities.fireball import Fireball; print('ok')"
python -c "
from game.entities.fire_boss import FireBoss
assert hasattr(FireBoss, 'update_boss'), 'missing update_boss'
assert hasattr(FireBoss, 'BOSS_TYPE_NAME'), 'missing BOSS_TYPE_NAME'
assert FireBoss.BOSS_TYPE_NAME == 'fire'
print('FireBoss adere ao BossProtocol')
"
```

### 9.2 Spawn smoke test

```bash
python -c "
import pygame; pygame.init(); pygame.display.set_mode((1,1))
from game.entities.fire_boss import FireBoss
from game.systems.boss_context import BossUpdateContext, BossUpdateResult

b = FireBoss(100, 100)
# Mock minimo de EntityManager: precisa de .enemies, .spikes, .boss_lasers, etc.
class FakeEM:
    enemies = []
    spikes = []
    boss_lasers = []
    boss_squares = []
    boulders = []
    attack_debris = []
    serpent_bullets = []
    sound_manager = None
    def _dispatch_boss_sound_events(self, e): pass
em = FakeEM()
ctx = BossUpdateContext(dt=0.016, player_x=400, player_y=600, entity_manager=em)
result = b.update_boss(0.016, ctx)
assert isinstance(result, BossUpdateResult)
print('FireBoss.update_boss OK, retornou BossUpdateResult')
pygame.quit()
"
```

### 9.3 Em jogo

1. Inicie o jogo, vá para o nível configurado.
2. Verifique:
   - ✅ Boss entra do topo
   - ✅ Move lateralmente
   - ✅ Atira fireballs em padrões alternados
   - ✅ Toma dano normalmente
   - ✅ Morre + drop de score
   - ✅ EMP desacelera o boss (e as fireballs)
   - ✅ `boss_controller.boss_type == "fire"` durante o fight

---

## Checklist Final

- [ ] `fire_boss.py` criado, implementa `update_boss(dt, ctx) -> BossUpdateResult`
- [ ] `BOSS_TYPE_NAME = "fire"` declarado como class attribute
- [ ] Herda de `BossHitMixin` ou declara `is_boss = True` + `take_damage` + `rect`
- [ ] `fireball.py` criado com `rect` property e `update_in_context` (para EMP)
- [ ] Union type de `EntityManager.self.boss` expandido + import
- [ ] Union type de `LevelConfig.boss_type` em `fixed_levels.py` expandido + import
- [ ] Entrada em `FIXED_LEVELS` adicionada
- [ ] Ramo em `BossFightController._spawn_boss` adicionado
- [ ] (Se aplicável) `BossUpdateResult` ganhou campo novo + roteamento em `_consume_boss_result`
- [ ] Smoke test do `update_boss` passa
- [ ] Validação em-jogo OK

---

## Comparação: Antes (Cascata) vs Agora (Polimórfico)

| Aspecto | Antes (legado) | Agora (após item 1) |
|---------|---------------|---------------------|
| **Update no EntityManager** | `elif isinstance(self.boss, FireBoss): ...` (edita 2 lugares) | Nada — `boss.update_boss(ctx)` |
| **Identificação no Controller** | `elif isinstance(self.boss, FireBoss): self.boss_type = "fire"` | Nada — `getattr(type(boss), "BOSS_TYPE_NAME")` |
| **Roteamento de emissões** | Boss-específico, inline na cascata | Genérico via `BossUpdateResult` |
| **Adicionar boss novo** | Edita `entity_manager.py` (2x) + `boss_fight_controller.py` (1x) | Implementa `update_boss(dt, ctx)` no boss |
| **Slow-motion (game-over)** | Cascata duplicada | Mesmo `update_boss` rodando com `dt * slow_factor` |

---

## Referências

- [BossProtocol + Context](../game/systems/boss_context.py) — Contrato unificado.
- [Boss base](../game/entities/boss.py) — Exemplo com `update_boss` + floating squares.
- [SpikeBoss](../game/entities/spike_boss.py) — Exemplo retornando `new_spikes` + `new_lasers`.
- [SlimeBoss](../game/entities/slime_boss.py) — Boss que muta EntityManager direto (`update_boss` é só adapter).
- [StoneGolemBoss](../game/entities/stone_golem_boss.py) — Exemplo com 3 rotas + sync de `orbital_debris`.
- [CloudArchmageBoss](../game/entities/cloud_archmage_boss.py) — Roteamento custom de spawned (RockGlider, MountainPropeller).
- [BossHitMixin](../game/entities/boss_hit_mixin.py) — Contrato de colisão padrão.
- [EntityManager `_update_boss` + `_consume_boss_result`](../game/systems/entity_manager.py) — Dispatcher polimórfico.
- [BossFightController `_cache_boss_type` + `_spawn_boss`](../game/systems/boss_fight_controller.py) — Identificação via `BOSS_TYPE_NAME`, construção ainda por tipo.
- [Plano de revisão (item 1)](../NOVO_PLANO_DE_REVISÃO.MD) — Contexto da migração polimórfica.
