#!/usr/bin/env python3
"""
Script de teste de performance para Jogo Nave.

Este script executa o jogo automaticamente por um período determinado,
coletando métricas de performance como FPS, uso de memória e estatísticas de entidades.

Uso:
    python performance_test.py [--duration SECONDS] [--difficulty DIFFICULTY] [--output FILE]

Exemplo:
    python performance_test.py --duration 60 --difficulty HARDCORE --output results.json
"""

import pygame
import time
import json

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None
import os
import argparse
from typing import Dict, List, Any
import sys
import cProfile
import pstats
from io import StringIO

# Adicionar o diretório do jogo ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.app import GameApp
from game.core.difficulty import DifficultyPreset
from game.scenes.playing import PlayingScene
from game.core.levels import LevelManager


class PerformanceMonitor:
    """Monitora métricas de performance durante a execução do jogo."""

    def __init__(self):
        self.start_time = time.time()
        self.frame_count = 0
        self.fps_history: List[float] = []
        self.memory_history: List[float] = []
        self.entity_stats_history: List[Dict[str, Any]] = []
        self.frame_times: List[float] = []

    def update(self, dt: float, renderer: Any, entity_manager: Any) -> None:
        """Atualiza as métricas de performance."""
        self.frame_count += 1
        self.frame_times.append(dt)

        # Coletar FPS
        if hasattr(renderer, "get_fps_stats"):
            fps_stats = renderer.get_fps_stats()
            self.fps_history.append(fps_stats["fps"])

        # Coletar uso de memória
        if psutil is not None:
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            self.memory_history.append(memory_mb)

        # Coletar estatísticas de entidades
        if hasattr(entity_manager, "get_stats"):
            entity_stats = entity_manager.get_stats()
            self.entity_stats_history.append(entity_stats)

        # Manter apenas os últimos 300 valores (5 segundos a 60 FPS)
        max_history = 300
        if len(self.fps_history) > max_history:
            self.fps_history = self.fps_history[-max_history:]
        if len(self.memory_history) > max_history:
            self.memory_history = self.memory_history[-max_history:]
        if len(self.entity_stats_history) > max_history:
            self.entity_stats_history = self.entity_stats_history[-max_history:]
        if len(self.frame_times) > max_history:
            self.frame_times = self.frame_times[-max_history:]

    def get_summary(self) -> Dict[str, Any]:
        """Retorna um resumo das métricas coletadas."""
        if not self.fps_history:
            return {"error": "Nenhuma métrica coletada"}

        avg_fps = sum(self.fps_history) / len(self.fps_history)
        min_fps = min(self.fps_history)
        max_fps = max(self.fps_history)

        avg_memory = (
            sum(self.memory_history) / len(self.memory_history)
            if self.memory_history
            else 0.0
        )
        max_memory = max(self.memory_history) if self.memory_history else 0.0

        avg_frame_time = (
            sum(self.frame_times) / len(self.frame_times) * 1000
            if self.frame_times
            else 0.0
        )  # ms
        max_frame_time = max(self.frame_times) * 1000 if self.frame_times else 0.0  # ms

        # Estatísticas de entidades (última coleta)
        entity_stats = (
            self.entity_stats_history[-1] if self.entity_stats_history else {}
        )

        return {
            "duration_seconds": time.time() - self.start_time,
            "total_frames": self.frame_count,
            "fps": {
                "average": round(avg_fps, 2),
                "minimum": round(min_fps, 2),
                "maximum": round(max_fps, 2),
            },
            "frame_time_ms": {
                "average": round(avg_frame_time, 2),
                "maximum": round(max_frame_time, 2),
            },
            "memory_mb": {
                "average": round(avg_memory, 2),
                "maximum": round(max_memory, 2),
            },
            "entity_stats": entity_stats,
            "performance_rating": self._calculate_performance_rating(
                avg_fps, max_frame_time
            ),
        }

    def _calculate_performance_rating(
        self, avg_fps: float, max_frame_time: float
    ) -> str:
        """Calcula uma classificação de performance baseada nas métricas."""
        target_fps = 60.0
        max_acceptable_frame_time = 16.67  # ~60 FPS

        if (
            avg_fps >= target_fps * 0.95
            and max_frame_time <= max_acceptable_frame_time * 1.2
        ):
            return "EXCELENTE"
        elif (
            avg_fps >= target_fps * 0.85
            and max_frame_time <= max_acceptable_frame_time * 1.5
        ):
            return "BOM"
        elif avg_fps >= target_fps * 0.7:
            return "ACEITÁVEL"
        else:
            return "RUIM"


class AutomatedGameApp(GameApp):
    """Versão automatizada do jogo para testes de performance."""

    ship: Any
    config: Any
    input: Any
    states: Any

    def __init__(self, difficulty: DifficultyPreset, test_duration: float):
        super().__init__()
        self.test_duration = test_duration
        self.monitor = PerformanceMonitor()
        self.start_time = time.time()
        self.difficulty = difficulty

        # Configurar controles automáticos
        self.auto_pilot = True

    def run_performance_test(self) -> Dict[str, Any]:
        """Executa o teste de performance."""
        print(
            f"🚀 Iniciando teste de performance ({self.test_duration}s) - Dificuldade: {self.difficulty.name}"
        )
        print("⏹️  Pressione Ctrl+C para interromper antecipadamente")

        # Inicializar jogo
        level_manager = LevelManager()
        playing_scene = PlayingScene(self, level_manager, self.difficulty)
        self.states.push(playing_scene)

        # Iniciar profiling
        profiler = cProfile.Profile()
        profiler.enable()

        # Loop principal do teste
        clock = pygame.time.Clock()
        running = True

        try:
            while running and (time.time() - self.start_time) < self.test_duration:
                dt = clock.tick(120) / 1000.0  # 120 FPS máximo

                # Processar eventos
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            running = False

                # Simular entrada automática (manter nave no centro)
                if self.auto_pilot and hasattr(self.states.current, "ship"):
                    ship = self.states.current.ship
                    # Manter nave no centro horizontal
                    center_x = self.config.SCREEN_WIDTH // 2
                    if ship.x < center_x - 50:
                        self.input._pressed_keys.add(pygame.K_RIGHT)
                        self.input._pressed_keys.discard(pygame.K_LEFT)
                    elif ship.x > center_x + 50:
                        self.input._pressed_keys.add(pygame.K_LEFT)
                        self.input._pressed_keys.discard(pygame.K_RIGHT)
                    else:
                        self.input._pressed_keys.discard(pygame.K_LEFT)
                        self.input._pressed_keys.discard(pygame.K_RIGHT)

                    # Atirar continuamente
                    self.input._pressed_keys.add(pygame.K_SPACE)

                # Atualizar cena atual
                current_scene = self.states.current()
                if current_scene:
                    current_scene.update(dt)

                    # Coletar métricas (apenas para PlayingScene)
                    if hasattr(current_scene, "r") and hasattr(
                        current_scene, "entity_manager"
                    ):
                        self.monitor.update(
                            dt, current_scene.r, current_scene.entity_manager
                        )

                    # Renderizar
                    current_scene.render(self.screen)

                # Atualizar display
                pygame.display.flip()

        except KeyboardInterrupt:
            print("\n⏹️  Teste interrompido pelo usuário")

        finally:
            # Parar profiling
            profiler.disable()

        # Obter resultados
        results = self.monitor.get_summary()

        # Adicionar profiling aos resultados
        s = StringIO()
        ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
        ps.print_stats(20)  # Top 20 funções
        results["profiling"] = s.getvalue()

        return results


def main():
    parser = argparse.ArgumentParser(description="Teste de performance do Jogo Nave")
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="Duração do teste em segundos (padrão: 30)",
    )
    parser.add_argument(
        "--difficulty",
        choices=[d.name.lower() for d in DifficultyPreset],
        default="normal",
        help="Dificuldade do teste (padrão: normal)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="performance_results.json",
        help="Arquivo de saída para os resultados (padrão: performance_results.json)",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Executar sem interface gráfica (modo headless)",
    )

    args = parser.parse_args()

    # Configurar dificuldade
    difficulty_map = {d.name.lower(): d for d in DifficultyPreset}
    difficulty = difficulty_map[args.difficulty]

    # Configurar display
    if args.no_display:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    # Executar teste
    try:
        app = AutomatedGameApp(difficulty, args.duration)
        results = app.run_performance_test()

        # Salvar resultados
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        # Exibir resumo
        print("\n" + "=" * 50)
        print("📊 RESULTADOS DO TESTE DE PERFORMANCE")
        print("=" * 50)
        print(f"⏱️  Duração: {results['duration_seconds']:.1f}s")
        print(f"🎮 Frames: {results['total_frames']}")
        print(f"🎯 FPS Médio: {results['fps']['average']:.1f}")
        print(f"📉 FPS Mínimo: {results['fps']['minimum']:.1f}")
        print(f"📈 FPS Máximo: {results['fps']['maximum']:.1f}")
        print(f"⚡ Frame Time Médio: {results['frame_time_ms']['average']:.2f}ms")
        print(f"🐌 Frame Time Máximo: {results['frame_time_ms']['maximum']:.2f}ms")
        print(f"💾 Memória Média: {results['memory_mb']['average']:.1f}MB")
        print(f"🧠 Memória Máxima: {results['memory_mb']['maximum']:.1f}MB")
        print(f"🏆 Classificação: {results['performance_rating']}")
        print(f"\n💾 Resultados salvos em: {args.output}")

        # Exibir profiling
        if "profiling" in results:
            print("\n" + "=" * 50)
            print("🔍 PROFILING (Top 20 funções por tempo cumulativo)")
            print("=" * 50)
            print(results["profiling"])

        # Avisos de performance
        if results["fps"]["minimum"] < 30:
            print(
                "⚠️  AVISO: FPS mínimo muito baixo! Verifique gargalos de performance."
            )
        if results["frame_time_ms"]["maximum"] > 50:
            print("⚠️  AVISO: Frame time máximo muito alto! Possível stuttering.")

    except Exception as e:
        print(f"❌ Erro durante o teste: {e}")
        return 1

    finally:
        pygame.quit()

    return 0


if __name__ == "__main__":
    exit(main())
