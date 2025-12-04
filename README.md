# 🚀 Space Shooter - Jogo de Nave Espacial

Um emocionante jogo de tiro espacial com progressão infinita, desenvolvido em Python com Pygame. Desafie suas habilidades evitando asteroides, destruindo naves alienígenas, enfrentando chefes poderosos e coletando poder-ups para alcançar a maior pontuação possível!

## ✨ Funcionalidades Principais

- **Jogabilidade Infinita:** Sobreviva o máximo que puder contra ondas crescentes de inimigos.
- **Sistema de Dificuldade Dinâmico:** O jogo se adapta automaticamente à sua performance.
- **Inimigos Variados:**
  - Meteoros simples
  - Naves alienígenas
  - Meteoros teleguiados
  - Chefes desafiadores (Boss Spike, Boss Square, Boss Cannon)
  - Mini naves inimigas

- **Sistema de Poder-ups com Raridade:**
  - **Shield (20%):** Proteção temporária contra danos.
  - **Double Shot (25%):** Tiros duplos para maior poder de fogo.
  - **Speed Boost (15%):** Aumenta a velocidade de movimento.
  - **Piercing Shot (15%):** Seus tiros atravessam múltiplos inimigos.
  - **Mini Ships (10%):** Adiciona naves auxiliares que disparam com você.
  - **Extra Life (10%):** Ganhe uma vida extra.
  - **Score Multiplier (4%):** Multiplique sua pontuação.
  - **Rainbow (1%):** Ativa todos os outros poder-ups simultaneamente!

- **Sistema de Aprimoramentos:** Desbloqueie e configure aprimoramentos entre partidas
- **Progressão Meta:** Rastreamento de estatísticas e conquistas ao longo do tempo
- **Efeitos Visuais Imersivos:** Explosões, efeito de tela tremendo e partículas
- **Sistema de Som Completo:** Música de fundo, efeitos sonoros e múltiplas faixas musicais
- **Configurações Personalizáveis:** Ajuste volume de música, SFX e controles
- **Monitoramento de Performance:** Pressione F3 durante o jogo para ver métricas de FPS em tempo real

## 🎮 Como Jogar

### Controles

- **WASD ou Setas Direcionais:** Mover a nave
- **Espaço:** Atirar (mantenha pressionado para tiro contínuo)
- **P:** Pausar/Despausar o jogo
- **ESC:** Voltar/Sair
- **F3:** Mostrar/ocultar informações de performance

### Pré-requisitos

- Python 3.8 ou superior
- Git (opcional)

## 📥 Instalação

### Opção 1: Executável (Recomendado para Usuários)

1. Baixe o instalador `setup_spaceshooter.exe` na página de [Releases](https://github.com/ErickdeOliveiraBessaXavier/Jogo_Nave/releases)
2. Execute o instalador e siga as instruções
3. Clique em "Space Shooter" no menu Iniciar ou na Área de Trabalho para jogar

### Opção 2: Executar do Código-fonte (Para Desenvolvedores)

```bash
# 1. Clone o repositório
git clone https://github.com/ErickdeOliveiraBessaXavier/Jogo_Nave.git

# 2. Navegue até o diretório do projeto
cd Jogo_Nave

# 3. (Recomendado) Crie um ambiente virtual
# Em Windows
python -m venv venv
venv\Scripts\activate

# Em macOS/Linux
python3 -m venv venv
source venv/bin/activate

# 4. Instale as dependências
pip install -r requirements.txt

# 5. Execute o jogo
python run.py
```

## 🏗️ Estrutura do Projeto

O projeto é organizado de forma modular para facilitar manutenção e adição de novas funcionalidades:

```
Jogo_Nave/
├── game/
│   ├── assets/              # Fontes, sons, imagens e ícones
│   │   ├── cursors/         # Cursores personalizados
│   │   ├── fonts/           # Arquivos de fonte TTF
│   │   ├── images/          # Sprites e ícones
│   │   └── sounds/          # Músicas e efeitos sonoros
│   ├── core/                # Lógica central do jogo
│   │   ├── assets.py        # Carregamento de recursos
│   │   ├── config.py        # Configurações globais
│   │   ├── difficulty.py    # Sistema de dificuldade
│   │   ├── meta_progression.py  # Sistema de progressão e estatísticas
│   │   ├── paths.py         # Gerenciamento de caminhos de arquivo
│   │   ├── sound.py         # Sistema de som
│   │   ├── upgrades.py      # Sistema de aprimoramentos
│   │   └── state.py         # Gerenciador de cenas
│   ├── entities/            # Todas as entidades do jogo
│   │   ├── ship.py          # Nave do jogador
│   │   ├── alien.py         # Inimigos alienígenas
│   │   ├── bullet.py        # Projéteis
│   │   ├── boss.py          # Chefes
│   │   └── ...
│   ├── render/              # Renderização
│   │   └── renderer.py      # Engine de renderização
│   ├── scenes/              # Cenas da aplicação
│   │   ├── main_menu.py     # Menu principal
│   │   ├── playing.py       # Cena de jogo
│   │   ├── paused.py        # Tela de pausa
│   │   ├── settings.py      # Configurações
│   │   ├── statistics.py    # Estatísticas
│   │   └── ...
│   └── systems/             # Sistemas de gerenciamento
│       ├── entity_manager.py    # Gerencia entidades
│       ├── collisions.py        # Detecção de colisões
│       └── spawner.py           # Spawner de inimigos
├── requirements.txt         # Dependências Python
├── run.py                   # Ponto de entrada
├── Space_Shooter.spec       # Configuração PyInstaller
├── installer_script.iss     # Script Inno Setup
└── README.md                # Este arquivo
```

## 📊 Performance e Monitoramento

O jogo inclui ferramentas avançadas de monitoramento:

### Monitoramento em Tempo Real
- Pressione **F3** durante o jogo para ver métricas de performance
- Exibe FPS, tempo de frame, uso de memória e outras estatísticas

### Testes Automatizados (Desenvolvimento)
```bash
# Executar teste de performance
python performance_test.py --duration 30 --difficulty normal

# Profiling detalhado
python profile_game.py --duration 15

# Gerar relatório de otimizações
python optimization_report.py
```

## 🔧 Tecnologias Utilizadas

- **Linguagem:** Python 3.8+
- **Biblioteca Gráfica:** Pygame
- **Construção:** PyInstaller
- **Instalador:** Inno Setup
- **Arquitetura:** Padrão de Cenas com Gerenciamento de Estado

## 🐛 Solução de Problemas

### Jogo não inicia após instalação
- Tente reinstalar o jogo
- Verifique se sua placa de vídeo suporta OpenGL
- Consulte o arquivo de log em `%LOCALAPPDATA%\SpaceShooter\error.log`

### Sons não funcionam
- Verifique o volume nas configurações (ESC → Configurações)
- Certifique-se de que seus alto-falantes estão ligados

### Performance baixa
- Reduza a qualidade gráfica nas configurações
- Feche outros aplicativos em segundo plano
- Verifique a temperatura do seu computador

## 📈 Desenvolvimento Futuro

- [ ] Mais tipos de inimigos
- [ ] Novos poder-ups
- [ ] Sistema de pontuação online
- [ ] Melhorias gráficas
- [ ] Mais faixas de música

## 📝 Licença

Este projeto é distribuído sob licença aberta. Sinta-se livre para usar, modificar e distribuir.

## 🤝 Contribuições

Contribuições são bem-vindas! Se você gostaria de contribuir:

1. Faça um Fork do repositório
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Faça commit das suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Faça Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 👨‍💻 Desenvolvedor

**Erick de Oliveira Bessa Xavier**
- GitHub: [@ErickdeOliveiraBessaXavier](https://github.com/ErickdeOliveiraBessaXavier)

---

**Desenvolvido com ❤️ em Python**

Divirta-se jogando! 🎮
