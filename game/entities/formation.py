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


class Formation:
    """
    Gerencia um grupo de inimigos em formações geométricas.
    Inimigos entram em espiral e depois se alinham em diferentes padrões.
    """
    
    def __init__(
        self,
        enemy_type: Type[Any],
        count: int,
        entry_x: float,
        entry_y: float,
        patterns_sequence: List[FormationPattern] | None = None
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
            enemy.formation_angle = (i / count) * 2 * math.pi  # Ângulo inicial na espiral
            self.enemies.append(enemy)
        
        # Padrões
        if patterns_sequence is None:
            self.patterns_sequence = [
                FormationPattern.SPIRAL_ENTRY,
                FormationPattern.CIRCLE,
                FormationPattern.V_SHAPE
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
        
        # Estado da espiral
        self.spiral_time = 0.0
        self.spiral_radius = Config.FORMATION_SPIRAL_RADIUS
        self.spiral_complete = False
        
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
        self.fully_entered = False
    
    def _precalculate_final_positions(self):
        """Pré-calcula as posições finais para evitar saltos visuais."""
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
            self._update_spiral(dt)
        elif self.is_transitioning:
            self._update_transition(dt)
        else:
            self._update_pattern_positions(dt)
        
        # Atualizar cada inimigo e coletar balas
        all_bullets: List[Any] = []
        for enemy in self.enemies[:]:
            if hasattr(enemy, 'dead') and enemy.dead:
                self.enemies.remove(enemy)
                continue
            
            # Atualizar timers internos do inimigo (como shoot_timer)
            if hasattr(enemy, 'shoot_timer'):
                enemy.shoot_timer -= dt
                if enemy.shoot_timer <= 0:
                    from .alien_bullet import AlienBullet
                    enemy.shoot_timer = random.uniform(2.0, 4.0)
                    all_bullets.append(AlienBullet(enemy.x + enemy.w / 2, enemy.y + enemy.h))
        
        # Formação morre se todos os inimigos morrerem
        if len(self.enemies) == 0:
            self.dead = True
        
        # Formação morre se sair completamente da tela (desceu demais)
        if self.center_y > Config.SCREEN_HEIGHT + 150:
            self.dead = True
        
        return all_bullets

    def _update_spiral(self, dt: float):
        """Atualiza posições durante entrada em espiral."""
        self.spiral_time += dt
        
        for enemy in self.enemies:
            # Usa índice fixo do inimigo para manter consistência
            i = enemy.formation_index
            # Cada inimigo tem um offset de tempo na espiral
            time_offset = i * Config.FORMATION_SPIRAL_TIME_OFFSET
            t = max(0, self.spiral_time - time_offset)
            
            # Calcular posição na espiral
            angle = enemy.formation_angle + t * Config.FORMATION_SPIRAL_SPEED
            radius = self.spiral_radius * (1 - math.exp(-t * 0.5))
            
            # Mover para baixo enquanto gira
            target_x = self.center_x + radius * math.cos(angle)
            target_y = self.center_y + t * Config.FORMATION_ENTRY_SPEED + radius * math.sin(angle)
            
            enemy.x = target_x - enemy.w / 2
            enemy.y = target_y - enemy.h / 2
        
        # Verificar se a espiral está completa
        if self.spiral_time > self.count * Config.FORMATION_SPIRAL_TIME_OFFSET + 2.0:
            self.spiral_complete = True
            self.fully_entered = True
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
        
        # Movimento lento lateral para formações em padrão
        movement_time = self.time_in_pattern
        drift_x = math.sin(movement_time * 0.5) * Config.FORMATION_DRIFT_SPEED * dt
        
        self.center_x += drift_x
        
        # Movimento de descida após formação completa (não durante espiral)
        if self.current_pattern != FormationPattern.SPIRAL_ENTRY and not self.is_transitioning:
            self.center_y += Config.FORMATION_DESCENT_SPEED * dt
        
        # Aplicar offsets fixos relativos ao centro (que se move)
        for enemy in self.enemies:
            i = enemy.formation_index
            # CORRIGIDO: Verificar bounds para evitar IndexError
            if i < len(self.final_positions):
                # Offset relativo ao centro
                offset_x: float = cast(float, self.final_positions[i][0])
                offset_y: float = cast(float, self.final_positions[i][1])
                # Aplicar offset + posição do centro
                enemy.x = (self.center_x + offset_x) - enemy.w / 2
                enemy.y = (self.center_y + offset_y) - enemy.h / 2

    def _calculate_pattern_positions(self, pattern: FormationPattern) -> List[Tuple[float, float]]:
        """Calcula posições para cada inimigo no padrão especificado."""
        positions: List[Tuple[float, float]] = []
        count = self.count
        
        if pattern == FormationPattern.CIRCLE:
            radius = Config.FORMATION_CIRCLE_RADIUS
            for i in range(count):
                angle = (i / count) * 2 * math.pi
                x = self.center_x + radius * math.cos(angle)
                y = self.center_y + radius * math.sin(angle)
                positions.append((x, y))
        
        elif pattern == FormationPattern.V_SHAPE:
            spacing = Config.FORMATION_V_SPACING
            half = count // 2
            has_center = count % 2 == 1  # Se ímpar, tem nave no centro
            
            for i in range(count):
                if has_center and i == half:
                    # Nave central (vértice do V)
                    x = self.center_x
                    y = self.center_y
                elif i < half:
                    # Lado esquerdo do V
                    offset = half - i
                    x = self.center_x - offset * spacing
                    y = self.center_y + offset * spacing
                else:
                    # Lado direito do V
                    if has_center:
                        offset = i - half  # Para ímpar
                    else:
                        offset = i - half + 1  # Para par, começar do 1
                    x = self.center_x + offset * spacing
                    y = self.center_y + offset * spacing
                positions.append((x, y))
        
        elif pattern == FormationPattern.SQUARE:
            # MELHORADO: Distribuição mais uniforme
            side_length = Config.FORMATION_SQUARE_SIZE
            
            if count <= 4:
                # Poucos inimigos: colocar nos cantos
                corners = [
                    (-side_length/2, -side_length/2),  # Top-left
                    (side_length/2, -side_length/2),   # Top-right
                    (side_length/2, side_length/2),    # Bottom-right
                    (-side_length/2, side_length/2),   # Bottom-left
                ]
                for i in range(count):
                    x = self.center_x + corners[i][0]
                    y = self.center_y + corners[i][1]
                    positions.append((x, y))
            else:
                # Muitos inimigos: distribuir ao longo dos lados
                per_side = math.ceil(count / 4)
                for i in range(count):
                    side = i // per_side
                    pos_in_side = i % per_side
                    progress = pos_in_side / max(1, per_side - 1) if per_side > 1 else 0.5
                    
                    if side == 0:  # Topo
                        x = self.center_x - side_length/2 + progress * side_length
                        y = self.center_y - side_length/2
                    elif side == 1:  # Direita
                        x = self.center_x + side_length/2
                        y = self.center_y - side_length/2 + progress * side_length
                    elif side == 2:  # Baixo
                        x = self.center_x + side_length/2 - progress * side_length
                        y = self.center_y + side_length/2
                    else:  # Esquerda
                        x = self.center_x - side_length/2
                        y = self.center_y + side_length/2 - progress * side_length
                    positions.append((x, y))
        
        elif pattern == FormationPattern.LINE:
            spacing = Config.FORMATION_LINE_SPACING
            total_width = (count - 1) * spacing
            for i in range(count):
                x = self.center_x - total_width/2 + i * spacing
                y = self.center_y
                positions.append((x, y))
        
        return positions

    def _ease_in_out(self, t: float) -> float:
        """Função de easing para transições suaves."""
        return t * t * (3.0 - 2.0 * t)
    
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
                # Fallback: sem offset
                self.final_positions.append((0.0, 0.0))
        
        self.positions_locked = True

    def draw(self, surface: pygame.Surface):
        """Desenha todos os inimigos da formação."""
        for enemy in self.enemies:
            enemy.draw(surface)
    
    def get_enemies(self) -> List[Any]:
        """Retorna lista de inimigos da formação (referência direta para permitir remoções)."""
        return self.enemies