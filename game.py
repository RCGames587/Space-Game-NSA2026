# Example file showing a circle moving on screen
import pygame
import pygame_menu

# pygame setup
pygame.init()
screen = pygame.display.set_mode((1280, 720))
pygame.display.set_caption("NSA2026 Game")

clock = pygame.time.Clock()
running = True
dt = 0

player_pos = pygame.Vector2(screen.get_width() / 2, screen.get_height() / 2)

def set_difficulty(value, difficulty):
    #setting certain weights
    pass

def start_the_game():
    # Do the job here !
    pass

menu = pygame_menu.Menu('Nasa Mission', 600, 400,
                       theme=pygame_menu.themes.THEME_BLUE)

menu.add.selector('Difficulty :', [('Normal',2),('Hard', 3), ('Easy', 1)], onchange=set_difficulty)
menu.add.button('Play', start_the_game)
menu.add.button('Quit', pygame_menu.events.EXIT)


while running:
    # poll for events
    # pygame.QUIT event means the user clicked X to close your window
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
    
    screen.fill("purple")

    menu.mainloop(screen)

    # flip() the display to put your work on screen
    pygame.display.flip()


    dt = clock.tick(60) / 1000

pygame.quit()
