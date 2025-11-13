import pygame
from .core.config import Config
from .core.state import StateManager
from .scenes.playing import PlayingScene
from .core.input import Input


class GameApp:
    def __init__(self):
        pygame.init()
        
        # Configurar modo de tela (fullscreen ou janela)
        if Config.FULLSCREEN:
            # Pegar resolução nativa do monitor
            display_info = pygame.display.Info()
            self.native_width = display_info.current_w
            self.native_height = display_info.current_h
            
            # Criar surface de jogo (tamanho virtual)
            self.game_surface = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
            
            # Criar tela fullscreen
            self.screen = pygame.display.set_mode(
                (self.native_width, self.native_height),
                pygame.FULLSCREEN
            )
            
            # Calcular escala para manter proporção
            scale_x = self.native_width / Config.SCREEN_WIDTH
            scale_y = self.native_height / Config.SCREEN_HEIGHT
            self.scale = min(scale_x, scale_y)  # Manter proporção
            
            # Calcular offsets para centralizar
            scaled_width = int(Config.SCREEN_WIDTH * self.scale)
            scaled_height = int(Config.SCREEN_HEIGHT * self.scale)
            self.offset_x = (self.native_width - scaled_width) // 2
            self.offset_y = (self.native_height - scaled_height) // 2
        else:
            # Modo janela normal
            self.game_surface = None
            self.screen = pygame.display.set_mode(
                (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT)
            )
            self.scale = 1.0
            self.offset_x = 0
            self.offset_y = 0
        
        pygame.display.set_caption("Structured Pygame Template")
        self.clock = pygame.time.Clock()
        self.states = StateManager()
        self.input = Input()
        self.states.push(PlayingScene(self))

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(Config.FPS) / 1000.0

            # event -> actions (we keep direct events for scenes that need
            # them)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break
                # ESC para sair do fullscreen
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                    break
                self.states.current().handle_event(event)

            # update & render
            if Config.FULLSCREEN and self.game_surface is not None:
                # Renderizar em surface virtual
                self.states.current().update(dt)
                self.states.current().render(self.game_surface)
                
                # Escalar e centralizar na tela real
                self.screen.fill((0, 0, 0))  # Fundo preto nas bordas
                scaled_surface = pygame.transform.smoothscale(
                    self.game_surface,
                    (int(Config.SCREEN_WIDTH * self.scale), int(Config.SCREEN_HEIGHT * self.scale))
                )
                self.screen.blit(scaled_surface, (self.offset_x, self.offset_y))
            else:
                # Renderização normal em janela
                self.states.current().update(dt)
                self.states.current().render(self.screen)
            
            pygame.display.flip()

        pygame.quit()
