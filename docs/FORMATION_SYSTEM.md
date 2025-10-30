# Sistema de Formações de Inimigos

## Visão Geral

O sistema de formações permite que inimigos apareçam em grupos coordenados, entrando em movimento espiral e depois se alinhando em diferentes padrões geométricos (círculo, V, quadrado, linha).

## Arquivos Modificados/Criados

### Novos Arquivos
- `game/entities/formation.py` - Classe principal que gerencia formações de inimigos

### Arquivos Modificados
- `game/core/config.py` - Adicionadas constantes de configuração para formações
- `game/core/levels.py` - Adicionado suporte para configurar formações por nível
- `game/entities/__init__.py` - Exporta Formation e FormationPattern
- `game/entities/alien.py` - Suporte para controle por formação
- `game/systems/entity_manager.py` - Gerenciamento de formações
- `game/systems/spawner.py` - Lógica de spawn de formações
- `game/scenes/playing.py` - Integração com colisões

## Como Funciona

### 1. Padrões Disponíveis

```python
class FormationPattern(Enum):
    SPIRAL_ENTRY = "spiral_entry"  # Entrada em espiral
    CIRCLE = "circle"               # Círculo
    V_SHAPE = "v_shape"            # Formato em V
    SQUARE = "square"              # Quadrado
    LINE = "line"                  # Linha horizontal
```

### 2. Ciclo de Vida de uma Formação

1. **Spawn**: Criada pelo spawner acima da tela em intervalos configuráveis
2. **Entrada em Espiral**: Inimigos entram de cima girando em espiral, descendo lentamente
3. **Transição**: Movimento suave para o próximo padrão geométrico
4. **Padrão Geométrico**: Mantém formação enquanto desce pela tela
5. **Descida**: Formação desce continuamente até sair da tela ou ser destruída
6. **Ciclo**: Pode transicionar entre vários padrões durante a descida

### 3. Configuração por Nível

No arquivo `levels.py`:

```python
LevelConfig(
    level_number=2,
    enemy_spawn_config={
        Alien: 0.7,
    },
    enemies_to_clear=100,
    formations_enabled=True,  # Habilita formações
    formation_types=["spiral_circle", "spiral_v"],  # Tipos disponíveis
)
```

### 4. Tipos de Formação Pré-definidos

- `"spiral_circle"`: Espiral → Círculo
- `"spiral_v"`: Espiral → V
- `"spiral_square"`: Espiral → Quadrado
- `"full_cycle"`: Espiral → Círculo → V (ciclo completo)

## Configurações (Config.py)

```python
# Spawn
FORMATION_SPAWN_INTERVAL: (20.0, 35.0)  # Intervalo entre formações

# Espiral
FORMATION_SPIRAL_RADIUS: 80.0           # Raio da espiral
FORMATION_SPIRAL_SPEED: 2.0             # Velocidade de rotação
FORMATION_SPIRAL_TIME_OFFSET: 0.15      # Delay entre inimigos
FORMATION_ENTRY_SPEED: 60.0             # Velocidade de descida

# Padrões
FORMATION_PATTERN_DURATION: 8.0         # Tempo em cada padrão
FORMATION_TRANSITION_DURATION: 2.0      # Tempo de transição

# Dimensões
FORMATION_CIRCLE_RADIUS: 100.0
FORMATION_V_SPACING: 45.0
FORMATION_SQUARE_SIZE: 180.0
FORMATION_LINE_SPACING: 50.0
FORMATION_DRIFT_SPEED: 30.0             # Movimento lateral
FORMATION_DESCENT_SPEED: 50.0           # Velocidade de descida após formar padrão
```

## Uso Programático

### Criar uma Formação Manualmente

```python
from game.entities.formation import Formation, FormationPattern
from game.entities.alien import Alien

# Criar formação com 6 aliens
formation = Formation(
    enemy_type=Alien,
    count=6,
    entry_x=500,      # Centro da tela
    entry_y=100,      # Altura de entrada
    patterns_sequence=[
        FormationPattern.SPIRAL_ENTRY,
        FormationPattern.CIRCLE,
        FormationPattern.V_SHAPE
    ]
)

# Adicionar ao entity_manager
entity_manager.formations.append(formation)
```

### Personalizar Padrões

Você pode criar sequências personalizadas de padrões:

```python
# Apenas espiral e círculo
patterns = [FormationPattern.SPIRAL_ENTRY, FormationPattern.CIRCLE]

# Ciclo completo
patterns = [
    FormationPattern.SPIRAL_ENTRY,
    FormationPattern.CIRCLE,
    FormationPattern.V_SHAPE,
    FormationPattern.SQUARE
]
```

## Características Técnicas

### Movimento Suave
- Usa interpolação easing (ease-in-out) para transições suaves
- Movimento drift lateral adiciona dinamismo

### Controle de Inimigos
- Inimigos em formação têm `formation_controlled = True`
- Não se movem por conta própria
- Continuam atirando normalmente

### Colisões
- Inimigos em formação são incluídos automaticamente em todas as colisões
- Podem ser destruídos individualmente
- Formação é removida quando todos os inimigos morrem

### Performance
- Formações são atualizadas uma vez por frame
- Cleanup automático de formações vazias

## Dicas de Design

1. **Balanceamento**: Ajuste `FORMATION_SPAWN_INTERVAL` para evitar sobrecarga
2. **Variedade**: Use diferentes `formation_types` por nível
3. **Dificuldade**: Aumente a contagem de inimigos em níveis mais difíceis
4. **Timing**: `FORMATION_PATTERN_DURATION` controla quanto tempo o jogador tem para destruir

## Troubleshooting

### Formações não aparecem?
- Verifique se `formations_enabled=True` no LevelConfig
- Confirme que `formation_types` está definido
- Verifique o intervalo de spawn nas configurações

### Inimigos se movem estranhamente?
- Certifique-se que `formation_controlled` está sendo definido
- Verifique os valores de velocidade e raio na Config

### Colisões não funcionam?
- As formações são automaticamente incluídas nas colisões
- Verifique se `entity_manager.formations` está sendo passado corretamente

## Expansão Futura

Ideias para expandir o sistema:

1. **Padrões Dinâmicos**: Formações que mudam baseado na posição do jogador
2. **Formações Mistas**: Diferentes tipos de inimigos na mesma formação
3. **Ataques Coordenados**: Todos os inimigos atiram simultaneamente
4. **Formações Defensivas**: Alguns inimigos protegem outros
5. **Boss Formations**: Chefes que invocam formações especiais
