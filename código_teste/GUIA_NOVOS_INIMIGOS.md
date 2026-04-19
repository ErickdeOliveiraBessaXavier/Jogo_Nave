# Guia Moderno para Criar Novos Inimigos (v3.0)

Este guia resume o fluxo atual do projeto para adicionar inimigos com segurança,
incluindo o padrão composto (inimigo principal + ataque/entidade invocada),
compatibilidade com **EMP (slow motion)** e integração com spawn procedural.

---

## 1. Contrato Mínimo do Inimigo

Para um objeto ser tratado como inimigo no jogo, ele deve expor:

- `x, y, w, h`
- `rect` (de preferência `@property` retornando `pygame.Rect`)
- `dead` (bool)
- `health` (int)
- `get_points_value() -> int`
- `update(dt, ...)`

Se o inimigo usa HP real, implemente também:

- `take_damage(amount: int)`

Estrutura base:

```python
import pygame


class NovoInimigo:
    def __init__(self, x: float, y: float):
        self.x, self.y = x, y
        self.w, self.h = 40, 40
        self.health = 10
        self.dead = False
        self.active = True

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def take_damage(self, amount: int) -> None:
        self.health -= amount
        if self.health <= 0:
            self.dead = True

    def update(self, dt: float) -> None:
        pass

    def draw(self, screen: pygame.Surface) -> None:
        pass

    def get_points_value(self) -> int:
        return 100
```

---

## 2. Padrão Composto (Recomendado)

Quando o inimigo cria ataques persistentes (ex.: estalagmite, mina, totem, drone),
use **duas entidades**:

- entidade A: inimigo principal (decide quando atacar)
- entidade B: entidade do ataque (tem `dead/health/rect/update/draw` próprios)

Vantagens:

- colisão e pontuação ficam previsíveis
- mais fácil balancear HP do ataque separado do inimigo
- integração limpa no grid espacial e no EMP

---

## 3. Integração em `levels.py`

1. Importe o novo tipo.
2. Inclua no tema certo (`ENEMY_THEME_ALLOWLIST`).
3. Adicione pesos em perfis de tema/estágio quando necessário.
4. Inclua fallback para evitar pool vazio no tema.
5. Se for exclusivo de um mundo, inclua nas regras do `_create_world_boss_level` também.

Observação importante (tipagem):

- Hoje `LevelConfig.enemy_spawn_config` usa `dict[type, float]`.
- Isso evita churn de unions gigantes e reduz erros de tipagem ao adicionar novos tipos.

---

## 4. Integração em `spawner.py`

Checklist:

- [ ] adicionar contagem no `_count_enemies_by_type`
- [ ] definir cap em `_should_spawn_enemy` e `_is_hard_capped`
- [ ] implementar instanciamento em `_spawn_enemy_of_type`
- [ ] aplicar `enemy_health_multiplier` no spawn

Regra prática:

- inimigo forte/controlador de campo: cap baixo (1 ou 2)

---

## 5. Integração em `entity_manager.py`

Checklist:

- [ ] adicionar tipo em `self.enemies` (type hint)
- [ ] adicionar tipo em `enemy_spatial_grid` (type hint)
- [ ] no loop principal de update, usar `scaled_dt` para respeitar EMP
- [ ] se o update retornar entidades novas (ataques), anexar em `self.enemies`
- [ ] garantir que o rebuild do grid inclui essas entidades

Exemplo:

```python
elif isinstance(enemy, NovoInimigo):
    spawned = enemy.update(scaled_dt, (player_x, player_y))
    if spawned:
        self.enemies.extend(spawned)
```

---

## 6. Integração em `collisions.py`

Checklist:

- [ ] importar tipo se houver regra especial por `isinstance`
- [ ] definir tamanho padrão de explosão em `_calculate_default_explosion_size`
- [ ] se tiver HP próprio, incluir no branch de `_destroy_enemy` que chama `take_damage(1)`
- [ ] validar colisão com nave em `ship_vs_enemies` quando necessário

Regra prática:

- ataque invocado com HP (ex.: estalagmite) deve entrar na mesma lógica de HP de inimigos especiais

---

## 7. Configuração Recomendada

Para inimigos novos com mecânicas de telegraph/cooldown, adicione constantes em
`game/core/config.py` em vez de hardcode:

- `WARNING_DURATION`
- `COOLDOWN`
- `ATTACK_HEALTH`
- `MIN/MAX_ATTACK_SIZE`

Isso facilita tuning sem quebrar o comportamento.

---

## 8. Checklist Final de Entrega

- [ ] spawn no tema correto
- [ ] não aparece em temas errados
- [ ] respeita EMP/slow motion
- [ ] colisão com bala funciona
- [ ] colisão com nave funciona
- [ ] pontuação e explosão corretas
- [ ] sem erros de análise (`get_errors`)

---

## 9. Bloco de Briefing para IA (Copiar e Colar)

Use este bloco quando pedir para criar inimigos novos:

```text
Crie um novo inimigo seguindo o padrão do projeto:
- Classe principal em game/entities
- Se houver ataque persistente, criar entidade separada para o ataque
- Integrar em levels.py (allowlist, pesos, fallback)
- Integrar em spawner.py (count, cap, spawn)
- Integrar em entity_manager.py (update com scaled_dt, grid, append de entidades geradas)
- Integrar em collisions.py (explosion size, HP branch com take_damage)
- Adicionar constantes de tuning em core/config.py
- Rodar validação de erros e corrigir antes de finalizar
```
