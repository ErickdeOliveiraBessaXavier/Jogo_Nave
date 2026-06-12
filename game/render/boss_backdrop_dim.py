"""Escurecimento de fundo durante lutas de boss — padrão genérico p/ todos.

Quando um boss está ativo, o **fundo** (background) recebe um overlay escuro
permanente até o boss morrer, fazendo o boss e o gameplay "saltarem" da cena.
É desenhado logo após o background e **antes** das entidades, então apenas o
fundo escurece — nave, inimigos, projéteis e o próprio boss continuam em brilho
cheio (não prejudica a leitura do combate).

O escurecimento entra e sai por fade (sem pop ao spawnar/morrer o boss). Durante
a cutscene de entrada do Cloud Archmage o alvo é 0 — a intro já tem o próprio
escurecimento de tela cheia (`get_intro_dim_alpha`), evitando dobra.

Contratos (CLAUDE.md): a cena chama `update()` (mutação); `draw()` só lê e
desenha (§3). A surface é opaca e cacheada por tamanho; o alpha é global via
`set_alpha` (blit rápido, sem per-pixel) e sem alocação por frame (§7).
"""

from __future__ import annotations

from typing import Tuple

import pygame


class BossBackdropDim:
    DIM_MAX = 140       # alpha do escurecimento (0-255). Ajuste fino de intensidade.
    FADE_IN = 0.8       # s para escurecer ao iniciar a luta
    FADE_OUT = 0.6      # s para clarear ao boss morrer
    COLOR: Tuple[int, int, int] = (0, 0, 0)

    def __init__(self) -> None:
        self._alpha = 0.0
        self._size: Tuple[int, int] = (0, 0)
        self._surf: pygame.Surface | None = None

    def update(self, dt: float, boss_active: bool) -> None:
        target = float(self.DIM_MAX) if boss_active else 0.0
        if self._alpha < target:
            self._alpha = min(target, self._alpha + (self.DIM_MAX / self.FADE_IN) * dt)
        elif self._alpha > target:
            self._alpha = max(target, self._alpha - (self.DIM_MAX / self.FADE_OUT) * dt)

    def draw(self, surface: pygame.Surface) -> None:
        a = int(self._alpha)
        if a <= 0:
            return
        self._ensure(surface.get_size())
        assert self._surf is not None
        self._surf.set_alpha(a)
        surface.blit(self._surf, (0, 0))

    def _ensure(self, size: Tuple[int, int]) -> None:
        if self._surf is not None and self._size == size:
            return
        self._size = size
        # Surface opaca (sem SRCALPHA): set_alpha global rende blit mais barato
        # que per-pixel alpha. `convert()` alinha o formato ao display — sem isso,
        # cada blit paga conversão de formato (ordens de grandeza mais lento).
        surf = pygame.Surface(size)
        surf.fill(self.COLOR)
        try:
            surf = surf.convert()
        except pygame.error:
            pass  # sem display ainda (ex.: testes headless) — segue sem convert
        self._surf = surf
