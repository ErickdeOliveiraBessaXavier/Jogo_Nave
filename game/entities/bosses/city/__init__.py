"""Chefes do tema CITY e seus módulos satélite.

Aqui moram o **Metropolis Overlord** (nível 30, a fortaleza voadora) e a
**Tríade** (nível 34), com tudo que existe só para eles: pixel maps, projéteis
próprios, feixes, segmentos e as peças de coreografia.

Por que uma subpasta e não `bosses/` flat: os dois chefes trazem 15 módulos de
apoio juntos, e soltos na raiz eles afogariam os nove bosses antigos. A regra da
casa continua a mesma (`memory/entities-folder-structure.md`): **boss e seus
pixel maps vão para `bosses/`** — a subpasta é só o agrupamento por tema.

O que NÃO está aqui, de propósito: `city_mine`, `city_glow` e `city_palette`
ficaram em `enemies/city/` porque o tema também os usa fora da luta de chefe (a
mina entra pelo `levels/pipeline.py`). Satélite exclusivo de boss mora aqui;
peça compartilhada com o tema mora com o tema.
"""
