"""Utilitário para gerenciar caminhos de arquivos do jogo."""
import os
import sys
from pathlib import Path


def get_user_data_dir() -> Path:
    """
    Retorna o diretório de dados do usuário para o jogo.
    
    Em desenvolvimento: usa o diretório atual
    Em produção (executável): usa AppData/Local/SpaceShooter no Windows
    """
    if getattr(sys, 'frozen', False):
        # Executável PyInstaller
        if sys.platform == 'win32':
            # Windows: %LOCALAPPDATA%/SpaceShooter
            data_dir = Path(os.getenv('LOCALAPPDATA', os.path.expanduser('~'))) / 'SpaceShooter'
        else:
            # Linux/Mac: ~/.local/share/SpaceShooter
            data_dir = Path.home() / '.local' / 'share' / 'SpaceShooter'
        
        # Criar diretório se não existir
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    else:
        # Modo desenvolvimento: usa diretório atual
        return Path.cwd()


def get_profile_path() -> Path:
    """Retorna o caminho para o arquivo de perfil do jogador."""
    return get_user_data_dir() / 'player_profile.json'


def get_error_log_path() -> Path:
    """Retorna o caminho para o arquivo de log de erros."""
    return get_user_data_dir() / 'error.log'
