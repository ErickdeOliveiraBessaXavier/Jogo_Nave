"""Cabeça lateral da Tríade — "as Vozes".

Cada lateral tem HP próprio, hitbox própria e morte própria, mas **não é uma
entidade solta**: não vive em `em.enemies`, não recebe `update_in_context` e não
passa pelo `EntityManager`. Ela é uma PARTE do boss, e o boss é quem a atualiza,
desenha e roteia dano para ela (§9 — composição com fachada preservada).

Divisão de responsabilidade com o `ResonanceGate`:

  * o **portão** (`triad_resonance`) é dono do TEMPO e da REGRA — quem pode
    voltar, quando, e com quanto de vida;
  * a **cabeça** (aqui) é dona do CORPO — HP, sprite, flash, animação.

A cabeça não conhece o portão nem o boss. O boss lê o portão e empurra o
resultado para cá por métodos explícitos (`enter_down`, `enter_remat`,
`restore`), o que mantém as duas metades testáveis em separado (§1).
"""

from __future__ import annotations

import pygame

from . import triad_pixel_map as pmap
from .triad_resonance import HeadState


class TriadHead:
    """Uma das duas cabeças laterais. Estado de corpo; o de fluxo é do portão."""

    # Fração do HP máximo com que a brasa remonta. Frágil de propósito: durante
    # o REMAT a Coroa segue exposta, então suprimir a brasa precisa ser barato o
    # bastante para competir com queimar o núcleo — é essa comparação que faz a
    # decisão existir.
    EMBER_HP_FRACTION: float = 0.25

    _HIT_FLASH_TIME: float = 0.08

    def __init__(
        self,
        slot: int,
        part_key: str,
        max_hp: int,
        offset: tuple[float, float],
        radius: float,
    ) -> None:
        self.slot = slot
        self.part_key = part_key
        self.max_hp = max(1, int(max_hp))
        self.hp: float = float(self.max_hp)
        # Offset do centro da cabeça em relação ao (x, y) do boss. É mutável
        # porque as fases seguintes deslocam as cabeças (a Sentença manda as
        # laterais para as bordas); nesta etapa ele nunca muda do valor da arte.
        self.offset_x, self.offset_y = offset
        # Offset de CASA — a posição em que a arte já desenhou esta cabeça dentro
        # da tela compartilhada de 64×64. O sprite é blitado deslocado de
        # `offset - home`, senão mover a cabeça moveria só a hitbox e a origem do
        # feixe: na Sentença os lasers saíam do nada, com as cabeças coladas no
        # corpo (relatado em playtest).
        self.home_offset_x, self.home_offset_y = offset
        self.radius = radius

        self.center_x: float = 0.0
        self.center_y: float = 0.0

        # Laranja = "esta cabeça vai agir agora". Ninguém liga isso ainda; o
        # contrato existe desde já para os ataques só terem que setar o flag.
        self.attacking: bool = False
        # Direção do rosto, em radianos de tela. `None` = pose de repouso, o
        # blit cru da tela compartilhada (o caminho de sempre, sem giro nenhum).
        # A Sentença destaca a cabeça e a faz MIRAR: aí o sprite passa a ser
        # girado e ancorado no desenho, não na imagem. Ver `draw`.
        self.aim: float | None = None

        self._sprites = pmap.load_part(part_key)
        # Índice de frame vem do BOSS, não de um relógio próprio: as três
        # cabeças são uma criatura só e precisam respirar em sincronia. Com
        # relógios independentes elas dessincronizam e o conjunto tremula.
        self._frame_index: int = 0
        self._hit_flash: float = 0.0
        # 1.0 = sólida e opaca; abaixo disso é brasa remontando.
        self._alpha_scale: float = 1.0
        self._visible: bool = True
        self._damageable: bool = True
        # DISSOLUÇÃO (0 = sumida, 1 = presente). É o véu da Sentença: as Vozes
        # não vão para a arena disparar, elas SOMEM enquanto a coreografia roda e
        # voltam no fim. Separado do `_alpha_scale`, que é a barra de progresso
        # da brasa remontando — os dois se multiplicam sem se atropelar.
        self.fade: float = 1.0
        # ESCUDO: a cabeça para o tiro mas não recebe dano. É o estado da Fase 3
        # — ver `enter_orbiting`. Separado de `_damageable` de propósito: quem
        # decide o que o tiro FAZ é o roteamento de dano do boss; quem decide se
        # o tiro CHEGA é a área de colisão. Fundir os dois foi o que deixou as
        # Vozes em órbita atravessáveis.
        self.shielding: bool = False
        # Espelho do estado que o CORPO já assumiu. O portão é a fonte de
        # verdade; isto é só o "onde eu já estou", para o boss saber o que ainda
        # precisa aplicar. Sem ele, a transição REMAT→SOLID não tem borda
        # detectável (a brasa também é atacável, então nenhum flag de corpo muda).
        self.body_state: HeadState = HeadState.SOLID

    # ── Estados empurrados pelo boss (que os lê do portão) ───────────────────
    def enter_down(self) -> None:
        """Soquete vazio: não desenha, não recebe dano."""
        self.hp = 0.0
        self._visible = False
        self._damageable = False
        self.shielding = False
        self._alpha_scale = 0.0
        self.attacking = False
        self.body_state = HeadState.DOWN

    def enter_remat(self) -> None:
        """Brasa: visível, frágil e já atacável — é o alvo da supressão."""
        self.hp = max(1.0, self.max_hp * self.EMBER_HP_FRACTION)
        self._visible = True
        self._damageable = True
        self.shielding = False
        self.attacking = False
        self._alpha_scale = 0.25
        self.body_state = HeadState.REMAT

    def restore(self, hp_fraction: float) -> None:
        """Volta a ser sólida, com a fração de HP que o portão determinou."""
        self.hp = max(1.0, self.max_hp * hp_fraction)
        self._visible = True
        self._damageable = True
        self.shielding = False
        self._alpha_scale = 1.0
        self.body_state = HeadState.SOLID

    def enter_orbiting(self) -> None:
        """Fase 3: vira ESCUDO — para o tiro do jogador, mas não recebe dano.

        O portão caiu: as Vozes pararam de proteger a Coroa por REGRA (enquanto
        sólidas, a Coroa era intangível) e passaram a protegê-la por PRESENÇA —
        elas orbitam na frente do alvo e o tiro morre nelas. A pergunta da fase
        deixa de ser "consigo abrir a janela?" e vira "consigo acertar o núcleo
        com duas cabeças girando na frente?".

        `_damageable` fica falso e `shielding` verdadeiro, e a distinção é o
        ponto todo: **atacável** decide o que o tiro faz ao chegar, **escudo**
        decide se ele chega. Enquanto o escudo não existia, as duas coisas eram
        o mesmo flag, e a única forma de a Voz não tomar dano era o projétil
        atravessá-la — ela orbitava ameaçadoramente sem nenhuma consequência.

        Voltar a torná-las atacáveis está fora de questão: reabriria o ciclo de
        ressonância que a fase existe para ENCERRAR.
        """
        self.hp = float(self.max_hp)
        self._visible = True
        self._damageable = False
        self.shielding = True
        self._alpha_scale = 1.0
        self.body_state = HeadState.SOLID

    def place(self, world_x: float, world_y: float, boss_x: float, boss_y: float) -> None:
        """Põe a ÂNCORA da cabeça num ponto do mundo, convertendo para offset.

        A coreografia da Sentença raciocina em coordenadas de tela ("esta cabeça
        vai para a borda esquerda"); o estado da cabeça é offset relativo ao boss,
        que continua se movendo por baixo. A conversão mora aqui para o roteiro
        não ter que conhecer o (x, y) do boss.
        """
        self.offset_x = world_x - boss_x
        self.offset_y = world_y - boss_y

    def rest_pose(self) -> None:
        """Volta ao blit de repouso — sem giro, ancorado na tela compartilhada."""
        self.aim = None

    # ── Consultas ────────────────────────────────────────────────────────────
    @property
    def damageable(self) -> bool:
        return self._damageable

    @property
    def at_home(self) -> bool:
        """A cabeça está no soquete da arte?

        Quem pergunta é a COLISÃO do boss: a máscara combinada das partes é uma
        união em offset (0, 0), válida só enquanto cada peça está onde a arte a
        desenhou. Fora de casa (Sentença, órbita da Fase 3) a máscara mentiria.
        O limiar é de um pixel — a volta é por aproximação e não termina em
        igualdade exata de float.
        """
        return (
            abs(self.offset_x - self.home_offset_x) < 1.0
            and abs(self.offset_y - self.home_offset_y) < 1.0
        )

    @property
    def hp_ratio(self) -> float:
        return max(0.0, min(1.0, self.hp / self.max_hp))

    def collision_circle(self) -> tuple[float, float, float]:
        return self.center_x, self.center_y, self.radius

    @property
    def blocks_shots(self) -> bool:
        """A cabeça PARA o tiro? Atacável ou em escudo — nos dois casos, sim.

        É a pergunta da COLISÃO, e ela não é a mesma de `damageable`, que é a
        pergunta do DANO. Uma Voz em órbita responde True aqui e False lá.

        Uma cabeça que está dissolvendo (ou dissolvida) responde NÃO em qualquer
        estado: ela não está em cena. Enquanto o véu não fecha, o tiro pararia
        num fantasma translúcido.
        """
        if self.fade < 1.0:
            return False
        return self._damageable or self.shielding

    def current_mask(self) -> "pygame.mask.Mask | None":
        """Máscara do frame que está na tela, ou None se o tiro atravessa.

        É a área de COLISÃO da Voz: só os pixels desenhados do PNG. Uma cabeça
        no DOWN devolve None e some da máscara combinada do boss — tiro naquele
        soquete atravessa, que é o comportamento certo. Uma cabeça em escudo
        devolve a máscara: o tiro para nela, e é o `on_hit` do boss que decide
        que ele não fere.
        """
        if not self.blocks_shots:
            return None
        return self._sprites.mask(self._frame_index, self.attacking)

    def contact_rect(self) -> pygame.Rect:
        """Rect para o pré-filtro AABB; a validação fina é o círculo acima."""
        r = int(self.radius)
        return pygame.Rect(int(self.center_x - r), int(self.center_y - r), r * 2, r * 2)

    # ── Dano ─────────────────────────────────────────────────────────────────
    def flash(self) -> None:
        """Pisca sem receber dano — o impacto absorvido pelo ESCUDO.

        O flash é o mesmo do dano de propósito: o jogador precisa ver QUE
        acertou. O que muda é o resto (nenhum HP sai, nenhum som de dano toca) e
        o "MISS" que o boss desenha por cima, que é quem diz que não contou.
        """
        self._hit_flash = self._HIT_FLASH_TIME

    def take_damage(self, amount: float) -> bool:
        """Aplica dano. Devolve True se ESTE hit derrubou a cabeça.

        Não decide o que a queda significa — se foi morte de cabeça sólida ou
        supressão de brasa é leitura do portão, que conhece o estado. Aqui só
        se sabe que o HP acabou.
        """
        if not self._damageable or amount <= 0:
            return False
        self.hp -= amount
        self._hit_flash = self._HIT_FLASH_TIME
        if self.hp <= 0.0:
            self.hp = 0.0
            return True
        return False

    # ── Tick e render ────────────────────────────────────────────────────────
    def update(
        self,
        dt: float,
        boss_x: float,
        boss_y: float,
        remat_progress: float,
        frame_index: int,
    ) -> None:
        self.center_x = boss_x + self.offset_x
        self.center_y = boss_y + self.offset_y
        self._frame_index = frame_index
        self._hit_flash = max(0.0, self._hit_flash - dt)
        if self.body_state is HeadState.REMAT:
            # Brasa montando: o alpha É a barra de progresso da remontagem, e é
            # o único aviso que o jogador tem de que o portão está fechando.
            # Piso em 0.25 para a brasa nunca ser invisível enquanto é atacável.
            self._alpha_scale = 0.25 + 0.75 * remat_progress

    def draw(self, surface: pygame.Surface, origin: tuple[int, int]) -> None:
        """Blita o frame na origem compartilhada MAIS o quanto a cabeça se moveu.

        As três partes compartilham a tela de 64×64 da arte (ver
        `triad_pixel_map`), então em repouso a composição é a origem crua e o
        boss se monta sozinho. Quando a cabeça SAI de casa — a Sentença a manda
        para a borda da arena — o sprite tem que ir junto: a posição dela na
        tela compartilhada é fixa na arte, e só este deslocamento a move.
        """
        if not self._visible or self.fade <= 0.01:
            return
        white = self._hit_flash > 0.0
        if self.aim is not None:
            self._draw_aimed(surface, white)
            return
        frame = self._sprites.frame(self._frame_index, self.attacking, white=white)
        if frame is None:
            return
        origin = (
            origin[0] + int(self.offset_x - self.home_offset_x),
            origin[1] + int(self.offset_y - self.home_offset_y),
        )
        alpha = self._alpha_scale * self.fade
        if alpha >= 1.0:
            surface.blit(frame, origin)
            return
        # `set_alpha` na surface COMPARTILHADA do cache contaminaria as outras
        # instâncias e os frames seguintes; a cópia é paga só enquanto a brasa
        # remonta (3s por ciclo) ou enquanto o véu da Sentença abre e fecha,
        # nunca no estado estável.
        faded = frame.copy()
        faded.set_alpha(int(255 * max(0.0, min(1.0, alpha))))
        surface.blit(faded, origin)

    def _draw_aimed(self, surface: pygame.Surface, white: bool) -> None:
        """Pose de MIRA: sprite girado, ancorado no DESENHO e não na imagem.

        O caminho de repouso blita a tela de 64×64 inteira e deixa o boss se
        montar sozinho — não serve girada, porque o giro é em torno do centro da
        IMAGEM e o desenho ocupa um canto dela: a cabeça descreveria um arco em
        volta de um pivô vazio. Aqui o `aimed_part` devolve o recorte já girado
        mais o offset que mantém a âncora (um pixel real do rosto) parada.
        """
        posed = pmap.aimed_part(self.part_key, self.aim or 0.0, attacking=True)
        if posed is None:
            return
        sprite, ox, oy = posed
        if white:
            sprite = sprite.copy()
            sprite.fill((255, 255, 255), special_flags=pygame.BLEND_RGB_ADD)
        pos = (int(self.center_x + ox), int(self.center_y + oy))
        alpha = self._alpha_scale * self.fade
        if alpha >= 1.0:
            surface.blit(sprite, pos)
            return
        faded = sprite.copy()
        faded.set_alpha(int(255 * max(0.0, min(1.0, alpha))))
        surface.blit(faded, pos)
