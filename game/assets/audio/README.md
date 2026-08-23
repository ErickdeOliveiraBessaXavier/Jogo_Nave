# Áudio orientado por pastas (data-driven)

Uma árvore só para todo o som do jogo. A **presença** de um arquivo dentro da
pasta certa é o único registro necessário: não há lista de arquivos no código
nem caminho fixo, nem para música nem para efeito.

```
game/assets/audio/
├── music/                      # descoberta por SUBPASTA (a pasta é a chave)
│   ├── menu/                   #   contexto único → pasta plana
│   ├── themes/<WorldTheme>/    #   mountains, starfield, city, volcanic
│   └── bosses/<BOSS_TYPE_NAME>/#   metropolis_overlord, stone_golem, ...
└── sfx/                        # descoberta por NOME DE ARQUIVO (o nome é a chave)
    ├── ui/                     #   interface: click, hover, warning
    ├── weapons/                #   tiros (jogador, boss genérico, inimigo)
    ├── impacts/                #   explosões, dano, escudo, gemas
    ├── powerups/               #   ativação/recusa de aprimoramento, coleta
    ├── ambience/               #   chuva de meteoro, buraco negro, parada do tempo
    └── bosses/<BOSS_TYPE_NAME>/#   ataques de um boss específico
```

Formatos aceitos em qualquer lugar: `.ogg`, `.wav`, `.mp3` — mas **não use MP3**.

| uso | formato | por quê |
|---|---|---|
| música (longa, quase sempre loop) | **`.ogg`** | streamada por `mixer.music`; sem padding de encoder, então o loop fecha exato |
| SFX curto (< ~2 s) | **`.wav`** | `mixer.Sound` já decodifica tudo na carga; PCM é o mais simples e não pesa |
| SFX longo ou em loop (sirene, ambiência) | **`.ogg`** | mesma ausência de padding; em WAV a ambiência de 44 s custaria ~7,8 MB |

**Por que MP3 não.** O encoder acolchoa o arquivo com silêncio para fechar o
último bloco, e esse silêncio **sobrevive à decodificação** — medido aqui com
`pygame.sndarray` antes da migração:

| arquivo | início | fim | efeito |
|---|---|---|---|
| toda música | 23 ms | — | soluço a cada volta do loop |
| `ui/warning` (sirene em loop) | 50 ms | 85 ms | **135 ms de buraco por volta** |
| `metropolis_overlord_laser` (loop) | 35 ms | 15 ms | 50 ms por volta |
| SFX one-shot em geral | ~27 ms | — | atraso no ataque do som |

Hoje o repositório não tem nenhum MP3 e todos os arquivos medem **0,0 ms** de
borda.

**Ao converter, duas armadilhas:**

1. **`-map 0:a:0 -vn`** — os masters têm capa embutida (ID3 APIC). Sem isso o
   ffmpeg a transforma num stream **Theora** e o multiplexa no OGG. O `ffprobe`
   não reclama e o libvorbis lê, mas o `stb_vorbis` do SDL_mixer — que é quem o
   jogo usa — recusa com `VORBIS_invalid_first_page` e a faixa fica **muda**.
   Pegou 22 de 28 faixas na primeira tentativa da migração.
2. **A única verificação que vale é `pygame.mixer.music.load()` / `mixer.Sound()`
   de verdade.** Nem `ffprobe` nem tamanho de arquivo denunciam o caso acima.

---

## Música — a pasta é a chave

- **Tema (música ambiente):** solte arquivos em `music/themes/<tema>/`. O
  `<tema>` é o valor de `WorldTheme` (`mountains`, `starfield`, `city`,
  `volcanic`). Mundos `procedural` são expandidos para um destes.
- **Boss (música exclusiva):** solte arquivos em
  `music/bosses/<BOSS_TYPE_NAME>/`. O `<BOSS_TYPE_NAME>` é o atributo de classe
  do boss (ex.: `metropolis_overlord`, `mountain_serpent`, `stone_golem`).
- **Menu:** solte arquivos direto em `music/menu/` (pasta plana — contexto único).

**Comportamento**

- **Várias faixas numa pasta** → rotação automática (aleatória, sem repetir a
  mesma faixa em seguida), com transição suave (fade) entre faixas.
- **Uma faixa só** → ela repete continuamente (loop gapless).
- **Pasta de boss vazia** → usa a música de boss **genérica** (`bosses/normal/`).
- **Pasta de tema/menu vazia** → mantém a faixa que já estava tocando (sem corte).
  É o caso de `themes/volcanic/` hoje: **o Vulcão não tem música própria** e
  herda a do mundo anterior. Gap de conteúdo, não bug.

**Criar um tema ou boss novo:** crie a pasta, solte os arquivos. Fim — nenhum
código de configuração muda. Implementação: `game/core/music_library.py`.

---

## SFX — o nome do arquivo é a chave

A chave de um efeito é o **nome do arquivo sem extensão**. O loader
(`game/core/sfx_manager.py`) varre `sfx/` inteiro recursivamente:

| Arquivo | Chave registrada | Como o código toca |
|---|---|---|
| `impacts/shield_activate.wav` | `shield_activate` | `sound_manager.play_shield_activate()` |
| `ui/button_click.wav` | `button_click` | `sound_manager.play_sound("button_click")` |

As subpastas são **organização humana**: mover um arquivo de `ambience/` para
`impacts/` não muda a chave nem exige tocar em código. O que **não** pode é
haver dois arquivos com o mesmo nome em pastas diferentes — a chave fica
ambígua, o loader loga aviso e mantém o primeiro.

### Adicionar um SFX novo

1. Nomeie o arquivo com a chave desejada (`lower_snake_case`, ASCII).
2. Solte na subpasta que descreve o som.
3. Toque com `play_sound("<chave>")` — ou adicione um método dedicado em
   `sound.py` se precisar de canal/volume próprio.

Nenhum caminho a editar em `sound_config.py`.

### Famílias numeradas (sorteio aleatório)

Sufixo `_<n>` agrupa variações que o jogo sorteia para não repetir o mesmo som:

| Família | Arquivos | Grupo |
|---|---|---|
| `shot_{}` | `weapons/shot_1..3.wav` | `shots` |
| `explosion_asteroid_{}` | `impacts/explosion_asteroid_0..3.wav` | `explosions` |
| `meteor_rain_{}` | `ambience/meteor_rain_1..4.wav` | `meteor_rain` |

Acrescentar `shot_4.wav` entra na rotação sozinho. Declaradas em `SFX_FAMILIES`
(`sound_config.py`).

### Contrato: obrigatório vs. opcional

`sound_config.py` declara **chaves**, não caminhos:

- **`SFX_REQUIRED`** — som que o jogador espera. Ausente = `logging.error` no
  boot **e falha em `tests/test_audio_assets.py`**.
- **`SFX_OPTIONAL`** — tem fallback audível documentado; ausente só degrada o
  feedback. Cada entrada explica o fallback e por que o arquivo falta.

> **Por que o contrato existe:** `button_click` foi chamado em 19 lugares, em 8
> telas, apontando para um arquivo que **nunca existiu** — nenhum commit o
> adicionou. A carga pulava em silêncio (`if os.path.exists`, sem `else`) e
> `play_sound` é no-op em chave desconhecida, então todo clique do jogo era mudo
> enquanto o hover funcionava — o que fazia o bug parecer design.

---

## Nomenclatura

`lower_snake_case`, **ASCII puro**, sem espaço.

- **Sem acento.** Os nomes viajam por PyInstaller, build Linux, zip de
  distribuição e **pygbag (fetch por URL)**. Já houve 19 arquivos com acento
  aqui; o git os guardava escapados (`explis\303\243o_boss.wav`).
- **SFX: o nome do arquivo é a chave**, então ele é o contrato — `shield_break`,
  não `Som_Escudo_Destruído`.
- **Música: nome artístico** é aceitável (não é interpolado em código), mas em
  `lower_snake` ASCII. Variante de intensidade usa sufixo:
  `cloud_peak_circuit` / `cloud_peak_circuit_intense`.
- **Sem número de ordem** que não signifique nada. A pasta de ataques do
  Metropolis usava `01, 02, 02, 04` — sem `03` e com `02` repetido em dois
  ataques não relacionados. Hoje cada arquivo tem o nome da chave que o código usa.

> ⚠️ A rotação de faixas é **aleatória e uniforme**: sufixo de intensidade
> (`_intense`, `_war`) e de versão (`_v2`) **não** são selecionados por contexto
> — sorteiam igual às outras. O sufixo comunica uma intenção que o sistema ainda
> não implementa.

---

## Build: desktop e web

- **Desktop:** nada a fazer. A música já está em **OGG Vorbis ~131 kbps**
  (`-q:a 4`), derivada dos masters do histórico do git, e é essa a qualidade de
  distribuição. O `reencode_audio.ps1` (MP3→MP3 128k) ficou obsoleto e agora
  avisa em vez de rodar em vazio. Para mudar o alvo, **re-derive dos masters** —
  re-encodar o `.ogg` do repo é perda sobre perda.
- **Web (pygbag):** `reencode_audio_web.ps1` converte tudo sob `game\assets` para
  OGG leve em `web\assets` (música 48k, SFX 64k). A música entra mesmo já sendo
  OGG: o repo tem ~131k e o web precisa de 48k. Os SFX (`.mp3`/`.wav`) viram
  conteúdo OGG — o SDL no navegador detecta pelo magic byte `OggS`.
  `web/assets/` é gerado e está no `.gitignore`.

> **Por que a música é OGG e não MP3.** O MP3 acolchoa o arquivo com silêncio
> para fechar o último bloco do encoder — medido aqui: **23 ms** no início de
> cada faixa (`start_time=0.023021`). Numa trilha de fundo isso é inaudível; num
> **loop** é um soluço a cada volta, e quase toda faixa deste jogo é loop. Os
> `.ogg` atuais têm `start_time=0.000000`.
>
> **Ao converter, use `-map 0:a:0 -vn`.** Os masters têm capa embutida (ID3
> APIC); sem isso o ffmpeg a transforma num stream **Theora** e o multiplexa no
> OGG. O `ffprobe` não reclama e o libvorbis lê — mas o `stb_vorbis` do
> SDL_mixer, que é quem o jogo usa, recusa com `VORBIS_invalid_first_page` e a
> faixa fica **muda**. Aconteceu em 22 de 28 faixas na primeira tentativa. A
> única verificação que pega isso é um `pygame.mixer.music.load()` de verdade.
