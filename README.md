# 🚀 Jogo de Nave (Space Shooter)

Um emocionante jogo de tiro espacial de progressão infinita, desenvolvido em Python com a biblioteca Pygame. Desafie suas habilidades desviando de asteroides, destruindo naves alienígenas e enfrentando chefes poderosos para alcançar a maior pontuação possível.

## ✨ Funcionalidades Principais

- **Jogabilidade Infinita:** Sobreviva o máximo que puder contra ondas crescentes de inimigos.
- **Inimigos Variados:** Enfrente meteoros, naves alienígenas, meteoros teleguiados e chefes desafiadores.
- **Power-ups com Raridade:** Colete power-ups para ganhar vantagens, com um sistema de raridade que torna cada partida única:
  - **Shield (20%):** Proteção temporária contra danos.
  - **Double Shot (25%):** Aumenta seu poder de fogo com tiros duplos.
  - **Speed Boost (15%):** Aumenta a velocidade de movimento da sua nave.
  - **Piercing Shot (15%):** Seus tiros atravessam múltiplos inimigos.
  - **Mini Ships (10%):** Adiciona duas pequenas naves auxiliares que disparam com você.
  - **Extra Life (10%):** Ganhe uma vida extra.
  - **Score Multiplier (4%):** Multiplique sua pontuação.
  - **Rainbow (1%):** Ativa todos os outros power-ups simultaneamente!
- **Efeitos Visuais:** Inclui efeitos de explosão e "screen shake" para uma experiência mais imersiva.
- **Sistema de Pontuação:** Sua pontuação aumenta ao destruir inimigos.

## 🎮 Como Jogar

### Pré-requisitos

- Python 3.8 ou superior
- Git

### Instalação

Siga estes passos para configurar o ambiente de desenvolvimento e executar o jogo.

```bash
# 1. Clone o repositório
git clone https://github.com/ErickdeOliveiraBessaXavier/Jogo_Nave.git

# 2. Navegue até o diretório do projeto
cd Jogo_Nave

# 3. (Opcional mas recomendado) Crie e ative um ambiente virtual
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

### Controles

- **Setas Direcionais ou WASD:** Mover a nave.
- **Barra de Espaço:** Atirar (mantenha pressionado para tiro contínuo).
- **P:** Pausar e despausar o jogo.
- **R:** Reiniciar o jogo na tela de "Game Over".
- **ESC:** Sair do jogo.

## 🏗️ Estrutura do Projeto

O projeto é organizado de forma modular para facilitar a manutenção e a adição de novas funcionalidades.

```
Jogo_Nave/
├── game/
│   ├── assets/         # Contém fontes, sons e músicas
│   ├── core/           # Lógica central (configurações, estado, som)
│   ├── entities/       # Todas as entidades do jogo (jogador, inimigos, projéteis)
│   ├── render/         # Lógica de renderização
│   ├── scenes/         # Cenas do jogo (jogando, game over, pausa)
│   └── systems/        # Sistemas de gerenciamento (colisões, spawns)
├── requirements.txt    # Dependências do projeto
└── run.py              # Ponto de entrada da aplicação
```

## 🔧 Tecnologias Utilizadas

- **Linguagem:** Python 3
- **Biblioteca Gráfica:** Pygame
- **Estrutura:** Código modularizado com gerenciamento de cenas e entidades.

---

**Desenvolvido com ❤️ por [ErickdeOliveiraBessaXavier](https://github.com/ErickdeOliveiraBessaXavier)**