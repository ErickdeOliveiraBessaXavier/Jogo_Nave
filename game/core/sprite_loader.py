import logging
from typing import Any, Callable, List

import pygame

from ..core.assets import BASE_DIR, get_image


class SpriteLoader:
    """Gerenciador central de sprites animados."""

    _instance = None
    _loaded = False
    _animation_cache: dict[tuple[str, int, str], List[pygame.Surface]] = {}

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
            logging.info("  ⏳ Carregando %s...", name)
            loader_func()
            logging.info("  ✅ %s carregado!", name)

        SpriteLoader._loaded = True
        self.loaders.clear()
        logging.info("✅ Todos os sprites carregados!\n")

    async def load_all_async(self, on_progress=None) -> None:
        """Versão cooperativa de ``load_all`` para o WASM/pygbag.

        Cede o controle ao event loop (``await asyncio.sleep(0)``) entre cada
        loader, para o navegador conseguir desenhar a tela de loading e não
        congelar. ``on_progress(feitos, total, nome)`` é chamado antes de cada
        passo para atualizar a barra.
        """
        import asyncio

        if SpriteLoader._loaded:
            if on_progress is not None:
                on_progress(1, 1, "")
            return

        total = len(self.loaders)
        for i, (name, loader_func) in enumerate(self.loaders):
            if on_progress is not None:
                on_progress(i, total, name)
            await asyncio.sleep(0)  # deixa o navegador pintar o frame
            loader_func()

        if on_progress is not None:
            on_progress(total, total, "")
        await asyncio.sleep(0)

        SpriteLoader._loaded = True
        self.loaders.clear()

    @classmethod
    def load_animation_frames(
        cls,
        base_path: str,
        num_frames: int,
        name: str,
        filename_pattern: str = "boss_3_gosma_sprite ({i}).png",
    ) -> List[pygame.Surface]:
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
        cache_key = (base_path, num_frames, filename_pattern)
        if cache_key in cls._animation_cache:
            return list(cls._animation_cache[cache_key])

        frames: List[pygame.Surface] = []
        for i in range(1, num_frames + 1):
            filename = filename_pattern.format(i=i)
            path = BASE_DIR / "assets" / "images" / base_path / filename

            if not path.exists():
                logging.warning("%s: Frame %s não encontrado: %s", name, i, path)
                continue

            try:
                image = get_image(path)
                frames.append(image)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logging.error("%s: Erro ao carregar frame %s: %s", name, i, e)
                continue

        if not frames:
            logging.error(
                "%s: NENHUM frame foi carregado! Verifique o caminho dos sprites.", name
            )
        elif len(frames) < num_frames:
            logging.warning(
                "%s: Apenas %s/%s frames foram carregados.",
                name,
                len(frames),
                num_frames,
            )
        else:
            logging.info("%s: %s frames carregados com sucesso.", name, len(frames))

        cls._animation_cache[cache_key] = list(frames)
        return frames

    @classmethod
    def is_loaded(cls) -> bool:
        """Verifica se os sprites já foram carregados."""
        return cls._loaded


# Instância global
sprite_loader = SpriteLoader()
