---
name: boss-partes-fora-do-soquete
description: "Boss com partes que saem do corpo (Tríade: Sentença e órbita da Fase 3) — posição volta por reencaixe de DESVIO, e a máscara de união em offset (0,0) só vale com a peça em casa; fora dela, buffer largo remontado 1x/frame."
metadata:
  node_type: memory
  type: project
---

Vale para qualquer chefe cujas partes **saem do corpo** e voltam — hoje a
`TriadBoss` (Fase 3 põe as Vozes em órbita a ~200px), amanhã qualquer boss
segmentado.

**A Sentença deixou de mover cabeça.** A coreografia já mandou as Vozes reais
para as bordas da arena; hoje elas só **dissolvem** (`_VOICE_FADE`: fade-out
antes do primeiro feixe, fade-in depois do último) e quem ocupa a arena são os
ecos do `TriadCaster` — a marcação `Shot.voice` da partitura escolhe só o ROSTO
do eco. Motivo: mover uma peça do CORPO no meio da luta cria um problema novo a
cada momento da coreografia (onde ela fica entre as salvas, como volta, como sai
de novo no fecho), e nada disso o jogador lia como ficção. O fade É a transição
para o estágio de lasers, e nenhum offset se move.

## 1. Voltar de uma coreografia é REENCAIXE, não reatribuição

O movimento normal do corpo **atribui** a posição a partir de um seno
(`_update_drift`: `x = home + sin(t)*span`). Uma coreografia que move o corpo
para outro lugar e devolve o controle ao seno **teleporta** — medido a 720p na
Tríade: até 205px em x (a amplitude inteira da deriva), ~22px em y.

O reencaixe (`_RESYNC_TIME`, `_begin_resync`) congela o **desvio** entre onde a
coreografia deixou o corpo e onde o estado normal quer, e dissolve esse desvio
por `_smoothstep` ao longo de 1,6s. **Não** é lerp perseguindo o alvo: perseguir
um alvo que anda deixa atraso proporcional à velocidade dele — com o seno
partindo da fase zero (~72px/s) sobravam 19px, e o salto voltava no fim da
janela, menor e mais tarde. Desvio que decai chega exato por construção. Mesma
matemática no `entry` do `TriadCaster` e na abertura da órbita da Fase 3 (alvos
móveis); para alvo PARADO (o soquete) a aproximação exponencial basta e é o que
`_ease_heads_home` faz, com `_HEAD_RETURN_SPEED`.

## 2. Máscara de união só vale com a peça EM CASA

`_combined_mask` une as máscaras das partes em **offset (0, 0)**, porque a arte
desenha as três na mesma tela de 64×64. Isso deixa de ser verdade no instante em
que uma parte sai do soquete: a máscara continua no lugar antigo e vira **hitbox
fantasma**. Sintomas reais durante a Sentença: a nave morria ao encostar num
ponto vazio ao lado do tronco, o tiro do jogador morria ali sem "MISS" (o boss é
intangível na coreografia) e a cabeça desenhada na borda não colidia com nada.
A Sentença não tira mais ninguém do soquete, mas a regra vale para a órbita — e
para o próximo boss que mover uma peça.

O contrato de colisão do jogo (`get_enemy_collision_mask_data`) é **uma** máscara
com **uma** origem, então há dois caminhos:

* **partes em casa** — união em (0,0), cacheada por `_mask_key`; é o caminho da
  luta quase inteira;
* **parte destacada que precisa colidir** (o ESCUDO da Fase 3) — `_wide_mask`:
  buffer alocado uma vez, `clear()` + `draw` de cada parte no mesmo
  deslocamento que o `draw` usa, remontado **1× por frame** (`_wide_dirty` no
  update). Medido: 0,027ms a remontagem, 0,007ms a consulta cacheada. Sem o
  dirty-flag seria uma remontagem POR PROJÉTIL.

O critério único de quem entra na colisão é `TriadBoss._hit_mask`. Peça
**dissolvendo** sai dele junto com o desenho (`TriadHead.blocks_shots` exige
`fade >= 1`): hitbox invisível é a pior que existe.

## 3. "Para o tiro" ≠ "recebe dano"

`TriadHead.blocks_shots` (colisão) e `damageable` (dano) são perguntas
diferentes. Fundi-las foi o que deixou as Vozes da Fase 3 atravessáveis: a única
forma de não tomarem dano era o projétil passar por elas. Com o escudo
(`shielding`), o tiro para e o `on_hit` decide que não fere.

Cuidado que custou um bug: o **fallback por distância** (`_fallback_target`,
para impacto sem pixel exato) também tem de filtrar por quem PARA o tiro. Com
ele filtrando por `damageable`, o tiro que caía num furo do rosto da Voz em
escudo era creditado à Coroa — o escudo virava atalho para o dano.

Ver `[[metropolis-overlord-city-boss]]`, que também tem partes móveis.
