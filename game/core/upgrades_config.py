from __future__ import annotations

import math
from typing import List

import pygame

from .upgrades import UpgradeType

# Keybindings padrão para os slots de upgrade
DEFAULT_KEYBINDINGS: List[int] = [
    pygame.K_1,
    pygame.K_2,
    pygame.K_3,
    pygame.K_4,
    pygame.K_5,
    pygame.K_6,
    pygame.K_7,
    pygame.K_8,
    pygame.K_9,
    pygame.K_0,
    pygame.K_MINUS,
    pygame.K_EQUALS,
]

# Quantidade de slots de aprimoramentos ativos.
#
# TRÊS, e um upgrade por slot. O modelo anterior tinha 8 slots E um orçamento de
# PESO (cada upgrade pesava 1–3, capacidade = slots destravados) — dois sistemas
# ensinando a mesma coisa, e o jogador com 2 slots destravados que só conseguia
# equipar UM upgrade de peso 2 não tinha como saber por quê. O peso saiu do
# cálculo de equipar; `UpgradeMeta.slot_weight` sobrevive como **tier de poder**,
# exibido na tela de aprimoramentos e sem efeito nenhum sobre o que cabe.
UPGRADE_SLOT_COUNT: int = 3

# Sistema de desbloqueio de slots com estrelas.
#
# Um slot grátis e os outros dois comprados. Os custos ficam abaixo do preço da
# nave mais barata (25★) de propósito: ampliar o loadout é a primeira compra
# possível, não uma que compete com o hangar inteiro.
INITIAL_UNLOCKED_SLOTS = 1  # Slots inicialmente desbloqueados
SLOT_UNLOCK_COSTS = [
    0,  # Slot 1 - gratuito
    10,  # Slot 2 - custa 10 estrelas
    30,  # Slot 3 - custa 30 estrelas
]

# Tabela de custos do modelo ANTIGO (8 slots). Só existe para a migração de
# perfis salvos antes da mudança — ver `migrate_slot_model`. Não usar em regra
# nova.
_LEGACY_SLOT_UNLOCK_COSTS = [0, 0, 3, 5, 10, 20, 35, 50]


def migrate_slot_model(unlocked_slots: int, stars_spent: int) -> tuple[int, int]:
    """Converte `(unlocked_slots, stars_spent)` do modelo de 8 slots para o de 3.

    Devolve os valores já no modelo novo. Duas regras:

    - **Nada é tirado sem devolver.** Quem tinha mais de 3 slots destravados
      perde os excedentes, então as estrelas pagas por eles voltam para o saldo
      (abatidas de ``stars_spent``). Quem pagou 123★ pelos 8 slots recebe 83★ de
      volta — os 40★ que os 3 novos custariam ficam pagos.
    - **Slot conquistado continua conquistado.** Quem já tinha 2 ou 3 slots pelo
      modelo antigo (onde os dois primeiros eram grátis) fica com eles sem pagar
      a diferença. Cobrar retroativamente tiraria um slot que o jogador já usava.

    Idempotente: depois de rodar, ``unlocked_slots <= 3`` e o crédito legado
    (≤3★) nunca supera o custo novo (40★), então uma segunda passada devolve 0.
    """
    novos_slots = max(1, min(UPGRADE_SLOT_COUNT, unlocked_slots))
    pago_no_modelo_antigo = sum(_LEGACY_SLOT_UNLOCK_COSTS[:unlocked_slots])
    custo_no_modelo_novo = sum(SLOT_UNLOCK_COSTS[:novos_slots])
    reembolso = max(0, pago_no_modelo_antigo - custo_no_modelo_novo)
    # Nunca reembolsa mais do que foi gasto no total (perfil editado à mão).
    reembolso = min(reembolso, max(0, stars_spent))
    return novos_slots, stars_spent - reembolso
# Quais upgrades vêm desbloqueados por padrão (MVP)
DEFAULT_UNLOCKED: List[UpgradeType] = [
    UpgradeType.SHIELD_BURST,
    UpgradeType.HEAL,
    UpgradeType.EMP,
    UpgradeType.HOMING_SHOT,
    UpgradeType.ORBITAL_DISCHARGE,
    UpgradeType.EXPLOSIVE_SHOT,
    UpgradeType.GIANT_SHOT,
    UpgradeType.AIR_STRIKE,
    UpgradeType.BLACK_HOLE,
    UpgradeType.CANNON_TOWER,
    UpgradeType.BLINK_DASH,
    UpgradeType.GRAVITY_BOMB,
    UpgradeType.CHAIN_LIGHTNING,
    UpgradeType.ORBITAL_SHIELD,
    UpgradeType.PLASMA_BEAM,
    UpgradeType.WINGMAN,
    UpgradeType.BERSERK,
    UpgradeType.COOP_LINK,
    UpgradeType.IMPLOSION_SHOT,
    UpgradeType.CRITICAL_CORE,
    UpgradeType.CRYO_SHOT,
    UpgradeType.SHOCKWAVE,
    UpgradeType.CORROSIVE_AMMO,
]

# Parâmetros de balanceamento do EMP (tempo e intensidade)
EMP_SLOW_FACTOR: float = 0.35  # Mantém 35% da velocidade (mais lento)
EMP_BASE_DURATION: float = 10.0  # Tempo que o EMP fica ativo
EMP_LINGER_DURATION: float = (
    8.0  # Tempo que o slow persiste após ser atingido pela onda
)

# Parâmetros de balanceamento do Tiro Teleguiado
HOMING_SPEED_PENALTY: float = 0.75  # Nave fica a 75% da velocidade normal
HOMING_FIRE_RATE_PENALTY: float = (
    1.2  # Leva 20% mais tempo para atirar (cadência reduzida)
)
HOMING_DAMAGE_MULTIPLIER: float = 1.5  # Tiros teleguiados causam 50% mais dano direto

# Parâmetros de balanceamento da Descarga Orbital
ORBITAL_DISCHARGE_DAMAGE: int = 80  # Dano do arco descarregado por cada orbe

# Parâmetros de balanceamento do Tiro Explosivo
EXPLOSIVE_BULLET_DAMAGE: int = 30  # Dano aplicado a cada inimigo na área
EXPLOSIVE_BULLET_RADIUS: int = 60  # Raio da explosão em pixels

# Parâmetros do Tiro Gigante (Giant Shot)
GIANT_SHOT_SIZE_MULTIPLIER: float = 3.0  # Balas 3x maiores (escala visual + hitbox)

# Quanto o Giant Shot puxa a PROPORÇÃO do tiro para o quadrado: 0.0 preserva a
# proporção da nave (um tiro fino como o do padrão, 3x10, vira só uma barra
# comprida de 9x30 — cresce nos dois eixos, mas continua lendo como "ficou mais
# largo") e 1.0 vira um quadrado perfeito. A ÁREA é `mult²` vezes a original em
# QUALQUER valor — só a forma muda —, então mexer aqui é escolha estética e não
# um buff disfarçado. Naves de tiro já quadrado (magneto, engenheiro) ignoram.
GIANT_SHOT_SQUARENESS: float = 0.5

# Giant Shot também acelera o projétil levemente: o tiro grande "empurra" mais
# rápido. Só vale enquanto o upgrade dura — `Config.BULLET_SPEED` (o tiro
# normal, todas as naves) fica intacto.
GIANT_SHOT_SPEED_MULTIPLIER: float = 1.15


def giant_visual_scale(size_multiplier: float) -> float:
    """Fator visual (sprite do tiro e efeito de impacto) sob o Giant Shot.

    O hitbox já cresce pelo `size_multiplier` cheio (~3x via
    `GIANT_SHOT_SIZE_MULTIPLIER`). Sprites pequenas — o '+' do teleguiado, a
    granada do explosivo, o burst de impacto — ficariam exageradas nesse fator,
    então tomamos a raiz quadrada: crescem de forma perceptível e coerente com o
    hitbox maior, sem virar um borrão que engole a tela. `1.0` (sem Giant Shot)
    passa reto — fonte única para bala e impacto não divergirem.
    """
    if size_multiplier <= 1.0:
        return 1.0
    return math.sqrt(size_multiplier)

# Parâmetros de balanceamento da Implosão (sucção no ponto de impacto)
#
# ATENÇÃO: em pixels do DESIGN BASE (1280×720); passa por `scale.scaled()` na
# hora do uso (§12) — nunca consuma cru. Sem isso a área encolhe em fração de
# tela conforme a resolução lógica sobe, e o upgrade fica mais fraco para quem
# joga em resolução maior. Fonte única: `implosion_pulse.suction_radius`.
#
# Raio PEQUENO de propósito: pega o alvo atingido e a vizinhança imediata, não
# varre a tela. Para comparar, a explosão do tiro explosivo tem 60px.
IMPLOSION_RADIUS: float = 82.5
# Dano por tique dentro da área, e o intervalo entre tiques (4 HP/s).
#
# Pequeno de propósito: em 2s de zona são ~8 de dano, menos que UMA bala (10).
# O upgrade continua sendo de controle — o dano é pressão de fundo sobre o grupo
# freado, não a forma de matar.
#
# O cooldown do tique vive no INIMIGO, não no pulso (`implosion_damage_cd`).
# Sob fogo sustentado há dezenas de pulsos vivos ao mesmo tempo; com o cooldown
# por pulso, cada um tiquetaria por conta própria e o dano escalaria com a
# cadência de tiro em vez de ficar no teto abaixo. Referência do projeto:
# `IcePoisonZone` faz 1 dano a cada 0.2s, mas é zona única e não empilha.
IMPLOSION_DAMAGE: int = 1
IMPLOSION_DAMAGE_INTERVAL: float = 0.25
# Duração da sucção: vale para o círculo E para o deslocamento dos inimigos, que
# são a mesma curva (ver `ImplosionPulse._eased`). 2s é tempo de o jogador VER a
# implosão acontecer — a versão anterior, de 0,18s, cumpria a física mas passava
# rápido demais para registrar como evento.
IMPLOSION_DURATION: float = 2.0
# Abertura do círculo: ele cresce de 0 ao raio cheio e ganha opacidade neste
# tempo, em vez de aparecer pronto. Sai de DENTRO da duração (7,5% dela), não
# se soma a ela.
#
# Existe porque o ease-in deixa o anel quase parado no primeiro segundo (aos
# 0,5s só 1,6% do encolhimento aconteceu): sem abertura, o jogador via um pop
# seguido de um anel estático, e o pop ficava ainda mais evidente por não ter
# movimento nenhum em volta para disfarçá-lo. Acima de ~0,25s a abertura passa a
# competir com a implosão e o efeito lê como uma onda que EXPLODE antes de sugar
# — o oposto do que ele comunica.
IMPLOSION_OPEN_TIME: float = 0.15
# Lentidão deixada pela sucção: 0.25 = o inimigo anda a 1/4 da velocidade (75%
# mais lento).
IMPLOSION_SLOW_FACTOR: float = 0.25
# Quanto o debuff SOBREVIVE à saída da zona.
#
# É o valor cravado no timer a cada frame em que o inimigo está dentro, então
# ele fica lento a zona inteira e sai com estes 3s pela frente — que é o que
# "3 segundos após o término" quer dizer. Não somar a duração da zona aqui: o
# timer é REPOSTO por frame, não aplicado uma vez, e somar daria 5s de sobrevida.
IMPLOSION_SLOW_LINGER: float = 3.0

# Parâmetros do Critical Core
#
# A rolagem é POR BALA, não por disparo: com o leque são 5 sorteios por puxada
# de gatilho, e é isso que faz o upgrade "cintilar" em vez de ligar e desligar a
# salva inteira. Uma salva toda crítica seria um evento raro e mudo; balas
# críticas soltas dão leitura contínua de que o upgrade está ativo.
#
# Os dois números só importam pelo produto: o dano médio enquanto ativo é
# `1 + chance × (mult - 1)` = 1 + 0,25 × 1,5 = **+37,5%**. Fica abaixo do
# Berserk (+50% fixo, mas em rajada rotativa curta) e acima de um power-up de
# dano comum. Mexer em um dos dois sem olhar o produto muda a força do upgrade
# sem parecer que mudou.
#
# A repartição escolhida (crítico grande e raro, em vez de pequeno e frequente)
# é o que dá o pico perceptível: 2,5× mata em uma bala o que exigia três.
CRITICAL_CORE_CHANCE: float = 0.25
CRITICAL_CORE_MULTIPLIER: float = 2.5
# O impacto do crítico é maior. Passa pelo mesmo `impact_scale` do Giant Shot,
# então os dois se compõem por multiplicação.
#
# É um dos DOIS feedbacks do upgrade, divididos por escopo: o impacto vale no
# hit não-letal, e no abate quem avisa é o número de score vermelho
# (`floating_score.CRITICAL_COLOR`) — no abate o impacto dá lugar à explosão de
# morte do inimigo, então sem a cor o crítico que MATA seria o único invisível.
CRITICAL_CORE_IMPACT_SCALE: float = 1.6

# Parâmetros do Cryo Shot
#
# Escada de lentidão por acertos ACUMULADOS no mesmo inimigo: 25% → 50% → 75%
# mais lento. Os valores são o que SOBRA da velocidade (0.75 = anda a 3/4).
#
# A identidade do upgrade é ser CONDICIONAL, e quem entrega isso é a duração
# curta, não a subida: subir é fácil (3 acertos), mas o nível inteiro cai de uma
# vez se o jogador soltar o alvo. É o que o separa da Implosão, que é área e não
# pede pontaria — aqui a recompensa é manter a pressão no mesmo inimigo.
#
# A queda é TOTAL e não degrau a degrau, de propósito: escada que desce sozinha
# vira um número flutuante que o jogador não consegue ler na tela. "Está gelado"
# ou "descongelou" é legível; "está no nível 2 descendo para 1" não.
CRYO_SLOW_STEPS: tuple[float, ...] = (0.75, 0.50, 0.25)
CRYO_MAX_STACKS: int = len(CRYO_SLOW_STEPS)

# ── O tiro enquanto o Cryo está ativo ──────────────────────────────────────
#
# O Cryo não muda só a cor do projétil: enquanto dura, a nave atira um TRIO de
# cristais, maiores e mais fortes que o tiro comum. Os três parâmetros abaixo
# são a face ofensiva do upgrade — a face de controle (escada, congelamento) e a
# de payoff (bomba de gelo) estão logo acima e abaixo.
#
# Leque APERTADO (±9°, contra os ±17° do Spread Shot): o Cryo é um upgrade de
# alvo único — a escada só sobe insistindo no MESMO inimigo. Um leque largo
# espalharia as cargas por três alvos diferentes e trabalharia contra a própria
# mecânica; apertado, os três cristais tendem a cair no mesmo corpo e é isso que
# torna o congelamento rápido de alcançar.
CRYO_SHOT_ANGLES: tuple[float, ...] = (-9.0, 0.0, 9.0)
# Área do projétil (visual + hitbox), pelo mesmo `size_multiplier` do Giant
# Shot. Cristal de gelo é um caco grosso, não uma agulha — e a área maior é o
# que faz o trio conectar inteiro num alvo médio em vez de só o tiro do meio.
# Consequência herdada do canal: tiro com `size_multiplier != 1.0` também ganha
# o `GIANT_SHOT_SPEED_MULTIPLIER`, então o cristal viaja ~15% mais rápido. É
# aceito de propósito — projétil grande e lento lê como pesado, e este é gelo.
CRYO_SHOT_SIZE_MULTIPLIER: float = 1.6
# Dano por cristal, sobre o dano já ajustado da nave. Multiplica ANTES do
# crítico, como o teleguiado — assim o crítico continua valendo os mesmos 2,5×
# sobre o que aquela bala causaria.
#
# 1.15 e não 1.35: o bônus por cristal é o MENOR dos três multiplicadores que o
# Cryo empilha, e era o mais fácil de esquecer. O upgrade já triplica a saída
# pelo trio e engorda a hitbox em 1.6× (o que faz os três conectarem em vez de
# só o do meio); somar +35% por projétil em cima disso colocava o dano bruto
# acima do de upgrades que não dão controle nenhum. O cristal continua batendo
# mais que a bala comum — que é o que ele precisa comunicar —, só não é mais o
# lugar onde o Cryo ganha a conta.
CRYO_SHOT_DAMAGE_MULTIPLIER: float = 1.15
# Redução APLICADA SÓ CONTRA ALVOS PESADOS (boss e miniboss), sobre o dano do
# cristal, da bomba e dos cacos. Ver `entities._shared.heavy_targets`.
#
# O valor é 0.5 porque é o mesmo que o Wingman (`_WINGMAN_BOSS_DAMAGE_MULT`) e a
# Estrela Espiral (`_BERSERK_BOSS_DAMAGE_MULT`) já usam, pelo MESMO motivo: são
# os três upgrades que emitem VÁRIOS projéteis por disparo. Contra um inimigo
# comum só um deles conecta; um corpo largo come o leque inteiro, e o dano por
# disparo salta sem que nada no upgrade tenha mudado. É um nerf de geometria,
# não de poder — por isso incide só onde a geometria é o problema.
#
# Contra BOSS ele se compõe com o `BOSS_UPGRADE_DAMAGE_MULTIPLIER` global (0.5),
# como nos outros dois: 0.5 × 0.5 = 25% do dano nominal. O miniboss não passa
# pelo nerf global (ele é inimigo comum para o roteador de colisão), então leva
# os 50% — a escada fica inimigo comum 100% → miniboss 50% → boss 25%.
CRYO_HEAVY_TARGET_DAMAGE_MULT: float = 0.5
# Renovado a cada acerto. 2.5s é o bastante para a troca de alvo custar o nível,
# sem punir a mira imperfeita entre dois tiros da cadência mais lenta do elenco
# (Aríete, ~3.7 tiros/s).
CRYO_SLOW_DURATION: float = 2.5
# CONGELAMENTO: ao encher a escada o inimigo entra no estágio congelado, que
# dura mais que os degraus de baixo. É a recompensa por ter mantido a pressão —
# subir custa 3 acertos, e o topo compra o dobro de tempo do que os degraus
# intermediários davam. Continua sendo reposto a cada acerto novo.
#
# O congelamento é TAMBÉM o pavio da bomba de gelo: os cristais armazenam
# energia por esta duração e estilhaçam no fim (ou na hora, se o alvo morrer
# antes). Ver `CRYO_BOMB_*` logo abaixo.
CRYO_FREEZE_DURATION: float = 5.0
# Quantos cristais se formam em volta do inimigo congelado. Poucos e grandes,
# não muitos e pequenos: o pedido é "parcialmente encapsulado", e cristal
# pequeno demais vira ruído em cima de sprites que já são pixel art densa.
CRYO_CRYSTAL_COUNT: int = 6
# Onde os cristais nascem e até onde vão, em fração do raio do inimigo. A base
# começa DENTRO (0.45) para parecer gelo brotando do corpo, e a ponta passa da
# borda (1.2) para o contorno ficar irregular. O miolo do sprite fica livre — o
# inimigo tem que continuar reconhecível.
CRYO_CRYSTAL_INNER: float = 0.78
CRYO_CRYSTAL_OUTER: float = 1.5
# Tetos em PIXELS para alvos grandes (bosses). As frações acima são do raio, e
# num boss de 120px de raio um cristal de 0.5*raio viraria uma lâmina de 60px
# cobrindo meia tela. Acima destes limites o gelo passa a crescer em NÚMERO
# (mais cristais ao longo do perímetro) em vez de em tamanho — o que lê como
# "casca de gelo se formando", e não como uma estrela gigante.
CRYO_CRYSTAL_MAX_LENGTH: float = 30.0  # o quanto a ponta passa da borda
CRYO_CRYSTAL_MAX_WIDTH: float = 11.0  # meia-largura do cristal
CRYO_CRYSTAL_ARC: float = 34.0  # px de perímetro por cristal em alvo grande
CRYO_CRYSTAL_COUNT_MAX: int = 16
# Paleta azul-gelo dessaturada: preenchimento, aresta e faceta de brilho.
CRYO_CRYSTAL_FILL: tuple[int, int, int] = (120, 185, 220)
CRYO_CRYSTAL_EDGE: tuple[int, int, int] = (205, 240, 255)
CRYO_CRYSTAL_SHINE: tuple[int, int, int] = (255, 255, 255)
# Janela final em que os cristais CARREGAM: clareiam rumo ao branco, crescem e
# cintilam mais rápido. É o aviso de que a bomba vai estourar — antes daqui o
# gelo era só um debuff silencioso que sumia sozinho, e o jogador não tinha como
# antecipar o estilhaço. Não é fade: o gelo não se dissolve mais, ele detona.
CRYO_CRYSTAL_CHARGE: float = 1.1

# ── Bomba de gelo (o payoff do Cryo Shot) ──────────────────────────────────
#
# Congelar deixou de ser só controle: os cristais são um pavio. Ao fim do
# congelamento (ou na morte do alvo, o que vier primeiro) eles estilhaçam,
# ferindo o alvo e cuspindo fragmentos que atingem a vizinhança.
#
# É o que dá ao upgrade um CICLO fechado — cargas → cristalizar → estouro —
# em vez de um debuff que expira sem evento nenhum. O dano continua condicional:
# só sai de três acertos mantidos no MESMO alvo.
#
# 40 = quatro balas comuns (`BULLET_BASE_DAMAGE` = 10) entregues de uma vez, no
# alvo que já custou três balas para congelar. Alto o bastante para o estouro
# ser o que mata um inimigo médio, baixo o bastante para não trivializar tanques.
# Contra boss ainda passa pelo `BOSS_UPGRADE_DAMAGE_MULTIPLIER` global.
CRYO_BOMB_DAMAGE: int = 40
# Explosão visual do estouro (raio em px do design base).
CRYO_BOMB_EXPLOSION_SIZE: int = 34
# Fragmentos cuspidos em leque completo. 8 fecha o círculo com espaçamento
# legível; mais que isso vira uma bola branca e o jogador perde os projéteis
# individuais de vista, que é justamente o que comunica "estilhaçou".
CRYO_BOMB_SHARDS: int = 8
# Dano por fragmento. Abaixo de uma bala comum de propósito: o prêmio do estouro
# é ATINGIR VÁRIOS, não repetir o dano do alvo principal em cada vizinho.
CRYO_SHARD_DAMAGE: int = 8
# Rápidos: o estilhaço tem que ler como explosão, não como salva de tiros. O
# tiro comum anda a `Config.BULLET_SPEED`; o fragmento passa disso.
CRYO_SHARD_SPEED: float = 620.0
# Alcance CURTO por tempo de vida, não por distância: o estouro limpa a
# vizinhança do alvo, não a tela. 0.4s × 620px/s ≈ 250px de raio útil.
CRYO_SHARD_LIFETIME: float = 0.4
# Lado do fragmento em px (quadrado — o sprite de cristal do tiro de gelo).
CRYO_SHARD_SIZE: int = 8

# Parâmetros do Shockwave
#
# Enquanto ativo, a morte de cada inimigo vira uma explosão PEQUENA no lugar
# onde ele estava. Reusa o `ExplosiveEffect` (mesma peça do tiro explosivo), que
# já traz visual, dano em área com dedup por inimigo e ciclo de vida.
#
# Raio menor que o do tiro explosivo (60px) de propósito: a onda não é uma
# segunda arma, é o eco da morte. Ela pega quem estava colado no que morreu.
SHOCKWAVE_RADIUS: float = 46.0
# Dano baixo: mata o que já estava quase morto e encadeia em enxame, sem virar
# a forma principal de matar. O valor é por onda, aplicado uma vez por inimigo.
SHOCKWAVE_DAMAGE: int = 12
SHOCKWAVE_LIFETIME: float = 0.3
# Ciano frio, para não ser confundido com a explosão laranja do tiro explosivo:
# são efeitos parecidos e a cor é o que diz de quem é qual.
SHOCKWAVE_COLOR: tuple[int, int, int] = (120, 230, 255)
# Teto de ondas VIVAS ao mesmo tempo. Não é só orçamento de frame: a onda mata
# inimigos, e cada morte gera outra onda. Como o dano das explosões é aplicado
# percorrendo a MESMA lista onde a nova onda entra, sem teto uma cascata em
# enxame cresceria dentro do próprio laço do frame. Com teto, ela é uma reação
# em cadeia satisfatória e limitada.
SHOCKWAVE_MAX_ACTIVE: int = 8

# Parâmetros do Corrosive Ammo
#
# Identidade OBRIGATÓRIA para não virar redundância com a Implosão: **alvo único
# e cumulativo**. A Implosão é área e não pede pontaria; o Corrosive só paga a
# pilha cheia para quem insiste no MESMO inimigo — daí "excelente contra chefes".
#
# 3 cargas, uma por acerto. O dano por tique é `carga × CORROSIVE_DAMAGE_PER_STACK`,
# então a pilha cheia vale 3× a primeira: subir a pilha é o upgrade inteiro.
CORROSIVE_MAX_STACKS: int = 3
CORROSIVE_DAMAGE_PER_STACK: int = 3
# O intervalo entre tiques mora no INIMIGO (`corrosive_damage_cd`), não na nave
# nem na bala. É o que impede o DPS de escalar com a cadência de tiro: acertar
# mais rápido sobe a pilha e renova a duração, mas nunca aperta os tiques. Sem
# isso, o Aríete (lento) e a Estrela (rápida) teriam upgrades diferentes.
#
# 0,5s dá 6 HP/s na carga 1 e 18 HP/s na pilha cheia. Para comparar: uma bala
# comum são 10 de dano de uma vez, e a Implosão faz 4 HP/s em ÁREA. O Corrosive
# em alvo único fica acima dela, que é o preço de exigir pontaria sustentada.
CORROSIVE_TICK_INTERVAL: float = 0.5
# Reposta (não somada) a cada acerto, como a escada do Cryo. 4s é generoso de
# propósito: diferente do Cryo, aqui o jogador não está comprando controle e sim
# dano ao longo do tempo, e um DoT que morre entre duas balas não se acumula.
#
# Ao expirar, a pilha cai INTEIRA. Pilha que desce degrau a degrau vira um número
# flutuante que ninguém lê na tela — "está corroído" ou "não está" é legível.
CORROSIVE_DURATION: float = 4.0
# Verde-ácido: cor que ainda não existe no vocabulário de efeitos do jogo (o
# gelo é azul, a onda é ciano, a explosão é laranja, a implosão é violeta).
#
# Musgo, não neon: o verde saturado já é do tiro teleguiado (0,255,100). A
# leitura de "ácido" vem da FORMA (bolhas, poços, gotejamento) — cor fluorescente
# só competiria com o teleguiado e com o halo do Estilete.
CORROSIVE_COLOR: tuple[int, int, int] = (146, 214, 78)
CORROSIVE_COLOR_DARK: tuple[int, int, int] = (62, 108, 40)
# O projétil corrosivo é MAIOR que o comum: ácido é líquido pesado, e a bolha
# precisa de área para os poços e o brilho caberem (abaixo de ~6px o sprite cai
# no caminho degradado). Pelo mesmo `size_multiplier` do Giant/Cryo, então os
# três se compõem por multiplicação.
#
# Consequência herdada do canal, igual à do Cryo: tiro com `size_multiplier !=
# 1.0` também ganha o `GIANT_SHOT_SPEED_MULTIPLIER`. Aceita de propósito — um
# pingo lento de ácido lê como fraco, e o alcance extra não muda balanceamento
# (o dano é o mesmo; quem fere é a marca no alvo).
CORROSIVE_SHOT_SIZE_MULTIPLIER: float = 1.45
# Bolhas desenhadas em volta do alvo corroído, POR CARGA. Poucas: o efeito tem
# que ser lido de relance sem cobrir o sprite (mesma regra dos cristais do Cryo).
CORROSIVE_BUBBLES_PER_STACK: int = 3

# Parâmetros de balanceamento do Air Strike
AIR_STRIKE_BOMB_COUNT: int = 20  # Bombas por ativação da ultimate
AIR_STRIKE_BOMB_DAMAGE: int = 100
AIR_STRIKE_BOMB_RADIUS: float = 80.0
AIR_STRIKE_BOMB_FALL_SPEED: float = 800.0
AIR_STRIKE_EXPLOSION_DURATION: float = 0.5  # segundos de animação/janela de dano
# Margem de segurança das bordas = raio + folga, para o círculo de explosão INTEIRO
# caber na tela em qualquer lado. A margem antiga (40/60px) era menor que o raio
# (80px), então o blast dos impactos junto às bordas transbordava — horizontal e
# verticalmente. Fonte única do clamp (gerador de alvos, entity_manager e a bomba).
AIR_STRIKE_SCREEN_MARGIN: float = AIR_STRIKE_BOMB_RADIUS + 12.0

# Parâmetros de balanceamento da Cannon Tower
CANNON_MINE_DAMAGE: int = 120
CANNON_MINE_RADIUS: float = 70.0

# Futuro: overrides por dificuldade ou progressão
# Example structure (não usado no MVP):
# PER_UPGRADE_BALANCE: dict[UpgradeType, dict[str, float | int]] = {
#     UpgradeType.SHIELD_BURST: {"cooldown": 45.0, "duration": 7.0},
# }
