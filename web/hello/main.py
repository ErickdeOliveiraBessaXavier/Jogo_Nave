"""Teste minimo pygbag: tela colorida animada. Se isto rodar no navegador,
o pipeline pygbag funciona e o problema esta no tamanho/init do jogo real."""
import asyncio
import pygame

print("[hello] pygame.init...")
pygame.init()
screen = pygame.display.set_mode((640, 360))
clock = pygame.time.Clock()
print("[hello] display pronto")


async def main():
    print("[hello] === loop iniciado ===")
    t = 0
    font = pygame.font.SysFont(None, 48)
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return
        t = (t + 1) % 256
        screen.fill((t, 100, 200))
        txt = font.render(f"pygbag OK {t}", True, (255, 255, 255))
        screen.blit(txt, (200, 160))
        pygame.display.flip()
        clock.tick(60)
        await asyncio.sleep(0)


asyncio.run(main())
