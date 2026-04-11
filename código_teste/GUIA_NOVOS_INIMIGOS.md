# Guia Moderno para Criar Novos Inimigos (v2.0)

Este documento descreve o processo atualizado para adicionar novos inimigos, utilizando **Protocols** (Duck Typing) para simplificar a integração e suporte a sistemas como **EMP (Slow Motion)**.

---

## Passo 1: Criar a Classe do Inimigo

1. **Localização**: `game/entities/nome_do_inimigo.py`
2. **Requisitos do Protocolo `Enemy`**: Para que o jogo reconheça sua classe como um inimigo automaticamente, ela **DEVE** ter estes atributos:
   *   `x, y, w, h` (float/int)
   *   `rect` (propriedade que retorna `pygame.Rect`)
   *   `dead` (bool)
   *   `health` (int)
   *   `get_points_value()` (método que retorna int)
   *   `update(dt, ...)` (método de atualização)

### Estrutura Recomendada:
```python
import pygame
import math
import random
from typing import Tuple, List, Any
from ..core import colors
from ..core.config import config as Config

class NovoInimigo:
    def __init__(self, x: float, y: float):
        self.x, self.y = x, y
        self.w, self.h = 40, 40
        self.health = 30  # Vida para suportar múltiplos tiros
        self.dead = False
        self.active = True # Importante para sistemas de Pool
        
    @property
    def rect(self) -> pygame.Rect:
        """Retângulo de colisão (acessado como atributo)."""
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def take_damage(self, amount: int):
        """Chamado automaticamente pelo sistema de colisões."""
        self.health -= amount
        if self.health <= 0:
            self.dead = True

    def update(self, dt: float, player_pos: Tuple[float, float] = None):
        """
        dt: Delta time (já considera slow motion se passado pelo EntityManager).
        player_pos: Opcional, para inimigos que perseguem ou miram.
        """
        # Exemplo: Movimento simples para baixo
        self.y += 100 * dt
        
        # Remoção automática por posição é feita pelo EntityManager.

    def draw(self, screen: pygame.Surface):
        # Lógica de desenho (Polygon, Circle ou Surface)
        pygame.draw.rect(screen, colors.RED, self.rect)

    def get_points_value(self) -> int:
        return 150
```

---

## Passo 2: Integrar no Sistema de Níveis (`levels.py`)

Apesar do sistema de colisão usar Protocols, o `LevelConfig` ainda precisa conhecer o tipo explicitamente para a criação (factory).

1. **Importe seu inimigo** no topo de `game/core/levels.py`.
2. **Atualizar Tipos Union**: Adicione `NovoInimigo` nos type hints da classe `LevelConfig` e seus métodos (busque por `Meteor | Alien | ...`).
3. **Adicione ao Tema**: No `_create_world_boss_level` ou nos `LEVEL_THEMES`, defina o peso/tempo de spawn:
   ```python
   if world.theme == WorldTheme.MEU_TEMA:
       enemy_spawn_config = { NovoInimigo: 1.5, Alien: 2.0 }
   ```

---

## Passo 3: Sistema de Colisões (`collisions.py`)

**A grande vantagem do Protocol:** Você quase não precisa mexer nas assinaturas das funções!

1. **Importe seu inimigo** apenas para fins de `isinstance` se precisar de lógica especial.
2. **Tamanho da Explosão**: Adicione uma entrada em `_calculate_default_explosion_size`:
   ```python
   if isinstance(enemy, NovoInimigo): return 45
   ```
3. **Dano Customizado**: Se seu inimigo tem HP, certifique-se de que ele está na lista de `isinstance` dentro de `_destroy_enemy` que chama `take_damage(1)`.

---

## Passo 4: Entity Manager (`entity_manager.py`)

O `EntityManager` gerencia o ciclo de vida e o **Slow Motion (EMP)**.

1. **Adicione ao `update` principal**:
   ```python
   elif isinstance(enemy, NovoInimigo):
       # Use scaled_dt para que o inimigo respeite o slow motion
       enemy.update(scaled_dt, (player_x, player_y))
   ```
2. **Grid Espacial**: Adicione o tipo ao Type Hint do `enemies` e `enemy_spatial_grid` para evitar avisos do linter.

---

## Passo 5: Spawner (`spawner.py`)

1. **Contagem de Inimigos**: No método `_count_enemies_by_type`, adicione uma chave para seu inimigo para que o jogo saiba quantos existem na tela e respeite os limites de performance.
2. **Limite de Spawn**: No `_should_spawn_enemy`, defina um limite máximo (ex: `if counts["novo_inimigo"] >= 3: return False`).
3. **Lógica de Spawn**: No `update`, adicione o bloco `elif enemy_type == NovoInimigo:` para instanciar a classe e aplicar o multiplicador de vida da dificuldade atual.

---

## Checklist de "Stone Sentry" (O Padrão Atual)

Siga o exemplo do `StoneSentry` (`game/entities/stone_sentry.py`) para a melhor implementação:
- [ ] Usa `@property rect` para sintaxe limpa.
- [ ] Implementa `take_damage` para suporte a HP.
- [ ] No `EntityManager`, recebe `scaled_dt` para funcionar com o upgrade de EMP.
- [ ] No `Spawner`, tem um limite fixo (ex: máximo 3 na tela).
- [ ] Em `collisions.py`, utiliza o `Enemy` Protocol automaticamente.
