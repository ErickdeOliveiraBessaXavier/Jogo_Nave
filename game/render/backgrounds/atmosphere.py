"""Background de Atmosfera: entrada/saída de planeta, nuvens e streaks."""

import random
from typing import List, Optional, Tuple

import pygame

from ...core.assets import BASE_DIR, get_image
from .base import Background, optimize_alpha_surface, optimize_surface


class VerticalCloud:
    """Nuvem que se move verticalmente para a fase de atmosfera."""

    def __init__(
        self,
        width: int,
        height: int,
        speed_range: Tuple[float, float],
        color: Tuple[int, int, int],
        is_entering: bool,
    ):
        self.screen_width = width
        self.screen_height = height
        self.speed_range = speed_range
        self.color = color
        self.is_entering = is_entering

        # Surface inicial
        self.scaled_surface = pygame.Surface((1, 1), pygame.SRCALPHA)
        # Último alpha aplicado à scaled_surface — evita set_alpha redundante
        # quando o alpha não muda entre frames (set_alpha dispara reformat).
        self._last_alpha: int = 255
        self.reset(is_first_time=True)

    def _generate_cloud_surface(self) -> pygame.Surface:
        w, h = random.randint(150, 350), random.randint(80, 180)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        # Desenha várias elipses sobrepostas para dar volume
        for _ in range(5):
            ew = random.randint(w // 2, w)
            eh = random.randint(h // 2, h)
            ex = random.randint(0, w - ew)
            ey = random.randint(0, h - eh)
            alpha = random.randint(40, 100)
            pygame.draw.ellipse(surf, (*self.color, alpha), (ex, ey, ew, eh))
        return optimize_alpha_surface(surf)

    def reset(self, is_first_time: bool = False) -> None:
        # Regenera a superfície para cada reset para maior variedade visual
        base_surface = self._generate_cloud_surface()

        scale = random.uniform(0.6, 1.4)
        self.scaled_surface = pygame.transform.smoothscale(
            base_surface,
            (
                int(base_surface.get_width() * scale),
                int(base_surface.get_height() * scale),
            ),
        )
        # Nova surface começa com alpha implícito 255 — ressincroniza o tracker
        # para que o próximo set_alpha em draw() execute sem ser pulado.
        self._last_alpha = 255

        self.x = random.uniform(-50, self.screen_width - 100)

        # Para um efeito orgânico de "entrar" na camada de nuvens,
        # as nuvens SEMPRE começam fora da tela e entram nela.
        # Usamos um range maior no primeiro spawn para elas não entrarem todas juntas.
        stagger = random.randint(20, 800) if is_first_time else random.randint(20, 150)

        if self.is_entering:  # Sobe (spawn embaixo)
            self.y = self.screen_height + stagger
        else:  # Desce (spawn em cima)
            self.y = -self.scaled_surface.get_height() - stagger

        self.speed = random.uniform(self.speed_range[0], self.speed_range[1])

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        # Direção: -1 se entering (sobe), 1 se exiting (desce)
        direction = -1.0 if self.is_entering else 1.0
        self.y += direction * self.speed * dt * speed_mult

        if self.is_entering:
            if self.y < -self.scaled_surface.get_height():
                self.reset()
        else:
            if self.y > self.screen_height:
                self.reset()

    def draw(self, surface: pygame.Surface, alpha_mult: float = 1.0) -> None:
        if alpha_mult <= 0:
            return

        # Calcula um fade local para evitar "pop" nas bordas de spawn
        # Quando está perto da borda de spawn, o alpha diminui
        edge_fade = 1.0
        fade_margin = 100.0

        if self.is_entering:  # Sobe (spawn em screen_height)
            dist_to_spawn = self.screen_height - self.y
            if dist_to_spawn < fade_margin:
                edge_fade = max(0.0, dist_to_spawn / fade_margin)
        else:  # Desce (spawn em -height)
            cloud_h = self.scaled_surface.get_height()
            dist_to_spawn = self.y + cloud_h
            if dist_to_spawn < fade_margin:
                edge_fade = max(0.0, dist_to_spawn / fade_margin)

        final_alpha = int(255 * alpha_mult * edge_fade)
        if final_alpha <= 0:
            return

        # set_alpha dispara reformat interno do SDL — só atualiza quando o
        # valor mudou. Cada instância tem sua própria scaled_surface, então
        # não há conflito com outras nuvens (sem necessidade de reset).
        if final_alpha != self._last_alpha:
            self.scaled_surface.set_alpha(final_alpha)
            self._last_alpha = final_alpha
        surface.blit(self.scaled_surface, (int(self.x), int(self.y)))


class AtmosphereStreak:
    """Riscos que simulam o vento vertical durante entrada/re-entrada."""

    def __init__(self, width: int, height: int, is_entering: bool):
        self.width = width
        self.height = height
        self.is_entering = is_entering
        self.x = 0.0
        self.y = 0.0
        self.speed = 0.0
        self.length = 0.0
        self.alpha = 0
        self.reset(is_first_time=True)

    def reset(self, is_first_time: bool = False) -> None:
        self.x = random.uniform(0, self.width)
        self.length = random.uniform(60, 180)
        self.speed = random.uniform(1400, 2200)
        self.alpha = random.randint(40, 110)

        # Para um efeito orgânico, sempre começa fora da tela.
        # Stagger inicial para não entrarem todos em uma linha só.
        stagger = random.uniform(20, 1200) if is_first_time else random.uniform(20, 150)

        if self.is_entering:  # Sobe (spawn embaixo)
            self.y = self.height + stagger
        else:  # Desce (spawn em cima)
            self.y = -self.length - stagger

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        direction = -1.0 if self.is_entering else 1.0
        self.y += direction * self.speed * dt * speed_mult

        if self.is_entering:
            # Margem maior para o reset quando esticado
            if self.y + self.length < -400:
                self.reset()
        else:
            if self.y > self.height + 400:
                self.reset()

    def draw(
        self,
        surface: pygame.Surface,
        global_alpha: float = 1.0,
        speed_mult: float = 1.0,
    ) -> None:
        alpha = int(self.alpha * global_alpha)
        if alpha <= 0:
            return

        # Estica o rastro proporcionalmente à velocidade
        # Para speed_mult=30x, o rastro fica bem longo para dar sensação de warp
        stretch_factor = 1.0 + (speed_mult - 1.0) * 0.4
        draw_length = self.length * stretch_factor

        # Desenha o rastro como uma linha vertical branca com alpha
        # Se is_entering (sobe), o rastro "estica" para baixo a partir de y
        if self.is_entering:
            start_pos = (int(self.x), int(self.y + draw_length))
            end_pos = (int(self.x), int(self.y))
        else:
            start_pos = (int(self.x), int(self.y))
            end_pos = (int(self.x), int(self.y + draw_length))

        # Linha principal
        pygame.draw.line(surface, (255, 255, 255, alpha), start_pos, end_pos, 1)


class AtmosphereBackground(Background):
    """Background para transição de atmosfera com transição de cor e nuvens."""

    # Planeta no rodapé: só translação vertical conforme a proximidade da
    # atmosfera. Perto (re-entry/ENTRANDO) ele sobe; longe (saída/ascensão ao
    # espaço) ele desce e some. Sem rotação nem escala.
    PLANET_CENTER_NEAR_OFFSET: float = (
        420.0  # px abaixo da base quando perto (0 = metade fora)
    )
    PLANET_TRAVEL: float = 240.0  # px que o planeta desce do perto até o longe

    def __init__(self, width: int, height: int, route: str = "exiting"):
        super().__init__(width, height)
        self.route = route
        self.is_entering = route == "entering"
        self.progress: float = 0.0
        self.last_speed_mult: float = 1.0

        # Cores: [Space (Dark)] <-> [Sky (Cyan/Blue)]
        # Exiting: progress 0 (Sky) -> progress 1 (Space)
        # Entering: progress 0 (Space) -> progress 1 (Sky)
        self.color_space_top = (5, 8, 15)
        self.color_space_bottom = (15, 25, 45)
        self.color_sky_top = (30, 100, 180)
        self.color_sky_bottom = (120, 200, 255)

        # Cache do gradiente fullscreen: recompõe só quando alguma componente
        # RGB inteira de c_top ou c_bottom mudar. Em transição típica de
        # progresso, isso acontece a cada ~10-50 frames — o resto reutiliza.
        # Sem cache, o método anterior fazia smoothscale 1×2 → fullscreen +
        # blit SRCALPHA per frame, dominando o frame time desse background.
        self._gradient_cache: Optional[pygame.Surface] = None
        self._gradient_cache_key: Optional[
            Tuple[Tuple[int, int, int], Tuple[int, int, int]]
        ] = None
        # Último alpha aplicado ao planeta — evita set_alpha redundante por frame
        self._planet_last_alpha: int = -1

        self.clouds: List[VerticalCloud] = []
        for _ in range(12):
            self.clouds.append(
                VerticalCloud(
                    width, height, (100, 250), (220, 230, 255), self.is_entering
                )
            )

        self.streaks: List[AtmosphereStreak] = []
        for _ in range(25):
            self.streaks.append(AtmosphereStreak(width, height, self.is_entering))

        # Planeta no rodapé. Carregado e escalado para a largura da tela uma
        # única vez (proporção mantida); a cada frame só é reposicionado na
        # vertical, sem transformação — blit direto, custo ~zero.
        planet_path = BASE_DIR / "assets" / "images" / "Imagem.png"
        planet_raw = get_image(planet_path, alpha=True)
        raw_w, raw_h = planet_raw.get_size()
        if raw_w > 0 and raw_h > 0:
            scaled_h = max(1, int(raw_h * width / raw_w))
            self.planet_base: pygame.Surface = pygame.transform.smoothscale(
                planet_raw, (width, scaled_h)
            )
        else:
            self.planet_base = planet_raw
        # Pré-cálculo de posicionamento (base ocupa a largura toda → x = 0).
        self._planet_x: int = (width - self.planet_base.get_width()) // 2
        self._planet_half_h: float = self.planet_base.get_height() / 2.0

    def set_progress(self, progress: float) -> None:
        self.progress = max(0.0, min(1.0, progress))

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        self.last_speed_mult = speed_mult
        # A densidade de nuvens e velocidade pode mudar com o progresso
        # mas por ora mantemos fixo para fluidez.
        for cloud in self.clouds:
            cloud.update(dt, speed_mult)

        for streak in self.streaks:
            streak.update(dt, speed_mult)

    def draw(self, surface: pygame.Surface) -> None:
        # Calcula cores atuais baseadas no progresso e rota
        # Exiting: p=0 (Atmo), p=1 (Space) -> t = progress
        # Entering: p=0 (Space), p=1 (Atmo) -> t = 1 - progress
        t = self.progress if self.route == "exiting" else 1.0 - self.progress

        c_top: tuple[int, int, int] = (
            int(self.color_sky_top[0] * (1 - t) + self.color_space_top[0] * t),
            int(self.color_sky_top[1] * (1 - t) + self.color_space_top[1] * t),
            int(self.color_sky_top[2] * (1 - t) + self.color_space_top[2] * t),
        )
        c_bottom: tuple[int, int, int] = (
            int(self.color_sky_bottom[0] * (1 - t) + self.color_space_bottom[0] * t),
            int(self.color_sky_bottom[1] * (1 - t) + self.color_space_bottom[1] * t),
            int(self.color_sky_bottom[2] * (1 - t) + self.color_space_bottom[2] * t),
        )

        # Desenha gradiente de fundo
        self._draw_gradient(surface, c_top, c_bottom)

        # Intensidade do efeito de vento/nuvens baseada na proximidade com a atmosfera
        # t=0 (Atmosphere), t=1 (Space)
        effect_intensity = 1.0 - (t * 0.8)

        # Planeta no rodapé (atrás das nuvens/vento). `t` codifica a proximidade
        # independente da rota (t=0 atmosfera/perto, t=1 espaço/longe). Como
        # `proximity = 1 - t`, o planeta sobe ao se aproximar (re-entry: t→0) e
        # desce ao se afastar (saída ao espaço: t→1), esmaecendo. Só translação
        # vertical — o centro repousa na base da tela (metade fora) quando perto.
        planet_alpha = max(0, min(255, int(255 * effect_intensity)))
        if planet_alpha > 0:
            proximity = 1.0 - t
            # set_alpha dispara reformat interno do SDL — evita chamar quando
            # o valor não mudou desde o frame anterior.
            if planet_alpha != self._planet_last_alpha:
                self.planet_base.set_alpha(planet_alpha)
                self._planet_last_alpha = planet_alpha
            center_y = (
                self.height
                + self.PLANET_CENTER_NEAR_OFFSET
                + self.PLANET_TRAVEL * (1.0 - proximity)
            )
            surface.blit(
                self.planet_base,
                (self._planet_x, int(center_y - self._planet_half_h)),
            )

        # Desenha nuvens (alpha/densidade proporcional à proximidade com a atmosfera)
        cloud_alpha_base = effect_intensity
        for i, cloud in enumerate(self.clouds):
            # Algumas nuvens somem primeiro
            individual_alpha = max(0.0, cloud_alpha_base - (i % 4) * 0.15)
            if individual_alpha > 0:
                cloud.draw(surface, individual_alpha)

        # Desenha riscos de vento
        streak_global_alpha = effect_intensity
        for streak in self.streaks:
            streak.draw(surface, streak_global_alpha, self.last_speed_mult)

    def _draw_gradient(
        self,
        surface: pygame.Surface,
        top: tuple[int, int, int],
        bottom: tuple[int, int, int],
    ) -> None:
        """Desenha gradiente vertical com cache de surface fullscreen.

        A composição (1×2 SRCALPHA + smoothscale para fullscreen + blit) é
        executada apenas quando as cores discretizadas mudam. O resto dos
        frames faz 1 blit fullscreen opaco direto do cache.
        """
        key = (top, bottom)
        if self._gradient_cache_key != key or self._gradient_cache is None:
            grad = pygame.Surface((1, 2), pygame.SRCALPHA)
            grad.set_at((0, 0), top)
            grad.set_at((0, 1), bottom)
            scaled = pygame.transform.smoothscale(grad, (self.width, self.height))
            # Achata em surface opaca — blit fullscreen ~2x mais rápido.
            opaque = pygame.Surface((self.width, self.height))
            opaque.blit(scaled, (0, 0))
            self._gradient_cache = optimize_surface(opaque)
            self._gradient_cache_key = key
        surface.blit(self._gradient_cache, (0, 0))

    def reset(self) -> None:
        self.progress = 0.0
        self.last_speed_mult = 1.0
        for cloud in self.clouds:
            cloud.reset(is_first_time=True)
        for streak in self.streaks:
            streak.reset(is_first_time=True)


# Factory function para facilitar criação
