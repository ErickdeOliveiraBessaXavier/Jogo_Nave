import asyncio
import faulthandler
import logging
import logging.handlers
import os
import sys
import traceback

# Ensure the project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# Handle global mantido vivo pelo processo inteiro: sem a referência, o GC
# fecharia o arquivo e o faulthandler perderia o dump.
_crash_dump_file = None


def _enable_faulthandler() -> None:
    """Ativa o `faulthandler` gravando em `crash.log`.

    Crash NATIVO (segfault/access violation em pygame/SDL, stack overflow C)
    NÃO levanta exceção Python — o `try/except` do `main()` não o captura e o
    jogo fecha sem `error.log`. O faulthandler intercepta o sinal fatal e
    escreve o traceback Python do ponto exato do crash neste arquivo.

    Em modo windowed (`sys.stderr is None`) o dump iria para o vazio; por isso
    apontamos para um arquivo dedicado, mantido aberto pela vida do processo.
    """
    global _crash_dump_file
    try:
        from game.core.paths import get_user_data_dir

        crash_path = get_user_data_dir() / "crash.log"
        _crash_dump_file = open(crash_path, "w", encoding="utf-8")
        faulthandler.enable(file=_crash_dump_file, all_threads=True)
    except Exception:
        # Fallback: stderr (pode ser None em windowed, mas não custa tentar).
        try:
            faulthandler.enable(all_threads=True)
        except Exception:
            pass


def _setup_logging():
    """Configura logging para arquivo + console.

    Em modo windowed (PyInstaller console=False), `sys.stdout` é None e
    o StreamHandler isolado some silenciosamente. Adicionar FileHandler
    garante que `logger.info/warning/error` ficam persistidos em
    `%LOCALAPPDATA%\\PixelPatrol\\game.log` (Windows) ou
    `~/.local/share/PixelPatrol/game.log` (Linux/Mac).

    Útil para diagnosticar bugs intermitentes (reconexão de gamepad,
    crashes em bosses) que não chegam a derrubar o processo.
    """
    handlers: list[logging.Handler] = []

    # Console handler — só funciona se sys.stdout existir.
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))

    # File handler — rotativo (1MB × 3 backups = ~4MB total).
    try:
        from game.core.paths import get_game_log_path

        log_path = get_game_log_path()
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handlers.append(file_handler)
    except Exception:
        # Se falhar (perm denied, disco cheio), seguimos sem file log.
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,  # Sobrescreve config prévia (importa caso outro módulo já tenha chamado).
    )


def main():
    """Main entry point for the game."""
    _enable_faulthandler()
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("=== Pixel Patrol iniciado ===")

    try:
        from game.app import GameApp

        app = GameApp()
        asyncio.run(app.run())
    except Exception:
        # Try to save the error to a file
        try:
            from game.core.paths import get_error_log_path

            error_log = get_error_log_path()
            with open(error_log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            logger.exception("Erro fatal — salvo em %s", error_log)
        except Exception as e:
            logger.exception("Erro fatal — não foi possível salvar log: %s", e)

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
