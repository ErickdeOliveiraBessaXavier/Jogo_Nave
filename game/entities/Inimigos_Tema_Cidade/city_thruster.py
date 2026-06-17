"""Propulsor energético (azul/ciano) — reusável pelo Metropolis Overlord.

Mesma linguagem do propulsor do `ElementalRobot`/`StoneGolemBoss`: ANÉIS de energia
que nascem na base, DESCEM e ENCOLHEM enquanto desbotam, mais um pequeno flare na
saída. A INTENSIDADE (escala com a velocidade) modula o brilho/alcance dos anéis;
nada exagerado. Usado na entrada dramática do boss (mais intenso no arranque final)
e herdado pelos segmentos da Fase 3 em escala menor (`scale`).

Contrato: `update(dt, ex, ey, intensity)` só avança o relógio (efeito é função do
tempo, sem estado por-partícula); `draw(surface, ex, ey, intensity)` só desenha (§3).
O dono fornece o ponto de emissão (base) a cada frame — o propulsor acompanha o
movimento. Surfaces dos anéis são pré-alocadas (reuso; sem alocar por frame, §7).
"""

from __future__ import annotations

import math

import pygame


class EnergyThruster:
    """Anéis de energia descendo da base do dono (jato azul/ciano)."""

    RINGS = 5
    SPEED = 2.0  # ciclos/s da descida dos anéis
    # Paleta perto → longe: ciano claro (saída) → azul → azul-escuro (cauda).
    _COLORS = ((160, 240, 255), (60, 160, 255), (28, 90, 200))

    def __init__(self, scale: float = 1.0) -> None:
        self.scale = scale
        self._t = 0.0
        # Unidade base do efeito (≈ o "S" do ElementalRobot, proporcional à escala).
        self._u = max(2, int(6 * scale))
        u = self._u
        # Uma surface por anel, reaproveitada a cada frame (largura máx = u*10).
        self._ring_surfs = [
            pygame.Surface((u * 10 + 2, u * 4 + 2), pygame.SRCALPHA)
            for _ in range(self.RINGS)
        ]

    def update(self, dt: float, _ex: float, _ey: float, _intensity: float) -> None:
        if dt > 0.0:
            self._t += dt

    def draw(self, surface: pygame.Surface, ex: float, ey: float, intensity: float) -> None:
        if intensity <= 0.02:
            return
        u = self._u
        cx = int(ex)
        start_y = int(ey)
        t = self._t
        pulse = 0.85 + 0.15 * math.sin(t * 14.0)  # pulsação sutil
        bright = min(1.0, intensity) * pulse       # brilho geral pela velocidade
        # Drop um pouco maior em alta intensidade (jato "esticando" no arranque).
        max_drop = int(u * 14 * (0.85 + 0.3 * min(1.0, intensity)))

        # Pequeno flare fixo na saída.
        bw = max(2, int(u * 2 * pulse))
        fc = self._COLORS[0]
        surface.fill(fc, (cx - bw // 2, start_y, bw, max(1, int(u * pulse))))

        for i in range(self.RINGS):
            phase = ((t * self.SPEED) + i / self.RINGS) % 1.0
            w = int(u * 10 * (1.0 - phase))
            if w < u:
                continue
            h = max(u, int(u * 4 * (1.0 - phase)))
            y = start_y + int(phase * max_drop) + u
            alpha = int(235 * (1.0 - phase * phase) * bright)
            if alpha <= 0:
                continue
            if phase < 0.18:
                cr, cg, cb = self._COLORS[0]
            elif phase < 0.55:
                cr, cg, cb = self._COLORS[1]
            else:
                cr, cg, cb = self._COLORS[2]
            rs = self._ring_surfs[i]
            rs.fill((0, 0, 0, 0))
            pygame.draw.rect(rs, (cr, cg, cb, alpha), (0, 0, w, h), max(1, u // 2))
            surface.blit(rs, (cx - w // 2, y - h // 2))
