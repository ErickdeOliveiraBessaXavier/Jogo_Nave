"""Entrypoint da build WEB (pygbag).

O pygbag empacota a pasta que contem este main.py. Ele roda o MESMO
GameApp async do desktop — a unica diferenca e este ponto de entrada
(o desktop usa run.py). Copiado para web/staging/main.py pelo build_web.ps1.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.app import GameApp


async def main():
    app = GameApp()
    await app.run()


asyncio.run(main())
