---
name: visual-quality-system
description: Sistema de Qualidade Visual (Alto/Médio/Baixo) — singleton central que escala efeitos cosméticos por performance; como estender a novos call sites
metadata: 
  node_type: memory
  type: project
  originSessionId: b9628b84-e528-473b-9fa6-47100ee0a764
---

Settings → "Qualidade Visual" (Alto/Médio/Baixo) reduz efeitos cosméticos sem
mexer em gameplay. Política **única** em `game/core/visual_quality.py`:
singleton `visual_quality` (mesmo padrão de `sound_manager`), com perfis frozen
por nível e API de escala.

**Como aplicar num efeito (one-liner por call site):**
```python
from ..core.visual_quality import visual_quality as vq
count = vq.particles(40)        # piso 1: efeito nunca some, só simplifica
if vq.glow_enabled: ...         # gate de efeito caro
if random.random() < vq.frequency(0.5): ...   # frequência de trail/spawn
```
Helpers de contagem: `particles/fragments/dust/impact/smoke/electric/ambient(n)`.
Gates: `glow_enabled, afterimages_enabled, dynamic_lights, complex_explosions,
ambient_effects, secondary_shake`. Contínuos: `trail_scale, glow_scale,
ambient_scale, frequency(p)`. `_count` garante piso de 1 (nunca zera — "versão
simplificada, não desaparece").

**Persistência/boot:** `UserPreferences.visual_quality` ("high"/"medium"/"low");
`app.py` chama `visual_quality.set_from_name(...)` no boot, ANTES de qualquer
sistema de efeito. Settings aplica ao vivo (`SettingsView._select_quality`) sem
reinício (efeitos leem o singleton por frame). Seletor fica na faixa inferior do
settings (própria seção, não disputa os 2 cards). Importar `visual_quality` em
`game/core/*`/`render/*`/`entities/*` não cria ciclo (core não depende de game).

**Já consumido por:** `Explosion._create_particles` (cobre TODAS as explosões),
`ElectricFieldZone` (raios/estática), `OrbitalTurret` (arcos/estática das
esferas), `OrbitalEnergyOrb` (espaçamento do trail), `DamageVignette` (rachaduras).
Categorias do pedido ainda NÃO ligadas a call sites (knobs existem, é só aplicar):
poeira/fumaça/ambientais/fragmentos de outros inimigos, afterimages diversos,
luzes dinâmicas, shake secundário. Estender = adicionar o one-liner no ponto.

**Pixelização (pós-processamento):** efeito estético opt-in, **ortogonal** ao
nível de qualidade (não escala partículas). Aplicado no ÚNICO choke point de
render — `app.py run()`, após `current_scene.render(self.screen)` e antes do
`display.flip()` — via `PixelizePost.apply()` em `game/render/post_process.py`
(downscale→upscale nearest, buffer reaproveitado entre frames; opera in-place no
frame inteiro, então independe de sprite vs `Rect` vs `draw.*`). Estado no mesmo
singleton: `visual_quality.pixelization` (`light`/`medium`/`strong` → fatores
FRACIONÁRIOS 1.3/1.6/2.0), `pixelization_enabled`, `pixelization_factor` (float);
rótulos em `PIXELIZATION_LEVELS`. **Sempre ativa — NÃO há `off`**; piso nativo =
`light`. `PixelizePost.apply` aceita float (downscale p/ `round(w/factor)` →
upscale nearest = blocos ~`factor`px, permitindo pixelização fina < bloco 2×2).
Downscale usa `smoothscale` (média de área), NÃO `scale`/nearest: nearest
point-sampleia e DESCARTA linhas/colunas → bordas de 1px apareciam "comidas".
Upscale segue nearest (mantém bordas duras dos blocos). Só troque se aceitar
regressão do artefato de borda comida.
Configs antigas com `off` caem no piso `light` na validação do load. Persistido
em `UserPreferences.pixelization` (default `light`), aplicado no boot com
`set_pixelization(...)`. Seletor próprio no Settings (3 botões Leve/Médio/Forte)
(`_select_pixelization` / `_draw_pixelization_selector`), linha logo ACIMA do
seletor de qualidade (cards sobem via offset negativo em `card_y` p/ abrir a
faixa). Pixeliza o HUD junto (abordagem simples de post-process).

**Diagnóstico (toggle F / `show_fps`):** overlay em `GameRenderer._draw_diagnostics`
mostra FPS, frame time (avg/max ms), partículas e entidades ativas, e o nível de
qualidade atual. Contadores em `EntityManager.debug_particle_count()` /
`debug_entity_count()`. Ver [[orbital-turret-zoneamento]].
