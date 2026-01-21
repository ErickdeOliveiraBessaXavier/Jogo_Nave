# Tutorial: Criando um Novo Boss para o Jogo

Este tutorial explica passo a passo como criar um novo boss para o jogo. O sistema de bosses é modular e permite diferentes tipos de ataques e comportamentos.

## Visão Geral do Sistema de Bosses

O jogo atualmente suporta três tipos de bosses:
- **Boss**: Boss clássico com lasers e quadrados orbitais
- **SpikeBoss**: Boss com espinhos que disparam projéteis
- **SlimeBoss**: Boss horizontal que derrama slime

Cada boss tem seu próprio arquivo de entidade e lógica específica de colisões.

## Passo 1: Criar a Entidade do Boss

### 1.1 Criar o arquivo da entidade

Crie um novo arquivo em `game/entities/` com o nome do seu boss (ex: `fire_boss.py`).

```python
from .boss import Boss  # Ou não herde se for completamente diferente
from ..core.config import Config
from ..core.colors import *
from typing import List, Tuple
import pygame
import math

class FireBoss:
    """
    Boss de fogo que lança bolas de fogo e deixa trilhas flamejantes.
    """

    def __init__(self, x: float, y: float, health: int = Config.FIRE_BOSS_HEALTH):
        # Posição e movimento
        self.x = x
        self.y = y
        self.w = Config.FIRE_BOSS_WIDTH
        self.h = Config.FIRE_BOSS_HEIGHT

        # Estado
        self.health = health
        self.max_health = health
        self.state = "entering"  # entering, normal, dying
        self.dead = False

        # Movimento
        self.speed = Config.FIRE_BOSS_SPEED
        self.entry_speed = Config.FIRE_BOSS_ENTRY_SPEED

        # Sistema de ataque
        self.attack_timer = 0.0
        self.attack_cooldown = Config.FIRE_BOSS_ATTACK_COOLDOWN

        # Animação
        self.animation_timer = 0.0

        # Rect para colisões
        self.rect = pygame.Rect(x, y, self.w, self.h)

    def update(self, dt: float, player_x: float, player_y: float) -> Tuple[List[Fireball], List[FlameTrail]]:
        """
        Atualiza o boss e retorna entidades criadas.

        Returns:
            Tuple[List[Fireball], List[FlameTrail]]: Projéteis e trilhas criadas
        """
        fireballs: List[Fireball] = []
        flame_trails: List[FlameTrail] = []

        if self.state == "entering":
            # Lógica de entrada na tela
            self.y += self.entry_speed * dt
            if self.y >= Config.FIRE_BOSS_ENTRY_Y:
                self.state = "normal"
                self.y = Config.FIRE_BOSS_ENTRY_Y

        elif self.state == "normal":
            # Movimento lateral
            self.x += self.speed * dt
            if self.x <= 0 or self.x >= Config.SCREEN_WIDTH - self.w:
                self.speed *= -1

            # Ataques
            self.attack_timer += dt
            if self.attack_timer >= self.attack_cooldown:
                self.attack_timer = 0.0
                # Criar fireball
                fireball = Fireball(self.x + self.w/2, self.y + self.h, player_x, player_y)
                fireballs.append(fireball)

                # Criar flame trail
                trail = FlameTrail(self.x + self.w/2, self.y + self.h)
                flame_trails.append(trail)

        # Atualizar animação
        self.animation_timer += dt

        # Atualizar rect
        self.rect.x = self.x
        self.rect.y = self.y

        return fireballs, flame_trails

    def take_damage(self, damage: int):
        """Recebe dano e verifica se morreu."""
        self.health -= damage
        if self.health <= 0:
            self.dead = True
            self.state = "dying"

    def draw(self, surface: pygame.Surface):
        """Desenha o boss."""
        # Corpo principal
        color = RED if self.state == "normal" else ORANGE
        pygame.draw.rect(surface, color, self.rect)

        # Olhos flamejantes
        eye_color = YELLOW
        eye_size = 10
        pygame.draw.circle(surface, eye_color, (self.x + 20, self.y + 15), eye_size)
        pygame.draw.circle(surface, eye_color, (self.x + self.w - 20, self.y + 15), eye_size)
```

### 1.2 Adicionar constantes no config.py

Adicione as constantes do seu boss em `game/core/config.py`:

```python
# FireBoss
FIRE_BOSS_HEALTH = 500
FIRE_BOSS_WIDTH = 80
FIRE_BOSS_HEIGHT = 60
FIRE_BOSS_SPEED = 100
FIRE_BOSS_ENTRY_SPEED = 150
FIRE_BOSS_ENTRY_Y = 50
FIRE_BOSS_ATTACK_COOLDOWN = 2.0
```

## Passo 2: Criar as Entidades de Ataque

### 2.1 Criar Fireball

Crie `game/entities/fireball.py`:

```python
import pygame
import math
from ..core.colors import *

class Fireball:
    """Bola de fogo lançada pelo FireBoss."""

    def __init__(self, x: float, y: float, target_x: float, target_y: float):
        self.x = x
        self.y = y
        self.speed = 200
        self.damage = 20
        self.dead = False

        # Calcular direção para o jogador
        dx = target_x - x
        dy = target_y - y
        distance = math.sqrt(dx*dx + dy*dy)

        if distance > 0:
            self.vx = (dx / distance) * self.speed
            self.vy = (dy / distance) * self.speed
        else:
            self.vx = 0
            self.vy = self.speed

        self.rect = pygame.Rect(x-5, y-5, 10, 10)

    def update(self, dt: float):
        """Atualiza posição da fireball."""
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Atualizar rect
        self.rect.centerx = self.x
        self.rect.centery = self.y

        # Verificar se saiu da tela
        if (self.x < -50 or self.x > Config.SCREEN_WIDTH + 50 or
            self.y < -50 or self.y > Config.SCREEN_HEIGHT + 50):
            self.dead = True

    def draw(self, surface: pygame.Surface):
        """Desenha a fireball."""
        pygame.draw.circle(surface, RED, (int(self.x), int(self.y)), 5)
        # Efeito de brilho
        pygame.draw.circle(surface, YELLOW, (int(self.x), int(self.y)), 3)
```

### 2.2 Criar FlameTrail

Crie `game/entities/flame_trail.py`:

```python
import pygame
from ..core.colors import *

class FlameTrail:
    """Trilha flamejante deixada pelo FireBoss."""

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
        self.lifetime = 3.0  # 3 segundos
        self.damage = 10
        self.dead = False

        self.rect = pygame.Rect(x-15, y-15, 30, 30)

    def update(self, dt: float):
        """Atualiza a trilha flamejante."""
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.dead = True

        # Atualizar rect
        self.rect.centerx = self.x
        self.rect.centery = self.y

    def draw(self, surface: pygame.Surface):
        """Desenha a trilha flamejante."""
        alpha = int((self.lifetime / 3.0) * 255)  # Fade out
        color = (255, 100, 0, alpha)  # Laranja com alpha

        # Criar surface temporária para alpha
        temp_surface = pygame.Surface((30, 30), pygame.SRCALPHA)
        pygame.draw.circle(temp_surface, color, (15, 15), 15)
        surface.blit(temp_surface, (self.x-15, self.y-15))
```

## Passo 3: Atualizar o Sistema de Colisões

### 3.1 Adicionar funções de colisão

Edite `game/systems/collisions.py` e adicione:

```python
def bullets_vs_fire_boss(
    bullets: list[Bullet],
    fire_boss: FireBoss,
    floating_scores: list[FloatingScore],
    entity_manager: EntityManager,
) -> int:
    """Colisão entre balas do jogador e FireBoss."""
    score_gain = 0

    for bullet in bullets[:]:
        if bullet.rect.colliderect(fire_boss.rect):
            damage = bullet.damage
            fire_boss.take_damage(damage)

            # Criar floating score
            floating_scores.append(FloatingScore(bullet.x, bullet.y, damage))

            # Efeito de explosão
            entity_manager.spawn_explosion(bullet.x, bullet.y, size=20, is_slime=False)

            # Remover bala
            bullets.remove(bullet)
            entity_manager.bullet_pool.release(bullet)

            score_gain += damage

    return score_gain

def fireballs_vs_ship(ship: Ship, fireballs: list[Fireball]) -> bool:
    """Colisão entre fireballs e nave do jogador."""
    for fireball in fireballs[:]:
        if fireball.rect.colliderect(ship.rect):
            fireballs.remove(fireball)
            return True
    return False

def flame_trails_vs_ship(ship: Ship, flame_trails: list[FlameTrail]) -> bool:
    """Colisão entre flame trails e nave do jogador."""
    for trail in flame_trails[:]:
        if trail.rect.colliderect(ship.rect):
            # Flame trails não são destruídos ao tocar na nave
            return True
    return False
```

## Passo 4: Atualizar o EntityManager

### 4.1 Adicionar imports

Em `game/systems/entity_manager.py`, adicione:

```python
from ..entities.fire_boss import FireBoss
from ..entities.fireball import Fireball
from ..entities.flame_trail import FlameTrail
```

### 4.2 Atualizar tipos

```python
self.boss: Boss | SpikeBoss | SlimeBoss | FireBoss | None = None
self.fireballs: list[Fireball] = []
self.flame_trails: list[FlameTrail] = []
```

### 4.3 Atualizar método update

Adicione no método `update`:

```python
elif isinstance(self.boss, FireBoss):
    fireballs, flame_trails = self.boss.update(
        enemy_dt, player_x, player_y
    )
    if fireballs:
        self.fireballs.extend(fireballs)
    if flame_trails:
        self.flame_trails.extend(flame_trails)
```

### 4.4 Atualizar limpeza

No método `cleanup`, adicione:

```python
self.fireballs = [fb for fb in self.fireballs if not fb.dead]
self.flame_trails = [ft for ft in self.flame_trails if not ft.dead]
```

### 4.5 Atualizar draw

No método `draw`, adicione:

```python
for fireball in self.fireballs:
    fireball.draw(surface)
for flame_trail in self.flame_trails:
    flame_trail.draw(surface)
```

## Passo 5: Atualizar a PlayingScene

### 5.1 Adicionar imports

Em `game/scenes/playing.py`, adicione:

```python
from ..entities.fire_boss import FireBoss
```

### 5.2 Atualizar _cache_boss_type

```python
elif isinstance(self.entity_manager.boss, FireBoss):
    self._boss_type_cache = "fire"
```

### 5.3 Adicionar colisões

Nas seções de colisão, adicione:

```python
elif self._boss_type_cache == "fire":
    from ..entities.fire_boss import FireBoss

    score_gain = self.collisions.bullets_vs_fire_boss(
        self.entity_manager.bullets,
        cast(FireBoss, self.entity_manager.boss),
        self.entity_manager.floating_scores,
        self.entity_manager,
    )
```

### 5.4 Adicionar dano ao jogador

Na seção de colisões com o jogador, adicione:

```python
# Colisões com fireballs
if self.collisions.fireballs_vs_ship(self.ship, self.entity_manager.fireballs):
    self._handle_ship_hit()

# Colisões com flame trails
if self.collisions.flame_trails_vs_ship(self.ship, self.entity_manager.flame_trails):
    self._handle_ship_hit()
```

## Passo 6: Atualizar os Levels

### 6.1 Adicionar import

Em `game/core/levels.py`, adicione:

```python
from ..entities.fire_boss import FireBoss
```

### 6.2 Atualizar tipos

```python
boss_type: Type[Boss | SpikeBoss | SlimeBoss | FireBoss] | None = None
```

### 6.3 Adicionar nível com FireBoss

```python
FIXED_LEVELS: dict[int, LevelConfig] = {
    # ... outros níveis ...
    10: LevelConfig(
        level_number=10,
        enemy_spawn_config={
            Meteor: 1.0,
            Alien: 2.0,
            EyeEnemy: 3.0,
        },
        enemies_to_clear=200,
        boss_type=FireBoss,
        mines_enabled=True,
        formations_enabled=True,
        theme_name="Boss de Fogo",
        score_multiplier=2.0,
    ),
}
```

## Passo 7: Testes e Debug

### 7.1 Verificar compilação

Execute:
```bash
python -m py_compile game/entities/fire_boss.py
python -m py_compile game/systems/entity_manager.py
python -m py_compile game/scenes/playing.py
```

### 7.2 Testar no jogo

1. Execute o jogo
2. Vá para o nível que tem o FireBoss
3. Verifique se o boss aparece
4. Teste os ataques
5. Verifique colisões

### 7.3 Possíveis problemas

- **Boss não aparece**: Verifique se o nível está correto em levels.py
- **Ataques não funcionam**: Verifique se as entidades são adicionadas ao EntityManager
- **Colisões não funcionam**: Verifique se as funções de colisão estão sendo chamadas
- **Erros de tipo**: Verifique se todos os tipos foram atualizados

## Checklist Final

- [ ] Entidade do boss criada
- [ ] Entidades de ataque criadas
- [ ] Constantes adicionadas ao config
- [ ] Sistema de colisões atualizado
- [ ] EntityManager atualizado
- [ ] PlayingScene atualizado
- [ ] Levels atualizado
- [ ] Código compila sem erros
- [ ] Boss aparece no nível correto
- [ ] Ataques funcionam
- [ ] Colisões funcionam
- [ ] Boss pode ser derrotado

## Dicas Gerais

1. **Mantenha consistência**: Siga o padrão dos bosses existentes
2. **Teste incrementalmente**: Teste cada parte antes de continuar
3. **Use constantes**: Defina tudo em config.py para fácil balanceamento
4. **Documente**: Adicione docstrings explicativas
5. **Reutilize código**: Veja como outros bosses fazem coisas similares
6. **Balanceamento**: Teste diferentes valores de vida, dano e velocidade

## Exemplo Completo

Veja os bosses existentes (Boss, SpikeBoss, SlimeBoss) como referência completa para implementar todas as funcionalidades avançadas como animações, sons, efeitos visuais, etc.</content>
<parameter name="filePath">c:\Users\eobx\OneDrive\Documentos\Jogos_Python\Nave\TUTORIAL_NOVO_BOSS.md