#!/usr/bin/env python3
"""Script para criar um cursor customizado em pixel art."""

import pygame
import os

# Inicializar pygame
pygame.init()

# Tamanho do cursor
cursor_size = 36
cursor_surface = pygame.Surface((cursor_size, cursor_size), pygame.SRCALPHA)

# Cores
white = (255, 255, 255, 255)
outline_color = (100, 100, 100, 150)  # Cinza semi-transparente

# Centro do cursor
center = cursor_size // 2

# Desenhar o contorno/sombra primeiro
# Linhas verticais
pygame.draw.line(cursor_surface, outline_color, (center, 5), (center, center - 5), 3)
pygame.draw.line(
    cursor_surface, outline_color, (center, center + 5), (center, cursor_size - 5), 3
)
# Linhas horizontais
pygame.draw.line(cursor_surface, outline_color, (5, center), (center - 5, center), 3)
pygame.draw.line(
    cursor_surface, outline_color, (center + 5, center), (cursor_size - 5, center), 3
)

# Desenhar as linhas brancas principais sobre o contorno
# Linhas verticais
pygame.draw.line(cursor_surface, white, (center, 4), (center, center - 6), 1)
pygame.draw.line(
    cursor_surface, white, (center, center + 6), (center, cursor_size - 4), 1
)
# Linhas horizontais
pygame.draw.line(cursor_surface, white, (4, center), (center - 6, center), 1)
pygame.draw.line(
    cursor_surface, white, (center + 6, center), (cursor_size - 4, center), 1
)

# Ponto central
pygame.draw.circle(cursor_surface, white, (center, center), 3)


# Criar diretório se não existir
cursor_dir = "game/assets/cursors"
os.makedirs(cursor_dir, exist_ok=True)

# Salvar a imagem do cursor
cursor_path = os.path.join(cursor_dir, "cursor.png")
pygame.image.save(cursor_surface, cursor_path)

print(f"✅ Cursor de mira criado com sucesso em: {cursor_path}")
print(f"   Tamanho: {cursor_size}x{cursor_size} pixels")
print(f"   Cor: Branco")
