"""Entrypoint da build WEB (pygbag).

Roda o MESMO GameApp async do desktop. No web, os sprites sao carregados de
forma COOPERATIVA (com tela de loading) aqui, porque o carregamento sincrono
do __init__ congelaria o navegador. Os prints vao para o console (F12).
"""
import asyncio
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_text_cache(pygame):
    """Memoiza ``Font.render`` por (fonte, texto, cor) — corrige a lentidão das
    telas não-menu no WASM, onde re-rasterizar texto por frame é caro. Textos de
    UI são estáticos, então o cache acerta e o custo some. O padrão do código é
    sempre ``surf = render(...); surf.set_alpha(a); blit(surf)``, então superfícies
    compartilhadas são seguras (o alpha é setado imediatamente antes de cada blit).
    """
    FontClass = pygame.font.Font
    orig_render = FontClass.render
    cache = {}

    def cached_render(self, text, antialias=True, color=(0, 0, 0), *args, **kwargs):
        if args or kwargs:  # ex.: cor de fundo — não cacheia esses casos
            return orig_render(self, text, antialias, color, *args, **kwargs)
        try:
            key = (id(self), text, bool(antialias), tuple(color))
        except TypeError:
            return orig_render(self, text, antialias, color)
        surf = cache.get(key)
        if surf is None:
            surf = orig_render(self, text, antialias, color)
            cache[key] = surf
        return surf

    try:
        FontClass.render = cached_render
        print("[web] cache de font.render instalado")
    except (TypeError, AttributeError) as e:
        # Tipo de extensão imutável: não dá pra fazer monkeypatch. Cai fora sem
        # quebrar (aí a correção teria que ser por cena).
        print(f"[web] AVISO: nao consegui instalar cache de font.render: {e}")


def _apply_pixelated_canvas():
    """Mantém o pixel art nítido ao escalar o canvas no navegador.

    O pygbag escala a resolução lógica (1280×720) para o tamanho de exibição.
    Sem isto o navegador interpola (bilinear) e borra a arte; ``pixelated`` força
    nearest-neighbor, preservando as bordas dos pixels em qualquer escala. É
    puramente cosmético e só faz sentido no web — o desktop usa ``pygame.SCALED``.
    Deve rodar DEPOIS do ``set_mode`` (o canvas só existe então).
    """
    import sys
    import platform

    if sys.platform != "emscripten":
        return
    try:
        platform.window.canvas.style.imageRendering = "pixelated"
        print("[web] canvas imageRendering=pixelated aplicado")
    except Exception as e:  # pylint: disable=broad-exception-caught
        # DOM indisponível/mudou: não é fatal, só perde a nitidez do upscale.
        print(f"[web] AVISO: nao consegui aplicar imageRendering=pixelated: {e}")


async def main():
    print("[web] === entrypoint iniciado ===")
    try:
        import pygame

        # === Fix de performance web: cache de font.render (SDL_ttf) ===
        # Causa raiz da lentidão fora do menu: telas não-menu re-rasterizam
        # texto todo frame, e SDL_ttf é caríssimo no WASM. O menu já pré-renderiza
        # glifos uma vez; aqui aplicamos o MESMO cache globalmente (só no web),
        # sem tocar em nenhuma cena. Textos estáticos passam a acertar o cache.
        _install_text_cache(pygame)

        from game.app import GameApp

        print("[web] construindo GameApp (init leve; sprites deferidos)...")
        app = GameApp()
        # Canvas já criado pelo set_mode: força upscale nearest-neighbor (pixel art).
        _apply_pixelated_canvas()
        print("[web] init OK — pre-carregando sprites com tela de loading")

        screen = app.screen
        w, h = screen.get_width(), screen.get_height()
        font = pygame.font.Font(None, 44)
        small = pygame.font.Font(None, 28)

        def draw_progress(done, total, name):
            pct = int(100 * done / total) if total else 0
            screen.fill((8, 10, 18))
            title = font.render("Pixel Patrol", True, (235, 235, 245))
            screen.blit(title, title.get_rect(center=(w // 2, h // 2 - 40)))
            # barra
            bw, bh = int(w * 0.5), 16
            bx, by = (w - bw) // 2, h // 2 + 10
            pygame.draw.rect(screen, (40, 44, 60), (bx, by, bw, bh), border_radius=8)
            pygame.draw.rect(
                screen, (90, 170, 255), (bx, by, int(bw * pct / 100), bh), border_radius=8
            )
            label = small.render(f"Carregando... {pct}%", True, (170, 180, 200))
            screen.blit(label, label.get_rect(center=(w // 2, by + 44)))
            pygame.display.flip()

        await app.preload(draw_progress)
        print("[web] sprites carregados — entrando no loop principal")
        await app.run()
        print("[web] loop encerrado normalmente")
    except BaseException:
        print("[web] !!! ERRO FATAL:")
        traceback.print_exc()
        raise


asyncio.run(main())
