# 🎵 Sistema de Som - Estrutura Organizada

## 📁 Nova Estrutura de Arquivos

```
game/assets/sounds/
├── music/                    # Arquivos de música (MP3)
│   ├── background.mp3        # Música de fundo principal
│   └── boss.mp3             # Música durante boss fights
│
├── sfx/                     # Efeitos sonoros (WAV)
│   ├── shots/               # Sons de tiro
│   │   ├── tiro_1.wav
│   │   ├── tiro_2.wav
│   │   └── tiro_3.wav
│   │
│   ├── explosions/          # Sons de explosão
│   │   ├── explosão_asteroides_0.wav
│   │   ├── explosão_asteroides_1.wav
│   │   ├── explosão_asteroides_2.wav
│   │   ├── explosão_asteroides_3.wav
│   │   ├── explosão_naves_alienigenas.wav
│   │   ├── explisão_boss.wav
│   │   ├── explisão_nave.wav
│   │   └── som_dano_boss.wav
│   │
│   └── ui/                  # Sons de interface
│       └── warning.mp3      # Som de aviso de boss
```

## 🎯 Arquitetura do Sistema

### **SoundManager** (`game/core/sound.py`)
- **Singleton Pattern**: Uma instância global `sound_manager`
- **Canais Dedicados**: Shots (canal 0), Warning (canal 1)
- **Controle de Volume Granular**: Master, SFX, Music, Shots específico
- **Anti-irritação**: Sistema inteligente para tiros

### **Configuração Externa** (`game/core/sound_config.py`)
- **Enums**: `SoundType`, `SoundCategory` para type safety
- **Configurações Centralizadas**: Volumes, canais, paths, comportamento
- **Type Hints**: Tipagem completa para melhor IDE support

## 🔧 Volumes Configurados

| Categoria | Volume | Descrição |
|-----------|--------|-----------|
| Master    | 50%    | Volume geral do jogo |
| SFX       | 70%    | Efeitos sonoros |
| Music     | 30%    | Música de fundo |
| Shots     | 40%    | Tiros específico (anti-irritação) |

## 🎮 Sistema de Canais

| Canal | Uso | Benefício |
|-------|-----|-----------|
| 0 | Tiros da nave | Controle independente, anti-spam |
| 1 | Warning/Avisos | Pode ser parado quando necessário |
| 2-7 | Disponíveis | Para expansões futuras |

## 🚀 Fluxo de Música

```
Início do Jogo → Música de Fundo
       ↓
   Boss Warning → Som de Aviso
       ↓
   Boss Aparece → Música do Boss
       ↓
  Boss Derrotado → Volta Música de Fundo
```

## 📋 API Principais

### Música
```python
sound_manager.play_background_music()  # Música principal
sound_manager.play_boss_music()        # Música do boss
sound_manager.pause_music()            # Pausar
sound_manager.resume_music()           # Resumir
sound_manager.stop_music()             # Parar
```

### Efeitos Sonoros
```python
sound_manager.play_shot()                 # Tiro (com anti-irritação)
sound_manager.play_explosion_asteroid()   # Explosão de asteroide
sound_manager.play_explosion_alien()      # Explosão de alien
sound_manager.play_explosion_boss()       # Explosão do boss
sound_manager.play_boss_damage()          # Dano no boss
sound_manager.play_ship_explosion()       # Explosão da nave
sound_manager.play_warning()              # Aviso de boss
```

### Controles
```python
sound_manager.set_master_volume(0.5)      # Volume geral
sound_manager.set_sfx_volume(0.7)         # Volume dos efeitos
sound_manager.set_music_volume(0.3)       # Volume da música
sound_manager.set_shot_volume(0.4)        # Volume dos tiros
sound_manager.stop_all_sfx()              # Parar todos os efeitos
sound_manager.get_volumes()               # Ver volumes atuais
```

## ✨ Recursos Avançados

### **Anti-irritação para Tiros**
- **Intervalo mínimo**: 50ms entre tiros
- **Volume dinâmico**: Reduz volume com tiros frequentes
- **Canal dedicado**: Controle independente

### **Gestão Inteligente de Música**
- **Prevenção de reload**: Não recarrega música já tocando
- **Estado persistente**: Lembra música atual e se está pausada
- **Transições suaves**: Troca automática entre normal/boss

### **Carregamento Robusto**
- **Verificação de arquivos**: Só carrega se existir
- **Tratamento de erros**: Continua funcionando mesmo com arquivos faltando
- **Relatórios detalhados**: Logs informativos durante carregamento

## 🎨 Benefícios da Nova Estrutura

1. **📁 Organização Clara**: Separação lógica por tipo e categoria
2. **🔧 Configuração Externa**: Fácil ajuste sem mexer no código
3. **🎯 Type Safety**: Enums e type hints previnem erros
4. **📈 Escalabilidade**: Estrutura preparada para crescer
5. **🛠️ Manutenibilidade**: Código limpo e bem documentado
6. **🔄 Flexibilidade**: Fácil adição de novos sons e categorias

## 🔮 Expansões Futuras

A estrutura está preparada para:
- **Voice Acting**: `sounds/voice/`
- **Ambientes**: `sounds/ambient/`
- **Múltiplas Músicas**: Sistema de playlist
- **Sound Profiles**: Configurações por usuário
- **Dynamic Audio**: Volume baseado em gameplay

---

*Sistema implementado com foco em organização, performance e experiência do usuário.*