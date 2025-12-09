# Guia para Criar Novos Inimigos

Este documento explica o processo completo para adicionar um novo inimigo ao jogo Nave.

## Passo 1: Criar a Classe do Inimigo

1. **Localização**: Crie um novo arquivo em `game/entities/nome_do_inimigo.py`

2. **Estrutura Básica**:
   ```python
   from typing import Optional
   import pygame
   import math
   from ..core import colors

   class NovoInimigo:
       def __init__(self, x: float, y: float, ...):  # Parâmetros necessários
           self.x = x
           self.y = y
           self.dead = False
           self.health = 1  # Vida do inimigo
           # Propriedades para compatibilidade
           self.w = largura
           self.h = altura

       def update(self, dt: float, screen_width: int = 1600, screen_height: int = 900) -> None:
           # Lógica de movimento e comportamento
           # IMPORTANTE: Use screen_width/screen_height para remover inimigos fora da tela
           if self.y > screen_height + 100:
               self.dead = True

       def draw(self, surface: pygame.Surface) -> None:
           if self.dead:
               return
           # Desenhar o inimigo

       def get_rect(self) -> pygame.Rect:
           return pygame.Rect(self.x - self.w/2, self.y - self.h/2, self.w, self.h)

       def take_damage(self, damage: int = 1) -> None:
           self.health -= damage
           if self.health <= 0:
               self.dead = True

       def get_points_value(self) -> int:
           return 10  # Pontos que concede ao ser destruído
   ```

3. **Métodos Obrigatórios**:
   - `__init__`: Inicialização com posição e outros parâmetros
   - `update(dt, screen_width, screen_height)`: Atualização lógica
   - `draw(surface)`: Renderização
   - `get_rect()`: Retângulo de colisão
   - `take_damage(damage)`: Receber dano
   - `get_points_value()`: Pontos concedidos

## Passo 2: Integrar no Sistema de Níveis (levels.py)

1. **Adicionar Import**:
   ```python
   from ..entities.nome_do_inimigo import NovoInimigo
   ```

2. **Atualizar Tipos no LevelConfig**:
   ```python
   enemy_spawn_config: dict[
       Type[Meteor | Alien | ExplosiveMine | EyeEnemy | NovoInimigo], float
   ]
   ```

3. **Atualizar Métodos do LevelConfig**:
   - `enemy_types` property
   - `get_spawn_time` method
   - `get_random_enemy_type` method

4. **Adicionar aos Temas**:
   ```python
   LEVEL_THEMES = {
       "tema_exemplo": LevelTheme(
           enemy_weight={"meteor": 1.0, "alien": 1.0, "novo_inimigo": 0.5},
           # ... outros campos
       ),
   }
   ```

5. **Adicionar Lógica de Spawn**:
   ```python
   # Eyes (nível 5+)
   if level_number >= NIVEL_MINIMO:
       novo_weight = theme.enemy_weight.get("novo_inimigo", 0.1) if theme else 0.1
       base_novo_time = (TEMPO_BASE / difficulty) / spawn_multiplier
       enemy_spawn_config[NovoInimigo] = self._clamp_spawn_time(
           base_novo_time * (2.0 / novo_weight)
       )
   ```

## Passo 3: Integrar no Sistema de Colisões (collisions.py)

**IMPORTANTE**: Se seu inimigo usa `get_rect()` em vez de propriedade `rect`, você precisa atualizar TODAS as referências a `enemy.rect` no arquivo collisions.py para usar uma verificação compatível:

```python
# Em vez de:
if b_rect.colliderect(enemy.rect):

# Use:
enemy_rect = enemy.rect if hasattr(enemy, 'rect') else enemy.get_rect()
if b_rect.colliderect(enemy_rect):
```

1. **Adicionar Import**:
   ```python
   from ..entities.nome_do_inimigo import NovoInimigo
   ```

2. **Atualizar Tipos Union**:
   ```python
   def get_collision_info(enemy: Meteor | Alien | ExplosiveMine | EyeEnemy | NovoInimigo) -> tuple[float, float, float]:
   ```

3. **Atualizar _destroy_enemy**:
   ```python
   def _destroy_enemy(
       self,
       enemy: Meteor | Alien | ExplosiveMine | EyeEnemy | NovoInimigo,
       enemies_list: list[Meteor | Alien | ExplosiveMine | EyeEnemy | NovoInimigo],
       entity_manager: "EntityManager",
       explosion_size: int | None = None,
   ) -> tuple[int, tuple[float, float, int]]:
   ```

4. **Atualizar bullets_vs_enemies**:
   ```python
   enemy_grid: SpatialGrid[Meteor | Alien | ExplosiveMine | EyeEnemy | NovoInimigo]
   enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy | NovoInimigo]
   ```

5. **Atualizar mini_ship_bullets_vs_enemies** (mesmo que acima)

6. **Atualizar ship_vs_enemies**:
   ```python
   enemy_grid: SpatialGrid[Meteor | Alien | ExplosiveMine | EyeEnemy | NovoInimigo]
   ```

7. **Atualizar Som de Colisão** (se necessário):
   ```python
   if isinstance(enemy, NovoInimigo):
       sound_manager.play_explosion_alien()  # ou outro som
   ```

8. **INIMIGOS INDISTRUTÍVEIS** (opcional): Se o inimigo não puder ser destruído por tiros/lasers:
   ```python
   # Em bullets_vs_enemies, mini_ship_bullets_vs_enemies:
   elif isinstance(enemy, NovoInimigo):
       # Efeitos visuais e sonoros quando atingido
       entity_manager.spawn_explosion(b.x, b.y, size=20)  # Explosão no ponto de impacto
       sound_manager.play_boss_damage()  # Som de impacto
       pass  # Inimigo imune a dano
   ```
   
   **IMPORTANTE**: Mesmo inimigos indestrutíveis devem **destruir as balas** que os atingem E **ser destruídos quando colidem com a nave** (causando dano ao jogador).
   ```python
   if b_rect.colliderect(enemy_rect):
       b.dead = True  # Bala sempre é destruída ao colidir
       
       if isinstance(enemy, NovoInimigo):
           # Efeitos + imunidade
           entity_manager.spawn_explosion(b.x, b.y, size=20)
           sound_manager.play_boss_damage()
   ```

## Passo 4: Integrar no Entity Manager (entity_manager.py)

1. **Adicionar Import**:
   ```python
   from ..entities.nome_do_inimigo import NovoInimigo
   ```

2. **Atualizar Lista de Inimigos**:
   ```python
   self.enemies: list[Meteor | Alien | ExplosiveMine | EyeEnemy | NovoInimigo] = []
   ```

3. **Atualizar SpatialGrid**:
   ```python
   self.enemy_spatial_grid: SpatialGrid[
       Meteor | Alien | ExplosiveMine | EyeEnemy | NovoInimigo
   ] = SpatialGrid()
   ```

4. **Atualizar Método update**:
   ```python
   elif isinstance(enemy, NovoInimigo):
       enemy.update(scaled_dt, screen_width, screen_height)
   ```

5. **ATUALIZAR assinatura do método update** (se o inimigo precisar de screen_width/screen_height):
   ```python
   def update(self, dt: float, player_x: float, player_y: float, freeze_enemies: bool = False, screen_width: int = 1600, screen_height: int = 900):
   ```

6. **ATUALIZAR chamada no playing.py** (se modificou a assinatura):
   ```python
   self.entity_manager.update(
       dt, self.ship.rect.centerx, self.ship.rect.centery, freeze_enemies=self.freeze_active,
       screen_width=Config.SCREEN_WIDTH, screen_height=Config.SCREEN_HEIGHT
   )
   ```

## Passo 5: Integrar no Spawner (spawner.py)

1. **Adicionar Import** (se necessário):
   ```python
   from ..entities.nome_do_inimigo import NovoInimigo
   ```

2. **Se Spawn Especial é Necessário**:
   ```python
   if enemy_type == NovoInimigo:
       # Lógica especial de spawn
       if player_x is not None and player_y is not None:
           new_enemy = NovoInimigo(x, y, player_x, player_y)
           # ...
   ```

3. **Caso Contrário**: O spawn padrão funcionará automaticamente.

## Passo 6: Testes

1. **Compilação**: Verificar se todos os arquivos compilam sem erros:
   ```bash
   python -m py_compile game/entities/nome_do_inimigo.py
   python -c "import game.core.levels"
   python -c "import game.systems.collisions"
   python -c "import game.systems.entity_manager"
   python -c "import game.systems.spawner"
   ```

2. **Execução**: Rodar o jogo e verificar se o inimigo aparece nos níveis apropriados.

3. **Colisões**: Testar se tiros, nave e outros elementos interagem corretamente.

4. **Problemas Comuns**:
   - **UnboundLocalError screen_width**: Certifique-se de que EntityManager.update aceita e passa screen_width/screen_height
   - **AttributeError 'rect'**: Use `hasattr(enemy, 'rect')` para verificar se usa propriedade ou método
   - **ImportError**: Verifique se todos os imports foram adicionados corretamente

## Exemplo Completo: SquareMinionBoss

Para referência, veja como o `SquareMinionBoss` foi implementado seguindo estes passos.

**Lições Aprendidas com SquareMinionBoss:**
- Inimigos que precisam de `screen_width`/`screen_height` requerem atualização do `EntityManager.update()` e sua chamada
- Usar `get_rect()` em vez de propriedade `rect` exige verificação `hasattr()` em colisões
- Sempre teste colisões completas (tiros, nave, lasers) após implementação
- Imports não utilizados geram warnings - remova-os
- **INIMIGOS INDISTRUTÍVEIS**: Para inimigos que não podem ser destruídos por tiros/lasers, adicione condições especiais em TODAS as funções de dano no `collisions.py`
- **BALAS SEMPRE DESAPARECEM**: Mesmo inimigos indestrutíveis devem destruir as balas que os atingem (`b.dead = True`)
- **COLISÃO COM NAVE**: Inimigos indestrutíveis ainda devem ser destruídos quando colidem com a nave (causando dano ao jogador)
- **FEEDBACK VISUAL/SONORO**: Adicione explosões e sons quando balas atingem inimigos indestrutíveis para feedback do jogador

## Implementando Inimigos Indestrutíveis

Para criar inimigos que não podem ser destruídos por tiros/lasers mas são destruídos na colisão com a nave (como o SquareMinionBoss), siga estes passos:

### 1. **Colisões com Tiros/Lasers (Indestrutível)**

Em `game/systems/collisions.py`, nas funções `bullets_vs_enemies()` e `lasers_vs_enemies()`, adicione condições especiais:

```python
# Em bullets_vs_enemies()
elif isinstance(enemy, SquareMinionBoss):
    # Inimigo indestrutível - não perde vida
    # Mas bala sempre desaparece
    b.dead = True
    # Feedback visual/sonoro
    self.entity_manager.create_explosion(b.x, b.y, "small")
    self.sound_manager.play_sound("enemy_hit")
    continue  # Pula o resto do processamento de dano

# Em lasers_vs_enemies() - mesma lógica
elif isinstance(enemy, SquareMinionBoss):
    # Laser não destrói, mas bala desaparece
    b.dead = True
    self.entity_manager.create_explosion(b.x, b.y, "small")
    self.sound_manager.play_sound("enemy_hit")
    continue
```

### 2. **Colisões com Nave (Destrutível)**

Em `ship_vs_enemies()`, **NÃO** adicione condições especiais. Deixe o inimigo ser destruído normalmente:

```python
# NÃO FAÇA ISSO para inimigos indestrutíveis:
# elif isinstance(enemy, SquareMinionBoss):
#     pass  # Não destrói

# DEIXE O PROCESSAMENTO NORMAL:
enemy.dead = True
self.entity_manager.create_explosion(enemy.x, enemy.y, "large")
self.sound_manager.play_sound("enemy_destroyed")
# Dano ao jogador continua normal
```

### 3. **Por que essa abordagem?**

- **Feedback do Jogador**: Explosões e sons confirmam que os tiros estão "atingindo" o inimigo
- **Balanceamento**: Inimigos indestrutíveis ainda podem ser evitados ou destruídos colidindo com a nave
- **Consistência**: Mantém o comportamento padrão para colisões com nave
- **Flexibilidade**: Permite inimigos "fortes" que exigem estratégia diferente

### 4. **Exemplo Completo - SquareMinionBoss**

```python
# bullets_vs_enemies()
elif isinstance(enemy, SquareMinionBoss):
    b.dead = True
    self.entity_manager.create_explosion(b.x, b.y, "small")
    self.sound_manager.play_sound("enemy_hit")
    continue

# lasers_vs_enemies() - mesma coisa
elif isinstance(enemy, SquareMinionBoss):
    b.dead = True
    self.entity_manager.create_explosion(b.x, b.y, "small")
    self.sound_manager.play_sound("enemy_hit")
    continue

# ship_vs_enemies() - SEM condição especial, deixa destruir normalmente
```

## Problemas Comuns e Soluções

| Problema | Sintoma | Solução |
|----------|---------|---------|
| UnboundLocalError screen_width | Erro ao atualizar inimigo | Atualizar assinatura EntityManager.update() e chamada em playing.py |
| AttributeError 'rect' | Erro em colisões | Usar `hasattr(enemy, 'rect')` para verificar propriedade vs método |
| ImportError | Módulo não encontrado | Verificar todos os imports foram adicionados |
| TypeError | Tipos incompatíveis | Atualizar todos os Union types |
| Inimigo não aparece | Sem erros, mas não spawna | Verificar pesos nos temas e nível mínimo |
| Inimigo indestrutível | Tiros passam através | Adicionar condições `elif isinstance(enemy, NovoInimigo): pass` em funções de dano de tiros + manter `b.dead = True` + efeitos visuais/sonoros. Inimigo ainda é destruído na colisão com nave |
| Inimigo indestrutível | Sem feedback visual | Adicionar `self.entity_manager.create_explosion()` e `self.sound_manager.play_sound()` nas condições especiais |
| Inimigo indestrutível | Não destruído por nave | Remover condições especiais de `ship_vs_enemies()` - deixar processamento normal |

## Notas Importantes

- **Ordem de Integração**: Sempre siga a ordem dos passos para evitar erros de tipo.
- **Tipos Union**: Atualize todos os tipos union quando adicionar um novo inimigo.
- **Spatial Grid**: A grid espacial é crítica para performance de colisões.
- **Spawn Especial**: Só necessário se o inimigo precisar de parâmetros especiais (como posição do jogador).
- **Balanceamento**: Ajuste pesos nos temas e nível mínimo de aparecimento.
- **Performance**: Certifique-se de que o update e draw são eficientes.
- **Parâmetros de Tela**: Se seu inimigo precisa de screen_width/screen_height, atualize EntityManager.update() e sua chamada.
- **Colisões**: Use verificação `hasattr(enemy, 'rect')` para compatibilidade entre propriedade e método.
- **Testes**: Sempre teste compilação e execução após cada mudança significativa.
- **Inimigos Indestrutíveis**: Para inimigos que não são destruídos por tiros, sempre adicione feedback visual/sonoro e certifique-se de que são destruídos na colisão com a nave.

## Checklist Final

- [ ] Classe do inimigo criada com todos os métodos obrigatórios
- [ ] Integrado em levels.py (tipos, temas, spawn)
- [ ] Integrado em collisions.py (tipos, colisões, compatibilidade rect/get_rect)
- [ ] Integrado em entity_manager.py (tipos, update, parâmetros de tela se necessário)
- [ ] Integrado em spawner.py (se necessário)
- [ ] **INIMIGOS INDISTRUTÍVEIS**: Adicionadas condições especiais em collisions.py (se aplicável) + efeitos visuais/sonoros quando atingidos + destruído na colisão com nave
- [ ] Testado compilação e execução
- [ ] Verificado colisões com tiros, nave e lasers
- [ ] Balanceado e funcionando corretamente</content>
<parameter name="filePath">c:\Users\eobx\OneDrive\Documentos\Jogos_Python\Nave\GUIA_NOVOS_INIMIGOS.md