---
name: enemy-health-multiplier-propagation
description: "Entidades emergentes (criadas por outras entidades, não pelo spawner) precisam receber health_multiplier via construtor, como o aggressiveness_multiplier."
metadata: 
  node_type: memory
  type: project
  originSessionId: a533f15b-88b0-43cf-a670-4a2a739d3db7
---

O `EnemySpawner` aplica `enemy_health_multiplier` (da dificuldade: Hard 1.3,
Pesadelo 1.5) **externamente** após construir cada inimigo. Quem nasce **fora**
desse caminho — entidades **emergentes**, criadas por outra entidade e empurradas
via `ctx.new_enemies` — não recebia o multiplicador (§11 no-op silencioso).

No CITY isso afetava: `FusedDrone` (`channeling.spawn_boss`), filhotes do carrier
(`CityDrone._make_offspring`) e bebês homing (`FusedDrone._spawn_homing`).

**Convenção (jun/2026):** tratar `health_multiplier` igual ao
`aggressiveness_multiplier` — param de construtor (default 1.0), **aplicado à
vida-base no `__init__`** (`self.health = max(1, int(base * health_multiplier))`),
**guardado** (`self.health_multiplier`) e **propagado aos filhos**. Onde o
construtor escala, **remover a aplicação externa do spawner** para não dobrar
(feito em `_spawn_city_drone_cluster`). O `HP_BOOST` 3× da canalização fica por
cima da vida já escalada (intencional).

**How to apply:** novo inimigo que gera outros em runtime → thread
`health_multiplier` pelo construtor e repasse `self.health_multiplier` aos
filhotes. Validar nos dois extremos (1.0 sem mudança; 1.5 escala, sem dobra).
Mesmo padrão já existe para o spawner externo — não misturar (escolha um:
construtor OU externo, nunca os dois no mesmo tipo).
