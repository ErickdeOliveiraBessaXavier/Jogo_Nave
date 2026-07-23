---
name: retro-background-scale-city-only
description: "Escala de conteúdo no Fundo Retrô foi corrigida SÓ no City; volcanic/mountains têm o mesmo \"bug\" mas a estética ampliada é desejada — não corrigir."
metadata: 
  node_type: memory
  type: project
  originSessionId: 4e67defa-aac5-46be-a5fc-83bd27c6a7e8
---

Com o Fundo Retrô ligado, o background do tema é construído em meia-res
(`SCREEN_*/2`) e sofre upscale de 2× no blit. Dimensões e velocidades escritas
em pixels de 720p dobram de tamanho e de velocidade aparente na tela.

Isso foi corrigido apenas no **City Neon** (em 2026-07-15), a pedido: prédios
altos/largos demais e parallax rápido demais. A base `Background` ganhou
`res_scale` + helpers `s()` (dimensões, mín. 1px) / `sf()` (velocidades), e
`city.py` passa tudo por eles.

**Volcanic e Mountains têm exatamente o mesmo comportamento e NÃO devem ser
"corrigidos": o usuário gosta da estética ampliada neles.**

**Why:** o desvio de escala nos outros temas é um efeito colateral técnico que
virou decisão de arte — não é derivável do código, e um conserto por simetria
seria regressão estética.

**How to apply:** ao mexer em `volcanic.py`/`mountains.py`, não aplicar
`s()`/`sf()` nas dimensões/velocidades por iniciativa própria; se a escala
parecer "errada" em meia-res, é intencional. Perguntar antes. Ver
[[visual-quality-system]] e [[city-neon-design-intent]].
