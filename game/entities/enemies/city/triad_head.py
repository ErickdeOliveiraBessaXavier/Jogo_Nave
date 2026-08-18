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
    _ANIM_FPS: float = 6.0

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
        self.radius = radius

        self.center_x: float = 0.0
        self.center_y: float = 0.0

        # Laranja = "esta cabeça vai agir agora". Ninguém liga isso ainda; o
        # contrato existe desde já para os ataques só terem que setar o flag.
        self.attacking: bool = False

        self._sprites = pmap.load_part(part_key)
        self._anim_time: float = 0.0
        self._hit_flash: float = 0.0
        # 1.0 = sólida e opaca; abaixo disso é brasa remontando.
        self._alpha_scale: float = 1.0
        self._visible: bool = True
        self._damageable: bool = True
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
        self._alpha_scale = 0.0
        self.attacking = False
        self.body_state = HeadState.DOWN

    def enter_remat(self) -> None:
        """Brasa: visível, frágil e já atacável — é o alvo da supressão."""
        self.hp = max(1.0, self.max_hp * self.EMBER_HP_FRACTION)
        self._visible = True
        self._damageable = True
        self.attacking = False
        self._alpha_scale = 0.25
        self.body_state = HeadState.REMAT

    def restore(self, hp_fraction: float) -> None:
        """Volta a ser sólida, com a fração de HP que o portão determinou."""
        self.hp = max(1.0, self.max_hp * hp_fraction)
        self._visible = True
        self._damageable = True
        self._alpha_scale = 1.0
        self.body_state = HeadState.SOLID

    # ── Consultas ────────────────────────────────────────────────────────────
    @property
    def damageable(self) -> bool:
        return self._damageable

    @property
    def hp_ratio(self) -> float:
        return max(0.0, min(1.0, self.hp / self.max_hp))

    def collision_circle(self) -> tuple[float, float, float]:
        return self.center_x, self.center_y, self.radius

    def contact_rect(self) -> pygame.Rect:
        """Rect para o pré-filtro AABB; a validação fina é o círculo acima."""
        r = int(self.radius)
        return pygame.Rect(int(self.center_x - r), int(self.center_y - r), r * 2, r * 2)

    # ── Dano ─────────────────────────────────────────────────────────────────
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
        self, dt: float, boss_x: float, boss_y: float, remat_progress: float
    ) -> None:
        self.center_x = boss_x + self.offset_x
        self.center_y = boss_y + self.offset_y
        self._anim_time += dt
        self._hit_flash = max(0.0, self._hit_flash - dt)
        if self.body_state is HeadState.REMAT:
            # Brasa montando: o alpha É a barra de progresso da remontagem, e é
            # o único aviso que o jogador tem de que o portão está fechando.
            # Piso em 0.25 para a brasa nunca ser invisível enquanto é atacável.
            self._alpha_scale = 0.25 + 0.75 * remat_progress

    def draw(self, surface: pygame.Surface, origin: tuple[int, int]) -> None:
        """Blita o frame no MESMO ponto de origem das outras partes.

        As três partes compartilham a tela de 64×64 da arte (ver
        `triad_pixel_map`), então nenhuma composição manual é necessária: mesma
        origem, e o boss se monta sozinho.
        """
        if not self._visible:
            return
        white = self._hit_flash > 0.0
        index = int(self._anim_time * self._ANIM_FPS)
        frame = self._sprites.frame(index, self.attacking, white=white)
        if frame is None:
            return
        if self._alpha_scale >= 1.0:
            surface.blit(frame, origin)
            return
        # `set_alpha` na surface COMPARTILHADA do cache contaminaria as outras
        # instâncias e os frames seguintes; a cópia é paga só enquanto a brasa
        # remonta (3s por ciclo), nunca no estado estável.
        faded = frame.copy()
        faded.set_alpha(int(255 * max(0.0, min(1.0, self._alpha_scale))))
        surface.blit(faded, origin)
