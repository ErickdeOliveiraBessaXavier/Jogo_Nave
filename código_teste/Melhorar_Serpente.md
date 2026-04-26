Análise completa. Identifiquei os gargalos mais críticos. Veja o relatório detalhado:Aqui está o diagnóstico completo. Os gargalos estão divididos em 3 prioridades:

---

**🔴 Críticos — resolver primeiro**

**1. `surface.copy()` nos afterimages da cabeça (linha 1508)**
Todo frame, para cada fantasma ativo, você chama `img["sprite"].copy()` só para setar alpha. O fix correto é pré-alocar uma surface dedicada para os ghosts e setar alpha diretamente, ou usar `blit` com um `special_flags` de alpha sem precisar copiar:
```python
# Em vez de:
ghost = img["sprite"].copy()
ghost.set_alpha(alpha)
# Use uma surface intermediária pré-alocada e blit com alpha manual via surface.set_alpha()
# ou simplesmente: surface.blit(img["sprite"], pos, special_flags=0) com modulação via fill temporária
```
O mais limpo é manter uma `pygame.Surface` temporária com `SRCALPHA` e reusar ela.

**2. `pygame.transform.rotate()` por frame em cada bloco e bala (linhas 534 e 667)**
Com 10 blocos + balas ativas, isso é N rotações por frame sem nenhum cache. A solução é quantizar o ângulo (ex: a cada 5°) e manter um dict de cache `{angle_quantized: surface}` por sprite:
```python
_rot_cache: dict[int, pygame.Surface] = {}

def _get_rotated(sprite, angle):
    key = int(angle) % 360
    if key not in _rot_cache:
        _rot_cache[key] = pygame.transform.rotate(sprite, key)
    return _rot_cache[key]
```
Isso troca CPU por memória, mas para sprites de 156×156px é totalmente viável (360 frames × ~100KB ≈ 36MB máximo, na prática bem menos com quantização de 5°).

**3. List comprehension de partículas a cada frame por bloco (linha 473)**
```python
self._particles = [p for p in self._particles if not p.dead]
```
Substitua por remoção in-place com iteração reversa — zero alocação:
```python
i = len(self._particles) - 1
while i >= 0:
    if self._particles[i].dead:
        self._particles.pop(i)
    i -= 1
```
Ou use `collections.deque` com `maxlen` se o número máximo de partículas for conhecido.

---

**🟡 Moderados — próximo passo**

**4. `hasattr(self, "_pending_shards")` todo frame (linha 1487)**
`_pending_shards` já é inicializado no `__init__`. Remova o `hasattr` — é uma verificação cara desnecessária.

**5. `_get_animation_frame_duration()` chamada duas vezes por iteração do while (linha 957)**
```python
# Atual: chama a função 2× por iteração
while self._animation_timer >= self._get_animation_frame_duration(current_idx):
    self._animation_timer -= self._get_animation_frame_duration(current_idx)
# Fix:
dur = self._get_animation_frame_duration(current_idx)
while self._animation_timer >= dur:
    self._animation_timer -= dur
    ...
    dur = self._get_animation_frame_duration(current_idx)
```

**6. `sum()` e `all()` sobre `_all_blocks` nas propriedades (linhas 1348–1356)**
São chamados potencialmente múltiplas vezes por frame. Mantenha contadores incrementais (`_left_alive`, `_right_alive`) atualizados em `on_block_killed()` e `revive()`.

**7. Rebuild da lista `_head_afterimages` todo frame (linha 1466)**
```python
self._head_afterimages = [img for img in self._head_afterimages if img["life"] > 0]
```
Substitua por `collections.deque` + remoção pela esquerda (os mais antigos morrem primeiro), ou remoção in-place reversa igual ao item 3.

---

**🔵 Menores — ganho marginal**

- `list(self._dead_block_respawn_timers.items())` no respawn (linha 1044) — itere o dict diretamente em Python 3.7+ e colete as keys para deletar separadamente.
- `_lerp_color()` no fallback circle — se o bloco está em hit flash, cachear a cor interpolada por frame (ela muda continuamente mas o custo do cálculo é baixo).

---

**Ordem de ataque recomendada:** resolve os itens 1 e 2 primeiro — praticamente toda a alocação pesada vem de `copy()` e `rotate()`. Depois o item 3 (partículas). Esses três sozinhos devem dar um ganho perceptível de 10–20 FPS dependendo de quantos blocos e fantasmas estão ativos ao mesmo tempo.