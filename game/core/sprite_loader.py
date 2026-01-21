import logging
from typing import Callable, Any, List
import pygame

from ..core.assets import get_image, BASE_DIR


class SpriteLoader:
    """Gerenciador central de sprites animados."""

    _instance = None
    _loaded = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not SpriteLoader._loaded:
            self.loaders: list[tuple[str, Callable[[], Any]]] = []

    def register(self, name: str, loader_func: Callable[[], Any]) -> None:
        """Registra uma função de carregamento de sprites."""
        if not SpriteLoader._loaded:
            self.loaders.append((name, loader_func))

    def load_all(self) -> None:
        """Carrega todos os sprites registrados."""
        if SpriteLoader._loaded:
            return

        logging.info("🎮 Carregando sprites animados...")
        for name, loader_func in self.loaders:
            logging.info(f"  ⏳ Carregando {name}...")
            loader_func()
            logging.info(f"  ✅ {name} carregado!")

        SpriteLoader._loaded = True
        logging.info("✅ Todos os sprites carregados!\n")

    @staticmethod
    def load_animation_frames(base_path: str, num_frames: int, name: str, filename_pattern: str = "boss_3_gosma_sprite ({i}).png") -> List[pygame.Surface]:
        """
        Método genérico para carregar frames de animação com validação e logging.

        Args:
            base_path: Caminho relativo à pasta assets/images (ex: "sprite_boss_03_slime")
            num_frames: Número de frames a carregar (1 a num_frames)
            name: Nome para logging
            filename_pattern: Padrão do nome do arquivo, use {i} para o número do frame

        Returns:
            Lista de surfaces carregadas
        """
        frames: List[pygame.Surface] = []
        for i in range(1, num_frames + 1):
            filename = filename_pattern.format(i=i)
            path = BASE_DIR / "assets" / "images" / base_path / filename

            if not path.exists():
                logging.warning(f"{name}: Frame {i} não encontrado: {path}")
                continue

            try:
                image = get_image(path)
                frames.append(image)
            except Exception as e:
                logging.error(f"{name}: Erro ao carregar frame {i}: {e}")
                continue

        if not frames:
            logging.error(f"{name}: NENHUM frame foi carregado! Verifique o caminho dos sprites.")
        elif len(frames) < num_frames:
            logging.warning(f"{name}: Apenas {len(frames)}/{num_frames} frames foram carregados.")
        else:
            logging.info(f"{name}: {len(frames)} frames carregados com sucesso.")

        return frames

    @classmethod
    def is_loaded(cls) -> bool:
        """Verifica se os sprites já foram carregados."""
        return cls._loaded


# Instância global
sprite_loader = SpriteLoader()
