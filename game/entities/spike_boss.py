import math
import random
from typing import List, Tuple, Optional

import pygame

from ..core import colors
from ..core.config import Config
from ..core.sound import sound_manager
from .spike import Spike
from .spike_boss_laser import SpikeBossLaser


class SpikeBoss:
    """
    Boss que gerencia espinhos nas laterais da tela.

    Características:
    - Movimento vertical suave no topo da tela
    - Três estados: entering, normal, frenzy
    - Cria parede de triângulos nas laterais
    - Controla ondas de ataque automaticamente via _update_waves()

    Responsabilidades:
    - Movimento e animação do boss
    - Criação inicial da parede de spikes
    - Controle de saúde e modo frenzy
    - Sistema de ondas de ataque (timing, seleção, ativação)

    Sistema de ondas:
    - Ondas são lançadas em intervalos configuráveis
    - Cada onda contém 3-6 spikes aleatórios
    - Spikes dentro da onda são espaçados por SPIKE_LAUNCH_COOLDOWN
    - Intervalo entre ondas muda em modo frenzy
    """

    def __init__(self, x: float, y: float, health: int = Config.SPIKE_BOSS_HEALTH):
        # Posição e tamanho
        self.w = 120
        self.h = 100
        self.x = x
        self.y = -self.h
        self.target_y = y

        # Saúde e estado
        self.health = health
        self.max_health = health
        self.dead = False

        # Movimento
        self.speed = Config.SPIKE_BOSS_SPEED
        self.direction = 1  # 1 = direita, -1 = esquerda
        self.entry_speed = Config.SPIKE_BOSS_ENTRY_SPEED

        # Máquina de estados
        self.state = "entering"  # entering, normal, frenzy
        self.frenzy_mode = False
        self.frenzy_shake_timer = 0.0

        # Efeitos visuais
        self.pulse = 0.0  # Para animação de pulsação
        self.pulse_speed = 3.0

        # Animação da boca
        self.mouth_timer = 0.0  # Timer para ciclo de abertura/fechamento

        # Sistema de comportamento dos olhos
        self.eye_mode = "tracking"  # "tracking" ou "frenetic"
        self.eye_mode_timer = 0.0
        self.eye_frenetic_timer = 0.0
        self.eye_frenetic_direction = 0  # -1 = esquerda, 0 = centro, 1 = direita

        # Sistema de parede de triângulos
        self.wall_initialized = False

        # Sistema de ondas de ataque (gerenciado internamente)
        self.wave_timer = 0.0  # Timer para próxima onda
        self.active_wave = False  # Se está lançando uma onda agora
        self.spikes_in_current_wave = 0  # Quantos da onda atual já lançaram
        self.current_wave_size = 0  # Tamanho da onda atual
        self.wave_launch_timer = 0.0  # Timer entre lançamentos dentro da onda

        # Posição do jogador (para olhos seguirem)
        self.player_x = 0.0
        self.player_y = 0.0

        # Flag para disparar todos os spikes ao entrar em frenzy
        self.should_launch_all_spikes = False

        # Sistema de pausa dramática do frenzy
        self.frenzy_pause_active = False
        self.frenzy_pause_timer = 0.0

        # Sistema de laser gigante (frenzy)
        self.laser_cooldown = 0.0
        self.laser_charging = False
        self.laser_charge_timer = 0.0
        self.laser_active_timer = 0.0

        # Sistema de ataque de proximidade
        self.proximity_attack_cooldown = 0.0
        self.proximity_attack_active = False
        self.proximity_wave_radius = 0.0
        self.proximity_wave_timer = 0.0
        self.proximity_telegraph_active = False  # Fase de aviso
        self.proximity_telegraph_timer = 0.0

    def take_damage(self, damage: int):
        """Recebe dano e verifica se entra em frenzy."""
        self.health -= damage

        # Verificar se morreu
        if self.health <= 0:
            self.health = 0
            self.dead = True
            self.laser_charging = False
            self.laser_active_timer = 0.0
            sound_manager.play_explosion_boss()
            return

        # Verificar se entra em frenzy
        if (
            not self.frenzy_mode
            and self.health <= self.max_health * Config.SPIKE_BOSS_FRENZY_THRESHOLD
        ):
            self._enter_frenzy()

        sound_manager.play_boss_damage()

    def _enter_frenzy(self):
        """Ativa modo frenzy com pausa dramática."""
        self.frenzy_mode = True
        self.state = "frenzy"
        self.frenzy_shake_timer = Config.SPIKE_BOSS_FRENZY_SHAKE_DURATION
        self.speed = Config.SPIKE_BOSS_FRENZY_SPEED

        # Ativar pausa dramática
        self.frenzy_pause_active = True
        self.frenzy_pause_timer = 0.0
        # Marcar que deve disparar todos os spikes
        self.should_launch_all_spikes = True
        # Som de frenzy (se disponível, senão sem som)
        if hasattr(sound_manager, "play_boss_frenzy"):
            sound_manager.play_boss_frenzy()  # type: ignore

    def is_pausing_game(self) -> bool:
        """
        Retorna True se o boss está em pausa dramática do frenzy.
        Usado pela playing.py para pausar outros elementos.
        """
        return self.frenzy_pause_active

    def update(
        self, dt: float, player_x: float, player_y: float, spikes: List[Spike]
    ) -> Tuple[List[Spike], List[SpikeBossLaser]]:
        """
        Atualiza o boss e retorna spikes e lasers criados.

        Args:
            dt: Delta time
            player_x: Posição X do jogador (para olhos seguirem)
            player_y: Posição Y do jogador (para olhos seguirem)
            spikes: Lista de todos os spikes ativos (para controle de ondas)

        Returns:
            Tupla (spikes criados, lasers criados)
            - Primeiro elemento: spikes da parede inicial (só na primeira vez)
            - Segundo elemento: laser gigante (se disparado)
        """
        spawned_spikes: List[Spike] = []
        # Armazenar posição do jogador para desenho dos olhos
        self.player_x = player_x
        self.player_y = player_y

        # Se está em pausa do frenzy, não atualiza nada além do timer e animações visuais
        if self.frenzy_pause_active:
            self.frenzy_pause_timer += dt
            self.pulse += self.pulse_speed * dt

            # Terminar pausa após duração
            if self.frenzy_pause_timer >= Config.SPIKE_BOSS_FRENZY_PAUSE_DURATION:
                self.frenzy_pause_active = False
                # Disparar todos os spikes
                self.should_launch_all_spikes = True

            return (spawned_spikes, [])

        # Atualizar animação de pulsação
        self.pulse += self.pulse_speed * dt

        # Atualizar animação da boca
        self.mouth_timer += dt
        if self.mouth_timer >= Config.SPIKE_BOSS_MOUTH_CYCLE_DURATION:
            self.mouth_timer = 0.0

        # Atualizar comportamento dos olhos
        self._update_eye_behavior(dt)

        # Estado: Entering
        if self.state == "entering":
            self.y += self.entry_speed * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self.state = "normal"
                # Inicializar parede de triângulos quando terminar de entrar
                if not self.wall_initialized:
                    spawned_spikes = self._initialize_wall()
                    self.wall_initialized = True
                    # Iniciar primeira onda após um delay
                    self.wave_timer = 2.0
            return (spawned_spikes, [])

        # Frenzy shake timer
        if self.frenzy_shake_timer > 0:
            self.frenzy_shake_timer -= dt

        if self.laser_active_timer > 0:
            self.laser_active_timer -= dt

        # Movimento horizontal
        if (
            not self.proximity_telegraph_active
            and not self.laser_charging
            and self.laser_active_timer <= 0
        ):
            self.x += self.speed * self.direction * dt

            # Inverter direção nas bordas
            if self.x <= 0:
                self.x = 0
                self.direction = 1
            elif self.x >= Config.SCREEN_WIDTH - self.w:
                self.x = Config.SCREEN_WIDTH - self.w
                self.direction = -1

        # Controlar ondas de ataque
        self._update_waves(dt, spikes)

        # Verificar ataque de proximidade
        self._check_proximity_attack(dt)

        # Verificar ataque de laser (só no frenzy)
        laser = self._update_laser_attack(dt)

        return (spawned_spikes, [laser] if laser else [])

    def get_wave_interval(self) -> float:
        """
        Retorna o intervalo entre ondas baseado no modo atual.
        Usado internamente por _update_waves().
        """
        if self.frenzy_mode:
            return Config.SPIKE_FRENZY_WAVE_INTERVAL
        return Config.SPIKE_WAVE_INTERVAL

    def should_start_wave(self, spikes: List[Spike]) -> bool:
        """
        Determina se deve iniciar uma nova onda de ataque.
        Usado internamente por _update_waves().

        Args:
            spikes: Lista de todos os spikes ativos

        Returns:
            True se deve iniciar nova onda (se há spikes disponíveis)
        """
        # Contar quantos spikes estão prontos para atacar (attached)
        ready_spikes = sum(1 for s in spikes if s.state == "attached")

        # Só inicia onda se tiver spikes disponíveis
        return ready_spikes > 0

    def _update_eye_behavior(self, dt: float):
        """
        Controla alternância entre seguir a nave e olhar freneticamente.

        Args:
            dt: Delta time
        """
        self.eye_mode_timer += dt

        # Modo: Seguindo a nave
        if self.eye_mode == "tracking":
            if self.eye_mode_timer >= Config.SPIKE_BOSS_EYE_TRACK_DURATION:
                # Mudar para modo frenético
                self.eye_mode = "frenetic"
                self.eye_mode_timer = 0.0
                self.eye_frenetic_timer = 0.0
                self.eye_frenetic_direction = random.choice(
                    [-1, 1]
                )  # Começa esquerda ou direita

        # Modo: Olhando freneticamente
        elif self.eye_mode == "frenetic":
            # Atualizar timer de mudança rápida
            self.eye_frenetic_timer += dt

            # Mudar direção rapidamente
            if self.eye_frenetic_timer >= Config.SPIKE_BOSS_EYE_FRENETIC_SPEED:
                self.eye_frenetic_timer = 0.0
                # Alternar entre esquerda (-1), centro (0), direita (1)
                self.eye_frenetic_direction = random.choice([-1, 0, 1])

            # Voltar para modo tracking após duração frenética
            if self.eye_mode_timer >= Config.SPIKE_BOSS_EYE_FRENETIC_DURATION:
                self.eye_mode = "tracking"
                self.eye_mode_timer = 0.0

    def _initialize_wall(self) -> List[Spike]:
        """
        Cria a parede completa de triângulos nas laterais.
        Os spikes começam grudados (attached) e aguardam comandos do entity_manager para atacar.

        Returns:
            Lista de todos os triângulos criados
        """
        spikes: List[Spike] = []

        # Calcular quantos triângulos cabem verticalmente
        spacing = Config.SPIKE_SIZE + Config.SPIKE_WALL_SPACING
        num_spikes_per_side = int(Config.SCREEN_HEIGHT / spacing)

        # Criar triângulos em ambas as laterais
        for from_left in [True, False]:
            for i in range(num_spikes_per_side):
                y_pos = i * spacing
                spike = Spike(y_pos, from_left=from_left)
                # Tempo alto - entity_manager controla quando atacam via wave system
                spike.time_until_attack = 999999.0
                spikes.append(spike)

        return spikes

    def _update_waves(self, dt: float, spikes: List[Spike]):
        """
        Controla o sistema de ondas de ataque dos spikes.

        Args:
            dt: Delta time
            spikes: Lista de todos os spikes ativos
        """
        import random

        # Se deve disparar todos os spikes (entrada em frenzy)
        if self.should_launch_all_spikes:
            self.should_launch_all_spikes = False
            # Ativar TODOS os spikes grudados imediatamente
            for spike in spikes:
                if spike.state == "attached":
                    spike.time_until_attack = random.uniform(
                        0.0, 0.2
                    )  # Lançamento quase instantâneo
            # Resetar sistema de ondas
            self.active_wave = False
            self.wave_timer = self.get_wave_interval()
            return

        # Atualizar timer da onda
        self.wave_timer -= dt

        # Se está em uma onda ativa
        if self.active_wave:
            self.wave_launch_timer -= dt

            # Hora de lançar próximo spike da onda
            if (
                self.wave_launch_timer <= 0
                and self.spikes_in_current_wave < self.current_wave_size
            ):
                # Encontrar spikes prontos (attached)
                ready_spikes = [s for s in spikes if s.state == "attached"]

                if ready_spikes:
                    # Escolher um aleatório
                    spike = random.choice(ready_spikes)
                    # Ativar o spike (reduzir time_until_attack para quase zero)
                    spike.time_until_attack = random.uniform(
                        Config.SPIKE_MIN_ATTACH_TIME, Config.SPIKE_MAX_ATTACH_TIME
                    )
                    self.spikes_in_current_wave += 1
                    self.wave_launch_timer = Config.SPIKE_LAUNCH_COOLDOWN

            # Onda completa
            if self.spikes_in_current_wave >= self.current_wave_size:
                self.active_wave = False
                self.wave_timer = self.get_wave_interval()

        # Iniciar nova onda
        elif self.wave_timer <= 0 and self.should_start_wave(spikes):
            self.active_wave = True
            self.current_wave_size = random.randint(
                Config.SPIKE_WAVE_MIN_SIZE, Config.SPIKE_WAVE_MAX_SIZE
            )
            self.spikes_in_current_wave = 0
            self.wave_launch_timer = 0.0

    def _check_proximity_attack(self, dt: float):
        """
        Verifica se o jogador está próximo demais e ativa ataque de área.

        Args:
            dt: Delta time
        """
        # Atualizar cooldown
        if self.proximity_attack_cooldown > 0:
            self.proximity_attack_cooldown -= dt

        # Fase de telegraph (aviso visual)
        if self.proximity_telegraph_active:
            self.proximity_telegraph_timer += dt

            if (
                self.proximity_telegraph_timer
                >= Config.SPIKE_BOSS_PROXIMITY_TELEGRAPH_DURATION
            ):
                # Terminou o aviso, iniciar ataque real
                self.proximity_telegraph_active = False
                self.proximity_telegraph_timer = 0.0
                self.proximity_attack_active = True
                self.proximity_wave_timer = 0.0
                # Som de explosão/ataque
                sound_manager.play_explosion_boss()
            return

        # Atualizar onda ativa
        if self.proximity_attack_active:
            self.proximity_wave_timer += dt
            progress = (
                self.proximity_wave_timer / Config.SPIKE_BOSS_PROXIMITY_WAVE_DURATION
            )
            self.proximity_wave_radius = (
                progress * Config.SPIKE_BOSS_PROXIMITY_WAVE_MAX_RADIUS
            )

            if progress >= 1.0:
                self.proximity_attack_active = False
                self.proximity_wave_radius = 0.0
                self.proximity_wave_timer = 0.0
            return

        # Não atacar se em cooldown ou em estado entering
        if (
            self.proximity_attack_cooldown > 0
            or self.state == "entering"
            or self.frenzy_pause_active
        ):
            return

        # Calcular distância até o jogador
        boss_center_x = self.x + self.w / 2
        boss_center_y = self.y + self.h / 2
        dx = self.player_x - boss_center_x
        dy = self.player_y - boss_center_y
        distance = math.sqrt(dx * dx + dy * dy)

        # Se jogador está muito próximo, ativar ataque
        if distance < Config.SPIKE_BOSS_PROXIMITY_DISTANCE:
            self._trigger_proximity_attack()

    def _trigger_proximity_attack(self):
        """Ativa o ataque de onda de proximidade."""
        self.proximity_telegraph_active = True
        self.proximity_telegraph_timer = 0.0
        self.proximity_attack_cooldown = Config.SPIKE_BOSS_PROXIMITY_COOLDOWN
        # Som de aviso (se disponível)
        if hasattr(sound_manager, "play_boss_warning"):
            sound_manager.play_boss_warning()  # type: ignore

    def _update_laser_attack(self, dt: float) -> Optional[SpikeBossLaser]:
        """
        Atualiza sistema de laser gigante (só ativo no frenzy).

        Args:
            dt: Delta time

        Returns:
            SpikeBossLaser se disparar um laser, None caso contrário
        """
        # Atualizar cooldown
        if self.laser_cooldown > 0:
            self.laser_cooldown -= dt

        # Atualizar carregamento
        if self.laser_charging:
            self.laser_charge_timer += dt

            # Disparar laser após carregamento
            if self.laser_charge_timer >= Config.SPIKE_BOSS_LASER_CHARGE_TIME:
                self.laser_charging = False
                self.laser_charge_timer = 0.0
                self.laser_cooldown = Config.SPIKE_BOSS_LASER_COOLDOWN
                self.laser_active_timer = Config.SPIKE_BOSS_LASER_LIFETIME

                # Criar laser
                boss_center_x = self.x + self.w / 2
                boss_bottom_y = self.y + self.h
                target_y = Config.SCREEN_HEIGHT

                # Som de laser (se disponível)
                if hasattr(sound_manager, "play_boss_laser"):
                    sound_manager.play_boss_laser()  # type: ignore

                return SpikeBossLaser(
                    x=boss_center_x,
                    y=boss_bottom_y,
                    target_y=target_y,
                    width=self.w,
                    lifetime=Config.SPIKE_BOSS_LASER_LIFETIME,
                )
            else:
                return None

        # Não atacar se não está em frenzy ou está em pausa/entering
        if not self.frenzy_mode or self.frenzy_pause_active or self.state == "entering":
            return None

        # Não atacar se em cooldown
        if self.laser_cooldown > 0:
            return None

        # Iniciar carregamento do laser
        self.laser_charging = True
        self.laser_charge_timer = 0.0

        return None

    def get_proximity_attack_data(self) -> tuple[bool, float, float, float] | None:
        """
        Retorna dados do ataque de proximidade para detecção de colisão.

        Returns:
            Tupla (ativo, center_x, center_y, raio) ou None se não ativo
        """
        if not self.proximity_attack_active:
            return None

        boss_center_x = self.x + self.w / 2
        boss_center_y = self.y + self.h / 2
        return (True, boss_center_x, boss_center_y, self.proximity_wave_radius)

    def _get_mouth_opening(self) -> float:
        """
        Calcula a abertura atual da boca baseado no ciclo de animação.

        Returns:
            Valor de 0.0 (fechada) a 1.0 (totalmente aberta)
        """
        # Criar ciclo suave: 0 -> 1 -> 0
        progress = self.mouth_timer / Config.SPIKE_BOSS_MOUTH_CYCLE_DURATION
        # Usar sin para criar movimento suave
        return abs(math.sin(progress * math.pi))

    def draw(self, surface: pygame.Surface):
        """Desenha o boss e efeitos visuais."""
        # Calcular abertura da boca (0.0 a 1.0)
        mouth_opening = self._get_mouth_opening()

        # Esticar corpo verticalmente quando boca abre
        body_stretch = int(mouth_opening * Config.SPIKE_BOSS_BODY_STRETCH)

        # Shake effect
        offset_x = 0
        offset_y = 0

        # Tremor intenso durante pausa do frenzy (birra de raiva)
        if self.frenzy_pause_active:
            offset_x = random.randint(-5, 5)
            offset_y = random.randint(-5, 5)
        # Tremor durante carregamento do laser
        elif self.laser_charging:
            offset_x = random.randint(-5, 5)
            offset_y = random.randint(-5, 5)
        # Tremor leve durante telegraph (medo)
        elif self.proximity_telegraph_active:
            offset_x = random.randint(-1, 1)
            offset_y = random.randint(-1, 1)
        # Tremor forte durante frenzy
        elif self.frenzy_shake_timer > 0:
            offset_x = random.randint(-3, 3)
            offset_y = random.randint(-3, 3)

        draw_x = int(self.x + offset_x)
        draw_y = int(self.y + offset_y - body_stretch)  # Sobe quando estica

        # Cor baseada no modo (vermelho se está no telegraph de proximidade)
        if (
            self.proximity_telegraph_active
            or self.laser_charging
            or self.laser_active_timer > 0
        ):
            # Modo "medo" - vermelho com olhos fechados
            body_color = colors.RED
            eye_color = colors.RED
            eyes_closed = True
        elif self.frenzy_mode:
            body_color = colors.DARK_RED
            eye_color = colors.RED
            eyes_closed = False
        else:
            body_color = (80, 80, 120)
            eye_color = colors.CYAN
            eyes_closed = False

        # Corpo principal (formato de cabeça com chifres) - altura aumenta com abertura
        current_height = self.h + body_stretch
        body_rect = pygame.Rect(draw_x, draw_y, self.w, current_height)
        pygame.draw.rect(surface, body_color, body_rect, border_radius=10)

        # Pulsação (borda brilhante)
        pulse_intensity = int(abs(math.sin(self.pulse)) * 100) + 100
        pulse_color = (
            (pulse_intensity, pulse_intensity // 2, pulse_intensity // 2)
            if self.frenzy_mode
            else (pulse_intensity, pulse_intensity, pulse_intensity + 55)
        )
        pygame.draw.rect(surface, pulse_color, body_rect, width=3, border_radius=10)

        # Chifres/espinhos no topo
        horn_points_left = [
            (draw_x + 10, draw_y + 20),
            (draw_x, draw_y - 15),
            (draw_x + 20, draw_y + 10),
        ]
        horn_points_right = [
            (draw_x + self.w - 10, draw_y + 20),
            (draw_x + self.w, draw_y - 15),
            (draw_x + self.w - 20, draw_y + 10),
        ]
        pygame.draw.polygon(surface, colors.DARK_RED, horn_points_left)
        pygame.draw.polygon(surface, colors.DARK_RED, horn_points_right)

        # Olhos (posição ajustada com altura atual do corpo)
        eye_size = 15
        left_eye_x = draw_x + self.w // 3
        right_eye_x = draw_x + 2 * self.w // 3
        eye_y = draw_y + current_height // 2

        # Se olhos estão fechados (modo medo), desenhar linhas ao invés de círculos
        if eyes_closed:
            # Desenhar linhas horizontais para simular olhos fechados
            line_length = eye_size
            pygame.draw.line(
                surface,
                colors.BLACK,
                (left_eye_x - line_length // 2, eye_y),
                (left_eye_x + line_length // 2, eye_y),
                3,
            )
            pygame.draw.line(
                surface,
                colors.BLACK,
                (right_eye_x - line_length // 2, eye_y),
                (right_eye_x + line_length // 2, eye_y),
                3,
            )
        else:
            # Desenhar olhos normalmente
            pygame.draw.circle(surface, eye_color, (left_eye_x, eye_y), eye_size)
            pygame.draw.circle(surface, eye_color, (right_eye_x, eye_y), eye_size)

            # Pupilas (comportamento alternado)
            pupil_color = colors.BLACK if not self.frenzy_mode else colors.YELLOW
            pupil_size = eye_size // 2
            pupil_max_offset = eye_size - pupil_size - 2  # Margem de segurança

            # Modo: Seguindo a nave
            if self.eye_mode == "tracking":
                # Calcular direção do olho esquerdo para o jogador
                left_dx = self.player_x - left_eye_x
                left_dy = self.player_y - eye_y
                left_distance = math.sqrt(left_dx * left_dx + left_dy * left_dy)

                if left_distance > 0:
                    # Normalizar e aplicar offset máximo
                    left_pupil_x = left_eye_x + int(
                        (left_dx / left_distance) * pupil_max_offset
                    )
                    left_pupil_y = eye_y + int(
                        (left_dy / left_distance) * pupil_max_offset
                    )
                else:
                    left_pupil_x = left_eye_x
                    left_pupil_y = eye_y

                # Calcular direção do olho direito para o jogador
                right_dx = self.player_x - right_eye_x
                right_dy = self.player_y - eye_y
                right_distance = math.sqrt(right_dx * right_dx + right_dy * right_dy)

                if right_distance > 0:
                    # Normalizar e aplicar offset máximo
                    right_pupil_x = right_eye_x + int(
                        (right_dx / right_distance) * pupil_max_offset
                    )
                    right_pupil_y = eye_y + int(
                        (right_dy / right_distance) * pupil_max_offset
                    )
                else:
                    right_pupil_x = right_eye_x
                    right_pupil_y = eye_y

            # Modo: Olhando freneticamente
            else:  # self.eye_mode == "frenetic"
                # Posição horizontal baseada na direção
                offset_x = self.eye_frenetic_direction * pupil_max_offset
                # Posição vertical aleatória suave
                offset_y = int(
                    math.sin(self.eye_frenetic_timer * 10) * pupil_max_offset * 0.5
                )

                left_pupil_x = left_eye_x + offset_x
                left_pupil_y = eye_y + offset_y

                right_pupil_x = right_eye_x + offset_x
                right_pupil_y = eye_y + offset_y

            # Desenhar pupilas
            pygame.draw.circle(
                surface, pupil_color, (left_pupil_x, left_pupil_y), pupil_size
            )
            pygame.draw.circle(
                surface, pupil_color, (right_pupil_x, right_pupil_y), pupil_size
            )

        # Desenhar aviso de proximidade (telegraph)
        if self.proximity_telegraph_active:
            boss_center_x = int(self.x + self.w / 2)
            boss_center_y = int(self.y + self.h / 2)

            # Calcular progresso e alpha (opacidade aumentando)
            progress = (
                self.proximity_telegraph_timer
                / Config.SPIKE_BOSS_PROXIMITY_TELEGRAPH_DURATION
            )
            start_alpha = 0.15 * 255  # Começa bem transparente
            end_alpha = 0.6 * 255  # Termina mais opaco
            alpha = int(start_alpha + (end_alpha - start_alpha) * progress)

            # Criar superfície transparente para área de perigo
            danger_radius = int(Config.SPIKE_BOSS_PROXIMITY_WAVE_MAX_RADIUS)
            danger_surface = pygame.Surface(
                (danger_radius * 2, danger_radius * 2), pygame.SRCALPHA
            )

            # Cor de perigo baseada no modo (usando constantes)
            danger_color = (
                Config.SPIKE_BOSS_PROXIMITY_WARNING_COLOR_FRENZY
                if self.frenzy_mode
                else Config.SPIKE_BOSS_PROXIMITY_WARNING_COLOR_NORMAL
            )

            # Desenhar círculo de perigo com transparência
            pygame.draw.circle(
                danger_surface,
                (*danger_color, alpha),  # Cor + alpha
                (danger_radius, danger_radius),
                danger_radius,
            )

            # Desenhar borda pulsante (pisca)
            pulse = int(self.proximity_telegraph_timer * 15) % 2  # Pisca rápido
            if pulse == 0:
                pygame.draw.circle(
                    danger_surface,
                    (*danger_color, min(255, alpha + 100)),  # Borda mais opaca
                    (danger_radius, danger_radius),
                    danger_radius,
                    width=5,
                )

            # Aplicar superfície transparente na tela
            surface.blit(
                danger_surface,
                (boss_center_x - danger_radius, boss_center_y - danger_radius),
            )

            # Símbolo de aviso "!" acima do boss
            font = pygame.font.Font(None, 40)
            warning_text = font.render("!", True, danger_color)
            text_rect = warning_text.get_rect(
                center=(boss_center_x, boss_center_y - 80)
            )
            surface.blit(warning_text, text_rect)

        # Desenhar onda de proximidade se ativa
        elif self.proximity_attack_active and self.proximity_wave_radius > 0:
            boss_center_x = int(self.x + self.w / 2)
            boss_center_y = int(self.y + self.h / 2)

            # Cores baseadas no modo (usando constantes)
            outer_color = (
                Config.SPIKE_BOSS_PROXIMITY_WAVE_COLOR_FRENZY
                if self.frenzy_mode
                else Config.SPIKE_BOSS_PROXIMITY_WAVE_COLOR_NORMAL
            )
            inner_color = (
                Config.SPIKE_BOSS_PROXIMITY_WAVE_INNER_COLOR_FRENZY
                if self.frenzy_mode
                else Config.SPIKE_BOSS_PROXIMITY_WAVE_INNER_COLOR_NORMAL
            )

            # Onda de energia pulsante (3 círculos para efeito de profundidade)
            # Onda externa
            pygame.draw.circle(
                surface,
                outer_color,
                (boss_center_x, boss_center_y),
                int(self.proximity_wave_radius),
                width=3,
            )

            # Onda média
            if self.proximity_wave_radius > 20:
                pygame.draw.circle(
                    surface,
                    outer_color,
                    (boss_center_x, boss_center_y),
                    int(self.proximity_wave_radius * 0.7),
                    width=2,
                )

            # Onda interna (mais intensa)
            if self.proximity_wave_radius > 40:
                pygame.draw.circle(
                    surface,
                    inner_color,
                    (boss_center_x, boss_center_y),
                    int(self.proximity_wave_radius * 0.4),
                    width=4,
                )

        # Efeito de carregamento do laser
        if self.laser_charging:
            boss_center_x = int(self.x + self.w / 2)
            boss_bottom_y = int(self.y + current_height)

            # Progresso do carregamento
            progress = self.laser_charge_timer / Config.SPIKE_BOSS_LASER_CHARGE_TIME

            # Partículas de energia convergindo para o centro
            num_particles = 8
            for i in range(num_particles):
                angle = (i / num_particles) * 360 + (self.laser_charge_timer * 360)
                radius = 60 * (1 - progress)  # Convergem para o centro
                px = boss_center_x + int(math.cos(math.radians(angle)) * radius)
                py = boss_bottom_y + int(math.sin(math.radians(angle)) * radius)
                particle_size = int(3 + 2 * progress)
                pygame.draw.circle(surface, colors.YELLOW, (px, py), particle_size)

        # Boca (interior branco atrás + dentes por cima)
        mouth_base_y = draw_y + int(current_height * 0.75)
        mouth_opening_pixels = int(mouth_opening * Config.SPIKE_BOSS_MOUTH_MAX_OPENING)

        tooth_height = 8  # Altura fixa dos dentes
        mouth_width = self.w - 40  # Largura total da boca

        # PRIMEIRO: Desenhar o interior branco da boca (atrás)
        if mouth_opening_pixels > 2:
            mouth_rect = pygame.Rect(
                draw_x + 20,
                mouth_base_y,  # Começa na linha da boca
                mouth_width,
                mouth_opening_pixels,  # Altura total da abertura
            )
            pygame.draw.rect(surface, colors.WHITE, mouth_rect)

        # SEGUNDO: Desenhar dentes espaçados ao longo da largura
        num_teeth = 4  # Número de dentes
        tooth_color = colors.GRAY
        tooth_width = 10  # Largura individual de cada dente

        # Calcular espaçamento para distribuir os dentes uniformemente
        spacing = (mouth_width - (num_teeth * tooth_width)) / (num_teeth + 1)

        for i in range(num_teeth):
            # Posição do dente com espaçamento uniforme
            tooth_x = draw_x + 20 + spacing + i * (tooth_width + spacing)

            # Triângulo apontando para baixo (sobrepõe o branco)
            tooth_points = [
                (int(tooth_x), mouth_base_y),  # Canto superior esquerdo
                (int(tooth_x + tooth_width), mouth_base_y),  # Canto superior direito
                (
                    int(tooth_x + tooth_width / 2),
                    mouth_base_y + tooth_height,
                ),  # Ponta inferior (fixa)
            ]

            pygame.draw.polygon(surface, tooth_color, tooth_points)

        # Barra de vida
        self._draw_health_bar(surface, draw_x, draw_y)

    def _draw_health_bar(self, surface: pygame.Surface, x: int, y: int):
        """Desenha barra de vida acima do boss."""
        bar_width = self.w
        bar_height = 8
        bar_x = x
        bar_y = y - 20

        # Fundo
        pygame.draw.rect(
            surface, colors.DARK_GRAY, (bar_x, bar_y, bar_width, bar_height)
        )

        # Vida atual
        health_ratio = self.health / self.max_health
        health_width = int(bar_width * health_ratio)
        health_color = (
            colors.GREEN
            if health_ratio > 0.5
            else colors.YELLOW if health_ratio > 0.25 else colors.RED
        )
        pygame.draw.rect(
            surface, health_color, (bar_x, bar_y, health_width, bar_height)
        )

        # Borda
        pygame.draw.rect(
            surface, colors.WHITE, (bar_x, bar_y, bar_width, bar_height), width=1
        )
