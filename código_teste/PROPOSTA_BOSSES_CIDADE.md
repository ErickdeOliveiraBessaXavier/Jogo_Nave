# 🏙️ Proposta de Boss: Tema Cidade (Cyberpunk)

## Nome: **The Metropolis Overlord** (O Soberano da Metrópole)

Este boss foi desenhado para ser o ápice do desafio no bioma **CITY**, utilizando a mecânica de "destruição por camadas" e suporte de unidades orbitais.

---

## 🎨 Conceito Estético
*   **Aparência:** Uma fortaleza voadora massiva que lembra o topo de um arranha-céu tecnológico.
*   **Visual:** Chassi em cinza industrial fosco com "veias" de neon magenta e azul elétrico pulsando entre as placas de armadura.
*   **Danos Visuais:** À medida que as camadas são destruídas, o boss revela fiação exposta, pistões hidráulicos soltando fumaça e faíscas elétricas.

---

## 🎬 Sequência de Introdução (Cinemática)
1.  **O Surgimento:** O boss aparece inicialmente no "horizonte", atrás das camadas de background da cidade (parallax), subindo lentamente como se estivesse emergindo das profundezas dos arranha-céus.
2.  **A Aproximação:** Após atingir o topo do horizonte, ele faz uma transição para o plano de jogo, descendo da parte superior da tela até se estabilizar no centro superior.
3.  **Ativação:** Ao estagnar, o boss emite um pulso sonoro industrial e invoca as **4 Esferas de Energia**, que se posicionam e começam a percorrer as laterais da tela.

---

## ⚔️ Mecânicas de Combate

### Fase 1: As Sentinelas Orbitais (Esferas de Energia)
Nesta fase, o corpo principal do boss é **INVULNERÁVEL**. As esferas não ficam estáticas; elas percorrem as laterais da tela (cima, baixo, esquerda, direita) criando um perímetro defensivo em movimento.

*   **Movimentação:** As esferas patrulham as bordas da tela em um padrão retangular, forçando o jogador a persegui-las enquanto desvia dos ataques.
*   **Esfera Superior Esquerda:** Dispara rajadas rápidas de tiros neon (foco em agilidade).
*   **Esfera Superior Direita:** Lança micro-mísseis seguidores (foco em evasão).
*   **Esfera Inferior Esquerda:** Emite feixes de laser verticais que cruzam a tela (foco em posicionamento).
*   **Esfera Inferior Direita:** Pulsa ondas EMP que reduzem a velocidade dos projéteis do jogador (foco em timing).
*   **Objetivo:** O jogador deve destruir as 4 esferas para desativar o escudo de energia do Overlord.

### Fase 2: Descascando a Blindagem (O Boss de Camadas)
Com o escudo desativado, o jogador pode atacar o corpo principal, que possui 3 camadas distintas de armadura:

1.  **Camada Externa (Blindagem Industrial):** Placas de aço pesadas. Requer dano massivo. Partículas de metal e placas inteiras se desprendem visualmente ao serem destruídas.
2.  **Camada Intermediária (Circuitos de Carbono):** Revela o interior tecnológico. O boss começa a "vazar" energia, disparando tiros aleatórios de seus circuitos danificados.
3.  **Camada Interna (Chassi Exposto):** Estrutura frágil, mas o boss entra em modo de sobrecarga, movendo-se mais rápido e usando ataques de área mais agressivos.

### Fase 3: O Núcleo Instável (Desespero Final)
Toda a armadura foi removida, restando apenas o núcleo de energia central exposto.
*   **Ataque Especial:** "The City Beam" – Um laser massivo que ocupa 30% da tela e requer um tempo de carregamento visível.
*   **Suporte:** O núcleo invoca pequenos *City Drones* para distrair o jogador.
*   **Risco:** Se o jogador demorar muito, o núcleo pode tentar regenerar uma das esferas de energia.

---

## 🛠️ Detalhes Técnicos Sugeridos

*   **Pixel-Map em Camadas:** Utilizar o sistema de `Layered Pixel-Maps` já estabelecido para o tema CITY.
*   **Sons:** Sons industriais pesados, alarmes de "Critical Damage" e música synthwave acelerada.
*   **Feedback de Impacto:** O boss deve tremer violentamente quando uma camada de armadura é rompida, acompanhado de uma pequena explosão de partículas.

---

## 💡 Por que isso funciona?
1.  **Priorização de Alvos:** Força o jogador a lidar com as esferas antes de focar no boss.
2.  **Satisfação Visual:** Ver o boss "se despedaçar" camada por camada dá um senso claro de progresso na luta.
3.  **Variedade de Gameplay:** Cada fase exige um tipo diferente de atenção do jogador (esquiva de mísseis -> posicionamento de laser -> dano puro no núcleo).
