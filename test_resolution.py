#!/usr/bin/env python3
"""Script de teste para verificar detecção de resolução do monitor."""

import pygame

# Inicializar pygame
pygame.init()

# Obter informações do display
info = pygame.display.Info()
print(f"Informações do Monitor Detectadas:")
print(f"  Largura: {info.current_w}px")
print(f"  Altura: {info.current_h}px")

# Testar importação
from game.core.config import Config
from game.core.screen_resolver import set_runtime_resolution, get_detected_resolution

print(f"\nConfigurações Padrão:")
print(f"  Config.SCREEN_WIDTH: {Config.SCREEN_WIDTH}")
print(f"  Config.SCREEN_HEIGHT: {Config.SCREEN_HEIGHT}")
print(f"  Config.FULLSCREEN: {Config.FULLSCREEN}")

# Simular o que o GameApp faz
if Config.FULLSCREEN:
    detected_width = info.current_w
    detected_height = info.current_h
    set_runtime_resolution(detected_width, detected_height)
    print(f"\nResolução em Tempo de Execução (fullscreen ativado):")
else:
    print(f"\nResolução em Tempo de Execução (windowed):")

detected_w, detected_h = get_detected_resolution()
print(f"  Largura detectada: {detected_w}px")
print(f"  Altura detectada: {detected_h}px")

print(f"\nPronto para executar o jogo com resolução nativa do monitor!")
pygame.quit()
