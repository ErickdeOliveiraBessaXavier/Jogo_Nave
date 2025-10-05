# 🎵 Sistema de Som - Documentação

## 📁 Nova Estrutura Organizada

```
game/assets/sounds/
├── music/                  # Músicas do jogo
│   ├── background.mp3     # Música de fundo principal
│   └── boss.mp3          # Música dos chefes
├── sfx/                   # Efeitos sonoros
│   ├── shots/            # Sons de tiro
│   │   ├── tiro_1.wav
│   │   ├── tiro_2.wav
│   │   └── tiro_3.wav
│   ├── explosions/       # Sons de explosão
│   │   ├── explosão_asteroides_0.wav
│   │   ├── explosão_asteroides_1.wav
│   │   ├── explosão_asteroides_2.wav
│   │   ├── explosão_asteroides_3.wav
│   │   ├── explosão_naves_alienigenas.wav
│   │   ├── explisão_boss.wav
│   │   ├── explisão_nave.wav
│   │   └── som_dano_boss.wav
│   └── ui/               # Sons de interface
│       └── warning.mp3   # Som de aviso de boss
```

## 🔧 Configuração

### Volumes Padrão
- **Volume Geral**: 50%
- **Efeitos Sonoros**: 70%
- **Música**: 30%
- **Tiros**: 40%

### Canais Dedicados
- **Canal 0**: Tiros (anti-irritação)
- **Canal 1**: Avisos/Warning
- **Canais 2-7**: Efeitos gerais

## 🎮 Como Usar

### Reproduzir Sons
```python
from game.core.sound import sound_manager

# Tiros
sound_manager.play_shot()

# Explosões
sound_manager.play_explosion_asteroid()
sound_manager.play_explosion_alien()
sound_manager.play_explosion_boss()
sound_manager.play_ship_explosion()

# Boss
sound_manager.play_boss_damage()

# UI
sound_manager.play_warning()
```

### Controlar Música
```python
# Música de fundo
sound_manager.play_background_music()

# Música do boss
sound_manager.play_boss_music()

# Controles
sound_manager.pause_music()
sound_manager.resume_music()
sound_manager.stop_music()
```

### Ajustar Volumes
```python
sound_manager.set_master_volume(0.8)    # 80%
sound_manager.set_sfx_volume(0.5)       # 50%
sound_manager.set_music_volume(0.3)     # 30%
sound_manager.set_shot_volume(0.4)      # 40%
```

## ✨ Recursos Avançados

### Sistema Anti-Irritação para Tiros
- Volume reduzido automaticamente
- Canal dedicado para controle preciso
- Previne sobrecarga sonora

### Gestão Inteligente de Música
- Troca automática entre música normal e boss
- Controle de estado (tocando/pausada)
- Prevenção de recarregamento desnecessário

### Carregamento Robusto
- Verificação de existência de arquivos
- Tratamento de erros do pygame
- Feedback detalhado no console

## 🔧 Configuração Avançada

O arquivo `sound_config.py` contém todas as configurações centralizadas:
- Tipos de som (enums)
- Caminhos de arquivos
- Configurações de volume
- Comportamentos especiais

## 📊 Monitoramento

```python
# Ver volumes atuais
sound_manager.get_volumes()

# Parar todos os efeitos
sound_manager.stop_all_sfx()

# Parar tudo (incluindo música)
sound_manager.stop_all()
```

## 🎯 Benefícios da Nova Estrutura

1. **Organização Clara**: Separação lógica por tipo de som
2. **Escalabilidade**: Fácil adicionar novos sons
3. **Manutenibilidade**: Configuração centralizada
4. **Performance**: Carregamento otimizado
5. **Flexibilidade**: Controles granulares de volume