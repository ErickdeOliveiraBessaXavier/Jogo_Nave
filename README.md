# 🚀 Space Shooter Game (Jogo de Nave)

Um emocionante jogo de tiro espacial desenvolvido com Python e Pygame! Controle sua nave, destrua inimigos e enfrente chefes épicos em múltiplos níveis.

## ✨ Funcionalidades

### 🎮 **Gameplay**
- **Controle fluido** da nave com movimentação e tiro contínuo
- **Múltiplos níveis** com dificuldade progressiva  
- **Sistema de inimigos** diversificado (meteoros, aliens, meteoros teleguiados)
- **Batalhas épicas** contra chefes com múltiplos ataques
- **Sistema de pontuação** baseado em performance

### 🎁 **Power-ups com Sistema de Raridade**
- **Shield** (40%) - Proteção temporária
- **Double Shot** (30%) - Tiro duplo
- **Speed Boost** (15%) - Velocidade aumentada  
- **Extra Life** (10%) - Vida adicional
- **Score Multiplier** (4%) - Multiplicador de pontos
- **Rainbow** (1%) - Todos os power-ups!

### 🎯 **Recursos Avançados**
- **Meteoros teleguiados** que perseguem o jogador
- **Sistema de spawn** individualizado por tipo de inimigo
- **Efeitos visuais** e screen shake
- **Configurações centralizadas** para fácil balanceamento

## 🎮 Como Jogar

### 📋 **Pré-requisitos**
```bash
Python 3.8+
Pygame 2.0+
```

### 🚀 **Instalação e Execução**
```bash
# 1. Clone o repositório
git clone https://github.com/ErickdeOliveiraBessaXavier/Jogo_Nave.git

# 2. Navegue até o diretório
cd Jogo_Nave

# 3. Instale dependências
pip install -r requirements.txt

# 4. Execute o jogo
python run.py
```

### 🎮 **Controles**
- **WASD** ou **Setas** - Movimento da nave
- **Espaço** - Atirar (segure para tiro contínuo)
- **P** - Pausar/Despausar
- **R** - Reiniciar (na tela de game over)

## 🏗️ **Arquitetura do Projeto**

```
game/
├── core/           # Sistemas principais
├── entities/       # Entidades do jogo (nave, inimigos, projéteis)
├── render/         # Sistema de renderização
├── scenes/         # Cenas do jogo (menu, jogo, game over)
└── systems/        # Sistemas de gameplay (spawn, colisões)
```

## 🔧 **Tecnologias Utilizadas**

- **Python 3.12** - Linguagem principal
- **Pygame** - Engine de jogos 2D
- **Dataclasses** - Configurações estruturadas
- **Type Hints** - Código tipado e documentado

## 📈 **Versões**

### v2.0 - Sistema de Raridade de Power-ups
- ✅ Implementado sistema de raridade individualizada
- ✅ Power-ups com probabilidades específicas
- ✅ Balanceamento aprimorado

### v1.5 - Meteoros Teleguiados  
- ✅ Meteoros que perseguem o jogador
- ✅ Sistema de spawn multi-timer
- ✅ Configurações centralizadas

### v1.0 - Versão Base
- ✅ Gameplay completo
- ✅ Sistema de chefes
- ✅ Power-ups básicos

## 🤝 **Contribuindo**

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -am 'feat: Nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

## 📄 **Licença**

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para detalhes.

## 🎯 **Roadmap**

- [ ] Sistema de conquistas
- [ ] Múltiplos tipos de nave
- [ ] Editor de níveis
- [ ] Música e efeitos sonoros
- [ ] Multiplayer local

---

**Desenvolvido com ❤️ por [ErickdeOliveiraBessaXavier](https://github.com/ErickdeOliveiraBessaXavier)**

## Controles

*   **Setas ou WASD:** Mover a nave.
*   **Barra de espaço ou Enter:** Atirar.
*   **P:** Pausar o jogo.
*   **R:** Reiniciar o jogo após o game over.

## Tecnologias Utilizadas

*   Python
*   Pygame
