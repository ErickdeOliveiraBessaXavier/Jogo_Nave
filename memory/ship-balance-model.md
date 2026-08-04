---
name: ship-balance-model
description: Modelo usado para balancear naves (abates/s por tier de HP, não DPS bruto) e as conclusões da revisão de 2026-07-23
metadata:
  type: project
---

Balanceamento de nave NÃO se avalia por DPS bruto. A métrica é **abates/s sustentado = tiros_s / ceil(HP / dano_por_tiro)**, medida em três tiers (swarm ≤18 HP, médio 45–130, alto 240+) e ponderada por um mix de encontro (~.4/.45/.15). DPS bruto engana porque ignora overkill: contra um drone de 6 HP o tiro de 18 desperdiça 67%.

Conclusões da revisão de 2026-07-23 (mantidas como premissa de futuras mudanças):

- HP de inimigo **não escala com o nível** — só com o preset de dificuldade (`enemy_health_multiplier`) e coop. O que escala por nível é variedade/quantidade.
- A causa da "nave rápida é sempre melhor" não era o dano: contra HP médio/alto o Aríete já era 20–34% melhor que a Padrão. Era (a) o swarm dominar o mix e (b) as stats de mobilidade se somarem na MESMA direção do trade de tiro (Estilete tinha a melhor mobilidade *e* o melhor output prático; Aríete, o oposto).
- **Não buffar dano de nave lenta** para resolver percepção — quebra o médio/alto HP. As alavancas certas são `bullet_speed_mult`, `pierce_count` e mobilidade.
- O charge do Caçador/Magneto dispara **5 teleguiados** com o dano já multiplicado (~150 de burst), não um tiro só. Por isso a cadência base baixa dele é justa — não tratar 0.75× de tiro comum como nave fraca.
- Alvo do balanceamento: nenhuma nave acima de ~1.4 nem abaixo de ~0.75 no índice composto vs Padrão, com Padrão/Magneto/Cofre em 1.00 por definição.

Revisão de 2026-08-03 (Estilete 1.87/0.40 → 1.60/0.50):

- **O dano por tiro é INTEIRO** (`_round_damage` sobre `BULLET_BASE_DAMAGE = 10`), então `damage_mult` só se move em degraus de 0.10 e valores intermediários são indistinguíveis (0.45 e 0.50 dão os mesmos 5). Consequência prática: **cadência e poder ficam grudados** num patamar de dano baixo. No Estilete, 0.40→0.50 vale exatamente +25% e paga um corte de ~22% na cadência com índice intacto; mas depois disso cada +0.05 de `fire_rate_mult` vale ~1,25 DPS e não existe compensação possível — não dá para mexer na cadência de graça. Planejar o par junto, nunca um de cada vez.
- **Até 2026-08-03 o modelo NÃO descrevia a experiência real.** Um gate de auto-fire com relógio próprio (removido; ver `CLAUDE.md` §14, "um relógio por cadência") cobrava uma fatia **diferente** de cada nave: Padrão −14%, Aríete/Caçador −24%, Estilete −29%. O índice composto sempre foi calculado sobre a cadência teórica, então o balanceamento relativo que o jogador sentia nunca foi o medido aqui. Depois da remoção os dois coincidem — qualquer percepção de desequilíbrio anterior a esta data foi formada sobre outro conjunto de números e não deve ser usada como referência.

Relacionado: [[fire-timer-cadence-architecture]].

Relacionado: [[variety-per-run-salt-and-pending-debut]] (composição de encontro), [[enemy-health-multiplier-propagation]].
