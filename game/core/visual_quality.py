"""Qualidade Visual — escala global de efeitos para performance.

Política **única** de redução de efeitos cosméticos por nível (Alto/Médio/Baixo).
Não altera gameplay: só mexe em contagem de partículas, glow, trails, fumaça,
luzes, fragmentos, shake secundário, etc. Sempre que possível os efeitos são
**simplificados** (menos partículas, glow mais barato), não removidos — preserva
a identidade visual.

Uso nos sistemas de efeito (one-liner por call site):

    from ..core.visual_quality import visual_quality as vq
    count = vq.particles(40)          # 40 no Alto, ~20 no Médio, ~10 no Baixo
    if vq.glow_enabled: ...           # gate de efeito caro
    if random.random() < vq.frequency(0.5): ...  # frequência de trail/spawn

O estado é um singleton mutável (como `sound_manager`/volumes): é uma preferência
de runtime aplicada no boot a partir de `UserPreferences`, não estado de partida
(§4 trata de estado de jogo, não de settings). O default é Alto.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QualityLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def label(self) -> str:
        return {"high": "Alto", "medium": "Médio", "low": "Baixo"}[self.value]


# Pixelização (pós-processamento do frame inteiro): mapeia a intensidade
# escolhida para o fator de bloco (downscale→upscale nearest). Sempre ativa —
# não há "off"; o piso nativo é "light". Fatores maiores = pixels mais chunky.
# Fatores fracionários (< 2) dão uma pixelização fina/suave, abaixo do menor
# bloco inteiro (2×2). "strong" (2.0) era o antigo "light".
PIXELIZATION_FACTORS: dict[str, float] = {
    "light": 1.3,
    "medium": 1.6,
    "strong": 2.0,
}

# Rótulos exibidos no seletor (mesma ordem do seletor de qualidade).
PIXELIZATION_LEVELS: list[tuple[str, str]] = [
    ("light", "Leve"),
    ("medium", "Médio"),
    ("strong", "Forte"),
]


@dataclass(frozen=True)
class QualityProfile:
    """Multiplicadores e gates de um nível de qualidade.

    Floats escalam contagens/frequências (1.0 = cheio). Bools fazem gate de
    efeitos caros (glow pesado, afterimages, luzes dinâmicas, etc.).
    """

    # Multiplicadores de contagem (cada categoria pedida pelo design)
    particle_scale: float        # partículas em geral / simultâneas
    fragment_scale: float        # fragmentos/detritos gerados
    dust_scale: float            # poeira
    impact_scale: float          # partículas de impacto
    smoke_scale: float           # fumaça
    electric_scale: float        # efeitos elétricos simultâneos (arcos)
    trail_scale: float           # frequência/densidade de trails
    glow_scale: float            # raio/intensidade de glow (quando ligado)
    ambient_scale: float         # efeitos ambientais/decorativos

    # Gates de efeitos caros
    glow_enabled: bool           # glow pesado (halos aditivos grandes)
    afterimages_enabled: bool    # afterimages/rastros persistentes
    dynamic_lights: bool         # luzes dinâmicas
    complex_explosions: bool     # explosões com camadas extras
    ambient_effects: bool        # efeitos ambientais de fundo
    secondary_shake: bool        # shake secundário (não o principal de gameplay)


_PROFILES: dict[QualityLevel, QualityProfile] = {
    # Alto: tudo cheio — referência visual do jogo.
    QualityLevel.HIGH: QualityProfile(
        particle_scale=1.0,
        fragment_scale=1.0,
        dust_scale=1.0,
        impact_scale=1.0,
        smoke_scale=1.0,
        electric_scale=1.0,
        trail_scale=1.0,
        glow_scale=1.0,
        ambient_scale=1.0,
        glow_enabled=True,
        afterimages_enabled=True,
        dynamic_lights=True,
        complex_explosions=True,
        ambient_effects=True,
        secondary_shake=True,
    ),
    # Médio: ~50% das partículas, menos trails/fragmentos, glow simplificado,
    # mas mantém afterimages/luzes em versão reduzida.
    QualityLevel.MEDIUM: QualityProfile(
        particle_scale=0.5,
        fragment_scale=0.5,
        dust_scale=0.5,
        impact_scale=0.6,
        smoke_scale=0.5,
        electric_scale=0.6,
        trail_scale=0.55,
        glow_scale=0.7,
        ambient_scale=0.5,
        glow_enabled=True,
        afterimages_enabled=True,
        dynamic_lights=True,
        complex_explosions=True,
        ambient_effects=True,
        secondary_shake=False,
    ),
    # Baixo: partículas no mínimo, sem afterimages/glow pesado/luzes dinâmicas e
    # menos decoração — versões simplificadas, nunca o efeito sumindo de vez.
    QualityLevel.LOW: QualityProfile(
        particle_scale=0.25,
        fragment_scale=0.3,
        dust_scale=0.2,
        impact_scale=0.35,
        smoke_scale=0.25,
        electric_scale=0.35,
        trail_scale=0.25,
        glow_scale=0.5,
        ambient_scale=0.25,
        glow_enabled=False,
        afterimages_enabled=False,
        dynamic_lights=False,
        complex_explosions=False,
        ambient_effects=False,
        secondary_shake=False,
    ),
}


class VisualQuality:
    """Singleton de qualidade visual: resolve contagens/gates pelo nível atual."""

    def __init__(self) -> None:
        self._level = QualityLevel.HIGH
        self._profile = _PROFILES[QualityLevel.HIGH]
        # Pixelização é ortogonal ao nível de qualidade: efeito estético aplicado
        # no frame final (não escala partículas). Sempre ativa; piso nativo Leve.
        self._pixelization = "light"

    # ── Nível ────────────────────────────────────────────────────────────────
    @property
    def level(self) -> QualityLevel:
        return self._level

    def set_level(self, level: QualityLevel) -> None:
        self._level = level
        self._profile = _PROFILES[level]

    def set_from_name(self, name: str) -> None:
        """Aplica nível por string ('high'/'medium'/'low'); inválido → Alto."""
        try:
            self.set_level(QualityLevel(str(name).lower()))
        except ValueError:
            self.set_level(QualityLevel.HIGH)

    @property
    def name(self) -> str:
        return self._level.value

    # ── Pixelização (pós-processamento) ──────────────────────────────────────
    @property
    def pixelization(self) -> str:
        """Nome da intensidade atual ('off'/'light'/'medium'/'strong')."""
        return self._pixelization

    def set_pixelization(self, name: str) -> None:
        """Aplica a intensidade por string; valor inválido → piso 'light'."""
        key = str(name).lower()
        self._pixelization = key if key in PIXELIZATION_FACTORS else "light"

    @property
    def pixelization_enabled(self) -> bool:
        return self.pixelization_factor > 1.0

    @property
    def pixelization_factor(self) -> float:
        """Fator de bloco (1.0 = desligado; sempre > 1 com os níveis atuais)."""
        return PIXELIZATION_FACTORS.get(self._pixelization, 1.3)

    # ── Escala de contagens (efeito nunca some: piso 1 quando base ≥ 1) ──────
    @staticmethod
    def _count(base: int, scale: float) -> int:
        if base <= 0 or scale <= 0.0:
            return 0
        return max(1, int(round(base * scale)))

    def particles(self, base: int) -> int:
        return self._count(base, self._profile.particle_scale)

    def fragments(self, base: int) -> int:
        return self._count(base, self._profile.fragment_scale)

    def dust(self, base: int) -> int:
        return self._count(base, self._profile.dust_scale)

    def impact(self, base: int) -> int:
        return self._count(base, self._profile.impact_scale)

    def smoke(self, base: int) -> int:
        return self._count(base, self._profile.smoke_scale)

    def electric(self, base: int) -> int:
        return self._count(base, self._profile.electric_scale)

    def ambient(self, base: int) -> int:
        return self._count(base, self._profile.ambient_scale)

    # ── Frequências / escalas contínuas ──────────────────────────────────────
    def frequency(self, base_chance: float) -> float:
        """Escala uma probabilidade de spawn (trails, faíscas) pelo trail_scale."""
        return base_chance * self._profile.trail_scale

    @property
    def trail_scale(self) -> float:
        return self._profile.trail_scale

    @property
    def glow_scale(self) -> float:
        return self._profile.glow_scale

    @property
    def ambient_scale(self) -> float:
        return self._profile.ambient_scale

    # ── Gates ────────────────────────────────────────────────────────────────
    @property
    def glow_enabled(self) -> bool:
        return self._profile.glow_enabled

    @property
    def afterimages_enabled(self) -> bool:
        return self._profile.afterimages_enabled

    @property
    def dynamic_lights(self) -> bool:
        return self._profile.dynamic_lights

    @property
    def complex_explosions(self) -> bool:
        return self._profile.complex_explosions

    @property
    def ambient_effects(self) -> bool:
        return self._profile.ambient_effects

    @property
    def secondary_shake(self) -> bool:
        return self._profile.secondary_shake


# Singleton global (mesmo padrão de `sound_manager`).
visual_quality = VisualQuality()
