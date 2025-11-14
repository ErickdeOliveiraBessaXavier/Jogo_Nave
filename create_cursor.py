#!/usr/bin/env python3
"""Script para criar um cursor customizado em pixel art."""

import pygame
import os

# Inicializar pygame
pygame.init()

# Criar uma superfície transparente para o cursor (36x36 pixels)
cursor_size = 36
cursor_surface = pygame.Surface((cursor_size, cursor_size), pygame.SRCALPHA)

# Cores
green = (0, 255, 0, 255)      # Verde brilhante
dark_green = (0, 180, 0, 255) # Verde escuro
white = (255, 255, 255, 255)  # Branco

# Desenhar um cursor em forma de seta em pixel art (escalado 2.25x)
# Pixel por pixel para criar um desenho em pixel art
scale = 2.25
pixels = []
base_pixels = [
    (0, 0), (1, 0),
    (0, 1), (1, 1), (2, 1),
    (0, 2), (1, 2), (2, 2), (3, 2),
    (0, 3), (1, 3), (2, 3), (3, 3), (4, 3),
    (0, 4), (1, 4),
    (1, 5), (2, 5),
]

# Escalar os pixels
for x, y in base_pixels:
    for i in range(int(scale)):
        for j in range(int(scale)):
            px = int(x * scale) + i
            py = int(y * scale) + j
            if px < cursor_size and py < cursor_size:
                pixels.append((px, py))

pixels = list(set(pixels))

# Desenhar a seta com verde
for x, y in pixels:
    cursor_surface.fill(green, (x, y, 1, 1))

# Adicionar um outline em verde escuro para melhor definição
for x, y in pixels:
    # Verificar vizinhos e desenhar outline
    for dx, dy in [(1, 0), (0, 1), (1, 1), (-1, 0), (0, -1), (-1, -1), (-1, 1), (1, -1)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < cursor_size and 0 <= ny < cursor_size:
            # Se não é um pixel da seta, desenhar outline
            if (nx, ny) not in pixels:
                current = cursor_surface.get_at((nx, ny))
                if current[3] == 0:  # Se transparente
                    cursor_surface.fill(dark_green, (nx, ny, 1, 1))

# Criar diretório se não existir
cursor_dir = "game/assets/cursors"
os.makedirs(cursor_dir, exist_ok=True)

# Salvar a imagem do cursor
cursor_path = os.path.join(cursor_dir, "cursor.png")
pygame.image.save(cursor_surface, cursor_path)

print(f"✅ Cursor criado com sucesso em: {cursor_path}")
print(f"   Tamanho: {cursor_size}x{cursor_size} pixels")
print(f"   Cor: Verde (#00FF00)")
