# Plano — Performance no Mundo 1 (Cordilheiras)

Itens de otimização focados no Mundo 1 — MOUNTAINS (níveis 1-10) e no
roster de inimigos exclusivo do tema. Cada item lista **sintoma observado**,
**causa**, **direção concreta** e **risco**. Itens classificados por
**probabilidade de impacto real no frame time** — alta primeiro.

---

## Premissas

- Análise feita por inspeção do código, sem profiling de runtime.
- Os itens "Alta probabilidade" têm gargalo plausível e fix mecânico de baixo
  risco. **Itens "Média probabilidade" exigem profiling antes de mexer** —
  ganho potencial existe mas não justifica churn sem medição.
- Mundo 1 já tem cobertura razoável de pools, caches e generators (ver
  histórico do CLAUDE.md §7). Estes são os pontos remanescentes.

---

## Critérios de gravidade

- **Alto impacto** — alocação contínua em entidade frequente, fillrate alto,
  ou padrão O(n²) onde swap-and-pop O(n) está disponível.
- **Médio impacto** — alocação ou fillrate em entidade limitada por cap,
  ou ganho condicional ao estado de jogo.
- **A medir** — possível gargalo, mas churn alto e ganho incerto sem profiling.

---

## Backlog

### Alto impacto

#### 1. `StoneSentry._update_particles` aloca lista nova por frame

**Sintoma observado:**

```python
def _update_particles(self, dt: float) -> None:
    updated_particles: list[Particle] = []
    for particle in self._particles:
        particle.x += particle.vx * dt
        particle.y += particle.vy * dt
        particle.lifetime -= dt
        if particle.lifetime > 0 and particle.y < Config.SCREEN_HEIGHT + 20:
            updated_particles.append(particle)
    self._particles = updated_particles
```

Filter-into-new-list por frame. Viola o §6 do CLAUDE.md (swap-and-pop sem
alocação). O `StoneGolemBoss._update_particles` no mesmo projeto resolve
exatamente esse trabalho com write-pointer e `del lst[write:]`.

**Causa:** Método não migrado quando o padrão swap-and-pop foi padronizado.

**Direção:** Copiar o padrão existente do golem:

```python
def _update_particles(self, dt: float) -> None:
    particles = self._particles
    write = 0
    for p in particles:
        p.x += p.vx * dt
        p.y += p.vy * dt
        p.lifetime -= dt
        if p.lifetime > 0 and p.y < Config.SCREEN_HEIGHT + 20:
            particles[write] = p
            write += 1
    del particles[write:]
```

**Arquivos afetados:** `entities/stone_sentry.py`. Mudança mecânica, ~8 linhas.

**Risco:** Baixo. Sem mudança de comportamento.

**Status:** **Aplicado** (2026-05-28). Migrado para swap-and-pop com write-pointer
e bind local de `Config.SCREEN_HEIGHT + 20`.

---

#### 2. `RockGlider.draw` faz 6 `pygame.draw.rect` por glider por frame nos thruster trails

> **Revisão 2026-05-28:** O plano original afirmava 5 phase offsets / 10 draw.rect
> por glider. O código atual tem `RING_PHASE_OFFSETS = (0.0, 1/3, 2/3)` — **3
> offsets**, totalizando 6 draw.rect/glider. A "Opção B" deste item (reduzir
> 5→3) já foi aplicada anteriormente. A urgência descrita abaixo está
> superestimada; o cache de strip pode ainda valer, mas o payoff é ~metade
> do que o plano original sugeria. Reabrir só com profiling.

**Sintoma observado:**

```python
for cx_ring, side_phase in ((..., 0.0), (..., 0.5)):  # 2 nozzles
    for phase_offset in self.RING_PHASE_OFFSETS:       # 3 offsets (já reduzido)
        # ... cálculo de ring_w, ring_h, ring_y, cor ...
        pygame.draw.rect(screen, ring_color, (...), 1)
```

2 nozzles × 3 phase offsets = **6 `draw.rect` por glider por frame**.
`RockGlider` é o inimigo base do Mundo 1 — sempre presente, em quantidade.
Com cap dinâmico permitindo 12+ gliders simultâneos: **~72 chamadas
`draw.rect` por frame só para trails de thruster**.

**Causa:** Trail desenhado diretamente na surface principal sem cache.
`base_phase` muda continuamente (depende de `self._time`), então cache
por valor exato não funciona, mas por **bucket discretizado** funciona.

**Direção — duas opções:**

**Opção A (mais conservadora):** Pré-renderizar a tira de 5 anéis numa
surface SRCALPHA cacheada por `(base_phase_bucket, side_phase_bucket)`.
Buckets de ~16 unidades em `base_phase` × 2 em `side_phase` = 32 entradas
cap. **1 blit por nozzle em vez de 5 `draw.rect`** = 4 blits por glider.

```python
@classmethod
def _get_thruster_strip(cls, base_phase: float, side_phase: float) -> pygame.Surface:
    bp = int(base_phase * 16) % 16
    key = (bp, side_phase)
    cached = cls._thruster_strip_cache.get(key)
    if cached is not None:
        return cached
    # construir surface com os 5 rects desenhados
    ...
```

**Opção B (mais agressiva):** Reduzir `RING_PHASE_OFFSETS` de 5 para 3.
Visualmente o efeito de trail continua coerente; testes A/B fáceis.

**Recomendação:** Opção A. Mantém o visual idêntico, ganho mecânico.
> **Revisão 2026-05-28:** A Opção B já foi aplicada (3 offsets). Opção A continua
> válida tecnicamente, mas o payoff caiu pela metade. Reabrir só com profiling.

**Arquivos afetados:** `entities/rock_glider.py`. Adicionar cache de classe
+ método auxiliar. ~25 linhas.

**Risco:** Baixo-médio. Discretização do `base_phase` pode introduzir
"steps" perceptíveis se o bucket for grosso demais; 16 buckets devem ser
suficientes (1/16 de ciclo a ~2.3 Hz = ~28 ms por step, mais rápido que
o frame budget de 16 ms).

**Status:** Pendente — payoff reduzido após revisão; bloquear em profiling.

---

#### 3. `MountainStalagmite._draw_body` aloca `pygame.Surface(SRCALPHA)` por frame

> **Revisão 2026-05-28 — INVÁLIDO. Não aplicar.**
>
> - `MountainStalagmite._draw_body` **não existe**. O draw real (`MountainStalagmite.draw()`,
>   linha 293) chama `_draw_flat_spike()`, que faz `pygame.draw.polygon(surface, ...)`
>   **direto na surface principal**, sem SRCALPHA intermediária.
> - O método `_draw_body` na linha 1681 do mesmo arquivo é de **`MountainMage`** (o
>   mago flutuante), não da estalagmite. Confusão de nome.
> - O trecho de código SRCALPHA citado abaixo é de `_draw_shadow_stalactite` (linha 681),
>   que está **definido mas nunca chamado** em parte alguma do projeto. Dead code.
> - Nem hit_flash nem APPEARING usam surface intermediária na estalagmite real —
>   `_resolve_colors()` troca tuplas RGB e `_draw_flat_spike` desenha direto.
>
> **Ação real:** remover `_draw_shadow_stalactite` do arquivo se confirmado dead
> code (polimento, não performance). Nenhuma otimização de SRCALPHA aplicável.

**Sintoma observado:**

```python
surf_w = W * 2 + 60          # W ~140, surf_w ~340
surf_h = height + 40          # height ~280, surf_h ~320
s = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
# ... 3 draw.polygon ...
surface.blit(s, (ox, oy))
```

Surface intermediária SRCALPHA de ~340×320 = **~109k pixels alocados por
frame por estalagmite**, com 3 `draw.polygon` em cima e blit final.

`MountainMage` é cap-limitado em poucos por tela (`SPAWNER_CAP_MOUNTAIN_MAGE`),
mas cada um invoca 1-3 estalagmites + estalactites visíveis ao mesmo tempo.
`CloudArchmageBoss` na phase 2 invoca em pulsos (intervalo
`_PHASE2_STALAGMITE_INTERVAL = 1.4 s` × ~6 estalagmites/pulso).

**Causa:** Surface intermediária necessária porque os polígonos têm alpha
controlado por parâmetro (durante APPEARING fade-in e durante hit_flash).
Sem alpha local, os polígonos sangrariam pela surface principal.

**Direção:** Duas otimizações combinadas:

**a) Caminho rápido para `alpha == 255`:** No caso comum (estalagmite
ativa, fora de APPEARING e hit_flash), desenhar polígonos direto na
surface principal. Elimina a surface intermediária em ~95% dos frames de
vida da entidade.

```python
def _draw_body(self, surface, alpha=255, scale=1.0):
    # ... cálculos de pontos ...
    if alpha >= 255:
        # Caminho rápido: direto na surface principal
        pygame.draw.polygon(surface, color_base, body_pts)
        pygame.draw.polygon(surface, color_mid, mid_pts)
        pygame.draw.polygon(surface, (32, 16, 10), body_pts, width=2)
    else:
        # Caminho com alpha (APPEARING, hit_flash): surface intermediária
        # ... código atual ...
```

**b) (Opcional, se a) não bastar):** Para o caminho com alpha, cachear a
surface por `(W_bucket, height_bucket, shape_phase_bucket, color_set, alpha_bucket)`.
`shape_phase` é o único que muda continuamente — bucketizar em ~16 entradas.
Cache total ~64 entradas.

**Recomendação:** Implementar apenas (a) primeiro, medir, e só implementar
(b) se ainda houver gargalo no boss phase 2 com 6 estalagmites simultâneos.

**Arquivos afetados:** `entities/mountain_mage.py` (classe
`MountainStalagmite` e por simetria `MountainStalactite`).

**Risco:** Médio. O caminho rápido sem surface intermediária assume que
os polígonos não se sobrepõem de forma que o alpha "soma" — verificar
visualmente que o resultado é idêntico (deve ser, pois alpha=255 ignora
blending).

**Status:** **Inválido** (2026-05-28) — premissa errada; ver revisão acima.

---

### Médio impacto

#### 4. `SerpentRockBullet.draw` usa `set_alpha` em surface cacheada compartilhada

> **Revisão 2026-05-28:** O título e a math originais ("SerpentBlock × 14 blocos
> × 3 afterimages") estavam errados. `SerpentBlock._draw_sprite` faz **1
> blit por bloco** sem afterimages. O trecho citado é de `SerpentRockBullet.draw`
> (linha 833 em `mountain_serpent_boss.py`) — projétil do boss, não bloco.
> Quantidade real: depende do número de bullets ativos × afterimages cada.
> Cap baixo durante boss fight; impacto provavelmente pequeno. Reabrir só
> com profiling do boss da Serpente.

**Sintoma observado (em `SerpentRockBullet`):**

```python
for img in self._afterimages:
    alpha = int((img["life"] / self._TRAIL_LIFETIME) * 128)
    rotated = self._get_rotated_surface(self._sprite, img["angle"])

    old_alpha = rotated.get_alpha()
    rotated.set_alpha(alpha)
    dest = rotated.get_rect(center=(int(img["x"]), int(img["y"])))
    surface.blit(rotated, dest.topleft)
    rotated.set_alpha(old_alpha)
```

Cada `set_alpha` em surface compartilhada dispara reformat interno do SDL.
Mesmo padrão aparece em `MountainSerpentBoss._draw_head_afterimages` (linha
~1947) para a cabeça do boss.

**Causa:** O cache `_get_rotated_surface` retorna a mesma surface para
ângulos iguais, e múltiplos blocos têm ângulos próximos (todos rodam no
mesmo padrão). O `set_alpha` muta atributo compartilhado.

**Direção:** Cache por `(angle_bucket, alpha_bucket)` retornando surface
já com alpha aplicado:

```python
@classmethod
def _get_rotated_alpha_surface(
    cls, sprite, angle, alpha
) -> pygame.Surface:
    angle_bucket = int(angle / 8) * 8 % 360  # 8° buckets
    alpha_bucket = (alpha // 16) * 16         # 16-level alpha
    key = (id(sprite), angle_bucket, alpha_bucket)
    cached = cls._rotated_alpha_cache.get(key)
    if cached is not None:
        return cached
    rotated = pygame.transform.rotate(sprite, angle_bucket)
    rotated = rotated.copy()
    rotated.set_alpha(alpha_bucket)
    cls._rotated_alpha_cache[key] = cached
    # cap em ~360 entradas (45 ângulos × 8 alphas)
    return rotated
```

`blit` simples, sem set/restore por frame.

**Arquivos afetados:** `entities/mountain_serpent_boss.py` (classes
`SerpentRockBullet` e opcionalmente o `_draw_head_afterimages` do boss).

**Risco:** Baixo. Mudança contida na classe; trail visualmente idêntico
com bucketing de 8°/16 níveis.

**Status:** Pendente — escopo corrigido; bloquear em profiling do boss.

---

#### 5. `MountainStalactite` — mesma classe de alocação que estalagmite

> **Revisão 2026-05-28 — INVÁLIDO. Não aplicar.**
>
> Espelha o problema do item 3: `MountainStalactite.draw()` (linha 970)
> chama `_draw_flat_spike_flipped()`, que faz `pygame.draw.polygon(surface, ...)`
> direto na surface principal. Sem SRCALPHA por frame. Nada para otimizar.

**Sintoma:** Espelho invertido da `MountainStalagmite`. Mesmo padrão de
surface intermediária SRCALPHA por frame.

**Direção:** Mesma do item 3. As duas classes compartilham helpers em
`_build_flat_spike_pts` — vale considerar extração de um método
`_draw_spike_polygons` em util compartilhado para evitar divergência.

**Status:** **Inválido** (2026-05-28) — premissa errada; ver revisão acima.

---

### A medir antes de mexer

#### 6. `MountainsBackground` — fillrate do parallax de 6 camadas

> **Atualização 2026-05-28 — Aplicado.**
>
> Teste empírico (skip do blit das 6 layers) confirmou: FPS subiu de 55-70
> para ~85-95+. Diferença observada vs Starfield: ~6 ms, consistente com
> ~4.2M pixels SRCALPHA/frame das layers.
>
> **Fix aplicado:** trim + split de cada layer em duas faixas. Apenas a
> região jagged entre `highest_y` (pico mais alto) e `lowest_peak_y` (pico
> mais baixo) precisa de SRCALPHA. Acima do pico mais alto é 100%
> transparente (não é blittado); abaixo do pico mais baixo é 100% opaco
> (blit opaco ~2x mais rápido). `LayerData` carrega `top_surface`,
> `bot_surface` e os offsets `top_y_offset`/`bot_y_offset` (relativos à
> layer) para posicionamento correto. Margens de 1-2px evitam artefato de
> borda. Confirmado empiricamente: FPS subiu significativamente vs versão
> sem otimização.

**Observação:**

- 6 camadas, cada uma de largura ≥ screen_width
- Cada layer ocupa `height * h_pct` da altura (alturas: 65%, 55%, 45%, 32%, 20%, 12%)
- Cada layer faz **2 blits** quando `offset != 0` (parallax infinito)
- **Total bruto a 1280×720:** ~4.2M pixels de mountain layers + ~920k do céu
  + nuvens + estrelas = ~5.5M pixels blitados/frame só de background.

A 1080p, dobra. A 4K, quadruplica.

**Por que é "a medir":** As surfaces estão usando `convert()` (não `convert_alpha()`),
o que é correto e rápido para blits opacos. `LayerData.width` está cacheada.
O céu composto está cacheado com discretização de alpha. Em outras palavras:
**o background já está otimizado para o que faz**. A questão é se o que faz
ainda é um gargalo.

**Direção condicional:** Antes de mexer, ativar `--show-fps` no Mundo 1
(MOUNTAINS) vs Mundo 2 (STARFIELD, sem parallax pesado) na mesma cena de
combate. Comparar frame time médio.

- Se diferença for **< 1 ms**: fechar este item. O background não é o
  gargalo.
- Se diferença for **1-3 ms**: avaliar redução de altura das camadas
  distantes (layer 0 é 65% da altura mas tem parallax 0.1 — quase parada
  e atrás de todo o resto). Recortar a parte visível superior.
- Se diferença for **> 3 ms**: investigar se a opção `convert()` foi
  aplicada com sucesso (fallback silencioso pode estar mascarando falha).

**Risco se executado sem medição:** Alto. Background é uma área barulhenta
em pixel count mas com otimizações específicas; mudanças cegas podem
introduzir regressão visual sem ganho perceptível.

**Status:** Bloqueado em profiling

---

## Itens já bem otimizados (não tocar)

- **`MountainsBackground._sky_composited` cache de transição dia/noite** —
  comentário do código documenta: "1 unidade de alpha leva ~14 frames a
  60 FPS — recompõe raramente". Bom estado.
- **`MountainGeode._indicator_surface` pré-alocada** — documentação inline
  confirma: "evita alloc por frame".
- **`StoneSentry._eye_sprite_cache`, `_particle_surface_cache`, `_body_surface_cache`,
  `_render_cache`** — quatro caches por classe com chave bucketizada,
  estrutura sólida.
- **`MountainSerpentBoss._head_frames`** — pré-construído uma vez via
  `_build_head_sprite`, cacheado por instância.
- **`MountainsBackground._star_surf_cache`** — pré-renderizado por
  `(size, alpha_level)` com 16 níveis.
- **`StoneGolemBoss._update_particles`** — já usa swap-and-pop com write-pointer
  (é a referência para o item 1).

---

## Ordem de execução recomendada

```
1. StoneSentry._update_particles — swap-and-pop (item 1)  [Alto, fix mecânico]
2. MountainStalagmite/Stalactite — caminho rápido alpha=255 (itens 3, 5)  [Alto]
3. RockGlider thruster strip cache (item 2)               [Alto, maior payoff]
4. SerpentBlock rotated-alpha cache (item 4)              [Médio, só durante boss]
5. Profile do MountainsBackground (item 6)                [Bloqueado em medição]
```

Itens 1, 2 e 3 podem ser feitos em paralelo — sem dependência entre eles.
Item 4 só rende durante o boss da Cordilheira (níveis 3, 23, etc), então
não afeta gameplay regular do Mundo 1.

---

## Decisões deliberadamente adiadas

- **Reduzir altura das camadas distantes do parallax (item 6)** — viola a
  premissa do CLAUDE.md de não otimizar sem medição. Reabrir quando
  profiling indicar `MountainsBackground` como gargalo concreto (> 3 ms
  de diferença vs STARFIELD).

- **Cache global de polígonos de estalagmite** — discutido como opção (b)
  do item 3. Adiar até verificar se o caminho rápido (a) já resolve.

- **Reduzir `RING_PHASE_OFFSETS` de 5 para 3 no `RockGlider`** — opção B
  do item 2. Discutida e descartada em favor da Opção A (cache de strip),
  que preserva visual.

- **Migrar `MountainsBackground` para `pygame.SCALED` + render menor** —
  decisão arquitetural que afeta todos os mundos, não apenas o 1. Fora
  do escopo deste plano.

---

## Status resumido

| # | Item | Impacto | Status |
|---|------|---------|--------|
| 1 | `StoneSentry._update_particles` — swap-and-pop | Alto | **Aplicado (2026-05-28)** |
| 2 | `RockGlider` thruster strip cache | Médio (revisado) | Pendente — bloquear em profiling |
| 3 | `MountainStalagmite._draw_body` — caminho rápido alpha=255 | — | **Inválido** (método não existe; draw real já usa polígono direto) |
| 4 | `SerpentRockBullet` rotated-alpha cache (escopo corrigido) | Médio | Pendente — bloquear em profiling |
| 5 | `MountainStalactite._draw_body` (espelho do item 3) | — | **Inválido** (mesma razão do item 3) |
| 6 | `MountainsBackground` parallax — split top SRCALPHA + bot opaco | Alto | **Aplicado (2026-05-28)** |

---

## Notas para validação

Após cada item:

- **Visual:** Comparar antes/depois em vídeo curto (10 s) de combate denso
  no Mundo 1. Diff visual deve ser zero — qualquer mudança aparente
  invalida o fix.
- **FPS:** Capturar média e percentil 1% (frame time pior) durante 60 s de
  gameplay no nível 5 (combate denso, sem boss). Ganho esperado por item:
  - Item 1: marginal isoladamente, soma com itens 3/5
  - Item 2: notável em fases com 8+ gliders simultâneos
  - Item 3/5: notável durante phase 2 do CloudArchmageBoss
  - Item 4: notável durante boss fight do MountainSerpent

Se um item executado **não** mostrar ganho mensurável após validação,
documentar o resultado e considerar reverter — overhead de manutenção sem
ganho não justifica.