"""Utilitário para gerenciar caminhos de arquivos do jogo."""

import os
import sys
from pathlib import Path


def get_user_data_dir() -> Path:
    """
    Retorna o diretório de dados do usuário para o jogo.

    Em desenvolvimento: usa o diretório atual
    Em produção (executável): usa AppData/Local/PixelPatrol no Windows
    """
    if getattr(sys, "frozen", False):
        # Executável PyInstaller
        if sys.platform == "win32":
            # Windows: %LOCALAPPDATA%/PixelPatrol
            data_dir = (
                Path(os.getenv("LOCALAPPDATA", os.path.expanduser("~")))
                / "PixelPatrol"
            )
        else:
            # Linux/Mac: ~/.local/share/PixelPatrol
            data_dir = Path.home() / ".local" / "share" / "PixelPatrol"

        # Criar diretório se não existir
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    # Modo desenvolvimento: usa diretório atual
    return Path.cwd()


def get_profile_path() -> Path:
    """Retorna o caminho para o arquivo de perfil do jogador."""
    return get_user_data_dir() / "player_profile.json"


def get_preferences_path() -> Path:
    """Retorna o caminho para o arquivo de preferências do jogador."""
    return get_user_data_dir() / "user_preferences.json"


def get_error_log_path() -> Path:
    """Retorna o caminho para o arquivo de log de erros."""
    return get_user_data_dir() / "error.log"


def get_game_log_path() -> Path:
    """Retorna o caminho para o arquivo de log contínuo do jogo.

    Captura `logger.info/warning/error` de todos os módulos. Útil para
    diagnosticar bugs intermitentes (reconexão de gamepad, crashes em
    bosses, etc.) que não chegam a matar o processo.
    """
    return get_user_data_dir() / "game.log"
