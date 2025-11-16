"""
Módulo para armazenar a resolução detectada do monitor em tempo de execução.
"""

# Armazenar a resolução detectada do monitor
_detected_screen_width = 1600
_detected_screen_height = 900


def set_runtime_resolution(width: int, height: int) -> None:
    """Define a resolução detectada do monitor."""
    global _detected_screen_width, _detected_screen_height
    _detected_screen_width = width
    _detected_screen_height = height


def get_detected_resolution() -> tuple[int, int]:
    """Retorna a resolução detectada do monitor."""
    return _detected_screen_width, _detected_screen_height
