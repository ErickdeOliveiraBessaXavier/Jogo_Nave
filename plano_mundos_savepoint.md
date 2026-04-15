# Plano: Sistema de Seleção de Mundos com Savepoints

## 1. ARQUITETURA DE DADOS

### 1.1 Estender `MetaProgression` (meta_progression.py)
```python
@dataclass
class WorldUnlockStatus:
    """Status de desbloqueio de um mundo."""
    world_id: int
    is_unlocked: bool
    first_accessed_at: Optional[datetime] = None
    last_checkpoint_level: int = 0  # Nível mais alto alcançado neste mundo
    
@dataclass
class GameProgress:
    """Adicionar a MetaProgression"""
    world_unlocks: Dict[int, WorldUnlockStatus] = field(default_factory=dict)
    current_checkpoint_world: int = 1  # Mundo onde jogador reaparece se perder
```

**Regra de negócio:**
- Mundo 1 sempre desbloqueado
- Mundo N+1 desbloqueia quando jogador completa Mundo N (atinge boss_level)
- Savepoint = primeira vez que entra em um novo mundo
- Se perder, reaparece no último mundo desbloqueado, com score = 0

---

## 2. ESTADOS E TRANSIÇÕES

### 2.1 Novo enum em `main_menu.py`
```python
class MenuView(Enum):
    MAIN = 0
    DIFFICULTY_SELECTION = 1
    WORLD_SELECTION = 2  # NOVO
```

### 2.2 Fluxo de transição
```
MainMenu (START_GAME clicked)
    ↓
WorldSelectionScene (novo)
    ↓ (mundo selecionado)
↓
DifficultySelectionScene (existente)
    ↓
PlayingScene (existente)
```

---

## 3. NOVA CENA: `WorldSelectionScene`

**Localização:** `scenes/world_selection.py`

### 3.1 Responsabilidades
- **Renderização:** Grid/lista de mundos com status visual (bloqueado/desbloqueado)
- **Interação:** Clique/seta para selecionar, ENTER para confirmar
- **Validação:** Apenas permitir entrada em mundos desbloqueados
- **Feedback visual:** Mostrar último checkpoint e score do savepoint

### 3.2 Estrutura da cena
```python
class WorldSelectionScene(Scene):
    def __init__(self, app: "GameApp"):
        self.selected_world_id: int = app.progression.current_checkpoint_world
        self.world_cards: List[WorldCard] = []  # UI components
        self._build_world_cards()  # Renderizar grid
        
    def _build_world_cards(self):
        """Construir cards para cada mundo configurado."""
        for world_config in get_all_worlds():
            unlock_status = self.app.progression.world_unlocks[world_config.world_id]
            card = WorldCard(
                world_config=world_config,
                is_unlocked=unlock_status.is_unlocked,
                is_checkpoint=world_config.world_id == self.app.progression.current_checkpoint_world,
                last_best_score=unlock_status.last_best_score_at_checkpoint
            )
            self.world_cards.append(card)
    
    def _confirm_selection(self):
        """Validar seleção e avançar."""
        card = self.world_cards[self.selected_world_id - 1]
        if not card.is_unlocked:
            return  # Ignorar clique em mundos bloqueados
        
        # Guardar seleção na progressão
        self.app.progression.selected_world_id = card.world_config.world_id
        
        # Resetar score do jogador (savepoint zerando pontos)
        self.app.progression.current_session_stats.score = 0
        
        # Avançar para dificuldade
        self.app.push_scene(DifficultySelectionScene(self.app))
```

### 3.3 Componente `WorldCard`
```python
@dataclass
class WorldCard:
    """Card visual de um mundo."""
    world_config: WorldConfig
    is_unlocked: bool
    is_checkpoint: bool = False
    last_best_score_at_checkpoint: int = 0
    
    # Rendering state
    hover: bool = False
    rect: pygame.Rect = field(init=False)
    
    def render(self, surface: pygame.Surface, position: Tuple[int, int]):
        """Renderizar card com estado visual."""
        # Border color: dourado se checkpoint, cinza se bloqueado
        border_color = (
            CUSTOM_GOLD if self.is_checkpoint
            else (150, 150, 150) if not self.is_unlocked
            else CUSTOM_PURPLE
        )
        
        # Alpha = 50% se bloqueado
        alpha = 255 if self.is_unlocked else 128
        
        # Renderizar: titulo, descrição, cores do mundo, status
        # Se hover: aumentar escala ligeiramente
```

---

## 4. INTEGRAÇÃO COM `MetaProgression`

### 4.1 Métodos novos
```python
class MetaProgression:
    def unlock_next_world(self):
        """Desbloquear próximo mundo após completar boss."""
        current_world_id = self.get_current_world()
        next_world_id = current_world_id + 1
        
        if next_world_id <= 4:  # Máximo 4 mundos nomeados
            self.world_unlocks[next_world_id].is_unlocked = True
            self.world_unlocks[next_world_id].first_accessed_at = datetime.now()
            self.current_checkpoint_world = next_world_id
            self.save()  # Persistir imediatamente
    
    def set_checkpoint_on_level_start(self, level_number: int):
        """Chamado quando jogador inicia um novo nível."""
        world_config = get_world_for_level(level_number)
        
        # Se é primeira vez neste mundo, marcar como checkpoint
        if not self.world_unlocks[world_config.world_id].checkpoint_set:
            self.current_checkpoint_world = world_config.world_id
            self.world_unlocks[world_config.world_id].checkpoint_set = True
            self.save()
    
    def reset_to_checkpoint(self):
        """Jogador perdeu: resetar para próximo checkpoint."""
        # Encontrar primeiro nível do mundo checkpoint
        checkpoint_world = get_world_for_level_by_id(self.current_checkpoint_world)
        next_level = checkpoint_world.start_level
        
        # Resetar score, manter meta-dados
        self.current_session_stats.score = 0
        self.current_session_stats.deaths += 1
        
        # Voltar para PlayingScene no nível inicial do checkpoint
        return next_level
```

### 4.2 Integração com `PlayingScene`
```python
class PlayingScene:
    def on_level_start(self):
        # Marcar checkpoint se primeira vez neste mundo
        self.app.progression.set_checkpoint_on_level_start(self.current_level)
    
    def on_boss_defeated(self):
        # Desbloquear próximo mundo
        self.app.progression.unlock_next_world()
        self.app.push_scene(WorldTransitionScene(...))
    
    def on_player_death(self):
        next_level = self.app.progression.reset_to_checkpoint()
        # Voltar para menu ou reiniciar no checkpoint
        self.app.pop_scene()
        self.app.push_scene(PlayingScene(self.app, level=next_level))
```

---

## 5. SCHEMA DE PERSISTÊNCIA

### 5.1 Estrutura JSON (save file)
```json
{
  "version": 2,
  "world_unlocks": {
    "1": {"world_id": 1, "is_unlocked": true, "first_accessed_at": "2024-01-15T10:30:00"},
    "2": {"world_id": 2, "is_unlocked": true, "first_accessed_at": "2024-01-15T11:45:00"},
    "3": {"world_id": 3, "is_unlocked": false, "first_accessed_at": null}
  },
  "current_checkpoint_world": 2,
  "last_checkpoint_level": 11,
  ...
}
```

### 5.2 Migração de save antigo
```python
def _migrate_progression_v1_to_v2(data: dict):
    """Adicionar world_unlocks a saves antigos."""
    if "world_unlocks" not in data:
        # Deduzir mundos desbloqueados do highest_level
        highest_level = data.get("highest_level_reached", 1)
        world_unlocks = {}
        for world_id in range(1, 5):
            world = WORLDS[world_id]
            is_unlocked = highest_level >= world.start_level
            world_unlocks[world_id] = {
                "world_id": world_id,
                "is_unlocked": is_unlocked,
                "first_accessed_at": None
            }
        data["world_unlocks"] = world_unlocks
        data["current_checkpoint_world"] = 1
    return data
```

---

## 6. MELHORES PRÁTICAS APLICADAS

### 6.1 Separação de Responsabilidades
- **WorldSelectionScene:** Apenas UI e input
- **WorldCard:** Componente visual isolado
- **MetaProgression:** Lógica de negócio (unlock, checkpoint)
- **world_config.py:** Dados de configuração (já segregado)

### 6.2 Imutabilidade & Type Safety
- `WorldUnlockStatus` como `@dataclass` com campos type-hinted
- `WorldCard` com `field(init=False)` para computed properties
- Usar `Enum` para estados (desbloqueado/checkpoint/bloqueado)

### 6.3 Persistência Robusta
- Save imediatamente após unlock/checkpoint (não defer)
- Migração automática de versão em load
- Logs estruturados para debug (`logger.info(f"🌍 Mundo {world_id} desbloqueado")`)

### 6.4 Caching & Performance
- Usar `@lru_cache` no `get_world_for_level()` se chamar em loop
- Pré-construir WorldCards uma única vez no `__init__`
- Lazy-render cards fora da viewport

### 6.5 Testabilidade
- Lógica de unlock isolada em método puro
- Mock de `MetaProgression` para testar `WorldSelectionScene`
- Dados de teste em fixtures

---

## 7. CHECKLIST DE IMPLEMENTAÇÃO

### Fase 1: Dados & Lógica
- [ ] Estender `WorldUnlockStatus` em `meta_progression.py`
- [ ] Adicionar `world_unlocks` dict em `GameProgress`
- [ ] Implementar `unlock_next_world()` e `reset_to_checkpoint()`
- [ ] Adicionar migração v1→v2 em load

### Fase 2: UI
- [ ] Criar `scenes/world_selection.py` com `WorldSelectionScene`
- [ ] Implementar `WorldCard` com renderização + states
- [ ] Adicionar navegação (setas/mouse, ENTER, ESC)
- [ ] Integrar som feedback (click, lock sound)

### Fase 3: Integração de Fluxo
- [ ] Modificar `MainMenuScene`: ao clicar START, ir para WorldSelection
- [ ] Adicionar `MenuView.WORLD_SELECTION`
- [ ] Integrar com `DifficultySelectionScene`
- [ ] Conectar eventos em `PlayingScene` (on_boss, on_death)

### Fase 4: Testes & Polish
- [ ] Testar unlock progressivo (1→2→3→4)
- [ ] Testar checkpoint após game over
- [ ] Testar persistência (reload savefile)
- [ ] Testes de UI (navegação, feedback visual)
- [ ] Validar score reset em novo checkpoint

---

## 8. DIAGRAMA DE ESTADO (StateChart)

```
[GameProgress]
├─ world_unlocks: {1: unlocked, 2: locked, 3: locked, 4: locked}
├─ current_checkpoint_world: 1
└─ selected_world_id: (transient, set durante WorldSelect)

[PlayingScene] 
├─ on_level_start() → set_checkpoint_on_level_start()
├─ on_boss_defeated() → unlock_next_world() → push(WorldTransitionScene)
└─ on_player_death() → reset_to_checkpoint() → restart at level N

[WorldSelectionScene]
├─ render_world_cards() 
├─ update_hover_state()
└─ on_confirm() → save selected_world_id → push(DifficultySelection)
```

---

## 9. EXEMPLO DE FLUXO JOGADOR

```
1. MainMenu → "Iniciar Jogo" 
   ↓ (criou GameProgress com world_unlocks={1: unlocked, 2-4: locked})

2. WorldSelectionScene
   - Mostra: Mundo 1 (UNLOCK), Mundo 2 (LOCK), Mundo 3 (LOCK), Mundo 4 (LOCK)
   - Seleciona Mundo 1
   ↓

3. DifficultySelectionScene → seleciona NORMAL
   ↓

4. PlayingScene: Mundo 1, Níveis 1-10
   - Atinge level 10 (boss) → unlock_next_world() → Mundo 2 agora UNLOCKED
   - Derrota boss → WorldTransitionScene → volta para menu
   ↓

5. Volta ao MainMenu, clica START novamente
   ↓

6. WorldSelectionScene
   - Mostra: Mundo 1 (CHECKPOINT, "Best Score: 15.000"), Mundo 2 (UNLOCK, NEW)
   - Seleciona Mundo 2
   - Score é resetado para 0 (savepoint mechanism)
   ↓

7. PlayingScene: Mundo 2, Níveis 11-25
   - Perde em level 15
   - on_player_death() → reset_to_checkpoint() 
   - Retorna a PlayingScene, level 11 (início do Mundo 2)
   - Continua com score = 0
```

---

## 10. CONSIDERAÇÕES ESPECIAIS

### Perdendo em um mundo anterior ao checkpoint
```python
# Jogador estava no Mundo 2, perder no nível 15
# reset_to_checkpoint() verifica current_checkpoint_world
# Se é Mundo 2, volta para nível 11 (start_level de Mundo 2)
# Score mantém o que acumulou DEPOIS do checkpoint
```

### Múltiplos saves (futuro)
```python
# Se expandir para múltiplos slots de save
class SaveSlot:
    slot_id: int
    progression: GameProgress
    last_saved: datetime
    playtime: timedelta
```

### Permadeath (Nightmare mode)
```python
# Em DifficultyPreset.NIGHTMARE com special_rules: ["permadeath"]
# on_player_death() em vez de reset_to_checkpoint():
# - Game Over (não volta ao mundo)
# - Oferecer reload de save anterior
```

---

## 11. NOTAS TÉCNICAS

- **Thread-safety:** Salvar em thread separada se salvar é lento
- **Memory:** WorldCards como lista ao invés de dict (order import)
- **Animation:** Usar `AnimationConfig` do main_menu para consistência
- **Accessibility:** Renderizar mundo desbloqueado com visual claro (padding, brilho)