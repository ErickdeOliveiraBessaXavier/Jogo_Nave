"""Base e utilitários compartilhados dos backgrounds de mundo."""

from abc import ABC, abstractmethod

import pygame

from ...core.config import config as Config


def optimize_surface(surf: pygame.Surface) -> pygame.Surface:
    """Aplica convert() para alinhar formato com o display (blits ~2-3x mais rápidos).
    Faz fallback silencioso se o display ainda não estiver pronto."""
    try:
        return surf.convert()
    except pygame.error:
        return surf


def optimize_alpha_surface(surf: pygame.Surface) -> pygame.Surface:
    """Aplica convert_alpha() para alinhar formato RGBA com o display.
    Faz fallback silencioso se o display ainda não estiver pronto."""
    try:
        return surf.convert_alpha()
    except pygame.error:
        return surf


class Background(ABC):
    """Classe base para backgrounds de mundos."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        # Razão entre a altura de construção e a altura lógica da tela: 1.0 em
        # resolução cheia, 0.5 com "Fundo retrô" (meia-res + upscale no blit).
        # Dimensões e velocidades escritas em pixels de 720p precisam passar por
        # `s()`/`sf()` para manter a mesma leitura na tela final — sem isso o
        # conteúdo aparece com o dobro do tamanho e o dobro da velocidade.
        self.res_scale: float = height / max(1, Config.SCREEN_HEIGHT)

    def s(self, value: float) -> int:
        """Escala um valor de pixel do design (720p) para a resolução de
        construção, com mínimo de 1px (evita sumir em meia-res)."""
        return max(1, int(round(value * self.res_scale)))

    def sf(self, value: float) -> float:
        """Como `s()`, mas sem arredondar — para velocidades e acumuladores."""
        return value * self.res_scale

    @abstractmethod
    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        """Atualiza animação do background."""
        raise NotImplementedError

    @abstractmethod
    def draw(self, surface: pygame.Surface) -> None:
        """Desenha o background."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Reseta para estado inicial."""
        raise NotImplementedError

    def set_progress(self, _progress: float) -> None:
        """Hook opcional: progresso 0..1 (usado pela atmosfera). No-op por padrão."""
        return None

    def set_allow_spawning(self, _allow: bool) -> None:
        """Hook opcional: liga/desliga spawn de elementos (corpos celestes do
        starfield). No-op por padrão."""
        return None

    def set_day_night_paused(self, _paused: bool) -> None:
        """Hook opcional: congela/retoma o ciclo dia/noite. No-op por padrão.

        Contrato de **estado derivado**, como `set_progress`/`set_allow_spawning`:
        o `Renderer.background()` reaplica o valor a cada frame a partir da
        condição que o justifica (o tempo do fundo estar em warp). Não é um
        par ligar/desligar por evento — quem quiser pausar deve fazer a
        condição valer, nunca chamar isto uma vez e confiar na borda de
        desligamento. O `Background` sobrevive à cena que o usa, então uma
        borda perdida congela o ciclo para o resto da sessão.
        """
        return None
