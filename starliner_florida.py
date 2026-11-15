"""Starliner: Florida launch + portrait mission planner.
Install: python -m pip install pygame
Run: python starliner_florida.py
Arcade gameplay, NOT a real launch/orbital dynamics simulation.
"""
import math
import random
from dataclasses import dataclass
import pygame

W, H = 720, 1000
MAP = pygame.Rect(20, 140, 680, 630)
WHITE, CYAN, GOLD = (228, 236, 250), (80, 215, 240), (255, 205, 100)
GREEN, RED = (100, 230, 160), (250, 105, 110)
CHOICES = [
    [('Light', 7), ('Standard', 10), ('Heavy', 14)],
    [('Small', 85), ('Medium', 125), ('Large', 170)],
    [('Efficient', 130, 1.4), ('Balanced', 180, 2.0), ('Powerful', 235, 2.8)],
    [('Light', 95, 0), ('Standard', 130, 2), ('Reinforced', 170, 4)],
    [('Normal', False), ('Hard', True)],
]
ATMOSPHERE = 100.0
THRUST_SCALE = 1.65
RESERVE_GOAL = 30.0


def ascent_step(altitude, speed, fuel, dry_mass, power, burn, throttle, dt):
    """Shared by the playable ascent and full-throttle design forecast.

    Time, mass, thrust and drag are deliberately arcade-scaled.
    Fuel is shared with the later navigation stages.
    """
    mass = dry_mass + fuel * .045 + 5
    available = min(throttle, fuel / (burn * dt)) if fuel > 0 else 0
    thrust = power / mass * THRUST_SCALE * available
    gravity = 9.81 * (6371 / (6371 + max(0, altitude))) ** 2
    drag = .8 * speed * abs(speed) * math.exp(-max(0, altitude) / 24)
    speed += (thrust - gravity - drag) * .018 * dt
    altitude += speed * dt
    fuel = max(0., fuel - burn * available * dt)
    return altitude, speed, fuel


def forecast(rocket):
    altitude, speed, fuel, elapsed = 0., 0., rocket.capacity, 0.
    while elapsed < 180:
        altitude, speed, fuel = ascent_step(
            altitude, speed, fuel, rocket.dry_mass, rocket.power, rocket.burn, 1., .05)
        elapsed += .05
        if altitude >= ATMOSPHERE:
            return True, fuel, elapsed
        if altitude < -.002 or (fuel <= 0 and speed <= 0):
            break
    return False, fuel, elapsed


@dataclass
class Waypoint:
    position: pygame.Vector2
    throttle: float
    stage: bool = False


class MenuBackground:
    """Replace update/draw here to change the menu animation."""
    def __init__(self, size):
        self.width, self.height = size
        rng = random.Random(12)
        self.stars = [[rng.uniform(0, self.width), rng.uniform(0, self.height),
                       rng.uniform(15, 65)] for _ in range(100)]
        self.time = 0.

    def update(self, dt):
        self.time += dt
        for star in self.stars:
            star[1] = (star[1] + star[2] * dt) % self.height

    def draw(self, surface):
        surface.fill((7, 12, 28))
        for x, y, speed in self.stars:
            pygame.draw.circle(surface, (100, 140, 190), (int(x), int(y)), 2 if speed > 45 else 1)
        pygame.draw.circle(surface, (22, 55, 89), (590, 870), 230)
        pygame.draw.circle(surface, (40, 100, 130), (590, 870), 230, 5)
        x = 350 + math.sin(self.time * .6) * 90
        y = 360 + math.cos(self.time * .8) * 20
        pygame.draw.polygon(surface, WHITE, [(x, y - 40), (x - 17, y + 25), (x + 17, y + 25)])
        pygame.draw.polygon(surface, GOLD, [(x - 10, y + 27),
                            (x, y + 60 + math.sin(self.time * 18) * 8), (x + 10, y + 27)])


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
        self.window_size = (468, 650)
        self.window = pygame.display.set_mode(self.window_size)
        self.screen = pygame.Surface((W, H))
        pygame.display.set_caption('Starliner - Florida Launch')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 26)
        self.small = pygame.font.Font(None, 22)
        self.big = pygame.font.Font(None, 46)
        self.background = MenuBackground((W, H))
        self.running, self.modal = True, False
        self.buttons = []
        self.state = 'MAIN_MENU'
        self.options = [1, 1, 1, 1, 0]
        self.level = 1
        self.time = 0.
        self.notice = ''
        self.rocket = None
        self.launched = False

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

    def mouse_position(self, position=None):
        position = pygame.mouse.get_pos() if position is None else position
        return position[0] * W / self.window_size[0], position[1] * H / self.window_size[1]

    def button(self, title, rect, callback):
        rect = pygame.Rect(rect)
        color = (55, 90, 120) if rect.collidepoint(self.mouse_position()) else (30, 50, 76)
        pygame.draw.rect(self.screen, color, rect, border_radius=7)
        pygame.draw.rect(self.screen, CYAN, rect, 1, border_radius=7)
        label = self.font.render(title, True, WHITE)
        self.screen.blit(label, label.get_rect(center=rect.center))
        self.buttons.append((rect, callback))

    def new_game(self):
        self.options = [1, 1, 1, 1, 0]
        self.returning = self.launched = self.modal = False
        self.time = 0.
        self.station = pygame.Rect(275, 170, 170, 65)
        self.entry = pygame.Rect(280, 170, 160, 65)
        self.asteroids = [[pygame.Vector2(220, 580), 43, .2],
                          [pygame.Vector2(480, 450), 50, 1.8],
                          [pygame.Vector2(280, 330), 38, 3.0]]
        self.rocket = Rocket((360, 720), self.options)
        self.altitude = self.ascent_speed = self.elapsed = 0.
        self.ascent_throttle = 1.
        self.design_checked = False
        self.state = 'GROUND'
        self.notice = 'Welcome to Florida Base. Review Rocket Design before ignition.'
        self.preview = forecast(self.rocket)

    def open_design(self):
        if self.state != 'GROUND' or self.launched:
            self.notice = 'Design is available on the ground only.'
            return
        self.draft = self.options.copy()
        self.design_preview = forecast(Rocket((0, 0), self.draft))
        self.modal = True

    def cycle(self, row, step):
        self.draft[row] = (self.draft[row] + step) % len(CHOICES[row])
        self.design_preview = forecast(Rocket((0, 0), self.draft))

    def close_design(self, apply):
        if apply:
            self.options = self.draft.copy()
            self.rocket = Rocket((360, 720), self.options)
            self.preview = self.design_preview
            self.design_checked = True
            self.notice = 'Design committed. Check lift and reserve, then ignite.'
        self.modal = False

    def ignite(self):
        if not self.design_checked:
            self.notice = 'Open Rocket Design and Apply design to complete the ground check.'
            return
        self.state = 'ASCENT'
        self.launched = True
        self.altitude = self.ascent_speed = self.elapsed = 0.
        self.ascent_throttle = 1.
        self.notice = 'UP/W: increase throttle. DOWN/S: decrease. Reach 100 km.'

    def briefing_next(self):
        self.brief_index += 1
        if self.brief_index >= 3:
            self.planner()

    def planner(self):
        self.state = 'PLAN'
        self.points, self.selected = [], None
        self.default_throttle, self.default_stage = .65, False
        self.notice = 'Click to plot a safe route. The destination is automatic.'

    def change_throttle(self):
        target = self.points[self.selected] if self.selected is not None else None
        values = [.4, .65, 1.]
        value = values[(values.index(target.throttle if target else self.default_throttle) + 1) % 3]
        self.default_throttle = value
        if target:
            target.throttle = value

    def toggle_stage(self):
        if self.selected is None:
            self.default_stage = not self.default_stage
        else:
            self.points[self.selected].stage = not self.points[self.selected].stage

    def clear(self):
        self.points, self.selected = [], None

    def launch(self):
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
        self.result, self.state = message, 'FAIL'

    def undock(self):
        self.rocket.pos.y = H - 190 - self.rocket.pos.y
        self.rocket.angle = -90
        self.station.y = H - 190 - self.station.bottom
        for asteroid in self.asteroids:
            asteroid[0].y = H - 190 - asteroid[0].y
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

    def toggle_pause(self):
        if self.state == 'PAUSED':
            self.state = self.pause_from
        elif self.state in ('ASCENT', 'FLIGHT', 'REENTRY'):
            self.pause_from = self.state
            self.state = 'PAUSED'

    def update(self, dt):
        if self.state == 'MAIN_MENU':
            self.background.update(dt)
            return
        if self.modal:
            return
        if self.state == 'GROUND':
            self.time += dt
        elif self.state == 'ASCENT':
            keys = pygame.key.get_pressed()
            direction = int(keys[pygame.K_UP] or keys[pygame.K_w]) - int(keys[pygame.K_DOWN] or keys[pygame.K_s])
            self.ascent_throttle = max(.4, min(1., self.ascent_throttle + direction * .4 * dt))
            self.elapsed += dt
            self.time += dt
            self.altitude, self.ascent_speed, self.rocket.fuel = ascent_step(
                self.altitude, self.ascent_speed, self.rocket.fuel,
                self.rocket.dry_mass, self.rocket.power, self.rocket.burn, self.ascent_throttle, dt)
            if self.altitude >= ATMOSPHERE:
                self.rocket.pos = pygame.Vector2(360, 720)
                self.rocket.vel *= 0
                self.rocket.angle = -90
                self.brief_index = 0
                self.state = 'BRIEFING'
            elif self.altitude < 0:
                if self.ascent_speed < -.12:
                    self.fail('Launch failed: insufficient lift or a pad impact. Try a lighter hull or stronger engine.')
                else:
                    self.altitude, self.ascent_speed = 0., 0.
            elif self.rocket.fuel <= 0 and self.ascent_speed <= 0:
                self.fail('Ascent stalled below 100 km. Fit more fuel or reduce launch mass.')
            if self.state == 'ASCENT' and self.elapsed > 180:
                self.fail('Launch timed out. Use more throttle or redesign for stronger lift.')
        elif self.state == 'FLIGHT':
            self.time += dt
            old = self.rocket.pos.copy()
            point = self.route[self.route_index]
            reached = self.rocket.fly(point, dt)
            for asteroid in self.asteroids:
                center = self.asteroid_pos(asteroid)
                segment = self.rocket.pos - old
                t = max(0., min(1., (center - old).dot(segment) / segment.length_squared())) if segment.length_squared() else 0.
                if (old + segment * t).distance_to(center) < asteroid[1] + 12:
                    self.fail('Asteroid collision. Give your route more clearance.')
                    return
            target = self.entry if self.returning else self.station
            crossed = bool(target.inflate(24, 24).clipline(tuple(old), tuple(self.rocket.pos)))
            if self.rocket.rect.colliderect(target) or crossed:
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
                self.fail('Fuel exhausted. Save more fuel during ascent or choose a shorter route.')
                return
            if reached:
                if point.stage:
                    self.rocket.booster = False
                self.route_index += 1
                if self.route_index >= len(self.route):
                    self.fail('Destination missed. Plot the final approach again.')
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
                    self.state, self.result = 'WIN', 'Splashdown successful. Crew recovered!'

    def draw_design(self):
        self.buttons = []
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 195))
        self.screen.blit(shade, (0, 0))
        pygame.draw.rect(self.screen, (18, 30, 51), (35, 65, 650, 870), border_radius=14)
        pygame.draw.rect(self.screen, CYAN, (35, 65, 650, 870), 2, border_radius=14)
        self.text('GROUND / ROCKET DESIGN', 65, 92, CYAN, 'big')
        self.text('Build for ascent AND the trip home.', 65, 148)
        for i, label in enumerate(['Hull', 'Fuel tank', 'Engine', 'Heat shield', 'Difficulty']):
            y = 200 + i * 93
            item = CHOICES[i][self.draft[i]]
            self.text(label + ': ' + item[0], 70, y, GOLD)
            self.button('<', (490, y - 6, 65, 37), lambda i=i: self.cycle(i, -1))
            self.button('>', (565, y - 6, 65, 37), lambda i=i: self.cycle(i, 1))
            if i == 0:
                stats = f'Hull mass: {item[1]}. Lower mass helps lift off.'
            elif i == 1:
                stats = f'Fuel: {item[1]}. Fuel adds {item[1] * .045:.2f} mass when full.'
            elif i == 2:
                stats = f'Thrust: {item[1]}. Burn: {item[2]:.1f} fuel/s at full throttle.'
            elif i == 3:
                stats = f'Heat tolerance: {item[1]}. Added mass: {item[2]}.'
            else:
                stats = 'Asteroids move during flight.' if item[1] else 'Asteroids remain stationary.'
            self.wrap(stats, 70, y + 36, 560)
        rocket = Rocket((0, 0), self.draft)
        twr = rocket.power * THRUST_SCALE / (rocket.mass * 9.81)
        ok, remaining, duration = self.design_preview
        self.text(f'Launch mass {rocket.mass:.2f} | Lift ratio {twr:.2f} (needs > 1)', 70, 680, GREEN if twr > 1 else RED)
        self.text('100 km forecast: ' + (f'{duration:.0f}s / {remaining:.1f} fuel left' if ok else 'CANNOT CLEAR ATMOSPHERE'), 70, 718, GREEN if ok else RED)
        self.text(f'Reserve target: {RESERVE_GOAL:.0f}+ fuel for navigation (not guaranteed)', 70, 751, GOLD)
        self.wrap('Forecast assumes full throttle. More shield protects reentry but adds mass. These are arcade values, not real spacecraft specifications.', 70, 790, 565)
        self.button('Cancel', (70, 870, 240, 45), lambda: self.close_design(False))
        self.button('Apply design', (330, 870, 310, 45), lambda: self.close_design(True))

    def draw_launch(self):
        ground = self.state == 'GROUND'
        altitude = 0 if ground else self.altitude
        fade = max(0., min(1., altitude / ATMOSPHERE))
        color = tuple(round(a + (b - a) * fade) for a, b in zip((45, 120, 180), (6, 10, 27)))
        pygame.draw.rect(self.screen, color, (20, 145, 680, 600), border_radius=10)
        if altitude > 25:
            rng = random.Random(8)
            for _ in range(65):
                pygame.draw.circle(self.screen, (150, 175, 200), (rng.randrange(30, 690), rng.randrange(160, 720)), 1)
        if altitude < 12:
            pad_y = int(675 + altitude * 40)
            pygame.draw.rect(self.screen, (28, 95, 110), (20, pad_y, 680, 70))
            pygame.draw.rect(self.screen, (55, 104, 71), (20, pad_y, 460, 70))
            pygame.draw.rect(self.screen, (110, 120, 132), (280, pad_y - 8, 165, 16))
            pygame.draw.rect(self.screen, (65, 75, 92), (285, pad_y - 155, 20, 150))
            for dy in range(20, 155, 30):
                pygame.draw.line(self.screen, (155, 165, 175), (285, pad_y - dy), (305, pad_y - dy - 25), 3)
            self.text('FLORIDA BASE', 45, min(710, pad_y + 20), WHITE, 'small')
        if not ground:
            for i in range(4):
                cy = 180 + ((i * 161 + self.elapsed * 55) % 540)
                if altitude < 28:
                    pygame.draw.ellipse(self.screen, (165, 199, 216), (55 + i * 150, cy, 100, 25))
        rocket_y = 615 if ground else 465 + max(0, 1 - altitude / 5) * 150
        x = 370
        if not ground and self.rocket.fuel > 0:
            length = 40 + self.ascent_throttle * 65 + math.sin(self.time * 45) * 10
            pygame.draw.polygon(self.screen, GOLD, [(x - 15, rocket_y + 28), (x, rocket_y + length), (x + 15, rocket_y + 28)])
            pygame.draw.polygon(self.screen, (255, 130, 65), [(x - 7, rocket_y + 28), (x, rocket_y + length * .7), (x + 7, rocket_y + 28)])
        pygame.draw.polygon(self.screen, WHITE, [(x, rocket_y - 75), (x - 18, rocket_y - 35), (x - 18, rocket_y + 30), (x + 18, rocket_y + 30), (x + 18, rocket_y - 35)])
        pygame.draw.polygon(self.screen, CYAN, [(x - 18, rocket_y), (x - 34, rocket_y + 35), (x - 18, rocket_y + 28)])
        pygame.draw.polygon(self.screen, CYAN, [(x + 18, rocket_y), (x + 34, rocket_y + 35), (x + 18, rocket_y + 28)])
        pygame.draw.circle(self.screen, (35, 80, 110), (x, int(rocket_y - 25)), 9)
        self.text('FLORIDA / PRE-LAUNCH' if ground else 'ASCENT / LEAVING EARTH', 35, 90, GOLD)
        if ground:
            ok, reserve, duration = self.preview
            self.text('1. Review design   2. Confirm lift   3. Ignite', 35, 770, CYAN)
            self.text('Atmosphere forecast: ' + ('PASS' if ok else 'FAIL'), 35, 805, GREEN if ok else RED)
            self.text(f'Estimated fuel at 100 km: {reserve:.1f}' if ok else 'Change your design before launch.', 35, 835, GOLD)
            self.button('Rocket Design', (25, 880, 320, 52), self.open_design)
            self.button('Ignition / Take off', (365, 880, 330, 52), self.ignite)
            self.wrap(self.notice, 30, 949, 660, GOLD)
        else:
            self.text(f'Altitude {altitude:.1f} / 100 km | Climb {self.ascent_speed:.2f} km/s', 35, 770)
            self.text(f'Throttle {self.ascent_throttle:.0%} | Fuel {self.rocket.fuel:.1f}/{self.rocket.capacity}', 35, 805, GOLD)
            pygame.draw.rect(self.screen, (35, 48, 67), (35, 847, 650, 16))
            pygame.draw.rect(self.screen, CYAN, (35, 847, round(650 * min(1, altitude / 100)), 16))
            self.wrap(self.notice, 35, 890, 640, CYAN)
            self.text('SPACE: pause | ESC: main menu | Design locked', 35, 958, size='small')

    def draw_map(self):
        pygame.draw.rect(self.screen, (12, 21, 40), MAP)
        for x in range(40, 700, 40):
            pygame.draw.line(self.screen, (20, 32, 50), (x, MAP.top), (x, MAP.bottom))
        for y in range(150, 770, 40):
            pygame.draw.line(self.screen, (20, 32, 50), (MAP.left, y), (MAP.right, y))
        for a in self.asteroids:
            pygame.draw.circle(self.screen, (105, 96, 100), self.asteroid_pos(a), a[1])
        pygame.draw.rect(self.screen, (35, 100, 125), self.station)
        pygame.draw.rect(self.screen, CYAN, self.station, 3)
        self.text('ISS: docking area', self.station.x + 10, self.station.y + 22)
        if self.returning:
            pygame.draw.rect(self.screen, (95, 73, 32), self.entry)
            pygame.draw.rect(self.screen, GOLD, self.entry, 3)
            self.text('ENTRY ZONE', self.entry.x + 20, self.entry.y + 22, GOLD)
        if self.state in ('PLAN', 'FLIGHT'):
            points = self.points if self.state == 'PLAN' else self.route[self.route_index:]
            positions = [self.rocket.pos] + [p.position for p in points]
            if len(positions) > 1:
                pygame.draw.lines(self.screen, (65, 145, 145), False, positions, 2)
            for i, p in enumerate(points):
                color = GOLD if self.state == 'PLAN' and i == self.selected else CYAN
                pygame.draw.circle(self.screen, color, p.position, 9, 2)
                self.text(f'{i + 1}: {p.throttle:.0%}' + (' DROP' if p.stage else ''), min(p.position.x + 12, 570), p.position.y - 20, color, 'small')
        forward = pygame.Vector2(1, 0).rotate(self.rocket.angle)
        side = pygame.Vector2(-forward.y, forward.x)
        pos = self.rocket.pos
        pygame.draw.polygon(self.screen, WHITE, [pos + forward * 18, pos - forward * 12 + side * 10, pos - forward * 12 - side * 10])
        if self.rocket.booster:
            pygame.draw.circle(self.screen, GOLD, pos - forward * 15, 6)
        self.text(f'Fuel {self.rocket.fuel:.1f}/{self.rocket.capacity} | Mass {self.rocket.mass:.1f}', 25, 85)
        self.text('Booster: ' + ('attached' if self.rocket.booster else 'released'), 25, 112, GOLD, 'small')

    def present(self):
        pygame.transform.smoothscale(self.screen, self.window_size, self.window)
        pygame.display.flip()

    def draw(self):
        self.buttons = []
        self.screen.fill((8, 13, 27))
        if self.state == 'MAIN_MENU':
            self.background.draw(self.screen)
            self.text('STARLINER', 245, 135, CYAN, 'big')
            self.text('Launch. Plan. Dock. Return.', 240, 205)
            self.button('Play / Florida Base', (180, 510, 360, 62), self.new_game)
            self.button('Quit', (180, 595, 360, 62), self.quit)
            self.text('Arcade mission prototype', 255, 935, size='small')
        elif self.state == 'PAUSED':
            self.text('MISSION PAUSED', 205, 260, CYAN, 'big')
            self.text('Simulation stopped. Press SPACE to resume.', 155, 350)
            self.button('Resume', (180, 450, 360, 60), self.toggle_pause)
            self.button('Main menu', (180, 535, 360, 60), self.main_menu)
        else:
            self.text('STARLINER / ' + self.state, 25, 25, CYAN, 'big')
            if self.state in ('GROUND', 'ASCENT'):
                self.draw_launch()
            elif self.state == 'BRIEFING':
                lines = [f'Atmosphere cleared! You reached 100 km with {self.rocket.fuel:.1f} fuel remaining. The next phase switches to arcade space navigation.',
                         'Plot a route to the ISS. Touch any part of its docking rectangle to dock. Select waypoints to change throttle or drop your booster.',
                         'Design is now locked. After docking, the map flips vertically. Plot your return, then bank through reentry and deploy the parachute.']
                self.wrap(lines[self.brief_index], 65, 300, 590)
                self.text(f'{self.brief_index + 1} / 3', 65, 440, GOLD)
                self.button('Next' if self.brief_index < 2 else 'Open map', (180, 520, 360, 60), self.briefing_next)
            elif self.state in ('PLAN', 'FLIGHT', 'DOCKED'):
                self.draw_map()
                if self.state == 'PLAN':
                    point = self.points[self.selected] if self.selected is not None else None
                    throttle = point.throttle if point else self.default_throttle
                    stage = point.stage if point else self.default_stage
                    self.button(f'Throttle {throttle:.0%}', (20, 790, 210, 45), self.change_throttle)
                    self.button('Drop: ' + ('YES' if stage else 'NO'), (245, 790, 210, 45), self.toggle_stage)
                    self.button('Clear', (470, 790, 230, 45), self.clear)
                    self.text('Vehicle design locked after takeoff', 25, 861, GOLD)
                    self.button('Launch route', (365, 850, 335, 50), self.launch)
                    self.text('Left-click: add/select | Right-click: delete', 25, 915, size='small')
                    self.wrap(self.notice, 25, 945, 665, GOLD)
                elif self.state == 'DOCKED':
                    self.wrap('Docking confirmed. Depart to flip the map and plan your return.', 35, 805, 650, GREEN)
                    self.button('Depart ISS', (180, 880, 360, 60), self.undock)
                else:
                    self.wrap('SPACE: pause/resume | J: release booster | Esc: main menu', 25, 810, 665, GOLD)
                    self.text('Autopilot active', 25, 890)
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
                self.text('MISSION COMPLETE' if self.state == 'WIN' else 'MISSION FAILED', 155, 260, GREEN if self.state == 'WIN' else RED, 'big')
                self.wrap(self.result, 65, 370, 590)
                self.button('Retry from Florida', (180, 510, 360, 60), self.new_game)
                self.button('Main menu', (180, 595, 360, 60), self.main_menu)
        if self.modal:
            self.draw_design()
        self.present()

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
                if event.key == pygame.K_SPACE:
                    self.toggle_pause()
                elif self.state == 'FLIGHT' and event.key == pygame.K_j:
                    self.rocket.booster = False
                elif self.state == 'REENTRY' and event.key == pygame.K_p:
                    self.deploy()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            position = self.mouse_position(event.pos)
            if event.button == 1:
                for rect, callback in self.buttons:
                    if rect.collidepoint(position):
                        callback()
                        return
            if self.modal:
                return
            if self.state == 'PLAN' and MAP.inflate(-30, -30).collidepoint(position):
                for i, point in enumerate(self.points):
                    if point.position.distance_to(position) < 18:
                        if event.button == 1:
                            self.selected = i
                        elif event.button == 3:
                            self.points.pop(i)
                            self.selected = None
                        return
                if event.button == 1 and len(self.points) < 12:
                    self.points.append(Waypoint(pygame.Vector2(position), self.default_throttle, self.default_stage))
                    self.selected = len(self.points) - 1

    def run(self):
        self.draw()
        while self.running:
            dt = min(self.clock.tick(60) / 1000, .04)
            for event in pygame.event.get():
                self.handle(event)
                if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN) and self.running:
                    self.draw()
            if not self.running:
                break
            self.update(dt)
            self.draw()
        pygame.quit()


if __name__ == '__main__':
    Game().run()
