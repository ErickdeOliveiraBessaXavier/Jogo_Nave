# Pixel Patrol — Jogo de Nave Espacial

Um jogo de tiro espacial com progressão por mundos e dificuldade adaptativa,
feito em Python com Pygame. Atravesse biomas distintos, encare ondas crescentes
de inimigos, derrote os chefes de cada mundo e colete poder-ups para alcançar a
maior pontuação possível.

## Funcionalidades Principais

- **Progressão por mundos:** quatro biomas com identidade própria — Espaço,
  Montanha, Cidade e Vulcão — cada um com seus inimigos, chefes e trilha sonora.
- **Dificuldade dinâmica:** o jogo adapta a pressão das ondas à sua performance,
  com presets (Casual, Normal, Hardcore, Pesadelo).
- **Variedade de inimigos:** meteoros, naves alienígenas, projéteis teleguiados,
  drones e tanques urbanos, torres orbitais e mais — apresentados em rampa para
  não sobrecarregar de uma vez.
- **Chefes por mundo:** cada bioma culmina em um chefe próprio com padrões de
  ataque e fases distintas.
- **Poder-ups com raridade:** Escudo, Tiro Duplo, Velocidade, Tiro Perfurante,
  Mini Naves, Vida Extra, Multiplicador de Pontuação, Parada de Tempo, Dano
  Aumentado e o raríssimo Rainbow, que combina vários efeitos de uma vez.
- **Sistema de aprimoramentos:** desbloqueie e configure melhorias entre partidas.
- **Progressão meta:** estatísticas e histórico de desempenho ao longo do tempo.
- **Efeitos visuais imersivos:** explosões, tremor de tela, partículas e vinhetas
  de dano.
- **Áudio completo:** música por mundo/chefe e efeitos sonoros.
- **Configurações personalizáveis:** volume de música/efeitos, resolução
  (576p a 1080p) e controles.
- **Suporte a teclado e controle (gamepad).**
- **Overlay de performance:** pressione F3 durante o jogo para ver FPS e tempo de
  frame em tempo real.

## Como Jogar

### Controles (teclado)

- **WASD ou Setas:** mover a nave
- **Espaço:** atirar (segure para tiro contínuo)
- **P:** pausar / despausar
- **ESC:** voltar / sair
- **F3:** mostrar / ocultar informações de performance

Controles de gamepad também são suportados e podem ser ajustados nas
configurações.

## Instalação

### Opção 1: Executável (recomendado para jogar)

1. Baixe o instalador na página de
   [Releases](https://github.com/ErickdeOliveiraBessaXavier/Jogo_Nave/releases)
2. Execute o instalador e siga as instruções
3. Inicie o Pixel Patrol pelo menu Iniciar ou pela Área de Trabalho

### Opção 2: Executar do código-fonte

Pré-requisitos: Python 3.10 ou superior.

```bash
# 1. Clone o repositório
git clone https://github.com/ErickdeOliveiraBessaXavier/Jogo_Nave.git
cd Jogo_Nave

# 2. (Recomendado) Crie um ambiente virtual
# Windows
python -m venv venv
venv\Scripts\activate
# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Execute o jogo
python run.py
```

## Estrutura do Projeto

```
Jogo_Nave/
├── game/
│   ├── assets/        # Fontes, sons, música, imagens e cursores
│   ├── core/          # Logica central (config, dificuldade, audio, progressao)
│   ├── entities/      # Nave, inimigos, chefes, projeteis e poder-ups
│   ├── render/        # Renderizacao do quadro de jogo
│   ├── scenes/        # Menu, jogo, pausa, configuracoes, estatisticas
│   └── systems/       # Gerencia de entidades, colisoes e spawn
├── requirements.txt   # Dependencias Python
├── pyproject.toml     # Configuracao do projeto
└── run.py             # Ponto de entrada
```

## Tecnologias

- **Linguagem:** Python 3.10+
- **Biblioteca gráfica:** Pygame
- **Arquitetura:** cenas com gerenciamento de estado, comunicação por eventos e
  sistemas desacoplados

## Solução de Problemas

- **O jogo não inicia:** confira se o Python e o Pygame estão instalados
  (`pip install -r requirements.txt`) e se sua placa de vídeo suporta a
  aceleração usada pelo Pygame.
- **Sem som:** verifique o volume nas configurações (ESC, Configurações) e os
  alto-falantes do sistema.
- **Performance baixa:** reduza a resolução nas configurações e feche outros
  aplicativos em segundo plano.

## Licença

Projeto distribuído sob licença aberta. Sinta-se livre para usar, modificar e
distribuir.

## Desenvolvedor

Erick de Oliveira Bessa Xavier — GitHub:
[@ErickdeOliveiraBessaXavier](https://github.com/ErickdeOliveiraBessaXavier)
