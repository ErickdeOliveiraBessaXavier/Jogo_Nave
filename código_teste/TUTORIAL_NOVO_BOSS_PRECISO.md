# Tutorial: Criando um Novo Boss para o Jogo (Versão Precisa)

> **Versão Atualizada**: Este tutorial está **alinhado com a arquitetura real** do projeto. Diferentes do tutorial anterior, ele documenta os padrões implementados nos 4 bosses existentes.

## Padrões Arquiteturais

### ✅ O Que Você Precisa Saber

1. **Hierarquia de Bosses**: Não existe herança - cada boss é uma classe **independente**
2. **Union Types**: Bosses são gerenciados como: `Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss | None`
3. **Padrão de Retorno**: Cada boss retorna entidades de formas **diferentes**
4. **Visual**: Apenas SlimeBoss usa `sprite_loader` para carregar frames de `.png`. Os demais (Boss, SpikeBoss, GiantMeteorBoss) usam desenho geométrico com `pygame.draw` (círculos, retângulos, polígonos)
5. **Sistema EMP**: Todos os bosses sofrem com o efeito de slowdown do EMP (upgrade ativável que desacelera 65% por 10s). Aplicado automaticamente via multiplicador no `entity_manager.update()` - nenhuma ação necessária

---

## 📊 Comparação de Padrões Existentes

| Boss | Update Retorna | Spawn | Visual | Particularidade |
|------|---|---|---|---|
| **Boss** | `(lasers[], squares[])` | Externo | Geométrico (pygame.draw) | Face tracking |
| **SpikeBoss** | `(spikes[], lasers[])` | Externo | Geométrico (pygame.draw) | Pausa o jogo |
| **SlimeBoss** | `None` | Interno | **Sprite animado** | Recebe EntityManager |
| **GiantMeteorBoss** | `None` | Interno | Geométrico (pygame.draw) | Cai e causa dano área |

---

## 🔌 Sistema EMP Explicado

### O Que É?

**EMP (Electromagnetic Pulse)** é um upgrade ativável do jogador que desacelera todos os inimigos e bosses.

### Como Funciona?

1. **Ativação**: Jogador pressiona tecla do upgrade EMP
2. **Efeito Visual**: Onda expandindo-se do centro da nave (classe `EMPWave`)
3. **Desaceleração**: TODOS os inimigos/bosses ficam a **35% da velocidade** (65% mais lento)
4. **Duração**: 10 segundos
5. **Linger**: Após a onda passar, o slowdown persiste por mais 8 segundos

### Configuração

```python
# Em game/core/upgrades_config.py
EMP_SLOW_FACTOR: float = 0.35          # 35% velocidade = 65% desaceleração
EMP_BASE_DURATION: float = 10.0        # Segundos do efeito principal
EMP_LINGER_DURATION: float = 8.0       # Segundos após onda passar
```

### Como Afeta Novos Bosses

**Automático!** No `entity_manager.update()`, há um multiplicador que verifica:

```python
def emp_mul_for(entity: Any) -> float:
    if not emp_active:
        return 1.0
    return slow_factor  # 0.35
```

Todos os `dt` são multiplicados por este valor. **Você não precisa fazer nada especial** - basta usar `enemy_dt` ao invés de `dt` e o EMP funciona automaticamente.

---

### 1.1 Estrutura Base

Crie `game/entities/fire_boss.py`:

```python
import math
import random
import logging
from typing import List, Tuple

import pygame

from ..core.config import config as Config
from ..core.sound import sound_manager
from ..core.sprite_loader import sprite_loader
from ..core.colors import *


class FireBoss:
    """
    Boss de fogo com ataque de projéteis teleguiados.
    
    Padrão Arc (como Boss original):
    - Spawna entidades EXTERNAS (fireballs)
    - Retorna entidades para o EntityManager adicionar
    - Usa sprite_loader para animações
    - Suporta EMP slowdown automático
    """

    # Cache de frames (carregado uma vez na classe)
    _animation_frames: list[pygame.Surface] | None = None

    @classmethod
    def load_animation_frames(cls) -> list[pygame.Surface]:
        """Carrega e redimensiona sprites de animação."""
        if cls._animation_frames is not None:
            return cls._animation_frames
        
        # ✅ IMPORTANTE: Registrar no sprite_loader para preload
        sprite_loader.register("fire_boss", cls.load_frames_for_preload)
        
        # Carregar se já não estivesse
        return cls._load_frames()

    @classmethod
    def load_frames_for_preload(cls) -> list[pygame.Surface]:
        """Método público para preload."""
        return cls._load_frames()

    @classmethod
    def _load_frames(cls) -> list[pygame.Surface]:
        """Carrega os frames do sprite sheet."""
        # Exemplo: usando sprite sheet com 8 frames em linha
        frames = sprite_loader.load_animation_frames(
            "sprite_boss_fire",  # Nome do arquivo: sprite_boss_fire.png
            8,  # Número de frames horizontais
            "FireBoss"  # Identificador para logging
        )
        cls._animation_frames = frames
        return frames

    def __init__(
        self, 
        x: float, 
        y: float, 
        health: int | None = None,
        difficulty_multiplier: float = 1.0,
    ):
        # ===== POSIÇÃO E TAMANHO =====
        self.w = Config.FIRE_BOSS_WIDTH if hasattr(Config, 'FIRE_BOSS_WIDTH') else 100
        self.h = Config.FIRE_BOSS_HEIGHT if hasattr(Config, 'FIRE_BOSS_HEIGHT') else 80
        self.x = x
        self.y = -self.h  # Começar fora da tela
        self.target_y = y  # Posição final após entrada

        # ===== SAÚDE E ESTADO =====
        self.health = health if health is not None else Config.FIRE_BOSS_HEALTH if hasattr(Config, 'FIRE_BOSS_HEALTH') else 300
        self.max_health = self.health
        self.dead = False
        self.state = "entering"  # Estados: entering, normal, dying
        self.hit_score = 50  # Pontos por acertar o boss

        # ===== MOVIMENTO =====
        self.speed = Config.FIRE_BOSS_SPEED if hasattr(Config, 'FIRE_BOSS_SPEED') else 100
        self.direction = 1
        self.entry_speed = Config.FIRE_BOSS_ENTRY_SPEED if hasattr(Config, 'FIRE_BOSS_ENTRY_SPEED') else 150

        # ===== ATAQUE PATTERN =====
        self.attack_timer = 0.0
        self.attack_cooldown = Config.FIRE_BOSS_ATTACK_COOLDOWN if hasattr(Config, 'FIRE_BOSS_ATTACK_COOLDOWN') else 1.5
        self.attack_pattern = 0  # Padrão de ataque cíclico (0=reto, 1=teleguiado, 2=spread)

        # ===== ANIMAÇÃO =====
        self.animation_frames = self.load_animation_frames()
        self.has_valid_frames = bool(self.animation_frames and len(self.animation_frames) > 0)
        self.current_frame = 0
        self.animation_timer = 0.0
        self.animation_speed = 0.1  # segundos por frame

        # ===== COLISÃO =====
        self.rect = pygame.Rect(x, y, self.w, self.h)

        # ✅ IMPORTANTE: Suporte a EMP (obrigatório)
        self.emp_linger_timer = 0.0

    def update(
        self, 
        dt: float, 
        player_x: float, 
        player_y: float,
    ) -> Tuple[List["Fireball"], List["FlameTrail"]]:
        """
        Atualiza o boss e retorna entidades criadas.
        
        ⚠️ IMPORTANTE:
        - Não recebe entity_manager (ao contrário de SlimeBoss)
        - Retorna entidades para EntityManager adicionar
        - É afetado automaticamente por EMP (não fazer nada especial)
        
        Args:
            dt: Delta time
            player_x: Posição X do jogador
            player_y: Posição Y do jogador
        
        Returns:
            (fireballs_criadas, flame_trails_criadas)
        """
        fireballs: List["Fireball"] = []
        flame_trails: List["FlameTrail"] = []

        if self.state == "entering":
            # Descendo na tela
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.state = "normal"
                self.y = self.target_y

        elif self.state == "normal":
            # Movimento lateral
            self.x += self.speed * self.direction * dt
            
            # Inverter direção ao bater nas bordas
            if self.x <= Config.SCREEN_WIDTH * 0.1 or self.x >= Config.SCREEN_WIDTH * 0.9 - self.w:
                self.direction *= -1

            # Sistema de ataque
            self.attack_timer += dt
            if self.attack_timer >= self.attack_cooldown:
                self.attack_timer = 0.0
                
                # Rotacionar padrão de ataque
                self.attack_pattern = (self.attack_pattern + 1) % 3
                
                # ===== PADRÃO 0: Tiro teleguiado direto =====
                if self.attack_pattern == 0:
                    fireball = Fireball(
                        self.x + self.w / 2,
                        self.y + self.h,
                        player_x,
                        player_y,
                        damage=20
                    )
                    fireballs.append(fireball)
                    
                    # Criar trilha visual
                    trail = FlameTrail(self.x + self.w / 2, self.y + self.h)
                    flame_trails.append(trail)
                
                # ===== PADRÃO 1: Cone de 3 projéteis =====
                elif self.attack_pattern == 1:
                    angles = [-20, 0, 20]  # graus relativos
                    for angle_offset in angles:
                        fb = Fireball(
                            self.x + self.w / 2,
                            self.y + self.h,
                            player_x,
                            player_y,
                            damage=15,
                            angle_offset=angle_offset
                        )
                        fireballs.append(fb)
                
                # ===== PADRÃO 2: Spread em múltiplas direções =====
                elif self.attack_pattern == 2:
                    for angle in range(0, 360, 90):  # 4 direções
                        fb = Fireball(
                            self.x + self.w / 2,
                            self.y + self.h,
                            player_x,
                            player_y,
                            damage=15,
                            fixed_angle=angle
                        )
                        fireballs.append(fb)

        elif self.state == "dying":
            # Animação de morte (opcional - remover se não usar)
            pass

        # ===== ANIMAÇÃO =====
        self.animation_timer += dt
        if self.animation_timer >= self.animation_speed:
            self.animation_timer = 0.0
            self.current_frame = (self.current_frame + 1) % len(self.animation_frames)

        # ===== ATUALIZAR RECT =====
        self.rect.x = self.x
        self.rect.y = self.y

        return fireballs, flame_trails

    def take_damage(self, damage: int):
        """Recebe dano e verifica morte."""
        self.health -= damage
        if self.health <= 0:
            self.dead = True
            self.state = "dying"

    def draw(self, surface: pygame.Surface):
        """Desenha o boss."""
        if not self.has_valid_frames or not self.animation_frames:
            # Fallback: desenho primitivo se sprites não carregarem
            pygame.draw.rect(surface, RED, self.rect)
            return
        
        # Desenhar frame atual
        frame = self.animation_frames[self.current_frame]
        surface.blit(frame, (int(self.x), int(self.y)))
        
        # ===== HUD DO BOSS (barra de vida) =====
        # Barra de fundo
        bar_width = self.w
        bar_height = 8
        bar_x = self.x
        bar_y = self.y - 15
        pygame.draw.rect(surface, DARK_GRAY, (bar_x, bar_y, bar_width, bar_height))
        
        # Barra de vida
        if self.max_health > 0:
            health_width = (self.health / self.max_health) * bar_width
            pygame.draw.rect(surface, RED, (bar_x, bar_y, health_width, bar_height))
            
            # Borda
            pygame.draw.rect(surface, WHITE, (bar_x, bar_y, bar_width, bar_height), 2)
```

### 1.2 Adicionar Constantes em `config.py`

Em `game/core/config.py`, procure a seção de configuração de bosses e adicione:

```python
# ========================================
# FIRE BOSS SETTINGS
# ========================================
FIRE_BOSS_HEALTH: int = 400
FIRE_BOSS_WIDTH: int = 100
FIRE_BOSS_HEIGHT: int = 80
FIRE_BOSS_SPEED: float = 120.0
FIRE_BOSS_ENTRY_SPEED: float = 150.0
FIRE_BOSS_ATTACK_COOLDOWN: float = 1.5
```

---

## Passo 2: Criar as Entidades de Ataque

### 2.1 Criar `game/entities/fireball.py`

```python
import math
import pygame
from ..core.config import config as Config
from ..core.colors import *


class Fireball:
    """Bola de fogo do FireBoss com suporte a diferentes padrões."""

    def __init__(
        self,
        x: float,
        y: float,
        target_x: float,
        target_y: float,
        damage: int = 20,
        angle_offset: float = 0.0,  # Offset em graus para cone
        fixed_angle: float | None = None,  # Ângulo fixo (para spread)
    ):
        self.x = x
        self.y = y
        self.speed = 250  # pixels/segundo
        self.damage = damage
        self.dead = False
        self.lifetime = 0.0
        self.max_lifetime = 10.0  # 10 segundos antes de desaparecer

        # ===== CÁLCULO DE DIREÇÃO =====
        if fixed_angle is not None:
            # Usar ângulo fixo (conversão de graus para radianos)
            radian = math.radians(fixed_angle)
            self.vx = math.cos(radian) * self.speed
            self.vy = math.sin(radian) * self.speed
        else:
            # Calcular direção para o jogador + offset
            dx = target_x - x
            dy = target_y - y
            distance = math.sqrt(dx * dx + dy * dy)

            if distance > 0:
                # Normalizar
                base_angle = math.atan2(dy, dx)
                # Aplicar offset
                offset_rad = math.radians(angle_offset)
                final_angle = base_angle + offset_rad
                
                self.vx = math.cos(final_angle) * self.speed
                self.vy = math.sin(final_angle) * self.speed
            else:
                self.vx = 0
                self.vy = self.speed

        self.rect = pygame.Rect(x - 5, y - 5, 10, 10)

    def update(self, dt: float):
        """Atualiza posição."""
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.lifetime += dt

        self.rect.centerx = self.x
        self.rect.centery = self.y

        # Verificar se saiu da tela ou expirou
        if (
            self.x < -50
            or self.x > Config.SCREEN_WIDTH + 50
            or self.y < -50
            or self.y > Config.SCREEN_HEIGHT + 50
            or self.lifetime >= self.max_lifetime
        ):
            self.dead = True

    def draw(self, surface: pygame.Surface):
        """Desenha a fireball."""
        # Núcleo (vermelho/laranja)
        pygame.draw.circle(surface, (255, 100, 0), (int(self.x), int(self.y)), 6)
        # Brilho exterior (amarelo)
        pygame.draw.circle(surface, YELLOW, (int(self.x), int(self.y)), 3)
```

### 2.2 Criar `game/entities/flame_trail.py`

```python
import pygame
from ..core.colors import *


class FlameTrail:
    """Trilha de fogo deixada pelo FireBoss."""

    def __init__(self, x: float, y: float, radius: float = 15.0):
        self.x = x
        self.y = y
        self.radius = radius
        self.lifetime = 2.0  # 2 segundos
        self.max_lifetime = 2.0
        self.damage = 10
        self.dead = False

        self.rect = pygame.Rect(x - radius, y - radius, radius * 2, radius * 2)

    def update(self, dt: float):
        """Atualiza a trilha."""
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.dead = True

        self.rect.centerx = self.x
        self.rect.centery = self.y

    def draw(self, surface: pygame.Surface):
        """Desenha com fade-out."""
        # Calcular alpha baseado no tempo restante
        alpha_progress = self.lifetime / self.max_lifetime
        
        # Usar surface com alpha para fade
        trail_surface = pygame.Surface(
            (int(self.radius * 2), int(self.radius * 2)), pygame.SRCALPHA
        )
        
        # Cor com alpha
        color = (255, 150, 0, int(150 * alpha_progress))
        pygame.draw.circle(
            trail_surface,
            color,
            (int(self.radius), int(self.radius)),
            int(self.radius)
        )
        
        # Desenhar na tela
        surface.blit(
            trail_surface,
            (int(self.x - self.radius), int(self.y - self.radius))
        )
```

---

## Passo 3: Atualizar o EntityManager

### 3.1 Importar e Adicionar Lista

Em `game/systems/entity_manager.py`, adicione no `__init__`:

```python
# Imports no topo do arquivo
from ..entities.fire_boss import FireBoss
from ..entities.fireball import Fireball
from ..entities.flame_trail import FlameTrail

# ... no __init__, depois de self.boss e outras listas:
self.fireballs: list[Fireball] = []
self.flame_trails: list[FlameTrail] = []
```

### 3.2 Atualizar Tipo de Boss

Em `game/systems/entity_manager.py`, procure por:

```python
self.boss: Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss | None = None
```

E altere para:

```python
self.boss: Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss | FireBoss | None = None
```

### 3.3 Atualizar Método `update()`

Em `game/systems/entity_manager.py`, procure a seção onde os bosses são atualizados:

```python
if self.boss:
    # SpikeBoss retorna (List[Spike], List[SpikeBossLaser])
    if isinstance(self.boss, SpikeBoss):
        # ... código do SpikeBoss
    # SlimeBoss apenas atualiza (internamente spawna drips)
    elif isinstance(self.boss, SlimeBoss):
        # ... código do SlimeBoss
    # GiantMeteorBoss apenas atualiza
    elif isinstance(self.boss, GiantMeteorBoss):
        # ... código do GiantMeteorBoss
    # Boss normal retorna (List[BossLaser], List[BossSquare])
    else:  # isinstance(self.boss, Boss)
        # ... código do Boss normal
```

E adicione **ANTES** do`elif isinstance(self.boss, SlimeBoss)`:

```python
# FireBoss retorna (List[Fireball], List[FlameTrail])
elif isinstance(self.boss, FireBoss):
    fireballs, flame_trails = self.boss.update(
        enemy_dt, player_x, player_y
    )
    if fireballs:
        self.fireballs.extend(fireballs)
    if flame_trails:
        self.flame_trails.extend(flame_trails)
```

### 3.4 Atualizar Método `cleanup()`

Procure pelo método `cleanup()` e adicione:

```python
# Limpar fireballs e flame trails
self.fireballs = [fb for fb in self.fireballs if not fb.dead]
self.flame_trails = [ft for ft in self.flame_trails if not ft.dead]
```

### 3.5 Atualizar Método `draw()`

Procure pela seção `def draw()` e adicione:

```python
# Desenhar fireballs
for fireball in self.fireballs:
    fireball.draw(surface)

# Desenhar flame trails
for trail in self.flame_trails:
    trail.draw(surface)
```

### 3.6 Atualizar Método `clear_for_level_transition()`

Procure e adicione:

```python
self.fireballs.clear()
self.flame_trails.clear()
```

---

## Passo 4: Implementar Colisões em `collisions.py`

Em `game/systems/collisions.py`, adicione:

```python
def bullets_vs_fire_boss(
    self,
    bullets: list[Bullet],
    fire_boss: FireBoss,
    floating_scores: list[FloatingScore],
    entity_manager: "EntityManager",
) -> int:
    """Detecta colisão entre balas do jogador e FireBoss."""
    if not bullets or not fire_boss or fire_boss.dead:
        return 0
    
    score_gain = 0
    
    for bullet in bullets[:]:
        if bullet.rect.colliderect(fire_boss.rect):
            damage = bullet.damage
            fire_boss.take_damage(damage)
            
            # Criar floating score
            floating_scores.append(FloatingScore(bullet.x, bullet.y, damage))
            
            # Efeito visual
            entity_manager.spawn_explosion(bullet.x, bullet.y, size=20)
            
            # Remover bala
            bullets.remove(bullet)
            entity_manager.bullet_pool.release(bullet)
            
            score_gain += damage
    
    return score_gain


def fireballs_vs_ship(
    self,
    ship: "Ship",
    fireballs: list[Fireball],
) -> bool:
    """Detecta colisão entre fireballs e nave."""
    for fireball in fireballs[:]:
        if fireball.rect.colliderect(ship.rect):
            fireballs.remove(fireball)
            return True
    return False


def flame_trails_vs_ship(
    self,
    ship: "Ship",
    flame_trails: list[FlameTrail],
) -> bool:
    """Detecta colisão entre flame trails e nave."""
    for trail in flame_trails[:]:
        if trail.rect.colliderect(ship.rect):
            return True
    return False
```

---

## Passo 5: Atualizar PlayingScene

### 5.1 Importar na Seção de Imports

Em `game/scenes/playing.py`, adicione:

```python
from ..entities.fire_boss import FireBoss
from ..entities.fireball import Fireball
from ..entities.flame_trail import FlameTrail
```

### 5.2 Atualizar Cache de Tipo de Boss

Em `playing.py`, na função `_cache_boss_type()`:

```python
def _cache_boss_type(self):
    """Cachear tipo de boss quando ele spawna"""
    if self.entity_manager.boss:
        from ..entities.giant_meteor_boss import GiantMeteorBoss
        from ..entities.slime_boss import SlimeBoss
        from ..entities.spike_boss import SpikeBoss
        from ..entities.fire_boss import FireBoss

        if isinstance(self.entity_manager.boss, SpikeBoss):
            self._boss_type_cache = "spike"
        elif isinstance(self.entity_manager.boss, SlimeBoss):
            self._boss_type_cache = "slime"
        elif isinstance(self.entity_manager.boss, GiantMeteorBoss):
            self._boss_type_cache = "giant_meteor"
        elif isinstance(self.entity_manager.boss, FireBoss):
            self._boss_type_cache = "fire"
        else:
            self._boss_type_cache = "normal"
    else:
        self._boss_type_cache = None
```

### 5.3 Adicionar Colisões do Boss

Em `playing.py`, na função `_check_boss_collisions()`, adicione **ANTES** do `elif self._boss_type_cache == "slime"`:

```python
elif self._boss_type_cache == "fire":
    from ..entities.fire_boss import FireBoss

    fire_boss = cast(FireBoss, boss)
    score_gain = self.collisions.bullets_vs_fire_boss(
        self.entity_manager.bullets,
        fire_boss,
        self.entity_manager.floating_scores,
        self.entity_manager,
    )
```

### 5.4 Adicionar Dano do Boss à Nave

Em `playing.py`, na função `_check_ship_damage()`, adicione no final:

```python
# ===== COLISÕES COM FIREBALLS E FLAME TRAILS =====
if self.entity_manager.fireballs:
    if self.collisions.fireballs_vs_ship(self.ship, self.entity_manager.fireballs):
        self._handle_ship_hit()

if self.entity_manager.flame_trails:
    if self.collisions.flame_trails_vs_ship(self.ship, self.entity_manager.flame_trails):
        self._handle_ship_hit()
```

---

## Passo 6: Atualizar Levels

### 6.1 Importar em `levels.py`

```python
from ..entities.fire_boss import FireBoss
```

### 6.2 Atualizar Union Type

Em `game/core/levels.py`, procure por:

```python
boss_type: Type[Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss] | None = None
```

E altere para:

```python
boss_type: Type[Boss | SpikeBoss | SlimeBoss | GiantMeteorBoss | FireBoss] | None = None
```

### 6.3 Adicionar Level com FireBoss

Em `FIXED_LEVELS` (em `levels.py`), adicione:

```python
    10: LevelConfig(
        level_number=10,
        enemy_spawn_config={
            Meteor: 1.0,
            Alien: 2.0,
            EyeEnemy: 3.0,
        },
        enemies_to_clear=150,
        boss_type=FireBoss,  # ← Novo boss!
        mines_enabled=True,
        formations_enabled=True,
        theme_name="Vulcão Infernal",
        score_multiplier=1.8,
    ),
```

---

## Passo 7: Criar Arquivo de Sprite (Essencial)

Você precisa fornecer um sprite sheet para o boss funcionar:

1. **Locação**: `game/assets/images/sprite_boss_fire.png`
2. **Dimensões**: 800x80 pixels (8 frames de 100x80)
3. **Formato**: PNG com transparência (ou fazer fallback em `config.py`)

Sem o arquivo PNG, o boss usará fallback de desenho primitivo (retângulo vermelho).

---

## Passo 8: Testes e Validação

### 8.1 Verificar Sintaxe

```bash
python -m py_compile game/entities/fire_boss.py
python -m py_compile game/entities/fireball.py
python -m py_compile game/entities/flame_trail.py
python -m py_compile game/systems/entity_manager.py
python -m py_compile game/systems/collisions.py
python -m py_compile game/scenes/playing.py
```

### 8.2 Testar no Jogo

1. Iniciar o jogo
2. Ir ao nível 10 (ou qualquer nível com FireBoss)
3. Verificar:
   - ✅ Boss aparece do topo
   - ✅ Move lateralmente
   - ✅ Lança fireballs em diferentes padrões
   - ✅ Trilhas de fogo aparecem
   - ✅ Colisão de balas contra boss funciona
   - ✅ FireBalls causam dano à nave
   - ✅ Boss pode ser derrotado
   - ✅ Explosões e efeitos visuais aparecem

### 8.3 Possíveis Erros

| Erro | Solução |
|------|---------|
| `ModuleNotFoundError: No module named 'fire_boss'` | Verificar if `__init__.py` está correto em `game/entities/` |
| `AttributeError: type object 'FireBoss' has no attribute 'boss'` | Typo no tipo de boss em config.py |
| Boss não aparece | Verificar if nível está configurado corretamente em `levels.py` |
| Balas não causam dano | Verificar if `_check_boss_collisions()` está chamando `bullets_vs_fire_boss` |
| Sem sprite visual | Criar/adicionar arquivo `.png` em `game/assets/images/` |

---

## Checklist Final

- [ ] `fire_boss.py` criado com estrutura correta
- [ ] `fireball.py` criado com lógica de movimento
- [ ] `flame_trail.py` criado com fade-out
- [ ] Constantes adicionadas em `config.py`
- [ ] Imports adicionados em `entity_manager.py`
- [ ] Listas `fireballs` e `flame_trails` criadas em Entity Manager
- [ ] Chamada de `update()` do FireBoss adicionada
- [ ] `cleanup()` atualizado
- [ ] `draw()` atualizado
- [ ] Colisões implementadas em `collisions.py`
- [ ] Cache de tipo de boss atualizado em `playing.py`
- [ ] Colisões do boss adicionadas em `playing.py`
- [ ] Colisões da nave com projéteis adicionadas
- [ ] Type hint atualizado em `levels.py`
- [ ] Level com FireBoss criado em `levels.py`
- [ ] Arquivo sprite criado (ou verificado fallback)
- [ ] Testes de compilação passando
- [ ] Boss aparece no jogo
- [ ] Colisões funcionam corretamente

---

## Diferenças Importantes vs Tutorial Anterior

| Aspecto | Tutorial Antigo | Este Tutorial |
|--------|---|---|
| **Herança** | `class FireBoss(Boss)` | `class FireBoss` (nenhuma herança) |
| **Update** | `def update(dt, player_x, player_y)` | Igual, mas padrão documentado |
| **Sprites** | ❌ "Todos usam sprite_loader" | ✅ "Apenas SlimeBoss usa sprites" |
| **Retorno** | Sempre retorna entidades | Documentado: FireBoss retorna, SlimeBoss não |
| **EntityManager** | Novos atributos | Usa padrões existentes |
| **EMP System** | Não menciona | ✅ Explicado: automático, 65% slowdown |

---

## 👀 Opções de Visual para Novo Boss

### Opção 1: Desenho Geométrico (Como Boss, SpikeBoss, GiantMeteorBoss)

Mais simples, sem necesidade de arquivos PNG:

```python
def draw(self, surface: pygame.Surface):
    # Desenhar corpo com pygame.draw
    pygame.draw.rect(surface, RED, (self.x, self.y, self.w, self.h))
    
    # Desenhar olhos
    pygame.draw.circle(surface, YELLOW, (self.x + 20, self.y + 15), 8)
    pygame.draw.circle(surface, YELLOW, (self.x + self.w - 20, self.y + 15), 8)
    
    # Barra de vida
    pygame.draw.rect(surface, DARK_GRAY, (self.x, self.y - 15, self.w, 8))
    health_width = (self.health / self.max_health) * self.w
    pygame.draw.rect(surface, RED, (self.x, self.y - 15, health_width, 8))
```

### Opção 2: Sprite Animado (Como SlimeBoss)

Requer arquivo PNG mas oferece visual melhor:

```python
# Carrega sprite sheet: game/assets/images/sprite_boss_fire.png (800x80 = 8 frames)
self.animation_frames = self.load_animation_frames()
frame = self.animation_frames[self.current_frame]
surface.blit(frame, (int(self.x), int(self.y)))
```

---

## Referências

- [Boss Real](../game/entities/boss.py) - Padrão de boss com face tracking
- [SlimeBoss Real](../game/entities/slime_boss.py) - Padrão com spawning interno
- [SpikeBoss Real](../game/entities/spike_boss.py) - Padrão com pausa de jogo
- [EntityManager](../game/systems/entity_manager.py) - Como entidades são gerenciadas
- [Collisions](../game/systems/collisions.py) - Sistema de colisão com máscara

