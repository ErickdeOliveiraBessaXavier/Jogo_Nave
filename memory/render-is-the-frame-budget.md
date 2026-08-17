---
name: render-is-the-frame-budget
description: Medido 17/08/2026 — o render é ~93% do frame (update 0,6 ms vs render 7,9 ms) e o fundo sozinho é 50% do render. O contador do F3 saturava em exatamente 30 por ser alimentado com o dt clampado. Como perfilar de novo.
metadata:
  node_type: memory
  type: project
---

Investigação de 17/08/2026, disparada por "no navegador fica estagnado em 30 fps".
Web media 20–28 fps reais; desktop 50–80.

## O contador do F3 era um PISO, não uma medida

`update_fps` era alimentado com o `dt` do jogo, que chega **clampado** em
`_MAX_FRAME_DT` (1/30) por `app.py`. Com o frame real acima de 33,3 ms todo `dt`
vale exatamente 1/30, então `fps_counter / fps_timer` dá exatamente 30 — a 30, a
18 ou a 8 fps reais. `avg`/`max frame time` idem, presos em 33,3 ms, que é
justo onde começa o pico que se quer achar.

**Corrigido:** `Renderer.update_fps()` lê `time.perf_counter()` e não recebe mais
`dt`. Exceção deliberada ao §3 (render não lê relógio): a regra existe para
animação, que deve parar com o jogo; o medidor precisa do contrário. Ignora
intervalos > 1 s (troca de cena, pausa, aba em background).

Consequência de gameplay que explica o "está mais lento" (não só picotado):
abaixo de 30 fps o clamp do §14 põe o jogo inteiro em **câmera lenta**. A 20–28
fps o mundo roda a 67–93% da velocidade.

## Onde o tempo vai (medido, nível 1, driver SDL real)

| parte | ms/frame | fatia |
|---|---|---|
| `update` (física, colisão, IA, spawner) | 0,61 | 7% |
| `render` | 7,91 | **93%** |

Dentro do render:

| seção | ms/frame | fatia do render |
|---|---|---|
| `renderer.background` | 2,76 | **50%** |
| → `mountains.draw` (26 blits/frame) | 1,86 | |
| → upscale do fundo retrô | 0,90 | |
| HUD unificado | 0,85 | 15% |
| `renderer.preparation` (transitório) | 0,82 | |

Volume por frame: **113 `blit`**, **72 `draw.rect`**, 8 `font.render`. É o
**número de travessias Python→C** que explica o web: no WASM cada uma custa
várias vezes mais que no CPython nativo. Não é um bug do web — é o mesmo frame,
sem folga para absorver.

## O que a medição DESMENTIU

- **"Cachear as camadas estáticas do fundo"** — não existem. As camadas rolam
  por parallax. E o fundo já está otimizado: céu composto em cache, split
  opaco/alpha, bind local do `blit`, meia-resolução + `transform.scale` de 3
  argumentos (escreve no destino, sem alocar). Os 2,76 ms são fillrate legítimo.
- **"Baixar a qualidade para Baixo"** — Baixo não compra nada além de Médio
  (5,26 vs 5,32 ms). O que sobra é estrutural. Alto→Médio corta 33%; Médio→Baixo
  corta ~1%.
- **Cachear as caixas do HUD** — só a fileira de slots VAZIOS é inerte (feita:
  ~10 travessias → 1 blit, −0,26 ms). Score/kills/players são conteúdo dinâmico
  por frame; sobraria a moldura, com ganho no ruído.

## Aplicado

- `preferences.py`: `_DEFAULT_VISUAL_QUALITY = "medium" if IS_WEB else "high"`.
  Único ganho grande (−33% do render). Desktop intocado.
- `game_renderer.py`: cache da fileira de slots vazios, chaveado por
  `(n, ui_scale, touch_mode, keybindings, i18n.language)`.

## O diferencial que apontou o culpado: menu liso, gameplay lento

Observação do usuário (o experimento controlado mais útil da investigação): no
**mesmo tema** das cordilheiras, o menu roda liso e o gameplay não. Mesmo fundo,
mesma resolução — só muda o que roda por cima. Medido em estado estável (após
900 frames de aquecimento, ~40 inimigos em tela):

| | ms/frame |
|---|---|
| fundo sozinho (o que o menu paga) | 3,44 |
| frame de gameplay completo | 9,09 |

O fundo custa **o mesmo** nos dois — ele não é o problema, apesar de ser 50% do
frame. Os 5,65 ms de diferença eram `entity_manager.draw` (3,12) + HUD (0,91).

**O culpado era um inimigo só:** `rock_glider.draw` a 1,64 ms/frame, 18% do
frame inteiro. Os anéis de propulsor faziam 3 fases × 2 bocais = **6
`pygame.draw.rect` por glider por frame**; o RockGlider é o swarm base do tema
(§11: o mais frequente), então com 20 em tela eram **120 travessias Python→C só
de anel**.

**Corrigido** pré-rasterizando o ciclo em 12 passos (`RING_ANIM_STEPS`), mesmo
padrão do `_eye_surface_cache` que já existia no arquivo: 6 `draw.rect` → 1
blit. Cache construído junto da geometria dos bocais (depende dela, e é
reconstruído quando o glider muda de tamanho).

| | antes | depois |
|---|---|---|
| frame de gameplay | 9,09 ms | 6,96 ms (−23%) |
| além do fundo | 5,65 ms | 3,27 ms (−42%) |
| `rock_glider_pool.draw` | 1,67 ms | 0,95 ms |

**Lição geral:** o custo não estava onde o perfil de tottime apontava primeiro
(o fundo, maior fatia isolada), e sim no que **escala com a contagem de
entidades**. Num shmup o swarm base multiplica qualquer desperdício por 20–40.
Procurar `draw.rect`/`blit` em loop dentro do `draw` de inimigo frequente é o
primeiro lugar a olhar, não o último.

## O cache de texto do web estava METADE contornado

Outro diferencial do usuário: no menu (starfield) o fundo roda liso; ao abrir
**Configurações** o MESMO fundo fica mais lento. Não é intencional — as duas
cenas chamam `starfield.update(dt)` igual (o `star_speed_mult` do MainMenu só é
>1 durante o warp). É o clamp do §14 de novo: Configurações derruba o frame
abaixo de 30 e o `dt` clampado faz as estrelas andarem devagar de verdade.

| tela | ms/frame |
|---|---|
| MainMenu | 1,69 |
| Configurações | 9,33 — **mais cara que o frame de gameplay** |

Causa raiz, e ela valia para o jogo inteiro: `_PixelGridFont.render`
(`core/assets.py`) faz **dois `transform.smoothscale`** por texto on-grid, para
~1px de feathering. Em Configurações eram **76 `smoothscale`/frame**.

O cache de texto do web (`web/main.py:_install_text_cache`) **não cobria isso**:
ele substitui `pygame.font.Font.render`, mas `_PixelGridFont` é subclasse e
**sobrescreve** `render` — a chamada entra na subclasse e só o `super().render()`
lá dentro via cache. O glifo era reaproveitado; os dois `smoothscale` rodavam
todo frame. **Memoizar no nível da subclasse** é o conserto.

Feito: cache LRU **por instância** de fonte (`OrderedDict`, teto 256). Por
instância e não global chaveado por `id(self)` porque o `get_font` é um
`lru_cache` que despeja fontes — um `id()` reciclado pelo GC devolveria a
surface da fonte errada.

Configurações: **9,33 → 6,56 ms (−30%)** no desktop. O HUD de gameplay usa o
mesmo caminho e se beneficia, mas a magnitude não foi isolada (o probe de
gameplay varia de contagem de entidades entre corridas — não comparar corridas
não-semeadas).

**Confirmado em campo:** o usuário reportou melhora grande no web, acima do que
os −30% de desktop sugeriam. Calibragem para priorizar as próximas: **medição de
desktop SUBESTIMA o ganho de tirar operação de software rendering**
(`smoothscale`, `scale`, blit SRCALPHA de área grande), porque no WASM não há
aceleração para elas. O inverso vale para lógica Python pura, que escala mais
parecido entre as duas plataformas. Ao escolher alvo, dar peso extra a
`transform.*` e a alpha blending por frame.

**Semântica nova:** a surface devolvida é COMPARTILHADA entre chamadas iguais. O
padrão do código (`surf = render(); surf.set_alpha(a); blit(surf)`) é seguro;
quem guardar a surface para mutar depois precisa copiar. É a mesma semântica que
o cache do web já impunha a todo texto off-grid.

## Varredura do padrão "transform por frame sem cache"

Depois do achado da fonte, varri o projeto pelo mesmo padrão (render por
software no caminho por frame). Estado em 17/08/2026:

- **`pickups/star.py` — CORRIGIDO.** Tinha DUAS falhas somadas: (1) o `update`
  fazia `transform.rotate` da imagem inteira e guardava em `self.current_image`,
  **atributo que ninguém lia** — rotate por estrela/frame com resultado
  descartado; (2) o `draw` refazia `scale` + `rotate` do zero por frame.
  Medido com 20 estrelas: só os transforms custavam **2,575 ms/frame**, contra
  **0,173 ms** do update+draw inteiro depois do cache (~16×). Corrigido com
  cache de classe por `(tamanho, passo de rotação)`, 36 passos (10°), teto 512
  (uso real: ~252 entradas = 7 tamanhos × 36).
- **`enemies/city/carrier_debris.py` — PENDENTE.** `transform.rotate(s.img,
  s.angle)` por destroço por frame, sem cache nenhum. Prioridade menor que a
  estrela porque destroço é transitório (só quando um CargoCarrier morre).
- **Já cacheados, não mexer:** `homing_bullet` (`_rot_cache` quantizado),
  `mountain_serpent_boss` (`_rotation_cache`), `cutting_storm`
  (`_pixel_cache`/`_streak_cache`), `cyber_tank` (`_arrow_cache`),
  `cloud_archmage_boss` (`_tint_cache`).

**Como procurar da próxima vez:** `grep -rn "pygame\.transform\." game/` e, para
cada arquivo, checar se existe `_cache` perto. Transform sem cache no `draw` de
algo que aparece em quantidade é sempre suspeito. E vale conferir se o resultado
é realmente **lido** — o caso da estrela mostra que dá para pagar por um
transform inteiro e jogar fora.

## Como perfilar de novo (as duas armadilhas)

Harness headless que roda o loop real (`GameApp` + `PlayingScene`, update +
render, cProfile). Duas coisas fazem o probe medir zero e mentir:

1. **`SDL_VIDEODRIVER=dummy` não rasteriza** — render mede `0.00 ms/frame` e o
   probe fica cego justo na parte que pesa. Precisa do driver real.
2. **`PlayingScene.render` tem guard de cena-topo** e aborta se a cena não está
   empilhada em `app.states`. Chamar **`render_world(surface)`**, que é o
   caminho sem guard (existe para as overlays desenharem o jogo por baixo).

Relacionado: [[visual-quality-system]], [[web-cdn-runtime-firefox]].
