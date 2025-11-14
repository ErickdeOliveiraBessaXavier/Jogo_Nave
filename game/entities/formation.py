import pygame
import math
import random
from enum import Enum
from typing import List, Type, Any, Tuple, cast
from ..core.config import Config


class FormationPattern(Enum):
    """Padrões de formação disponíveis."""

    SPIRAL_ENTRY = "spiral_entry"
    CIRCLE = "circle"
    V_SHAPE = "v_shape"
    SQUARE = "square"
    LINE = "line"


class EntryPattern(Enum):
    """Padrões de entrada disponíveis."""

    CURVED_PATH = "curved_path"  # Galaga clássico
    LOOP = "loop"  # Loop completo antes da posição
    WAVE = "wave"  # Onda sincronizada
    FAN = "fan"  # Leque abrindo
    DIAGONAL_CROSS = "diagonal_cross"  # Diagonais cruzadas


class Formation:
    """
    Gerencia um grupo de inimigos em formações geométricas.
    Inimigos entram com diferentes padrões animados (curvas, loops, ondas, etc.)
    e depois se alinham em formações geométricas (círculo, V, quadrado, linha).
    """

    def __init__(
        self,
        enemy_type: Type[Any],
        count: int,
        entry_x: float,
        entry_y: float,
        patterns_sequence: List[FormationPattern] | None = None,
    ):
        """
        Inicializa uma formação.

        Args:
            enemy_type: Tipo de inimigo a criar (ex: Alien)
            count: Número de inimigos na formação
            entry_x: Posição X central de entrada
            entry_y: Posição Y inicial (geralmente acima da tela)
            patterns_sequence: Sequência de padrões (padrão: espiral -> círculo -> V)
        """
        # Validação: count deve ser >= 1
        if count < 1:
            raise ValueError(f"Formation count must be >= 1, got {count}")

        self.enemy_type = enemy_type
        self.count = count
        self.center_x = entry_x
        self.center_y = entry_y

        # Criar inimigos
        self.enemies: List[Any] = []
        for i in range(count):
            enemy = enemy_type()
            # Desabilitar movimento padrão do inimigo
            enemy.formation_controlled = True
            enemy.formation_index = i
            # Adicionar controle de opacidade para fade-in
            enemy.alpha = 0  # Começar invisível
            enemy.fade_in_time = 0.0  # Tempo de fade
            self.enemies.append(enemy)

        # Padrões
        if patterns_sequence is None:
            self.patterns_sequence = [
                FormationPattern.SPIRAL_ENTRY,
                FormationPattern.CIRCLE,
                FormationPattern.V_SHAPE,
            ]
        else:
            self.patterns_sequence = patterns_sequence

        self.current_pattern_index = 0
        self.current_pattern = self.patterns_sequence[0]

        # Controle de tempo
        self.time_in_pattern = 0.0
        self.pattern_duration = Config.FORMATION_PATTERN_DURATION
        self.transition_progress = 0.0
        self.is_transitioning = False

        # Estado da entrada
        self.entry_time = 0.0

        # Escolher padrão de entrada aleatoriamente
        self.entry_pattern = self._choose_random_entry_pattern()

        # Posições-alvo para transições suaves
        self.target_positions: List[Tuple[float, float]] = []

        # Posições fixas finais de cada inimigo (após formação completada)
        # PRÉ-CALCULAR todas as posições para evitar "saltos" visuais
        self.final_positions: List[Tuple[float, float]] = []
        self.positions_locked = False

        # Pré-calcular posições finais para o primeiro padrão não-espiral
        self._precalculate_final_positions()

        # Estado
        self.dead = False
        self.formation_complete = (
            False  # True quando todas as naves entraram e formação está estável
        )

    def _choose_random_entry_pattern(self) -> EntryPattern:
        """Escolhe aleatoriamente um padrão de entrada com pesos diferentes."""
        patterns = [
            EntryPattern.CURVED_PATH,
            EntryPattern.LOOP,
            EntryPattern.WAVE,
            EntryPattern.FAN,
            EntryPattern.DIAGONAL_CROSS,
        ]
        weights = [0.35, 0.25, 0.20, 0.12, 0.08]  # Soma = 1.0
        return random.choices(patterns, weights=weights)[0]

    def _precalculate_final_positions(self):
        """Pré-calcula as posições finais para evitar saltos visuais."""
        # Validação: verificar se há pelo menos um padrão
        if not self.patterns_sequence:
            raise ValueError("patterns_sequence cannot be empty")

        # Encontrar o primeiro padrão que não é SPIRAL_ENTRY
        target_pattern = None
        for pattern in self.patterns_sequence:
            if pattern != FormationPattern.SPIRAL_ENTRY:
                target_pattern = pattern
                break

        if target_pattern is None:
            # Se só tem espiral, usar círculo como fallback
            target_pattern = FormationPattern.CIRCLE

        # Calcular posições do padrão alvo
        positions = self._calculate_pattern_positions(target_pattern)

        # Armazenar offsets relativos ao centro
        self.final_positions = []
        for i in range(self.count):
            if i < len(positions):
                pattern_x, pattern_y = positions[i]
                offset_x = pattern_x - self.center_x
                offset_y = pattern_y - self.center_y
                self.final_positions.append((offset_x, offset_y))
            else:
                self.final_positions.append((0.0, 0.0))

        # Marcar como pré-calculado (será travado definitivamente após primeira transição)
        self.positions_locked = True

    def update(self, dt: float) -> List[Any]:
        """Atualiza a formação e retorna lista de balas geradas pelos inimigos."""
        if self.dead:
            return []

        self.time_in_pattern += dt

        # Verificar se deve mudar de padrão
        if not self.is_transitioning and self.time_in_pattern >= self.pattern_duration:
            self._start_pattern_transition()

        # Atualizar posições baseado no padrão atual
        if self.current_pattern == FormationPattern.SPIRAL_ENTRY:
            self._update_entry(dt)
        elif self.is_transitioning:
            self._update_transition(dt)
        else:
            self._update_pattern_positions(dt)

        # Atualizar cada inimigo e coletar balas
        all_bullets: List[Any] = []
        for enemy in self.enemies[:]:
            if hasattr(enemy, "dead") and enemy.dead:
                self.enemies.remove(enemy)
                continue

            # Atualizar timers internos do inimigo (como shoot_timer)
            # MAS só permitir tiro se a formação estiver completamente formada
            if (
                hasattr(enemy, "shoot_timer")
                and self.formation_complete
                and not self.is_transitioning
            ):
                enemy.shoot_timer -= dt
                if enemy.shoot_timer <= 0:
                    from .alien_bullet import AlienBullet

                    enemy.shoot_timer = random.uniform(2.0, 4.0)
                    all_bullets.append(
                        AlienBullet(enemy.x + enemy.w / 2, enemy.y + enemy.h)
                    )

        # Formação morre se todos os inimigos morrerem
        if len(self.enemies) == 0:
            self.dead = True

        # Formação morre se sair completamente da tela (desceu demais)
        if self.center_y > Config.SCREEN_HEIGHT + 150:
            self.dead = True

        return all_bullets

    def _update_entry(self, dt: float):
        """Delega para o método de entrada correto baseado no padrão escolhido."""
        if self.entry_pattern == EntryPattern.CURVED_PATH:
            self._update_curved_entry(dt)
        elif self.entry_pattern == EntryPattern.LOOP:
            self._update_loop_entry(dt)
        elif self.entry_pattern == EntryPattern.WAVE:
            self._update_wave_entry(dt)
        elif self.entry_pattern == EntryPattern.FAN:
            self._update_fan_entry(dt)
        elif self.entry_pattern == EntryPattern.DIAGONAL_CROSS:
            self._update_diagonal_cross_entry(dt)

    def _update_curved_entry(self, dt: float):
        """Atualiza posições durante entrada em fila indiana com trajetória curva (estilo Galaga)."""
        self.entry_time += dt

        for enemy in self.enemies:
            # Usa índice fixo do inimigo para manter consistência
            i = enemy.formation_index
            # Cada nave entra com um delay (fila indiana)
            time_offset = i * Config.FORMATION_ENTRY_TIME_OFFSET
            t = max(0, self.entry_time - time_offset)

            if t <= 0:
                # Nave ainda não começou a entrar, manter fora da tela
                enemy.x = self.center_x - enemy.w / 2
                enemy.y = -100
                enemy.alpha = 0  # Invisível
                continue

            # Fade-in suave: aumentar opacidade nos primeiros 0.5 segundos
            enemy.fade_in_time += dt
            fade_duration = 0.5
            enemy.alpha = min(255, int((enemy.fade_in_time / fade_duration) * 255))

            # Progresso da entrada (0 a 1) - normalizado em 3.5 segundos
            entry_progress = min(1.0, t / 3.5)

            # Determinar lado de entrada (alternado para visual interessante)
            # Naves pares entram pela esquerda, ímpares pela direita
            side = 1 if i % 2 == 0 else -1

            # Trajetória curva sinusoidal (estilo Galaga)
            # Começa de um lado, faz curvas e vai se aproximando do centro
            curve_x = (
                math.sin(t * Config.FORMATION_ENTRY_CURVE_FREQUENCY)
                * Config.FORMATION_ENTRY_CURVE_AMPLITUDE
            )

            # Reduzir amplitude da curva conforme se aproxima da formação final
            curve_x *= 1.0 - entry_progress * 0.85

            # Offset inicial baseado no lado de entrada
            start_offset_x = (
                side * Config.FORMATION_ENTRY_CURVE_OFFSET_X * (1.0 - entry_progress)
            )

            # Movimento vertical constante
            descent_y = t * Config.FORMATION_ENTRY_SPEED

            # Posição final: centro + curva + offset inicial que diminui
            target_x = self.center_x + curve_x + start_offset_x
            target_y = (
                self.center_y + 50 + descent_y
            )  # Começa próximo ao centro (não muito acima)

            # LIMITAR POSIÇÃO HORIZONTAL (respeitar limites da tela)
            margin = 30
            target_x = max(
                margin + enemy.w / 2,
                min(Config.SCREEN_WIDTH - margin - enemy.w / 2, target_x),
            )

            # LIMITAR POSIÇÃO VERTICAL (permitir aparecer suavemente, mas não subir muito)
            # Limite superior: não pode subir mais que uma nave completa acima da tela
            # Limite inferior: deixa descer normalmente
            target_y = max(
                -enemy.h, min(target_y, Config.SCREEN_HEIGHT)
            )  # Não volta acima de -enemy.h

            enemy.x = target_x - enemy.w / 2
            enemy.y = target_y - enemy.h / 2

        # Verificar se a entrada está completa
        # Todas as naves entraram + tempo para última nave completar trajetória
        total_entry_time = self.count * Config.FORMATION_ENTRY_TIME_OFFSET + 4.0
        if self.entry_time > total_entry_time:
            self.formation_complete = True
            self._start_pattern_transition()

    def _update_loop_entry(self, dt: float):
        """Entrada com loop completo (estilo boss do Galaga)."""
        self.entry_time += dt

        for enemy in self.enemies:
            i = enemy.formation_index
            time_offset = i * Config.FORMATION_ENTRY_TIME_OFFSET
            t = max(0, self.entry_time - time_offset)

            if t <= 0:
                enemy.x = self.center_x - enemy.w / 2
                enemy.y = -100
                enemy.alpha = 0  # Invisível
                continue

            # Fade-in suave
            enemy.fade_in_time += dt
            fade_duration = 0.5
            enemy.alpha = min(255, int((enemy.fade_in_time / fade_duration) * 255))

            # Progresso normalizado
            entry_progress = min(1.0, t / 3.5)

            # Fazer um loop circular completo
            loop_angle = t * 2.5  # Velocidade do loop
            loop_radius = 150.0 * (1.0 - entry_progress * 0.7)  # Raio diminui

            # Posição no loop
            loop_x = math.cos(loop_angle) * loop_radius
            loop_y = math.sin(loop_angle) * loop_radius

            # Descida gradual
            descent_y = t * Config.FORMATION_ENTRY_LOOP_SPEED

            # Convergir para o centro (loop afeta ambos X e Y)
            target_x = self.center_x + loop_x * (1.0 - entry_progress * 0.6)
            target_y = (
                self.center_y + 50 + descent_y + loop_y * 0.5
            )  # Próximo ao centro

            # LIMITAR POSIÇÃO HORIZONTAL
            margin = 30
            target_x = max(
                margin + enemy.w / 2,
                min(Config.SCREEN_WIDTH - margin - enemy.w / 2, target_x),
            )

            # LIMITAR POSIÇÃO VERTICAL (não deixar subir além do topo)
            target_y = max(-enemy.h, min(target_y, Config.SCREEN_HEIGHT))

            enemy.x = target_x - enemy.w / 2
            enemy.y = target_y - enemy.h / 2

        if self.entry_time > self.count * Config.FORMATION_ENTRY_TIME_OFFSET + 4.0:
            self.formation_complete = True
            self._start_pattern_transition()

    def _update_wave_entry(self, dt: float):
        """Entrada sincronizada em onda."""
        self.entry_time += dt

        for enemy in self.enemies:
            i = enemy.formation_index
            t = self.entry_time

            # Fade-in suave para todas as naves
            enemy.fade_in_time += dt
            fade_duration = 0.5
            enemy.alpha = min(255, int((enemy.fade_in_time / fade_duration) * 255))

            # Todas entram ao mesmo tempo, mas com offset de fase
            phase_offset = (i / self.count) * math.pi * 2

            # Progresso
            entry_progress = min(1.0, t / 3.0)

            # Onda horizontal
            wave_x = math.sin(t * 2.0 + phase_offset) * 180.0
            wave_x *= 1.0 - entry_progress * 0.8

            # Descida
            descent_y = t * Config.FORMATION_ENTRY_WAVE_SPEED

            target_x = self.center_x + wave_x
            target_y = self.center_y + descent_y  # Começa no centro e desce

            # LIMITAR POSIÇÃO HORIZONTAL
            margin = 30
            target_x = max(
                margin + enemy.w / 2,
                min(Config.SCREEN_WIDTH - margin - enemy.w / 2, target_x),
            )

            # LIMITAR POSIÇÃO VERTICAL (não deixar subir além do topo)
            target_y = max(-enemy.h, min(target_y, Config.SCREEN_HEIGHT))

            enemy.x = target_x - enemy.w / 2
            enemy.y = target_y - enemy.h / 2

        if self.entry_time > 3.5:
            self.formation_complete = True
            self._start_pattern_transition()

    def _update_fan_entry(self, dt: float):
        """Entrada em leque - todas partem do centro e abrem."""
        self.entry_time += dt

        for enemy in self.enemies:
            i = enemy.formation_index
            t = self.entry_time

            # Fade-in suave
            enemy.fade_in_time += dt
            fade_duration = 0.5
            enemy.alpha = min(255, int((enemy.fade_in_time / fade_duration) * 255))

            # Progresso
            entry_progress = min(1.0, t / 3.0)

            # Ângulo único para cada nave
            angle = (i / self.count) * math.pi * 1.5 - math.pi * 0.75  # Leque de 270°

            # Raio que aumenta com o tempo
            radius = t * 100.0 * entry_progress

            # Posição no leque
            fan_x = math.cos(angle) * radius
            fan_y = math.sin(angle) * radius * 0.5  # Achatar verticalmente

            # Descida
            descent_y = t * Config.FORMATION_ENTRY_FAN_SPEED

            target_x = self.center_x + fan_x
            target_y = self.center_y + 30 + descent_y + fan_y  # Próximo ao centro

            # LIMITAR POSIÇÃO HORIZONTAL
            margin = 30
            target_x = max(
                margin + enemy.w / 2,
                min(Config.SCREEN_WIDTH - margin - enemy.w / 2, target_x),
            )

            # LIMITAR POSIÇÃO VERTICAL (não deixar subir além do topo)
            target_y = max(-enemy.h, min(target_y, Config.SCREEN_HEIGHT))

            enemy.x = target_x - enemy.w / 2
            enemy.y = target_y - enemy.h / 2

        if self.entry_time > 3.5:
            self.formation_complete = True
            self._start_pattern_transition()

    def _update_diagonal_cross_entry(self, dt: float):
        """Entrada em diagonais cruzadas."""
        self.entry_time += dt

        for enemy in self.enemies:
            i = enemy.formation_index
            time_offset = i * Config.FORMATION_ENTRY_TIME_OFFSET
            t = max(0, self.entry_time - time_offset)

            if t <= 0:
                enemy.x = self.center_x - enemy.w / 2
                enemy.y = -100
                enemy.alpha = 0  # Invisível
                continue

            # Fade-in suave
            enemy.fade_in_time += dt
            fade_duration = 0.5
            enemy.alpha = min(255, int((enemy.fade_in_time / fade_duration) * 255))

            # Metade vem da esquerda, metade da direita
            side = 1 if i < self.count // 2 else -1

            # Progresso
            entry_progress = min(1.0, t / 3.5)

            # Movimento diagonal
            diag_x = side * 300 * (1.0 - entry_progress)
            diag_y = t * Config.FORMATION_ENTRY_DIAGONAL_SPEED

            target_x = self.center_x + diag_x
            target_y = self.center_y + 50 + diag_y  # Próximo ao centro

            # LIMITAR POSIÇÃO HORIZONTAL
            margin = 30
            target_x = max(
                margin + enemy.w / 2,
                min(Config.SCREEN_WIDTH - margin - enemy.w / 2, target_x),
            )

            # LIMITAR POSIÇÃO VERTICAL (permitir aparecer suavemente)
            target_y = max(-enemy.h, target_y)

            enemy.x = target_x - enemy.w / 2
            enemy.y = target_y - enemy.h / 2

        if self.entry_time > self.count * Config.FORMATION_ENTRY_TIME_OFFSET + 4.0:
            self.formation_complete = True
            self._start_pattern_transition()

    def _start_pattern_transition(self):
        """Inicia transição para o próximo padrão."""
        # Avançar para próximo padrão
        old_pattern = self.current_pattern
        self.current_pattern_index += 1
        if self.current_pattern_index >= len(self.patterns_sequence):
            # Reiniciar ciclo ou manter último padrão
            self.current_pattern_index = 1  # Pula espiral

        self.current_pattern = self.patterns_sequence[self.current_pattern_index]
        self.time_in_pattern = 0.0
        self.is_transitioning = True
        self.transition_progress = 0.0

        # Destravar posições apenas se mudou para um padrão diferente
        if old_pattern != self.current_pattern:
            self.positions_locked = False

        # Calcular posições-alvo para o novo padrão
        self.target_positions = self._calculate_pattern_positions(self.current_pattern)

    def _update_transition(self, dt: float):
        """Atualiza transição suave entre padrões."""
        self.transition_progress += dt / Config.FORMATION_TRANSITION_DURATION

        if self.transition_progress >= 1.0:
            self.transition_progress = 1.0
            self.is_transitioning = False
            # Travar posições finais quando a transição terminar (se ainda não travadas)
            if not self.positions_locked:
                self._lock_final_positions()

        # Interpolação suave (easing)
        t = self._ease_in_out(self.transition_progress)

        # Mover cada inimigo em direção à posição-alvo usando seu índice FIXO
        for enemy in self.enemies:
            i = enemy.formation_index  # Usa índice fixo do inimigo
            if i < len(self.target_positions):
                target_x: float = cast(float, self.target_positions[i][0])
                target_y: float = cast(float, self.target_positions[i][1])
                current_x = enemy.x + enemy.w / 2
                current_y = enemy.y + enemy.h / 2

                # Interpolação suave em direção ao alvo
                new_x: float = current_x + (target_x - current_x) * t * dt * 5
                new_y: float = current_y + (target_y - current_y) * t * dt * 5

                enemy.x = new_x - enemy.w / 2
                enemy.y = new_y - enemy.h / 2

    def _update_pattern_positions(self, dt: float):
        """Atualiza posições quando já está no padrão (adiciona movimento de descida)."""
        # Se as posições ainda não foram travadas, travar agora
        if not self.positions_locked:
            self._lock_final_positions()

        # Movimento de descida após formação completa (não durante espiral)
        if (
            self.current_pattern != FormationPattern.SPIRAL_ENTRY
            and not self.is_transitioning
        ):
            self.center_y += Config.FORMATION_DESCENT_SPEED * dt

        # Aplicar offsets fixos relativos ao centro (que se move)
        for enemy in self.enemies:
            i = enemy.formation_index
            # IMPORTANTE: final_positions mantém tamanho original (count).
            # Quando inimigos morrem, são removidos de self.enemies mas seus índices
            # originais (formation_index) são preservados. Por isso verificamos bounds.
            # Isso cria "buracos" visuais na formação quando inimigos são destruídos.
            if i < len(self.final_positions):
                # Offset relativo ao centro
                offset_x: float = cast(float, self.final_positions[i][0])
                offset_y: float = cast(float, self.final_positions[i][1])
                # Aplicar offset + posição do centro
                enemy.x = (self.center_x + offset_x) - enemy.w / 2
                enemy.y = (self.center_y + offset_y) - enemy.h / 2

    def _calculate_pattern_positions(
        self, pattern: FormationPattern
    ) -> List[Tuple[float, float]]:
        """Calcula posições para cada inimigo no padrão especificado."""
        positions: List[Tuple[float, float]] = []
        count = self.count

        if pattern == FormationPattern.CIRCLE:
            radius = Config.FORMATION_CIRCLE_RADIUS
            for i in range(count):
                angle = (i / count) * 2 * math.pi
                x = self.center_x + radius * math.cos(angle)
                y = self.center_y + radius * math.sin(angle)

                # GARANTIR que não fique cortado no topo
                # Assumindo altura de nave ~30px
                min_y = 50  # Margem mínima do topo
                y = max(min_y, y)

                positions.append((x, y))

        elif pattern == FormationPattern.V_SHAPE:
            # V-shape funciona tanto com contagem ímpar (tem centro) quanto par (sem centro)
            # Recomendado: usar 5 ou 7 naves para visual mais balanceado
            spacing = Config.FORMATION_V_SPACING
            half = count // 2
            has_center = count % 2 == 1  # Se ímpar, tem nave no centro
            min_y = 50  # Margem mínima do topo

            for i in range(count):
                if has_center and i == half:
                    # Nave central (vértice do V) - apenas para contagem ímpar
                    x = self.center_x
                    y = max(min_y, self.center_y)
                elif i < half:
                    # Lado esquerdo do V
                    offset = half - i
                    x = self.center_x - offset * spacing
                    y = max(min_y, self.center_y + offset * spacing)
                else:
                    # Lado direito do V
                    if has_center:
                        offset = i - half  # Para ímpar
                    else:
                        offset = i - half + 1  # Para par, começar do 1
                    x = self.center_x + offset * spacing
                    y = max(min_y, self.center_y + offset * spacing)
                positions.append((x, y))

        elif pattern == FormationPattern.SQUARE:
            side_length = Config.FORMATION_SQUARE_SIZE

            # Apenas valores válidos: 4, 8 ou 12
            valid_counts = [4, 8, 12]
            if count not in valid_counts:
                # Encontrar o valor válido mais próximo
                count = min(valid_counts, key=lambda x: abs(x - count))

            if count == 0:
                return []

            positions = []
            half_len = side_length / 2

            # Calcular quantos inimigos por lado (distribuição uniforme)
            enemies_per_side = count // 4

            # Vértices do quadrado
            top_left = (-half_len, -half_len)
            top_right = (half_len, -half_len)
            bottom_right = (half_len, half_len)
            bottom_left = (-half_len, half_len)

            # TOPO: de top-left para top-right
            for i in range(enemies_per_side):
                progress = (i + 1) / (enemies_per_side + 1)
                x = self.center_x + top_left[0] + progress * side_length
                y = self.center_y + top_left[1]
                positions.append((x, y))

            # DIREITA: de top-right para bottom-right
            for i in range(enemies_per_side):
                progress = (i + 1) / (enemies_per_side + 1)
                x = self.center_x + top_right[0]
                y = self.center_y + top_right[1] + progress * side_length
                positions.append((x, y))

            # BAIXO: de bottom-right para bottom-left
            for i in range(enemies_per_side):
                progress = (i + 1) / (enemies_per_side + 1)
                x = self.center_x + bottom_right[0] - progress * side_length
                y = self.center_y + bottom_right[1]
                positions.append((x, y))

            # ESQUERDA: de bottom-left para top-left
            for i in range(enemies_per_side):
                progress = (i + 1) / (enemies_per_side + 1)
                x = self.center_x + bottom_left[0]
                y = self.center_y + bottom_left[1] - progress * side_length
                positions.append((x, y))

        elif pattern == FormationPattern.LINE:
            spacing = Config.FORMATION_LINE_SPACING
            total_width = (count - 1) * spacing
            min_y = 50  # Margem mínima do topo
            for i in range(count):
                x = self.center_x - total_width / 2 + i * spacing
                y = max(min_y, self.center_y)
                positions.append((x, y))

        return positions

    def _ease_in_out(self, t: float) -> float:
        """Função de easing para transições suaves."""
        return t * t * (3.0 - 2.0 * t)

    def _calculate_max_horizontal_offset(self) -> float:
        """Calcula o offset horizontal máximo da formação atual."""
        if self.current_pattern == FormationPattern.CIRCLE:
            return Config.FORMATION_CIRCLE_RADIUS
        elif self.current_pattern == FormationPattern.V_SHAPE:
            half = self.count // 2
            return half * Config.FORMATION_V_SPACING
        elif self.current_pattern == FormationPattern.SQUARE:
            return Config.FORMATION_SQUARE_SIZE / 2
        elif self.current_pattern == FormationPattern.LINE:
            return ((self.count - 1) * Config.FORMATION_LINE_SPACING) / 2
        else:
            return 100.0  # Fallback

    def _lock_final_positions(self):
        """Trava as posições finais de cada nave após formação completa."""
        if self.positions_locked:
            return

        # Calcular posições do padrão atual
        positions = self._calculate_pattern_positions(self.current_pattern)

        # Armazenar offset relativo ao centro para cada nave
        self.final_positions = []
        for i in range(self.count):
            if i < len(positions):
                # Posição calculada do padrão (já está relativa ao centro)
                pattern_x, pattern_y = positions[i]
                # Armazenar offset relativo ao centro
                offset_x = pattern_x - self.center_x
                offset_y = pattern_y - self.center_y
                self.final_positions.append((offset_x, offset_y))
            else:
                self.final_positions.append((0.0, 0.0))

        self.positions_locked = True

    def draw(self, surface: pygame.Surface):
        """Desenha todos os inimigos da formação."""
        for enemy in self.enemies:
            enemy.draw(surface)

    def get_enemies(self) -> List[Any]:
        """Retorna lista de inimigos da formação (referência direta para permitir remoções)."""
        return self.enemies
