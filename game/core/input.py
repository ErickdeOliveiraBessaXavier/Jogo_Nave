import pygame

KEYMAP = {
    pygame.K_LEFT: "move_left",
    pygame.K_a: "move_left",
    pygame.K_RIGHT: "move_right",
    pygame.K_d: "move_right",
    pygame.K_UP: "move_up",
    pygame.K_w: "move_up",
    pygame.K_DOWN: "move_down",
    pygame.K_s: "move_down",
    pygame.K_SPACE: "shoot",
    pygame.K_RETURN: "shoot",
    pygame.K_p: "pause",
    pygame.K_r: "restart",
    pygame.K_ESCAPE: "quit",
}


class Input:
    def poll_events(self) -> set[str]:
        actions: set[str] = set()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                actions.add("quit")
            elif event.type == pygame.KEYDOWN:
                if event.key in KEYMAP:
                    actions.add(KEYMAP[event.key])
        return actions

    def poll_held(self) -> set[str]:
        held: set[str] = set()
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            held.add("hold_left")
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            held.add("hold_right")
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            held.add("hold_up")
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            held.add("hold_down")
        if keys[pygame.K_SPACE] or keys[pygame.K_RETURN]:
            held.add("hold_shoot")
        return held
