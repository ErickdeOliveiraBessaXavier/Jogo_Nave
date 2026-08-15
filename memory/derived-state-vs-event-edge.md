---
name: derived-state-vs-event-edge
description: Estado de objeto que sobrevive à cena (Background no Renderer) é DERIVADO por frame, nunca ligado/desligado por par de eventos — a borda de desligamento se perde quando o jogador morre no meio.
metadata:
  type: project
---

Objeto que **vive mais que a cena** não pode ter estado ligado por um evento e
desligado por outro. Se algum caminho pula o desligamento, o estado fica preso
para o resto da sessão — e o restart não conserta, porque o objeto é o mesmo.

**O caso medido (ago/2026):** o ciclo dia/noite das Cordilheiras
(`MountainsBackground`) congela durante o boss fight — o `speed_multiplier` de
warp que acelera o parallax faria um anoitecer de 10 min passar em segundos.
Isso era `BossFightController.start()` → `set_day_night_paused(True)` e `end()`
→ `False`. Só que:

- o `Background` mora no **`Renderer`** (`app.renderer`), que sobrevive à
  `PlayingScene`;
- `Renderer.set_world_theme` **não recria** o tema quando ele é o mesmo;
- morrer no meio do boss fight vai para o `GameOverScene` sem passar pelo
  `end()`, e o "Continuar" recria a `PlayingScene` — com o MESMO background,
  congelado.

Resultado: o jogador perdia o ciclo dia/noite até fechar o jogo, e nenhum teste
pegava porque cada método isolado estava certo.

**Correção — estado derivado por frame**, ao lado dos hooks que já seguiam esse
contrato (`set_allow_spawning`, `set_progress`), em `Renderer.background()`:

```python
bg.set_day_night_paused(speed_multiplier != 1.0)
```

O boss controller **não toca mais no background** (a dependência
`background_getter` saiu do construtor). O warp da cutscene de entrada/saída de
mundo passou a ser coberto de graça, porque a condição é a mesma. Sem borda,
não há borda a perder.

**Como aplicar:** antes de escrever um par `ligar()`/`desligar()`, pergunte de
quem é o tempo de vida do objeto. Se ele sobrevive a quem liga, escreva a
condição e reaplique-a por frame. Se o custo por frame importar, guarde o
último valor e só escreva na mudança — o que não vale é confiar na borda.

Ver §17 do [[CLAUDE.md]] (o `Renderer` sobrevive à troca de cena) e
[[scene-decomposition-pattern]] (grep completo ao migrar estado entre sistemas).
