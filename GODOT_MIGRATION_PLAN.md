# 🚀 Plano de Migração para Godot - Space Shooter

## 📋 Estrutura do Projeto Atual (PyGame) - DETALHADO

```
game/
├── core/                           # Configurações e lógica base
│   ├── config.py                  # ⚙️ Todas as constantes do jogo
│   │   ├── Config (dataclass)      # Configurações globais
│   │   ├── PowerUpType (enum)      # Tipos de power-ups
│   │   ├── DISPLAY & PERFORMANCE   # FULLSCREEN, SCREEN_WIDTH/HEIGHT, FPS
│   │   ├── BASIC GAMEPLAY          # Velocidades, hitpoints, damage
│   │   ├── SPAWNING SETTINGS       # Taxa de spawn, cooldowns
│   │   ├── VISUAL SETTINGS         # Cores, efeitos
│   │   └── BALANCE TUNING          # Multiplicadores de dificuldade
│   │
│   ├── difficulty.py              # 📊 Sistema de dificuldade progressivo
│   │   ├── DifficultyPreset       # Presets: Easy, Medium, Hard, Insane
│   │   └── DifficultySettings     # Cálculos dinâmicos por nível
│   │
│   ├── input.py                   # ⌨️ Gerenciamento de entrada
│   │   ├── KEYMAP                 # Mapeamento de teclas (LEFT/RIGHT/SPACE/etc)
│   │   └── Input (class)          # poll_events() - coleta input do player
│   │
│   ├── levels.py                  # 🎮 Sistema de níveis complexo
│   │   ├── DifficultyConfig       # Constantes de balanceamento
│   │   ├── LevelConfig            # Config de cada nível
│   │   ├── LevelSystem            # Gerenciador de níveis
│   │   ├── SpawnConfig            # Configuração de spawn de inimigos
│   │   ├── BossConfig             # Configuração de bosses
│   │   ├── MeteorShower           # Chuva de meteoros
│   │   └── Level Progression      # Sistema de escalação de dificuldade
│   │
│   ├── meta_progression.py        # 🏆 Progressão entre jogos
│   │   ├── MetaProgression        # Desbloqueia níveis, upgrades permanentes
│   │   ├── Unlocks                # Rastreia o que foi desbloqueado
│   │   └── Cosmetics              # Skins, cores, etc
│   │
│   ├── upgrades.py                # 🔧 Sistema de upgrades do jogador
│   │   ├── Upgrade (dataclass)    # Estrutura de um upgrade
│   │   ├── UpgradeManager         # Gerencia upgrades aplicados
│   │   ├── Active Upgrades        # Double shot, shield, speed, etc
│   │   └── Upgrade Trees          # Hierarquia de upgrades
│   │
│   ├── upgrades_config.py         # 📋 Configuração detalhada de upgrades
│   │   ├── UPGRADE_DESCRIPTIONS   # Textos dos upgrades
│   │   ├── UPGRADE_COSTS          # Custo de cada upgrade
│   │   ├── UPGRADE_EFFECTS        # Impacto de cada upgrade
│   │   └── Balance Multipliers    # Ajustes de power
│   │
│   ├── state.py                   # 🎯 Máquina de estados do jogo
│   │   ├── GameState             # Estados: MENU, PLAYING, PAUSED, GAME_OVER
│   │   ├── State Transitions      # Lógica de mudança de estados
│   │   └── State Handlers         # Ações por estado
│   │
│   └── time.py                    # ⏱️ Gerenciamento de tempo
│       ├── Delta Time             # Frame timing
│       ├── Timers                 # Cooldowns, spawn rates
│       └── Frame Limiting         # Controle de FPS
│
├── entities/                       # 🎮 Todas as entidades do jogo (33 arquivos)
│   │
│   ├── 👨‍✈️ Player
│   │   ├── ship.py                # 🚀 NAVE DO JOGADOR
│   │   │   ├── Movement           # Posição, velocidade, aceleração
│   │   │   ├── Hitpoints          # Vida, invulnerabilidade
│   │   │   ├── Weapons            # Tipos de tiro (bullet, laser)
│   │   │   ├── Animation          # Sprite animation
│   │   │   ├── Collision          # Hitbox da nave
│   │   │   └── Status Effects     # Shield, speed boost, etc
│   │   │
│   │   ├── bullet.py              # 🔫 Balas básicas da nave
│   │   │   ├── Speed              # Velocidade do projétil
│   │   │   ├── Damage             # Dano causado
│   │   │   ├── Lifetime           # Tempo antes de desaparecer
│   │   │   ├── Collision Detection
│   │   │   └── Pooling            # Reutilização de objetos
│   │   │
│   │   └── player_laser.py        # ⚡ Laser carregável do jogador
│   │       ├── Charging Logic     # Acumula dano
│   │       ├── Fire Pattern       # Padrão do laser
│   │       ├── Range              # Alcance
│   │       └── Knockback          # Recuo do laser
│   │
│   ├── 👾 Inimigos - Tier 1 (Aparição frequente)
│   │   ├── meteor.py              # ☄️ METEORO (Inimigo básico)
│   │   │   ├── Size               # Pequeno, médio, grande
│   │   │   ├── HP                 # Vida do meteoro
│   │   │   ├── Speed              # Velocidade de queda
│   │   │   ├── Rotation           # Rotação durante queda
│   │   │   └── Break Apart        # Fragmentação ao explodir
│   │   │
│   │   └── alien.py               # 🛸 NAVE INIMIGA (Tiro inteligente)
│   │       ├── Behavior           # IA: patrulha, avalia, atira
│   │       ├── Movement           # Movimento em padrões
│   │       ├── Weapon             # Tiro para o player
│   │       ├── Formation Support  # Funciona em grupo
│   │       └── Tactical AI        # Evita obstáculos
│   │
│   ├── 👾 Inimigos - Tier 2 (Aparição média)
│   │   └── eye_enemy.py           # 👁️ OLHO INIMIGO (Laser contínuo)
│   │       ├── Eye Animation      # Piscar, olhar
│   │       ├── Laser Beam         # Dispara raio contínuo
│   │       ├── Tracking           # Segue o player
│   │       ├── HP                 # Vida média
│   │       └── Aggressive Pattern # Padrão de ataque
│   │
│   ├── 👑 Bosses
│   │   ├── boss.py                # 👹 BOSS 1 (Boss clássico)
│   │   │   ├── Boss HP            # Muita vida (200-500)
│   │   │   ├── Attack Patterns    # Múltiplos padrões
│   │   │   ├── Phase System       # Fases diferentes
│   │   │   ├── Cannon Attacks     # Tiros em espiral
│   │   │   ├── Movement           # Padrão de movimento
│   │   │   ├── Loot Drop          # Power-ups ao morrer
│   │   │   └── Music Change       # Tema especial
│   │   │
│   │   ├── boss_cannon.py         # 🎯 Canhão do boss
│   │   │   ├── Firing Direction   # Ângulo de tiro
│   │   │   ├── Bullet Type        # Tipo de projétil
│   │   │   ├── Rate of Fire       # Cadência
│   │   │   └── Sound Effects      # SFX de canhão
│   │   │
│   │   ├── boss_laser.py          # ⚡ Laser do boss
│   │   │   ├── Beam Direction     # Direção do laser
│   │   │   ├── Damage Over Time   # Dano contínuo
│   │   │   ├── Duration           # Tempo de duração
│   │   │   └── Visual Effects     # Glow e partículas
│   │   │
│   │   ├── boss_particles.py      # ✨ Efeitos de partículas do boss
│   │   │   ├── Spawn Emitter      # Gerador de partículas
│   │   │   ├── Particle Types     # Diferentes tipos de partículas
│   │   │   ├── Color Gradients    # Degradês de cores
│   │   │   └── Physics            # Gravidade, movimento
│   │   │
│   │   ├── boss_square.py         # 🟦 Quadrado de ataque do boss
│   │   │   ├── Collision Box      # Área do ataque
│   │   │   ├── Damage Area        # Região de dano
│   │   │   └── Visual Indicator   # Mostra onde vai acertar
│   │   │
│   │   └── spike_boss.py          # 🔱 BOSS 2 - Spike Boss (Boss espinhoso)
│   │       ├── Spike Armor        # Espinhos de defesa
│   │       ├── Spin Attack        # Rotação com espinhos
│   │       ├── Charging Pattern   # Carregamento de ataque
│   │       ├── Phase 1-3          # Diferentes fases
│   │       ├── Reflection Ability  # Reflete balas
│   │       ├── Desperation Mode   # Modo final agressivo
│   │       └── Music Escalation   # Música intensifica
│   │
│   ├── 🎁 Poderes e Itens
│   │   ├── powerup.py             # 📦 Power-ups genéricos
│   │   │   ├── PowerUp Types      # Life, Shield, Double Shot, Speed, etc
│   │   │   ├── Duration           # Tempo de ativação
│   │   │   ├── Visual Indication  # Cor/brilho do poder
│   │   │   ├── Collection         # Pickup logic
│   │   │   └── Effects            # O que o poder faz
│   │   │
│   │   ├── explosive_mine.py      # 💣 Minas explosivas
│   │   │   ├── Trigger Detection  # Detecta aproximação
│   │   │   ├── Detonation         # Explosion ao disparar
│   │   │   ├── Blast Radius       # Área de efeito
│   │   │   ├── Damage             # Dano da explosão
│   │   │   └── Chaining           # Explosão em cadeia
│   │   │
│   │   └── floating_score.py      # 💯 Números flutuantes de score
│   │       ├── Score Display      # Mostra pontos
│   │       ├── Float Animation    # Sobe e desaparece
│   │       ├── Color Based        # Cor depende do valor
│   │       └── Text Rendering     # Renderização de texto
│   │
│   ├── 🎯 Ataques Especiais
│   │   ├── spike_boss_laser.py    # ⚡ Laser do spike boss
│   │   │   ├── Beam Pattern       # Padrão especial
│   │   │   ├── Damage Per Frame   # Dano contínuo
│   │   │   └── Visual FX          # Efeitos especiais
│   │   │
│   │   └── emp_wave.py            # 🌊 Onda EMP (stun de inimigos)
│   │       ├── Radius             # Alcance da onda
│   │       ├── Stun Duration      # Tempo de paralisia
│   │       ├── Particle FX        # Efeito visual
│   │       └── Chain Reaction     # Propaga para outros
│   │
│   ├── 🔨 Suporte do Jogador
│   │   ├── mini_ship.py           # 🚁 Mini navios de apoio
│   │   │   ├── Orbit Pattern      # Órbita ao redor da nave
│   │   │   ├── Independent Fire   # Dispara sozinhos
│   │   │   ├── HP                 # Vida individual
│   │   │   ├── Targeting AI       # IA para mira
│   │   │   └── Formation Support  # Posição relativa ao player
│   │   │
│   │   └── mini_ship_bullet.py    # 🔫 Balas dos mini ships
│   │       ├── Speed              # Velocidade diferente
│   │       ├── Damage             # Dano reduzido
│   │       ├── Visual Difference  # Cor/tamanho diferente
│   │       └── Sound Effect       # SFX próprio
│   │
│   ├── 📊 Comportamento de Grupo
│   │   ├── formation.py           # 👥 Formações de inimigos
│   │   │   ├── Formation Types    # V, linha, espiral
│   │   │   ├── Leader Follower    # Inimigos seguem líder
│   │   │   ├── Sync Firing        # Atacam juntos
│   │   │   ├── Breakaway Logic    # Quando se separam
│   │   │   └── Reformation        # Recriam formação
│   │   │
│   │   └── guided_meteor.py       # ☄️ Meteoro guiado (inteligente)
│   │       ├── Tracking           # Segue o player
│   │       ├── Evasion            # Desvia de balas
│   │       ├── Smart Timing       # Cronometra rotação
│   │       ├── Speed Variation    # Varia velocidade
│   │       └── Difficulty Scale   # Mais difícil em níveis altos
│   │
│   ├── 💥 Efeitos Visuais
│   │   ├── explosion.py           # 💥 Explosões genéricas
│   │   │   ├── Animation Frames   # Sequência de frames
│   │   │   ├── Sound              # Som de explosão
│   │   │   ├── Particle Spray     # Partículas saindo
│   │   │   ├── Screen Shake       # Tremor da câmera
│   │   │   └── Pooling            # Reutilização
│   │   │
│   │   ├── mine_explosion.py      # 💣 Explosão de mina
│   │   │   ├── Intensity          # Explosão maior
│   │   │   ├── Knockback Force    # Empurra entidades
│   │   │   ├── Damage Multiplier  # Dano maior
│   │   │   └── Chain Trigger      # Causa em cadeia
│   │   │
│   │   ├── boss_particles.py      # ✨ Partículas especiais do boss
│   │   │   ├── Custom Colors      # Cores do boss
│   │   │   ├── Swirls             # Padrões especiais
│   │   │   └── Phase Effects      # Muda com fases
│   │   │
│   │   └── explosive_effect.py    # 🌫️ Efeito de explosão controlado
│   │       ├── Manual Control     # Controle de intensidade
│   │       ├── Custom Particles   # Customização
│   │       └── Performance Mode   # Versão leve para performance
│   │
│   ├── ⭐ Extras Decorativos
│   │   └── star.py                # ⭐ Estrelas de fundo (parallax)
│       └── air_strike_*           # 🎯 Ataques aéreos especiais
│
├── scenes/                         # 🎬 Cenas do jogo (UI + Lógica)
│   ├── main_menu.py               # 📋 Menu principal
│   │   ├── Title Animation        # Animação do título
│   │   ├── Buttons                # Play, Settings, Quit
│   │   ├── Background Music       # Tema do menu
│   │   └── Settings Panel         # Audio, controles
│   │
│   ├── playing.py                 # 🎮 Cena de JOGO (Principal)
│   │   ├── Game Loop              # Main update loop
│   │   ├── Spawn Manager          # Gera inimigos
│   │   ├── Collision Handler      # Detecta colisões
│   │   ├── Score System           # Calcula pontos
│   │   ├── Level Progression      # Avança de nível
│   │   ├── Boss Spawner           # Cria bosses
│   │   └── Audio Manager          # Sons durante jogo
│   │
│   ├── paused.py                  # ⏸️ Tela de pausa
│   │   ├── Pause Menu             # Resume, Settings, Quit
│   │   ├── Blur Background        # Desfoca jogo
│   │   ├── Music Pause            # Para a música
│   │   └── Input Handling         # Processa input pausa
│   │
│   ├── game_over.py               # 💀 Tela de Game Over
│   │   ├── Final Score Display    # Mostra score final
│   │   ├── Best Score             # Record anterior
│   │   ├── Restart Button         # Recomeça jogo
│   │   ├── Stats Summary          # Resumo da sessão
│   │   └── Highscore Update       # Atualiza record
│   │
│   ├── difficulty_selection.py    # 🎚️ Seleção de dificuldade
│   │   ├── Difficulty Buttons     # Easy, Medium, Hard, Insane
│   │   ├── Description Panel      # Explica cada nível
│   │   ├── Recommended Level      # Marca sugerido
│   │   └── Preview Stats          # Mostra mudanças
│   │
│   ├── upgrades_selection.py      # 🔧 Seleção de upgrades pré-jogo
│   │   ├── Upgrade Grid           # Display de upgrades
│   │   ├── Points Available       # Pontos restantes
│   │   ├── Apply Button           # Confirma seleção
│   │   ├── Reset Option           # Reseta upgrades
│   │   └── Cost Display           # Mostra custos
│   │
│   ├── settings.py                # ⚙️ Menu de configurações
│   │   ├── Volume Slider          # Áudio master
│   │   ├── Difficulty Modifier    # Ajuste de dificuldade
│   │   ├── Graphics Settings      # Qualidade visual
│   │   ├── Controls Mapping       # Remap de controles
│   │   ├── Language Select        # Idioma
│   │   └── Save/Load Config
│   │
│   └── statistics.py              # 📊 Tela de estatísticas
│       ├── Total Playtime         # Tempo total jogado
│       ├── Total Kills            # Inimigos derrotados
│       ├── Boss Defeats           # Bosses vencidos
│       ├── Highest Score          # Melhor score
│       ├── Longest Run            # Maior sequência
│       ├── Unlocks Display        # O que foi desbloqueado
│       └── Export Stats           # Salva dados
│
├── systems/                        # ⚙️ Sistemas de jogo
│   ├── entity_manager.py          # 🗂️ Gerenciador de entidades
│   │   ├── Add Entity             # Cria nova entidade
│   │   ├── Remove Entity          # Deleta entidade
│   │   ├── Update All             # Atualiza todos
│   │   ├── Get Entities By Type   # Filtra entidades
│   │   ├── Collision Queries      # Busca por colisão
│   │   └── Spatial Indexing       # Otimização de busca
│   │
│   ├── spawner.py                 # 👾 Gerador de inimigos
│   │   ├── Spawn Rates            # Taxa por tipo
│   │   ├── Wave System            # Ondas de inimigos
│   │   ├── Boss Spawn Logic       # Quando bosses aparecem
│   │   ├── Difficulty Scaling     # Ajusta por nível
│   │   ├── Spawn Points           # Posições de spawn
│   │   └── Cooldown Management    # Controla frequência
│   │
│   └── collisions.py              # 💥 Detecção de colisões
│       ├── Hitbox System          # Define hitboxes
│       ├── Collision Checks       # Detecta contatos
│       ├── Collision Callbacks    # Responde a contato
│       ├── Damage Calculation     # Calcula dano
│       ├── Push/Knockback         # Movimento por impacto
│       └── Status Effect Apply    # Aplica efeitos
│
├── render/                         # 🎨 Renderização
│   ├── renderer.py                # 🖼️ Motor de renderização
│   │   ├── Draw Sprites           # Renderiza sprites
│   │   ├── Draw Text              # Renderiza UI
│   │   ├── Layer System           # Gerencia profundidade
│   │   ├── Camera Follow          # Câmera no player
│   │   ├── Screen Effects         # Desfoque, distorção
│   │   ├── Performance Monitor    # Mostra FPS
│   │   └── Debug Visualization    # Mostra hitboxes
│   │
│   └── __init__.py
│
└── assets/                         # 🎨 Recursos do jogo
    ├── images/                    # 🖼️ Imagens (45MB+)
    │   ├── ship/                  # 🚀 Sprite da nave
    │   ├── enemies/               # 👾 Sprites dos inimigos
    │   │   ├── meteors/           # ☄️ Diferentes tamanhos
    │   │   ├── aliens/            # 🛸 Variações
    │   │   ├── eye/               # 👁️ Sprites do olho
    │   │   └── formations/        # Padrões de grupo
    │   ├── bosses/                # 👑 Sprites dos bosses
    │   │   ├── boss1/             # Frames de animação
    │   │   ├── spike_boss/        # Variações de fases
    │   │   ├── cannons/           # Canhões
    │   │   └── lasers/            # Efeitos de laser
    │   ├── effects/               # ✨ Efeitos visuais
    │   │   ├── explosions/        # Explosões (spritesheet)
    │   │   ├── particles/         # Partículas
    │   │   ├── powerups/          # Ícones de power
    │   │   └── trails/            # Rastros de movimento
    │   ├── ui/                    # 🖱️ Interface gráfica
    │   │   ├── buttons/           # Botões
    │   │   ├── icons/             # Ícones
    │   │   ├── panels/            # Painéis
    │   │   ├── fonts_rendered/    # Texto pré-renderizado
    │   │   └── backgrounds/       # Fundos de menu
    │   ├── backgrounds/           # 🌌 Fundos do jogo
    │   │   ├── space_bg.png       # Espaço estrelado
    │   │   ├── parallax_layers/   # Camadas de parallax
    │   │   ├── planets/           # 🪐 Planetas decorativos
    │   │   └── nebulas/           # Nebulosas
    │   ├── cursors/               # 🖱️ Cursores customizados
    │   │   ├── default/           # Padrão
    │   │   ├── hover/             # Hover em botão
    │   │   └── aim/               # Mira de tiro
    │   └── icons/                 # 📦 Ícones diversos
    │       ├── locked_icon/       # 🔒 Bloqueado
    │       └── star_icon/         # ⭐ Estrela
    │
    ├── sounds/                    # 🔊 Áudios (15MB+)
    │   ├── music/                 # 🎵 Musica de fundo
    │   │   ├── background.mp3     # Tema principal
    │   │   ├── background_02.mp3  # Variação
    │   │   ├── boss.mp3           # Tema de boss
    │   │   ├── spike_boss_theme/  # Tema spike boss
    │   │   └── menu-music.mp3     # Tema do menu
    │   │
    │   └── sfx/                   # 🔫 Efeitos sonoros
    │       ├── shots/             # Tiros
    │       │   ├── tiro_1-3.wav   # Sons de tiro diferentes
    │       │   ├── som_laser.mp3  # Som do laser
    │       │   ├── som_laser_carregando.mp3  # Carregamento
    │       │   └── tiro_laser_eye.wav  # Laser do olho
    │       │
    │       ├── explosions/        # Explosões
    │       │   ├── explosão_asteroides_0-3.wav  # Sons variados
    │       │   ├── explosão_nave.wav   # Explosão da nave
    │       │   ├── explosão_naves_alienigenas.wav  # Inimigo explodindo
    │       │   ├── explisão_boss.wav   # Boss explodindo
    │       │   └── som_dano_boss.wav   # Dano de boss
    │       │
    │       ├── ui/                # Efeitos de UI
    │       │   ├── sound_hover.wav    # Hover em botão
    │       │   ├── powerUp.wav        # Pega power-up
    │       │   ├── powerUp_02.wav     # Variação
    │       │   ├── Ativação_Aprimoramentos.wav  # Ativa upgrade
    │       │   ├── Usar_Depois.wav    # Som reservado
    │       │   ├── warning.mp3        # Alerta/perigo
    │       │   └── som_chuva_meteoro_1-4.wav  # Sons de chuva
    │       │
    │       └── special/           # Sons especiais
    │           ├── laser_spike_boss.wav  # Laser especial
    │           └── sci-fi-weapon-*.mp3   # Outros SFX
    │
    ├── fonts/                     # 🔤 Fontes
    │   └── PressStart2P-Regular.ttf  # Fonte retro pixel
    │
    └── README.md                  # 📖 Documentação dos assets
```

### 📊 Resumo por Tipo

**👨‍✈️ Jogador:** 3 arquivos (ship, bullet, laser)

**👾 Inimigos:** 3 tipos básicos (meteor, alien, eye_enemy)

**👑 Bosses:** 8 arquivos (boss, spike_boss, cannons, lasers, particles, squares)

**🎁 Itens:** 3 tipos (powerup, mines, floating_score)

**🔨 Suporte:** 2 tipos (mini_ship, mini_ship_bullet)

**📊 Grupo:** 2 sistemas (formation, guided_meteor)

**💥 Efeitos:** 4 tipos (explosion, mine_explosion, boss_particles, explosive_effect)

**⭐ Decoração:** 1 tipo (star, air_strike)

**Total:** 33+ arquivos de entidades + 8 cenas + 4 sistemas + assets

**Assets Totais:** ~60MB (45MB imagens + 15MB áudio)

---

## 🏗️ Estrutura Proposta para Godot

```
space_shooter_godot/
├── scenes/
│   ├── main_menu/
│   │   ├── MainMenu.tscn        # Cena visual
│   │   └── MainMenu.gd          # Script GDScript
│   │
│   ├── game/
│   │   ├── GameScene.tscn       # Cena principal
│   │   ├── GameScene.gd         # Lógica principal
│   │   ├── Player.tscn          # Nave do jogador
│   │   ├── Player.gd            # Lógica da nave
│   │   └── EnemySpawner.gd      # Gerador de inimigos
│   │
│   ├── enemies/
│   │   ├── Meteor.tscn
│   │   ├── Meteor.gd
│   │   ├── Alien.tscn
│   │   ├── Alien.gd
│   │   ├── EyeEnemy.tscn
│   │   ├── EyeEnemy.gd
│   │   ├── Boss.tscn
│   │   └── Boss.gd
│   │
│   ├── ui/
│   │   ├── PauseMenu.tscn
│   │   ├── PauseMenu.gd
│   │   ├── GameOver.tscn
│   │   ├── HUD.tscn
│   │   └── HUD.gd
│   │
│   └── upgrades/
│       ├── UpgradesMenu.tscn
│       └── UpgradesMenu.gd
│
├── scripts/
│   ├── GameManager.gd          # Gerenciador global (Config)
│   ├── DifficultyManager.gd    # Sistema de dificuldade
│   ├── LevelManager.gd         # Sistema de níveis
│   ├── InputManager.gd         # Gerenciador de entrada
│   ├── AudioManager.gd         # Gerenciador de áudio
│   ├── UpgradeManager.gd       # Sistema de upgrades
│   ├── PhysicsManager.gd       # Física personalizada
│   └── Constants.gd            # Constantes globais
│
├── assets/
│   ├── images/
│   │   ├── player/
│   │   ├── enemies/
│   │   ├── bosses/
│   │   ├── effects/
│   │   ├── backgrounds/
│   │   └── ui/
│   │
│   ├── sounds/
│   │   ├── sfx/
│   │   ├── music/
│   │   └── ui/
│   │
│   ├── fonts/
│   └── shaders/
│
└── project.godot            # Arquivo de configuração do Godot
```

---

## 📦 Mapeamento de Funcionalidades

### Core/Config → GameManager.gd
```gdscript
# Em vez de:
class Config:
    FULLSCREEN: bool = True
    SCREEN_WIDTH: int = 1600
    FPS: int = 120

# Uso em Godot:
extends Node

const FULLSCREEN = true
const SCREEN_WIDTH = 1600
const FPS = 120

func _ready():
    get_tree().root.content_scale_mode = Window.CONTENT_SCALE_MODE_VIEWPORT
    get_tree().root.content_scale_size = Vector2i(1600, 900)
```

### Entities → Scenes com Scripts
```gdscript
# Player.tscn (Cena visual)
- CharacterBody2D (root)
  - Sprite2D (imagem)
  - CollisionShape2D
  - AnimatedSprite2D
  - Timer (para cooldown de tiro)

# Player.gd (Script GDScript)
extends CharacterBody2D

var speed = 300
var ship_image = preload("res://assets/images/ship.png")

func _ready():
    $Sprite2D.texture = ship_image

func _process(delta):
    handle_input()
    update_position(delta)
```

### Scenes (UI) → Cenas Godot
```gdscript
# Mapeamento direto:
main_menu.py → scenes/main_menu/MainMenu.tscn + MainMenu.gd
playing.py   → scenes/game/GameScene.tscn + GameScene.gd
paused.py    → scenes/ui/PauseMenu.tscn + PauseMenu.gd
game_over.py → scenes/ui/GameOver.tscn + GameOver.gd
```

### Systems → Managers Globais
```gdscript
# EntityManager.py → gerenciado pelo Godot (SceneTree)
# Spawner.py → EnemySpawner.gd (nó na cena)
# Collisions.py → area_entered/body_entered signals
```

---

## 🎯 Fase de Migração Recomendada

### Fase 1: Setup Básico para Mobile (1-2 semanas)
- [ ] Criar projeto Godot com suporte Android/iOS
- [ ] Importar e **comprimir** assets (PNG 50-70%, MP3 64kbps)
- [ ] Criar GameManager mobile-first
- [ ] Configurar resolução portrait (540x960)
- [ ] Testar em emulador Android

### Fase 2: Mecânicas Básicas Mobile (2-3 semanas)
- [ ] Criar Player (nave) com toque contínuo
- [ ] Sistema de tiro automático
- [ ] **Virtual Joystick** (opcional) ou seguir dedo
- [ ] Inimigos básicos (Meteor)
- [ ] Testar controle no celular real (não só emulador)

### Fase 3: Inimigos Avançados (2-3 semanas)
- [ ] Alien (comportamento IA)
- [ ] EyeEnemy (movimento padrão)
- [ ] Todos os tipos de inimigos

### Fase 4: Bosses (2-3 semanas)
- [ ] Boss 1 (padrão)
- [ ] Boss 2 (Spike Boss)
- [ ] Padrões de ataque

### Fase 5: UI e Progresso (2 semanas)
- [ ] Menu principal
- [ ] Sistema de níveis
- [ ] Upgrade screen
- [ ] HUD (vida, score)

### Fase 6: Polimento (1-2 semanas)
- [ ] Efeitos sonoros
- [ ] Música
- [ ] Partículas
- [ ] Otimização

**Total estimado: 2-3 meses** (mais rápido que desktop, sem suportar Windows/Mac)

---

## 🚀 Arquitetura Mobile-First

### Prioridades Diferentes

**Desktop:**
- Qualidade visual máxima
- Resolução 1600x900
- Sem limites de tamanho

**Mobile:**
- Performance > Qualidade
- Resolução 540x960 (portrait)
- <25MB total
- Bateria eficiente
- Touch intuitivo

### Estrutura de Configuração Mobile

```gdscript
# Constants.gd (Autoload)
extends Node

# Display
const MOBILE_WIDTH = 540
const MOBILE_HEIGHT = 960
const MOBILE_FPS = 60  # Em vez de 120

# Assets
const USE_COMPRESSED_TEXTURES = true
const USE_LOW_QUALITY_AUDIO = true

# Physics
const MOBILE_PHYSICS_SCALE = 2.0  # Ajuste para sensibilidade

# Detecção automática
func is_mobile() -> bool:
    return OS.get_name() in ["Android", "iOS"]
```

---

## 🔑 Conceitos Importantes em Godot

### 1. Scene Tree (em vez de EntityManager)
```gdscript
# Godot gerencia automaticamente
add_child(enemy_instance)  # Adiciona à árvore
remove_child(enemy_instance)  # Remove da árvore
```

### 2. Signals (em vez de Event Listeners)
```gdscript
# Ao invés de callbacks Python:
signal enemy_died(score)

func _on_enemy_died():
    emit_signal("enemy_died", 100)

# Em outro script:
enemy.connect("enemy_died", self, "_on_receive_signal")
```

### 3. Physics (integrado)
```gdscript
# Ao invés de cálculos manuais:
extends CharacterBody2D

func _physics_process(delta):
    velocity = Vector2(200, 0)
    move_and_slide()
```

### 4. Autoload (Singletons Globais)
```gdscript
# GameManager.gd como Autoload
# Acesso de qualquer lugar:
GameManager.add_score(100)
GameManager.get_lives()
```

---

## 📱 Adaptações para Mobile (PRIORIDADE!)

### 🎮 Sistema de Controle Touch

#### Opção 1: Toque Contínuo (Recomendado para este jogo)
```gdscript
# Player.gd
extends CharacterBody2D

var touch_position: Vector2 = Vector2.ZERO
var is_touching: bool = false

func _input(event):
    if event is InputEventScreenTouch:
        if event.pressed:
            is_touching = true
            touch_position = event.position
        else:
            is_touching = false
    
    elif event is InputEventScreenDrag:
        touch_position = event.position

func _process(delta):
    if is_touching:
        # Seguir o dedo
        var direction = touch_position - global_position
        if direction.length() > 0:
            global_position = global_position.lerp(touch_position, 5.0 * delta)
            # Limitar aos limites da tela
            global_position.x = clamp(global_position.x, 0, get_viewport_rect().size.x)
            global_position.y = clamp(global_position.y, 0, get_viewport_rect().size.y)
```

#### Opção 2: Virtual Joystick (Alternativa)
```gdscript
# VirtualJoystick.gd
extends Control

var joystick_area: TouchScreenButton
var output_vector: Vector2 = Vector2.ZERO

func _ready():
    joystick_area = TouchScreenButton.new()
    add_child(joystick_area)

func _input(event):
    if event is InputEventScreenTouch:
        output_vector = (event.position - get_rect().get_center()).normalized()
```

### 🎯 Sistema de Tiro - Automático vs Toque

#### Automático (Melhor para mobile)
```gdscript
# Disparar continuamente, sem precisar clicar
func _ready():
    fire_rate_timer = Timer.new()
    add_child(fire_rate_timer)
    fire_rate_timer.wait_time = 0.15
    fire_rate_timer.timeout.connect(shoot)
    fire_rate_timer.start()

func shoot():
    var bullet = bullet_scene.instantiate()
    get_parent().add_child(bullet)
    bullet.global_position = global_position
```

#### Toque para Atirar (Alternativa)
```gdscript
# Atacar na área específica da tela
func _input(event):
    if event is InputEventScreenTouch and event.pressed:
        if event.position.y < get_viewport_rect().size.y * 0.3:  # Parte superior da tela
            shoot()
```

### 📱 Resolução Adaptativa para Celular

```gdscript
# GameManager.gd (Autoload)
extends Node

# Detectar tamanho da tela
func _ready():
    var screen_size = get_viewport_rect().size
    
    # Ajustar para portrait (vertical)
    if screen_size.y > screen_size.x:
        var target_width = 540
        var target_height = 960
        get_window().size = Vector2i(target_width, target_height)
    
    # Detectar densidade de pixels (celular de alta resolução)
    var dpi = DisplayServer.screen_get_dpi()
    print("DPI: ", dpi)  # 160 (padrão), 320+ (high-density)

# Escala responsiva
func get_scale_factor() -> float:
    var screen_size = get_viewport_rect().size
    return screen_size.x / 540.0  # Relativo a 540px de largura
```

### 🖼️ Assets Otimizados para Mobile

```
# Tamanhos recomendados (de 60MB → 15-20MB):

Imagens:
├── ship.png            → 256x256px (de 1024x1024)
├── enemies/
│   ├── meteor.png     → 128x128px
│   ├── alien.png      → 256x256px
│   └── boss.png       → 512x512px
└── effects/
    └── explosion.png  → 256x256px (spritsheet)

Áudio (MP3 comprimido):
├── sfx/ → 64kbps (em vez de 320kbps)
└── music/ → 128kbps

Total estimado: 18-25MB
```

### ⚙️ Otimizações para Performance Mobile

```gdscript
# 1. Reduzir FPS para 60 (em vez de 120)
func _ready():
    Engine.max_fps = 60

# 2. Pooling de objetos (inimigos e balas)
class_name BulletPool
extends Node

var bullet_pool: Array[Bullet] = []
var pool_size: int = 100

func _ready():
    for i in range(pool_size):
        var bullet = Bullet.new()
        bullet_pool.append(bullet)

# 3. Desativar sombras complexas
# Project Settings > Rendering > Textures > VRAM Compression > Enable
```

### 📏 Adaptação de UI para Touch

```gdscript
# Botões maiores (mínimo 44x44 pts)
func create_button(text: String) -> Button:
    var button = Button.new()
    button.text = text
    button.custom_minimum_size = Vector2(80, 60)  # Grande o suficiente para dedo
    button.add_theme_font_size_override("font_size", 24)
    return button

# Evitar small UI elements
# ✅ BOM: Botões 60x60px
# ❌ RUIM: Botões 30x30px (difícil de clicar com dedo)
```

### 📱 Exports e Build para Mobile

```gdscript
# Para Android no Project.godot:
[export_options.android]
package/name = "com.example.spaceshooter"
package/unique_name = "Space Shooter"
permissions = ["INTERNET"]
orientation = "portrait"  # Ou "sensor" para auto-rotate

# Para iOS:
[export_options.ios]
package/name = "Space Shooter"
orientation = "portrait"
```

### 🎮 Mapeamento de Controles Mobile

```
┌─────────────────────────────────┐
│                                 │
│     ÁREA DE MOVIMENTO           │  ← Toque para mover nave
│     (Esquerda/Direita)          │
│                                 │
├─────────────────────────────────┤
│  SCORE: 5000    VIDAS: 3        │  ← HUD
├─────────────────────────────────┤
│                                 │
│     ÁREA DE JOGO                │
│     (Automático ou toque)       │
│                                 │
│                [PAUSA]          │  ← Botão flutuante
└─────────────────────────────────┘
```

---

## 🎨 Assets: Compressão para Mobile

### Estratégia de Compressão

**Antes (Desktop):** 60MB
```
Imagens PNG (originais): 45MB
Áudio MP3 (320kbps): 15MB
```

**Depois (Mobile):** 18-22MB
```
Imagens PNG (50-70% qualidade): 15-18MB
Áudio MP3 (64kbps): 3-5MB
```

### Ferramentas Recomendadas

1. **TinyPNG** (Online) - Compressão PNG
   - Reduz 30-50% sem perda visual
   - https://tinypng.com/

2. **FFmpeg** (Comando) - Comprimir Áudio
   ```bash
   ffmpeg -i input.mp3 -b:a 64k output.mp3
   ```

3. **ImageMagick** - Batch resize
   ```bash
   convert input.png -resize 50% output.png
   ```

### Estrutura de Import
```
1. Copiar assets comprimidos para res://assets/
2. Godot importa automaticamente
3. Referenciar via caminho: preload("res://assets/images/ship.png")
4. Ativar compressão VRAM: Project Settings > Rendering > Textures > VRAM Compression
```

### Compatibilidade
- ✅ PNG (comprimido) → Funciona perfeitamente
- ✅ MP3 (64kbps) → Qualidade aceitável em fones
- ✅ TTF → Fonts automáticas

---

## 💾 Checklist Mobile-First

### Antes de Começar
- [ ] Instalar Godot 4.x
- [ ] Instalar Android SDK (para Android Export)
- [ ] Instalar extensão "Godot Tools" no VSCode
- [ ] Testar emulador Android no seu PC
- [ ] Baixar e **comprimir** seus assets

### Configuração Godot para Mobile
- [ ] File > Project Settings > Display > Window
  - [ ] Initial Size Width: 540
  - [ ] Initial Size Height: 960
  - [ ] Orientation: Portrait
  - [ ] Stretch Mode: Canvas Items
  - [ ] Stretch Aspect: Keep Size
- [ ] Project > Project Settings > Rendering
  - [ ] Textures > VRAM Compression: Enable (reduz memória)
  - [ ] Quality > Gles3: Disable (melhor performance)

### Primeira Semana
- [ ] Criar novo projeto Godot mobile
- [ ] Comprimir todas as imagens (50-70%)
- [ ] Comprimir todos os áudios (64kbps)
- [ ] Criar GameManager para mobile
- [ ] Criar Player com controle touch

### Testar no Hardware Real
- [ ] Conectar telefone Android via USB
- [ ] Fazer debug no Device
- [ ] Testar performance (deve rodar 60 FPS)
- [ ] Verificar bateria/temperatura

---

## 📚 Recursos Úteis

### Documentação
- https://docs.godotengine.org/ (Oficial)
- https://gdscript.com/ (GDScript cheatsheet)

### Tutoriais Recomendados
- Godot 2D Game Dev Course (YouTube)
- Making a Space Shooter in Godot (GDQuest)

### Comunidade
- r/godot (Reddit)
- Godot Engine Discord
- GodotGDScript forums

---

## ⚠️ Armadilhas Comuns

1. **Esquecer de salvamento:** Godot salva cenas, não estados
2. **Performance:** 60 FPS é padrão, otimize para mobile
3. **Resolução:** Defina cedo, mude depois é difícil
4. **Assets grandes:** Comprima se > 2MB cada
5. **Lógica em _process:** Use _physics_process para physics

---

## ✨ Próximas Etapas

1. **Agora:** Revisar este plano
2. **Semana 1:** Instalar Godot e criar projeto básico
3. **Semana 2:** Implementar primeira cena (menu ou jogo)
4. **Contínuo:** Adaptar cada módulo do seu projeto

**Boa sorte na migração! 🚀**

Você quer que eu comece a ajudar com alguma fase específica?
