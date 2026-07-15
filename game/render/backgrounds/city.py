"""Background de Cidade: skyline cyberpunk noturno em parallax.

Camadas de silhuetas de prédios (fundo claro/lento → frente escura/rápida),
céu noturno com estrelas piscando, nuvens à deriva e neon discreto nas janelas
dos prédios da frente. Paleta escura, pegada neon.
"""

import math
import random
from typing import Any, Dict, List, Tuple

import pygame

from .base import Background, optimize_alpha_surface, optimize_surface


class CityBackground(Background):
    """Cidade cyberpunk noturna com parallax, estrelas, nuvens e neon."""

    NUM_STARS = 70
    NUM_CLOUDS = 5

    # Quanto o conteúdo "engorda" no Fundo Retrô, onde o tema é desenhado em
    # meia-res e ampliado: 0.0 = fiel à resolução cheia, 1.0 = o skyline
    # gigante que a meia-res produzia antes de a escala existir. O meio-termo
    # é estético (pedido: prédios imponentes) e não custa desempenho — a
    # leveza vem do upscale, não do tamanho. Só afeta TAMANHOS: a velocidade
    # do parallax segue fiel via `sf()`. Inócuo em resolução cheia.
    RETRO_CHUNK = 0.40

    # Neon discreto (intencionalmente abaixo de 255 para casar com a paleta escura)
    _NEON_PALETTE: List[Tuple[int, int, int]] = [
        (0, 190, 210),    # ciano
        (200, 40, 170),   # magenta
        (130, 90, 230),   # roxo
        (40, 200, 150),   # verde-água
    ]
    _STAR_COLORS: List[Tuple[int, int, int]] = [
        (255, 255, 255),
        (180, 200, 255),
        (200, 230, 255),
    ]

    def __init__(self, width: int, height: int):
        super().__init__(width, height)
        # Interpola entre a escala fiel à tela e o comportamento antigo (1.0).
        self._content_scale: float = self.res_scale + self.RETRO_CHUNK * (
            1.0 - self.res_scale
        )
        self._toggle_timer: float = 0.0
        self._next_toggle: float = random.uniform(0.5, 1.3)
        self.stars: List[Dict[str, Any]] = []
        self.clouds: List[Dict[str, Any]] = []
        self.layers: List[Dict[str, Any]] = []
        self._cloud_variants: List[pygame.Surface] = []
        self.fog_y: int = 0
        self.moon_pos: Tuple[int, int] = (0, 0)
        self._win_w: int = self.cs(6)
        self._win_h: int = self.cs(9)

        self.sky = self._create_sky()
        self.fog = self._create_fog()
        self.moon = self._create_moon()
        self._create_cloud_variants()
        self._create_stars()
        self._create_clouds()
        self._create_layers()

    def cs(self, value: float) -> int:
        """Como `s()`, mas com a compensação de `RETRO_CHUNK` — para tamanhos
        do skyline. Velocidades continuam em `sf()` (fiéis à tela)."""
        return max(1, int(round(value * self._content_scale)))

    # ------------------------------------------------------------------ #
    # Construção
    # ------------------------------------------------------------------ #

    def _create_sky(self) -> pygame.Surface:
        """Gradiente vertical noturno, pré-renderizado uma vez (§7)."""
        surf = pygame.Surface((self.width, self.height))
        top = (6, 5, 16)
        bot = (18, 11, 30)
        h = max(1, self.height)
        draw_line = pygame.draw.line
        for y in range(self.height):
            t = y / h
            c = (
                int(top[0] + (bot[0] - top[0]) * t),
                int(top[1] + (bot[1] - top[1]) * t),
                int(top[2] + (bot[2] - top[2]) * t),
            )
            draw_line(surf, c, (0, y), (self.width, y))
        return optimize_surface(surf)

    def _create_fog(self) -> pygame.Surface:
        """Névoa do solo: gradiente translúcido (transparente no topo → denso
        na base), pré-renderizado uma vez (§7). Blitado por cima dos prédios
        para a base deles afundar na bruma."""
        fog_h = int(self.height * 0.38)
        surf = pygame.Surface((self.width, fog_h), pygame.SRCALPHA)
        tint = (30, 22, 48)
        max_alpha = 155
        draw_line = pygame.draw.line
        for yy in range(fog_h):
            t = yy / fog_h
            a = int(max_alpha * (t ** 1.6))  # adensa suave em direção à base
            draw_line(surf, (*tint, a), (0, yy), (self.width, yy))
        self.fog_y = self.height - fog_h
        return optimize_alpha_surface(surf)

    def _create_moon(self) -> pygame.Surface:
        """Lua minguante: disco pálido + recorte de sombra deslocado, com halo
        suave. Pré-renderizada uma vez (§7); estática no céu."""
        r = self.cs(32)
        pad = self.cs(14)
        size = (r + pad) * 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        # Halo suave atrás (escuro/frio, casa com a paleta)
        for extra, alpha in ((12, 16), (7, 24), (3, 34)):
            pygame.draw.circle(
                surf, (170, 185, 225, alpha), (cx, cy), r + self.cs(extra)
            )
        # Disco
        pygame.draw.circle(surf, (214, 220, 240), (cx, cy), r)
        # Recorte deslocado → crescente minguante (parte iluminada à esquerda).
        # Desenhar (0,0,0,0) numa surface SRCALPHA apaga os pixels (carve).
        pygame.draw.circle(surf, (0, 0, 0, 0), (cx + int(r * 0.5), cy), r)
        mx, my = int(self.width * 0.78), int(self.height * 0.16)
        self.moon_pos = (mx - size // 2, my - size // 2)
        return optimize_alpha_surface(surf)

    def _create_cloud_variants(self) -> None:
        """Pré-renderiza algumas nuvens (blobs translúcidos escuros)."""
        for _ in range(3):
            w = random.randint(self.cs(220), self.cs(380))
            h = random.randint(self.cs(70), self.cs(120))
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            for _ in range(7):
                ew = random.randint(w // 3, w // 2)
                eh = random.randint(h // 2, h)
                ex = random.randint(0, w - ew)
                ey = random.randint(0, h - eh)
                alpha = random.randint(22, 55)
                pygame.draw.ellipse(surf, (34, 26, 52, alpha), (ex, ey, ew, eh))
            self._cloud_variants.append(optimize_alpha_surface(surf))

    def _create_stars(self) -> None:
        for _ in range(self.NUM_STARS):
            self.stars.append({
                "x": random.uniform(0, self.width),
                "y": random.uniform(0, self.height * 0.65),
                "size": random.choice([1, 1, 1, 2]),
                "phase": random.uniform(0, math.tau),
                "tw": random.uniform(0.8, 3.0),
                "base": random.uniform(0.45, 1.0),
                "color": random.choice(self._STAR_COLORS),
            })

    def _create_clouds(self) -> None:
        for _ in range(self.NUM_CLOUDS):
            self.clouds.append({
                "variant": random.randrange(len(self._cloud_variants)),
                "x": random.uniform(0, self.width),
                "y": random.uniform(self.height * 0.05, self.height * 0.4),
                "speed": self.sf(random.uniform(10.0, 22.0)),
            })

    def _create_layers(self) -> None:
        """4 camadas de silhuetas (fundo claro/lento → frente escura/rápida).

        Neon (janelas) só nas 2 camadas frontais — as de trás são silhueta pura.
        """
        layer_configs: List[Dict[str, Any]] = [
            {"speed": 10.0, "color": (26, 20, 42), "count": 8, "wmin": 60, "wmax": 130, "hmin": 110, "hmax": 230, "neon": False},
            {"speed": 24.0, "color": (19, 15, 32), "count": 6, "wmin": 80, "wmax": 160, "hmin": 170, "hmax": 320, "neon": False},
            {"speed": 52.0, "color": (12, 10, 22), "count": 5, "wmin": 100, "wmax": 190, "hmin": 230, "hmax": 420, "neon": True},
            {"speed": 110.0, "color": (7, 6, 14), "count": 4, "wmin": 120, "wmax": 230, "hmin": 300, "hmax": 540, "neon": True},
        ]
        # Tamanhos e velocidades acima estão em pixels de 720p: escalar para a
        # resolução de construção (meia-res no fundo retrô) mantém a mesma
        # silhueta e o mesmo ritmo de parallax na tela final.
        for cfg in layer_configs:
            for key in ("wmin", "wmax", "hmin", "hmax"):
                cfg[key] = self.cs(cfg[key])
            cfg["speed"] = self.sf(cfg["speed"])

        for cfg in layer_configs:
            buildings: List[Dict[str, Any]] = []
            spacing = self.width / cfg["count"]
            for i in range(cfg["count"]):
                start_x = i * spacing + random.uniform(-self.cs(30), self.cs(30))
                buildings.append(self._make_building(cfg, start_x))
            self.layers.append({
                "speed": cfg["speed"],
                "color": cfg["color"],
                "neon": cfg["neon"],
                "cfg": cfg,
                "buildings": buildings,
            })

    def _make_building(self, cfg: Dict[str, Any], x: float) -> Dict[str, Any]:
        """Cria um prédio (silhueta + janelas neon com estado FIXO).

        Cada janela nasce acesa/apagada (~25% acesas) e só muda esporadicamente
        em `_flip_random_window` — piscar raro e aleatório, não oscilação.
        """
        width = random.randint(cfg["wmin"], cfg["wmax"])
        height = random.randint(cfg["hmin"], cfg["hmax"])
        windows: List[List[Any]] = []
        if cfg["neon"]:
            wh, gap = self._win_h, self.cs(15)
            y_top = self.height - height
            margin_x = self.cs(8)
            for wy in range(y_top + self.cs(12), self.height - self.cs(10), wh + gap):
                for wx_rel in range(margin_x, width - margin_x, gap):
                    windows.append([wx_rel, wy, random.random() < 0.25])
        return {
            "x": x,
            "width": width,
            "height": height,
            "neon_color": random.choice(self._NEON_PALETTE),
            "windows": windows,
        }

    # ------------------------------------------------------------------ #
    # Update
    # ------------------------------------------------------------------ #

    def update(self, dt: float, speed_mult: float = 1.0) -> None:
        # Piscar raro/aleatório: a cada intervalo sorteado, UMA janela qualquer
        # do skyline troca de estado. Independente do scroll/warp (ambiência
        # calma), em tempo real.
        self._toggle_timer += dt
        while self._toggle_timer >= self._next_toggle:
            self._toggle_timer -= self._next_toggle
            self._next_toggle = random.uniform(0.5, 1.3)
            self._flip_random_window()

        # Estrelas: só piscam (twinkle); posição fixa.
        for s in self.stars:
            s["phase"] += s["tw"] * dt

        # Nuvens: deriva horizontal, reaparecem à direita.
        for c in self.clouds:
            c["x"] -= c["speed"] * dt * speed_mult
            cw = self._cloud_variants[int(c["variant"])].get_width()
            if c["x"] + cw < 0:
                c["x"] = self.width
                c["y"] = random.uniform(self.height * 0.05, self.height * 0.4)
                c["variant"] = random.randrange(len(self._cloud_variants))

        # Prédios: scroll + reciclagem (rightmost calculado uma vez — O(n)).
        for layer in self.layers:
            scroll = layer["speed"] * dt * speed_mult
            buildings = layer["buildings"]
            rightmost = max(b["x"] + b["width"] for b in buildings) if buildings else self.width
            for b in buildings:
                b["x"] -= scroll
                if b["x"] + b["width"] < -self.cs(50):
                    new_x = max(
                        rightmost + random.randint(self.cs(20), self.cs(120)), self.width
                    )
                    nb = self._make_building(layer["cfg"], new_x)
                    b["x"] = new_x
                    b["width"] = nb["width"]
                    b["height"] = nb["height"]
                    b["neon_color"] = nb["neon_color"]
                    b["windows"] = nb["windows"]
                    rightmost = new_x + nb["width"]

    def _flip_random_window(self) -> None:
        """Inverte o estado de UMA janela aleatória entre as camadas neon."""
        candidates = [
            b
            for layer in self.layers
            if layer["neon"]
            for b in layer["buildings"]
            if b["windows"]
        ]
        if not candidates:
            return
        win = random.choice(random.choice(candidates)["windows"])
        win[2] = not win[2]

    # ------------------------------------------------------------------ #
    # Render
    # ------------------------------------------------------------------ #

    def draw(self, surface: pygame.Surface) -> None:
        # Céu noturno (gradiente pré-renderizado)
        surface.blit(self.sky, (0, 0))

        # Estrelas (piscando)
        draw_circle = pygame.draw.circle
        for s in self.stars:
            b = s["base"] * (0.55 + 0.45 * math.sin(s["phase"]))
            col = s["color"]
            c = (int(col[0] * b), int(col[1] * b), int(col[2] * b))
            draw_circle(surface, c, (int(s["x"]), int(s["y"])), s["size"])

        # Lua minguante (sobre as estrelas; nuvens passam à frente)
        surface.blit(self.moon, self.moon_pos)

        # Nuvens
        for c in self.clouds:
            surface.blit(
                self._cloud_variants[int(c["variant"])], (int(c["x"]), int(c["y"]))
            )

        # Camadas de prédios (trás → frente)
        draw_rect = pygame.draw.rect
        for layer in self.layers:
            color = layer["color"]
            neon = layer["neon"]
            for b in layer["buildings"]:
                self._draw_building(surface, b, color, neon, draw_rect)

        # Névoa do solo, por cima dos prédios (afunda as bases na bruma)
        surface.blit(self.fog, (0, self.fog_y))

    def _draw_building(
        self,
        surface: pygame.Surface,
        b: Dict[str, Any],
        color: Tuple[int, int, int],
        neon: bool,
        draw_rect: Any,
    ) -> None:
        x = int(b["x"])
        bw = b["width"]
        bh = b["height"]
        y = self.height - bh

        # Silhueta
        draw_rect(surface, color, (x, y, bw, bh))

        if not neon:
            return

        nc = b["neon_color"]
        # Linha de neon no topo (cumeeira)
        draw_rect(surface, nc, (x, y, bw, self.cs(2)))

        # Janelas: desenha só as ACESAS (estado fixo, trocado esporadicamente).
        ww, wh = self._win_w, self._win_h
        for w in b["windows"]:
            if w[2]:
                draw_rect(surface, nc, (x + w[0], w[1], ww, wh))

    def reset(self) -> None:
        self._toggle_timer = 0.0
        self._next_toggle = random.uniform(0.5, 1.3)
        self.stars.clear()
        self.clouds.clear()
        self.layers.clear()
        self._create_stars()
        self._create_clouds()
        self._create_layers()
