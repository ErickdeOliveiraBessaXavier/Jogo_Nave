# 🌆 Proposta de Novos Inimigos: Tema Cidade (Cyberpunk)

Este documento estabelece o blueprint técnico e estético para a nova linhagem de inimigos do bioma **CITY**. O objetivo é criar um desafio tático único, focado em controle de movimento e área, com uma estética industrial urbana coesa.

---

## 🛠️ Diretrizes de Design: "A Máquina Urbana"

### 1. Implementação Técnica: Pixel-Map em Camadas
Todos os inimigos serão construídos usando o sistema de **Layered Pixel-Maps**. 
*   **Camada de Base (Chassi):** Estrutura interna com fiação exposta e pistões.
*   **Camada de Blindagem (Armor):** Placas externas que podem ser destruídas individualmente para revelar a base.
*   **Camada de Glow (Neon):** Pixels emissivos que representam energia e indicadores de estado.
*   **Camada de Acessórios:** Antenas, canhões rotativos e bobinas que possuem animação independente.

### 2. Conectividade e Mundo Unificado
Os inimigos não são entidades isoladas, mas extensões da infraestrutura da cidade:
*   **Industrial Gritty:** Metais desgastados, manchas de óleo e rebarbas.
*   **Conexões Reais:** Cabos de fibra ótica conectando diferentes partes do corpo e acoplamentos hidráulicos visíveis.
*   **Paleta de Cores:** Base em *Gunmetal Gray* e *Deep Slate*, com destaques em *Electric Blue*, *Cyber Magenta* e *Toxic Orange*.

---

## 🛸 Catálogo de Unidades

### 1. City Drone (O Enxame)
*   **Visual:** Chassi ultra-leve em formato de disco com 4 micro-propulsores. Fiação central visível através de uma grade.
*   **Padrão de Movimento:** **"Spring-Zig-zag"**. Movimentam-se em saltos rápidos e erráticos, como se estivessem presos a molas invisíveis.
*   **Spawn/Organização:** **"Clustering"**. Nascem em nuvens desordenadas de 5 a 8 unidades, em vez de filas organizadas, preenchendo o espaço de forma orgânica.
*   **Morte:** **"Static Pop"**. Ao morrer, liberam uma pequena descarga elétrica (estática) que distorce visualmente a área ao redor por milissegundos.

### 2. Neon Sniper (O Olho de Longa Distância)
*   **Visual:** Drone alongado com um "rifle" integrado. Estabilizadores laterais que abrem como asas mecânicas.
*   **Padrão de Movimento:** **"Slide & Lock"**. Desloca-se horizontalmente de forma suave para se alinhar ao jogador e "ancora" no lugar para carregar o tiro.
*   **Spawn/Organização:** **"Perch Units"**. Sempre nascem nas extremidades superiores da tela (cantos), agindo como sentinelas.
*   **Morte:** **"Core Implosion"**. O núcleo magenta brilha intensamente e colapsa para dentro (implosão), puxando partículas próximas antes de desaparecer.

### 3. Police Interceptor (O Perseguidor)
*   **Visual:** Aerodinâmica de viatura pesada. Turbinas traseiras massivas com brilho alaranjado.
*   **Padrão de Movimento:** **"Patrol & Strike"**. Flutua preguiçosamente em patrulha. Quando o jogador entra no radar, ele "estanca" por 0.3s e dispara um dash violento.
*   **Spawn/Organização:** **"Squad Pairs"**. Sempre aparecem em duplas sincronizadas que cruzam a tela uma em direção à outra.
*   **Morte:** **"Crash & Burn"**. Não explode imediatamente; perde o controle, começa a girar e cai em diagonal soltando fumaça negra antes de explodir na parte inferior.

### 4. Cyber Tank (O Colosso Urbano)
*   **Visual:** Fortaleza móvel. Duas torres de canhão rotativas e placas de blindagem frontal sobrepostas.
*   **Padrão de Movimento:** **"Juggernaut"**. Descida constante, lenta e imparável. Ignora colisões leves e recuos.
*   **Spawn/Organização:** **"Gatekeeper"**. Aparece sozinho, geralmente precedido por um aviso sonoro de "Heavy Unit Incoming".
*   **Morte:** **"Structural Failure"**. As placas de metal voam em todas as direções (estilhaços que podem causar dano) e o chassi derrete em uma poça de metal fundido neon.

### 5. Cyber-Captor (A Armadilha de Energia)
*   **Visual:** Esfera mecânica central cercada por anéis orbitais que giram.
*   **Padrão de Movimento:** **"Orbiting"**. Não desce; fica orbitando um ponto fixo no topo da tela, tentando manter o raio conectado o maior tempo possível.
*   **Spawn/Organização:** **"Shadow Support"**. Nasce escondido atrás de inimigos maiores ou meteoros, sendo difícil de spotar inicialmente.
*   **Morte:** **"EMP Discharge"**. Ao ser destruído, libera uma onda amarela que desativa temporariamente (0.5s) qualquer projétil inimigo ou aliado muito próximo.

### 6. Tesla Twins (A Barreira Vertical)
*   **Visual:** Unidades verticais com grandes bobinas de cobre no topo.
*   **Padrão de Movimento:** **"Mirroring"**. Se um se move para a esquerda, o outro espelha o movimento para manter a tensão do raio entre eles.
*   **Spawn/Organização:** **"Boundary Link"**. Nascem em lados opostos da tela (um na extrema esquerda, outro na direita) criando uma "linha de chegada" que o jogador precisa romper.
*   **Morte:** **"Short Circuit"**. Se um for destruído, o sobrevivente entra em sobrecarga, fica vermelho e dispara tiros aleatórios por 2 segundos antes de autodestruir-se.
*   **✅ Implementado (jun/2026).** Resolução da ambiguidade no side-scroll do CITY: os gêmeos ancoram no **topo e na base** (não esquerda/direita) e o feixe é **vertical**, formando uma parede que avança para a esquerda — coerente com o título "Barreira Vertical". O feixe é sempre ON (sem brecha): o counterplay é **abater um gêmeo**. Coordenação no `TeslaLink` (§1); dano do feixe via `area_blast`.

---

## 🏗️ Fluxo de Implementação Sugerido
1.  **Definição das Sprites de Pixel-Map:** Criar os mapas de bits para cada camada em arquivos `.py` (ex: `city_drone_pixel_map.py`).
2.  **Core Logic:** Desenvolver as classes em `game/entities/` herdando de `EnemyHitMixin` e utilizando os novos tipos de movimento.
3.  **Ajuste de Pesos:** Configurar a aparição no `game/core/levels/pipeline.py` para garantir que o tema **CITY** pareça um exército coordenado.
