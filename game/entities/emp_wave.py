import pygame


class EMPWave:
    """Onda visual do EMP que se expande da nave."""

    def __init__(self, center_x: float, center_y: float):
        self.center_x = center_x
        self.center_y = center_y
        self.radius = 0.0
        # Definir raio máximo dinamicamente para alcançar fora da tela
        screen = pygame.display.get_surface()
        if screen:
            w = screen.get_width()
            h = screen.get_height()
            # Distância até o canto mais distante a partir do centro
            dx = max(center_x, w - center_x)
            dy = max(center_y, h - center_y)
            far_corner_distance = (dx * dx + dy * dy) ** 0.5
            # Adicionar margem extra para garantir saída completa
            self.max_radius = far_corner_distance + 50.0
        else:
            # Fallback seguro
            self.max_radius = 1000.0
        self.expansion_speed = 400.0  # pixels por segundo
        self.dead = False
        self.line_width = 3

    def update(self, dt: float):
        """Atualiza a expansão da onda."""
        self.radius += self.expansion_speed * dt

        # Marcar como morta quando atingir o raio máximo
        if self.radius >= self.max_radius:
            self.dead = True

    def draw(self, surface: pygame.Surface):
        """Desenha a onda do EMP."""
        if self.dead:
            return

        # Cor azul elétrica
        color = (100, 150, 255)

        # Desenhar múltiplos círculos para efeito de espessura com fade
        if self.radius > 0:
            try:
                # Círculo principal
                pygame.draw.circle(
                    surface,
                    color,
                    (int(self.center_x), int(self.center_y)),
                    int(self.radius),
                    self.line_width,
                )

                # Círculo interno para efeito de brilho
                if self.radius > 5:
                    pygame.draw.circle(
                        surface,
                        color,
                        (int(self.center_x), int(self.center_y)),
                        int(self.radius - 5),
                        max(1, self.line_width - 1),
                    )
            except Exception:
                # Ignorar erros de desenho se a onda sair da tela
                pass

    def get_radius(self) -> float:
        """Retorna o raio atual da onda."""
        return self.radius

    def is_affecting_position(self, x: float, y: float, dt: float) -> bool:
        """Verifica se uma posição está sendo afetada pela onda neste frame.

        A onda afeta tudo que está dentro do raio atual (área completa, não apenas a borda).
        """
        if self.dead:
            return False

        # Calcular distância do ponto ao centro
        dx = x - self.center_x
        dy = y - self.center_y
        distance = (dx * dx + dy * dy) ** 0.5

        # Afetar tudo dentro do raio atual da onda
        # Isso cria um efeito contínuo sem "saltos"
        return distance <= self.radius
