"""Portrait Starliner prototype. Install pygame, then run this file."""
import math
import random
from dataclasses import dataclass
import pygame

W, H = 720, 900
MAP = pygame.Rect(20, 140, 680, 630)
WHITE, CYAN, GOLD = (228, 236, 250), (80, 215, 240), (255, 205, 100)
GREEN, RED = (100, 230, 160), (250, 105, 110)
pygame.display.set_caption("NSA2026 Game")

class MenuBackground:
    """Animation hook: replace update/draw without changing menu logic."""
    def __init__(self, size):
        self.width, self.height = size
        rng = random.Random(12)
        self.stars = [[rng.uniform(0, self.width), rng.uniform(0, self.height),
                       rng.uniform(15, 65)] for _ in range(100)]
        self.time = 0

    def update(self, dt):
        self.time += dt
        for star in self.stars:
            star[1] = (star[1] + star[2] * dt) % self.height

    def draw(self, surface):
        surface.fill((7, 12, 28))
        for x, y, speed in self.stars:
            pygame.draw.circle(surface, (100, 140, 190), (int(x), int(y)), 2 if speed > 45 else 1)
        pygame.draw.circle(surface, (22, 55, 89), (590, 810), 230)
        pygame.draw.circle(surface, (40, 100, 130), (590, 810), 230, 5)
        x = 350 + math.sin(self.time * .6) * 90
        y = 360 + math.cos(self.time * .8) * 20
        pygame.draw.polygon(surface, WHITE, [(x, y - 40), (x - 17, y + 25), (x + 17, y + 25)])
        pygame.draw.polygon(surface, GOLD, [(x - 10, y + 27), (x, y + 60 + math.sin(self.time * 18) * 8), (x + 10, y + 27)])


@dataclass
class Waypoint:
    position: pygame.Vector2
    throttle: float
    stage: bool = False


# name, mass, fuel, thrust, burn, heat tolerance are arcade balancing values.
CHOICES = [
    [('Light', 7), ('Standard', 10), ('Heavy', 14)],
    [('Small', 85), ('Medium', 125), ('Large', 170)],
    [('Efficient', 130, 1.4), ('Balanced', 180, 2.0), ('Powerful', 235, 2.8)],
    [('Light', 95, 0), ('Standard', 130, 2), ('Reinforced', 170, 4)],
    [('Normal', False), ('Hard', True)]
]


class Rocket:
    def __init__(self, position, choices):
        hull, tank, engine, shield, _ = choices
        self.pos = pygame.Vector2(position)
        self.vel = pygame.Vector2()
        self.dry_mass = CHOICES[0][hull][1] + CHOICES[3][shield][2]
        self.fuel = self.capacity = CHOICES[1][tank][1]
        self.power, self.burn = CHOICES[2][engine][1:]
        self.heat_limit = CHOICES[3][shield][1]
        self.shield = shield
        self.booster = True
        self.angle = -90

    @property
    def mass(self):
        return self.dry_mass + self.fuel * .045 + (5 if self.booster else 0)

    @property
    def rect(self):
        return pygame.Rect(round(self.pos.x) - 12, round(self.pos.y) - 12, 24, 24)

    def fly(self, point, dt):
        delta = point.position - self.pos
        distance = delta.length()
        if distance < 5:
            self.vel *= 0
            return True
        acceleration = self.power / self.mass * (1 if self.booster else .58)
        speed = min((65 + self.power * .34) * point.throttle,
                    math.sqrt(2 * acceleration * max(0, distance - 2)))
        change = delta.normalize() * speed - self.vel
        limit = acceleration * point.throttle * dt
        if change.length() > limit:
            change.scale_to_length(limit)
        self.vel += change
        self.fuel = max(0, self.fuel - self.burn * point.throttle * dt)
        step = self.vel * dt
        reached = step.length() >= distance and step.dot(delta) > 0
        self.pos = point.position.copy() if reached else self.pos + step
        if self.vel.length_squared():
            self.angle = math.degrees(math.atan2(self.vel.y, self.vel.x))
        if reached:
            self.vel *= 0
        return reached


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption('NSA2026 Mission Planner')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 26)
        self.small = pygame.font.Font(None, 22)
        self.big = pygame.font.Font(None, 48)
        self.background = MenuBackground((W, H))
        self.running = True
        self.buttons = []
        self.state = 'MAIN_MENU'
        self.modal = False
        self.options = [1, 1, 1, 1, 0]
        self.time = 0
        self.notice = ''
        self.rocket = None

    def text(self, message, x, y, color=WHITE, size='normal'):
        font = self.big if size == 'big' else self.small if size == 'small' else self.font
        self.screen.blit(font.render(str(message), True, color), (x, y))

    def wrap(self, message, x, y, width, color=WHITE):
        line = ''
        for word in message.split():
            test = (line + ' ' + word).strip()
            if self.small.size(test)[0] > width and line:
                self.text(line, x, y, color, 'small')
                y += 24
                line = word
            else:
                line = test
        self.text(line, x, y, color, 'small')
        return y + 24

    def button(self, title, rect, callback):
        rect = pygame.Rect(rect)
        color = (55, 90, 120) if rect.collidepoint(pygame.mouse.get_pos()) else (30, 50, 76)
        pygame.draw.rect(self.screen, color, rect, border_radius=7)
        pygame.draw.rect(self.screen, CYAN, rect, 1, border_radius=7)
        label = self.font.render(title, True, WHITE)
        self.screen.blit(label, label.get_rect(center=rect.center))
        self.buttons.append((rect, callback))

    def new_game(self):
        self.options = [1, 1, 1, 1, 0]
        self.returning = False
        self.launched = False
        self.time = 0
        self.station = pygame.Rect(275, 170, 170, 65)
        self.entry = pygame.Rect(280, 170, 160, 65)
        self.asteroids = [[pygame.Vector2(220, 580), 43, .2],
                          [pygame.Vector2(480, 450), 50, 1.8],
                          [pygame.Vector2(280, 330), 38, 3.0]]
        self.rocket = Rocket((360, 720), self.options)
        self.brief_index = 0
        self.state = 'BRIEFING'

    def briefing_next(self):
        self.brief_index += 1
        if self.brief_index == 3:
            self.planner()

    def planner(self):
        self.state = 'PLAN'
        self.points = []
        self.selected = None
        self.default_throttle = .65
        self.default_stage = False
        self.notice = 'Click the map to add points. The destination is automatic.'

    def open_design(self):
        if self.launched:
            self.notice = 'Vehicle design is locked after the first launch.'
            return
        self.draft = self.options.copy()
        self.modal = True

    def cycle(self, row, step):
        self.draft[row] = (self.draft[row] + step) % len(CHOICES[row])

    def close_design(self, apply):
        if apply:
            self.options = self.draft.copy()
            self.rocket = Rocket(self.rocket.pos, self.options)
        self.modal = False

    def change_throttle(self):
        target = self.points[self.selected] if self.selected is not None else None
        values = [.4, .65, 1.0]
        old = target.throttle if target else self.default_throttle
        value = values[(values.index(old) + 1) % 3]
        self.default_throttle = value
        if target:
            target.throttle = value

    def toggle_stage(self):
        if self.selected is None:
            self.default_stage = not self.default_stage
        else:
            p = self.points[self.selected]
            p.stage = not p.stage

    def clear(self):
        self.points = []
        self.selected = None

    def launch(self):
        self.launched = True
        destination = self.entry.center if self.returning else self.station.center
        self.route = [Waypoint(p.position.copy(), p.throttle, p.stage) for p in self.points]
        self.route.append(Waypoint(pygame.Vector2(destination), .65))
        self.route_index = 0
        self.state = 'FLIGHT'

    def asteroid_pos(self, asteroid):
        pos, radius, phase = asteroid
        offset = math.sin(self.time * .8 + phase) * 35 if self.options[4] else 0
        return pos + pygame.Vector2(offset, 0)

    def fail(self, message):
        self.result = message
        self.state = 'FAIL'

    def undock(self):
        # Portrait equivalent of flipping the screen: mirror top to bottom.
        self.rocket.pos.y = H - 90 - self.rocket.pos.y
        self.rocket.angle = -90
        self.station.y = H - 90 - self.station.bottom
        for asteroid in self.asteroids:
            asteroid[0].y = H - 90 - asteroid[0].y
        self.returning = True
        self.planner()
        self.notice = 'Map flipped vertically. Plot your return to the entry zone.'

    def reentry(self):
        self.state = 'REENTRY'
        self.rocket.booster = False
        self.altitude, self.descent, self.heat = 100., 4., 10.
        self.bank, self.capsule_x = 0., 360.
        self.parachute = False
        self.notice = 'A/D or arrows: bank and steer. P: parachute.'

    def deploy(self):
        if self.altitude > 25:
            self.notice = 'Too high: deploy at or below 25 km.'
        elif self.descent > 2.5:
            self.notice = 'Too fast: bank to slow below 2.5 km/s.'
        else:
            self.parachute = True
            self.notice = 'Steer into the green recovery zone.'

    def update(self, dt):
        if self.state == 'MAIN_MENU':
            self.background.update(dt)
            return
        if self.modal:
            return
        if self.state == 'FLIGHT':
            self.time += dt
            old = self.rocket.pos.copy()
            point = self.route[self.route_index]
            reached = self.rocket.fly(point, dt)
            for asteroid in self.asteroids:
                if self.rocket.pos.distance_to(self.asteroid_pos(asteroid)) < asteroid[1] + 12:
                    self.fail('Asteroid collision. Give your route more clearance.')
                    return
            # Test the FULL target rectangle, not distance to its center.
            # Expanded-rectangle segment test prevents skipping it between frames.
            target = self.entry if self.returning else self.station
            touching = self.rocket.rect.colliderect(target)
            crossed = bool(target.inflate(24, 24).clipline(tuple(old), tuple(self.rocket.pos)))
            if touching or crossed:
                self.rocket.vel *= 0
                if self.returning:
                    self.reentry()
                else:
                    self.rocket.pos = pygame.Vector2(self.station.center)
                    self.state = 'DOCKED'
                return
            if not MAP.collidepoint(self.rocket.pos):
                self.fail('Rocket left the navigation area.')
                return
            if self.rocket.fuel <= 0:
                self.fail('Fuel exhausted. Try a larger tank or shorter route.')
                return
            if reached:
                if point.stage:
                    self.rocket.booster = False
                self.route_index += 1
        elif self.state == 'REENTRY':
            keys = pygame.key.get_pressed()
            direction = int(keys[pygame.K_RIGHT] or keys[pygame.K_d]) - int(keys[pygame.K_LEFT] or keys[pygame.K_a])
            self.bank += (direction - self.bank) * min(1, dt * 4)
            self.capsule_x = max(65, min(655, self.capsule_x + self.bank * 90 * dt))
            if self.parachute:
                self.descent = max(.65, self.descent - 3 * dt)
                self.heat = max(0, self.heat - 18 * dt)
            else:
                drag = .06 + .15 * abs(self.bank) + .08 * (1 - self.altitude / 100)
                self.descent = max(1.2, self.descent - drag * dt)
                heating = self.descent ** 2 * .65 * (1 - .7 * abs(self.bank))
                self.heat = max(0, self.heat + (heating - 1 - self.rocket.shield * .5) * dt)
            self.altitude = max(0, self.altitude - self.descent * dt)
            if self.heat > self.rocket.heat_limit:
                self.fail('Heat shield failed. Bank more or fit a stronger shield.')
            elif self.altitude <= 0:
                if not self.parachute:
                    self.fail('Hard impact: deploy the parachute before landing.')
                elif not 240 <= self.capsule_x <= 480:
                    self.fail('Missed recovery zone. Steer toward the green marker.')
                else:
                    self.state = 'WIN'
                    self.result = 'Splashdown successful. Crew recovered!'

    def draw_design(self):
        # Block underlying controls; only modal buttons are interactive.
        self.buttons = []
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 180))
        self.screen.blit(shade, (0, 0))
        pygame.draw.rect(self.screen, (18, 30, 51), (40, 105, 640, 790), border_radius=14)
        pygame.draw.rect(self.screen, CYAN, (40, 105, 640, 790), 2, border_radius=14)
        self.text('ROCKET DESIGN', 75, 130, CYAN, 'big')
        self.text('Preview choices; Apply commits your design.', 75, 185)
        labels = ['Hull', 'Fuel tank', 'Engine', 'Heat shield', 'Difficulty']
        for i, label in enumerate(labels):
            y = 235 + i * 95
            item = CHOICES[i][self.draft[i]]
            self.text(label + ': ' + item[0], 80, y, GOLD)
            self.button('<', (490, y - 6, 65, 37), lambda i=i: self.cycle(i, -1))
            self.button('>', (565, y - 6, 65, 37), lambda i=i: self.cycle(i, 1))
            if i == 0:
                stats = f'Dry hull mass: {item[1]} units. Less mass = more acceleration.'
            elif i == 1:
                stats = f'Fuel: {item[1]} units. Full fuel mass: {item[1] * .045:.2f}.'
            elif i == 2:
                stats = f'Thrust: {item[1]} units. Burn: {item[2]:.1f} fuel/s at 100%.'
            elif i == 3:
                stats = f'Heat tolerance: {item[1]}. Added shield mass: {item[2]}.'
            else:
                stats = 'Asteroids move during flight.' if item[1] else 'Asteroids remain stationary.'
            self.wrap(stats, 80, y + 37, 550)
        preview = Rocket((0, 0), self.draft)
        self.text(f'Launch mass: {preview.mass:.2f} | Acceleration: {preview.power / preview.mass:.2f}', 80, 735, GREEN)
        self.text('Arcade values, not real spacecraft specifications.', 80, 770, size='small')
        self.button('Cancel', (90, 820, 240, 48), lambda: self.close_design(False))
        self.button('Apply design', (355, 820, 270, 48), lambda: self.close_design(True))

    def draw_map(self):
        pygame.draw.rect(self.screen, (12, 21, 40), MAP)
        for x in range(40, 700, 40):
            pygame.draw.line(self.screen, (20, 32, 50), (x, MAP.top), (x, MAP.bottom))
        for y in range(150, 770, 40):
            pygame.draw.line(self.screen, (20, 32, 50), (MAP.left, y), (MAP.right, y))
        for a in self.asteroids:
            pygame.draw.circle(self.screen, (105, 96, 100), self.asteroid_pos(a), a[1])
        # The filled rectangle is exactly the ISS collision target.
        pygame.draw.rect(self.screen, (35, 100, 125), self.station)
        pygame.draw.rect(self.screen, CYAN, self.station, 3)
        self.text('ISS: docking area', self.station.x + 10, self.station.y + 22)
        if self.returning:
            pygame.draw.rect(self.screen, (95, 73, 32), self.entry)
            pygame.draw.rect(self.screen, GOLD, self.entry, 3)
            self.text('ENTRY ZONE', self.entry.x + 20, self.entry.y + 22, GOLD)
        if self.state in ('PLAN', 'FLIGHT', 'PAUSED'):
            points = self.points if self.state == 'PLAN' else self.route[self.route_index:]
            positions = [self.rocket.pos] + [p.position for p in points]
            if len(positions) > 1:
                pygame.draw.lines(self.screen, (65, 145, 145), False, positions, 2)
            for i, p in enumerate(points):
                selected = self.state == 'PLAN' and i == self.selected
                color = GOLD if selected else CYAN
                pygame.draw.circle(self.screen, color, p.position, 9, 2)
                self.text(f'{i + 1}: {int(p.throttle * 100)}%' + (' DROP' if p.stage else ''),
                          min(p.position.x + 12, 570), p.position.y - 20, color, 'small')
        forward = pygame.Vector2(1, 0).rotate(self.rocket.angle)
        side = pygame.Vector2(-forward.y, forward.x)
        pos = self.rocket.pos
        pygame.draw.polygon(self.screen, WHITE, [pos + forward * 18, pos - forward * 12 + side * 10,
                                                pos - forward * 12 - side * 10])
        if self.rocket.booster:
            pygame.draw.circle(self.screen, GOLD, pos - forward * 15, 6)
        self.text(f'Fuel {self.rocket.fuel:.1f}/{self.rocket.capacity} | Mass {self.rocket.mass:.1f}', 25, 85)
        self.text('Booster: ' + ('attached' if self.rocket.booster else 'released'), 25, 112, GOLD, 'small')

    def draw(self):
        self.buttons = []
        self.screen.fill((8, 13, 27))
        if self.state == 'MAIN_MENU':
            self.background.draw(self.screen)
            self.text('STARLINER', 245, 135, CYAN, 'big')
            self.text('Plan. Dock. Return.', 267, 205)
            self.button('Play', (200, 510, 320, 62), self.new_game)
            self.button('Quit', (200, 595, 320, 62), self.quit)
            self.text('Arcade mission prototype', 255, 920, size='small')
            pygame.display.flip()
            return
        self.text('STARLINER / ' + self.state, 25, 25, CYAN, 'big')
        if self.state == 'BRIEFING':
            lines = ['Plot a route to the ISS. Touch any part of its docking rectangle to dock.',
                     'Open Rocket Design from the map before launching. Select waypoints to change throttle and staging.',
                     'After docking, the map flips vertically. Plan a return route, then survive reentry.']
            self.wrap(lines[self.brief_index], 65, 300, 590)
            self.text(f'{self.brief_index + 1} / 3', 65, 420, GOLD)
            self.button('Next' if self.brief_index < 2 else 'Open map', (180, 520, 360, 60), self.briefing_next)
        elif self.state in ('PLAN', 'FLIGHT', 'PAUSED', 'DOCKED'):
            self.draw_map()
            if self.state == 'PLAN':
                point = self.points[self.selected] if self.selected is not None else None
                throttle = point.throttle if point else self.default_throttle
                stage = point.stage if point else self.default_stage
                self.button(f'Throttle {int(throttle * 100)}%', (20, 790, 210, 45), self.change_throttle)
                self.button('Drop: ' + ('YES' if stage else 'NO'), (245, 790, 210, 45), self.toggle_stage)
                self.button('Clear', (470, 790, 230, 45), self.clear)
                self.button('Rocket Design' if not self.launched else 'Design locked', (20, 850, 325, 50), self.open_design)
                self.button('Launch route', (365, 850, 335, 50), self.launch)
                self.text('Left-click: add/select | Right-click: delete', 25, 915, size='small')
                self.wrap(self.notice, 25, 945, 665, GOLD)
            elif self.state == 'DOCKED':
                self.wrap('Docking confirmed. Depart to flip the map and plan your return.', 35, 805, 650, GREEN)
                self.button('Depart ISS', (180, 880, 360, 60), self.undock)
            else:
                self.wrap('SPACE: pause/resume | J: release booster | Esc: main menu', 25, 810, 665, GOLD)
                self.text('PAUSED' if self.state == 'PAUSED' else 'Autopilot active', 25, 890)
        elif self.state == 'REENTRY':
            pygame.draw.rect(self.screen, (30, 60, 100), (20, 160, 680, 650))
            pygame.draw.rect(self.screen, (25, 95, 145), (20, 810, 680, 90))
            pygame.draw.rect(self.screen, GREEN, (240, 810, 240, 15))
            self.text(f'Altitude {self.altitude:.1f} km | Speed {self.descent:.2f} km/s', 25, 90)
            self.text(f'Heat {self.heat:.0f}/{self.rocket.heat_limit} | Bank {abs(self.bank):.0%}', 25, 120, GOLD)
            center = (round(self.capsule_x), round(220 + (100 - self.altitude) * 5.7))
            pygame.draw.circle(self.screen, WHITE, center, 16)
            if self.parachute:
                pygame.draw.arc(self.screen, GOLD, (center[0] - 45, center[1] - 90, 90, 65), 0, math.pi, 5)
                for dx in (-40, 40):
                    pygame.draw.line(self.screen, WHITE, (center[0] + dx, center[1] - 58), center)
            self.text('RECOVERY ZONE', 285, 850, GREEN)
            self.wrap(self.notice, 25, 925, 665, GOLD)
        elif self.state in ('WIN', 'FAIL'):
            self.text('MISSION COMPLETE' if self.state == 'WIN' else 'MISSION FAILED', 155, 260,
                      GREEN if self.state == 'WIN' else RED, 'big')
            self.wrap(self.result, 65, 370, 590)
            self.button('Play again', (180, 510, 360, 60), self.new_game)
            self.button('Main menu', (180, 595, 360, 60), self.main_menu)
        if self.modal:
            self.draw_design()
        pygame.display.flip()

    def quit(self):
        self.running = False

    def main_menu(self):
        self.modal = False
        self.state = 'MAIN_MENU'

    def handle(self, event):
        if event.type == pygame.QUIT:
            self.quit()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.modal:
                    self.close_design(False)
                elif self.state == 'MAIN_MENU':
                    self.quit()
                else:
                    self.main_menu()
            elif not self.modal:
                if self.state in ('FLIGHT', 'PAUSED'):
                    if event.key == pygame.K_SPACE:
                        self.state = 'PAUSED' if self.state == 'FLIGHT' else 'FLIGHT'
                    elif event.key == pygame.K_j:
                        self.rocket.booster = False
                elif self.state == 'REENTRY' and event.key == pygame.K_p:
                    self.deploy()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                for rect, callback in self.buttons:
                    if rect.collidepoint(event.pos):
                        callback()
                        return
            if self.modal:
                return
            if self.state == 'PLAN' and MAP.inflate(-30, -30).collidepoint(event.pos):
                for i, point in enumerate(self.points):
                    if point.position.distance_to(event.pos) < 18:
                        if event.button == 1:
                            self.selected = i
                        elif event.button == 3:
                            self.points.pop(i)
                            self.selected = None
                        return
                if event.button == 1 and len(self.points) < 12:
                    self.points.append(Waypoint(pygame.Vector2(event.pos), self.default_throttle, self.default_stage))
                    self.selected = len(self.points) - 1

    def run(self):
        self.draw()
        while self.running:
            dt = min(self.clock.tick(60) / 1000, .04)
            for event in pygame.event.get():
                self.handle(event)
                # Refresh the active screen's hitboxes after every input transition.
                if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN) and self.running:
                    self.draw()
            self.update(dt)
            self.draw()
        pygame.quit()


if __name__ == '__main__':
    Game().run()
