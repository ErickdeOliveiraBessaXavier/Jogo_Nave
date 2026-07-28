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

# Quantidade de slots de aprimoramentos ativos
UPGRADE_SLOT_COUNT: int = 8

# Sistema de desbloqueio de slots com estrelas
INITIAL_UNLOCKED_SLOTS = 2  # Slots inicialmente desbloqueados
SLOT_UNLOCK_COSTS = [
    0,  # Slot 1 - gratuito
    0,  # Slot 2 - gratuito
    3,  # Slot 3 - custa 3 estrelas
    5,  # Slot 4 - custa 5 estrelas
    10,  # Slot 5 - custa 10 estrelas
    20,  # Slot 6 - custa 20 estrelas
    35,  # Slot 7 - custa 35 estrelas
    50,  # Slot 8 - custa 50 estrelas
]
# Quais upgrades vêm desbloqueados por padrão (MVP)
DEFAULT_UNLOCKED: List[UpgradeType] = [
    UpgradeType.SHIELD_BURST,
    UpgradeType.HEAL,
    UpgradeType.EMP,
    UpgradeType.HOMING_SHOT,
    UpgradeType.LASER_SHOT,
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

# Parâmetros de balanceamento do Laser Shot
LASER_SHOT_DAMAGE: int = 80  # Dano do laser disparado pelas orbes

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
# O impacto do crítico é maior — é o ÚNICO feedback que o upgrade tem hoje (não
# há som nem número flutuante no vocabulário do jogo). Passa pelo mesmo
# `impact_scale` do Giant Shot, então os dois se compõem por multiplicação.
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
# Renovado a cada acerto. 2.5s é o bastante para a troca de alvo custar o nível,
# sem punir a mira imperfeita entre dois tiros da cadência mais lenta do elenco
# (Aríete, ~3.7 tiros/s).
CRYO_SLOW_DURATION: float = 2.5
# CONGELAMENTO: ao encher a escada o inimigo entra no estágio congelado, que
# dura mais que os degraus de baixo. É a recompensa por ter mantido a pressão —
# subir custa 3 acertos, e o topo compra o dobro de tempo do que os degraus
# intermediários davam. Continua sendo reposto a cada acerto novo.
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
# Paleta azul-gelo dessaturada: preenchimento, aresta e faceta de brilho.
CRYO_CRYSTAL_FILL: tuple[int, int, int] = (120, 185, 220)
CRYO_CRYSTAL_EDGE: tuple[int, int, int] = (205, 240, 255)
CRYO_CRYSTAL_SHINE: tuple[int, int, int] = (255, 255, 255)
# Tempo final em que os cristais se dissolvem. Sem isto o gelo SOME num frame,
# e some justamente quando o jogador está olhando para o inimigo que voltou a
# acelerar — o momento em que a transição mais precisa ser legível.
CRYO_CRYSTAL_FADE: float = 0.7

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
