"""Starliner arcade mission. Requires Python 3 and pygame; no external assets."""
import math
import random
from dataclasses import dataclass
import pygame



WIDTH, HEIGHT = 1280, 720
SPACE = pygame.Rect(30, 120, 1220, 455)
WHITE = (225, 236, 250)
CYAN = (76, 213, 240)
GOLD = (255, 205, 95)
RED = (250, 100, 105)
GREEN = (100, 230, 160)


@dataclass
class Waypoint:
    position: pygame.Vector2
    throttle: float
    stage: bool = False


class Rocket:
    def __init__(self, position, hull, tank, engine, shield):
        self.pos = pygame.Vector2(position)
        self.vel = pygame.Vector2()
        self.dry_mass = [7, 10, 14][hull]
        self.fuel = [85, 125, 170][tank]
        self.capacity = self.fuel
        self.power = [130, 180, 235][engine]
        self.burn_rate = [1.4, 2.0, 2.8][engine]
        self.shield = shield
        self.heat_limit = [95, 130, 170][shield]
        self.booster = True
        self.angle = 0
        self.throttle = 0

    @property
    def mass(self):
        return self.dry_mass + self.fuel * 0.045 + self.shield * 2 + (5 if self.booster else 0)

    @property
    def rect(self):
        return pygame.Rect(round(self.pos.x) - 12, round(self.pos.y) - 12, 24, 24)

    def stage(self):
        self.booster = False

    def fly(self, target, throttle, dt):
        # Arcade autopilot: accelerate toward a waypoint and brake on approach.
        self.throttle = throttle
        delta = target - self.pos
        distance = delta.length()
        if distance < 5:
            self.vel *= 0
            return True
        if self.fuel <= 0:
            self.throttle = 0
            return False
        acceleration = self.power / self.mass * (1 if self.booster else 0.58)
        speed_limit = (65 + self.power * 0.34) * throttle
        desired_speed = min(speed_limit, math.sqrt(2 * acceleration * max(0, distance - 2)))
        desired_velocity = delta.normalize() * desired_speed
        correction = desired_velocity - self.vel
        max_change = acceleration * throttle * dt
        if correction.length() > max_change:
            correction.scale_to_length(max_change)
        self.vel += correction
        self.fuel = max(0, self.fuel - self.burn_rate * throttle * dt)
        step = self.vel * dt
        if step.length() >= distance and step.dot(delta) > 0:
            self.pos = target.copy()
            self.vel *= 0
            return True
        self.pos += step
        self.angle = math.degrees(math.atan2(self.vel.y, self.vel.x)) if self.vel.length_squared() else self.angle
        return False


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('Starliner - Mission Planner')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 25)
        self.small = pygame.font.Font(None, 21)
        self.big = pygame.font.Font(None, 45)
        rng = random.Random(8)
        self.stars = [(rng.randrange(WIDTH), rng.randrange(100, 580), rng.choice([1, 1, 2])) for _ in range(120)]
        self.running = True
        self.reset()

    def reset(self):
        self.state = 'DESIGN'
        self.options = [1, 1, 1, 1, 0]
        self.buttons = []
        self.rocket = None
        self.notice = ''
        self.time = 0
        self.flip_left = 0
        self.dialog_index = 0
        self.dialog = [
            'Mission Control: Design your vehicle, then plot a route to the station.',
            'Click to add navigation points. Set throttle and booster release at each point.',
            'Avoid asteroids, dock with the ISS, and save fuel for the journey home.'
        ]

    def text(self, text, x, y, color=WHITE, large=False, small=False):
        font = self.big if large else self.small if small else self.font
        self.screen.blit(font.render(str(text), True, color), (x, y))

    def button(self, label, rect, action):
        rect = pygame.Rect(rect)
        hover = rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(self.screen, (55, 91, 120) if hover else (30, 50, 76), rect, border_radius=7)
        pygame.draw.rect(self.screen, CYAN, rect, 1, border_radius=7)
        image = self.font.render(label, True, WHITE)
        self.screen.blit(image, image.get_rect(center=rect.center))
        self.buttons.append((rect, action))

    def choose(self, index):
        self.options[index] = (self.options[index] + 1) % (2 if index == 4 else 3)

    def launch_rocket(self):
        self.rocket = Rocket((100, 350), *self.options[:4])
        self.returning = False
        self.station = pygame.Rect(1120, 290, 80, 100)
        self.entry = pygame.Rect(1090, 285, 95, 110)
        self.asteroids = [
            [pygame.Vector2(330, 330), 40, 0.3],
            [pygame.Vector2(570, 200), 49, 1.8],
            [pygame.Vector2(630, 460), 44, 3.0],
            [pygame.Vector2(880, 330), 55, 4.8]
        ]
        self.dialog_index = 0
        self.state = 'BRIEFING'

    def planner(self):
        self.state = 'PLAN'
        self.points = []
        self.selected = None
        self.default_throttle = 0.65
        self.default_stage = False
        self.notice = 'Add waypoints or launch directly. The destination is appended automatically.'

    def next_dialogue(self):
        self.dialog_index += 1
        if self.dialog_index >= len(self.dialog):
            self.planner()

    def add_point(self, position):
        for index, point in enumerate(self.points):
            if point.position.distance_to(position) < 16:
                self.selected = index
                return
        if len(self.points) >= 12:
            self.notice = 'Maximum 12 waypoints. Right-click a point to delete it.'
            return
        self.points.append(Waypoint(pygame.Vector2(position), self.default_throttle, self.default_stage))
        self.selected = len(self.points) - 1

    def change_throttle(self):
        values = [0.4, 0.65, 1.0]
        old = self.points[self.selected].throttle if self.selected is not None else self.default_throttle
        value = values[(min(range(3), key=lambda i: abs(values[i] - old)) + 1) % 3]
        self.default_throttle = value
        if self.selected is not None:
            self.points[self.selected].throttle = value

    def toggle_stage(self):
        if self.selected is None:
            self.default_stage = not self.default_stage
        else:
            point = self.points[self.selected]
            point.stage = not point.stage

    def clear_points(self):
        self.points = []
        self.selected = None

    def start_flight(self):
        goal = self.entry.center if self.returning else self.station.center
        self.route = [Waypoint(p.position.copy(), p.throttle, p.stage) for p in self.points]
        self.route.append(Waypoint(pygame.Vector2(goal), 0.65))
        self.route_index = 0
        self.rocket.vel *= 0
        self.state = 'FLIGHT'
        self.notice = 'Autopilot active. SPACE: pause. J: release booster now.'

    def asteroid_position(self, asteroid):
        position, radius, phase = asteroid
        offset = math.sin(self.time * 0.8 + phase) * 35 if self.options[4] else 0
        return position + pygame.Vector2(0, offset)

    def fail(self, reason):
        self.result = reason
        self.state = 'FAIL'

    def dock(self):
        self.rocket.pos = pygame.Vector2(self.station.center)
        self.rocket.vel *= 0
        self.state = 'DOCKED'

    def undock(self):
        # Mirror the map horizontally: the station is now on the left.
        self.rocket.pos.x = WIDTH - self.rocket.pos.x
        self.rocket.angle = 0
        self.station.x = WIDTH - self.station.right
        for asteroid in self.asteroids:
            asteroid[0].x = WIDTH - asteroid[0].x
        self.returning = True
        self.flip_left = 1.2
        self.planner()

    def begin_reentry(self):
        self.rocket.stage()
        self.state = 'REENTRY'
        self.altitude = 100.0
        self.descent = 4.0
        self.heat = 10.0
        self.bank = 0.0
        self.parachute = False
        self.capsule_x = 640.0
        self.notice = 'Hold LEFT/RIGHT or A/D to bank. P: deploy parachute below 25 km.'

    def deploy_chute(self):
        if self.altitude > 25:
            self.notice = 'Too high! Deploy the parachute at or below 25 km.'
        elif self.descent > 2.5:
            self.notice = 'Too fast! Bank harder to slow below 2.5 km/s.'
        else:
            self.parachute = True
            self.notice = 'Parachute deployed. Steer toward the green landing zone.'

    def update(self, dt):
        self.flip_left = max(0, self.flip_left - dt)
        if self.state == 'FLIGHT':
            self.time += dt
            point = self.route[self.route_index]
            reached = self.rocket.fly(point.position, point.throttle, dt)
            for asteroid in self.asteroids:
                if self.rocket.pos.distance_to(self.asteroid_position(asteroid)) < asteroid[1] + 12:
                    self.fail('Asteroid collision. Plot a route with more clearance.')
                    return
            if not SPACE.collidepoint(self.rocket.pos):
                self.fail('You left the navigation area.')
                return
            if not self.returning and self.rocket.rect.colliderect(self.station):
                self.dock()
                return
            if self.returning and self.rocket.rect.colliderect(self.entry):
                self.begin_reentry()
                return
            if reached:
                if point.stage:
                    self.rocket.stage()
                self.route_index += 1
                if self.route_index >= len(self.route):
                    self.begin_reentry() if self.returning else self.dock()
                    return
            if self.rocket.fuel <= 0:
                self.fail('Fuel exhausted. Try a shorter path, lower throttle, or larger tank.')
        elif self.state == 'REENTRY':
            keys = pygame.key.get_pressed()
            direction = int(keys[pygame.K_RIGHT] or keys[pygame.K_d]) - int(keys[pygame.K_LEFT] or keys[pygame.K_a])
            self.bank += (direction - self.bank) * min(1, dt * 4)
            self.capsule_x = max(110, min(1170, self.capsule_x + self.bank * 150 * dt))
            if self.parachute:
                self.descent = max(0.65, self.descent - 3.0 * dt)
                self.heat = max(0, self.heat - 18 * dt)
            else:
                drag = 0.06 + 0.15 * abs(self.bank) + 0.08 * (1 - self.altitude / 100)
                self.descent = max(1.2, self.descent - drag * dt)
                heating = self.descent ** 2 * 0.65 * (1 - 0.7 * abs(self.bank))
                self.heat = max(0, self.heat + (heating - 1.0 - self.rocket.shield * 0.5) * dt)
            self.altitude = max(0, self.altitude - self.descent * dt)
            if self.heat > self.rocket.heat_limit:
                self.fail('Heat shield failed. Bank more or choose a stronger shield.')
            elif self.altitude <= 0:
                if not self.parachute:
                    self.fail('Hard impact. Deploy your parachute before reaching the ground.')
                elif not 470 <= self.capsule_x <= 810:
                    self.fail('You landed outside the recovery zone. Steer toward the green marker.')
                else:
                    self.result = 'Splashdown successful! Crew recovered. Mission complete.'
                    self.state = 'WIN'

    def draw_rocket(self):
        rocket = self.rocket
        forward = pygame.Vector2(1, 0).rotate(rocket.angle)
        side = pygame.Vector2(-forward.y, forward.x)
        points = [rocket.pos + forward * 20, rocket.pos - forward * 13 + side * 11,
                  rocket.pos - forward * 13 - side * 11]
        pygame.draw.polygon(self.screen, WHITE, points)
        if rocket.booster:
            pygame.draw.circle(self.screen, GOLD, rocket.pos - forward * 16, 7)
        if self.state == 'FLIGHT':
            pygame.draw.line(self.screen, GOLD, rocket.pos - forward * 17,
                             rocket.pos - forward * (22 + 18 * rocket.throttle), 5)

    def draw_map(self):
        pygame.draw.rect(self.screen, (12, 20, 39), SPACE)
        for x, y, radius in self.stars:
            if SPACE.collidepoint(x, y):
                pygame.draw.circle(self.screen, (100, 125, 160), (x, y), radius)
        pygame.draw.rect(self.screen, (60, 90, 125), SPACE, 2)
        for asteroid in self.asteroids:
            center = self.asteroid_position(asteroid)
            pygame.draw.circle(self.screen, (104, 96, 98), center, asteroid[1])
            pygame.draw.circle(self.screen, (66, 62, 70), center + pygame.Vector2(9, -8), asteroid[1] // 3)
        pygame.draw.rect(self.screen, CYAN, self.station, 3)
        pygame.draw.line(self.screen, CYAN, (self.station.left - 20, self.station.centery),
                         (self.station.right + 20, self.station.centery), 8)
        self.text('ISS', self.station.x + 20, self.station.y - 25, CYAN)
        if self.returning:
            pygame.draw.rect(self.screen, GOLD, self.entry, 3)
            self.text('ENTRY', self.entry.x + 8, self.entry.y - 25, GOLD)
        if self.state in ('PLAN', 'FLIGHT', 'PAUSED'):
            points = self.points if self.state == 'PLAN' else self.route
            positions = [self.rocket.pos] + [p.position for p in points]
            if self.state != 'PLAN':
                positions = [self.rocket.pos] + [p.position for p in points[self.route_index:]]
            if len(positions) > 1:
                pygame.draw.lines(self.screen, (72, 135, 140), False, positions, 2)
            for i, point in enumerate(points):
                color = GOLD if self.state == 'PLAN' and i == self.selected else CYAN
                pygame.draw.circle(self.screen, color, point.position, 9, 2)
                self.text(f'{i + 1}: {int(point.throttle * 100)}%' + (' DROP' if point.stage else ''),
                          point.position.x + 12, point.position.y - 8, color, small=True)
        self.draw_rocket()
        self.text(f'Fuel: {self.rocket.fuel:.1f}/{self.rocket.capacity}   Mass: {self.rocket.mass:.1f}   '
                  f'Booster: {"attached" if self.rocket.booster else "released"}', 35, 88)

    def draw(self):
        self.buttons = []
        self.screen.fill((8, 13, 27))
        self.text('STARLINER / ' + self.state.replace('_', ' '), 35, 25, CYAN, large=True)
        if self.state == 'DESIGN':
            self.text('Choose your vehicle. Click each option to cycle.', 70, 100)
            labels = ['Hull', 'Fuel tank', 'Engine', 'Heat shield', 'Difficulty']
            choices = [['Light', 'Standard', 'Heavy'], ['Small', 'Medium', 'Large'],
                       ['Efficient', 'Balanced', 'Powerful'], ['Light', 'Standard', 'Reinforced'],
                       ['Normal: fixed asteroids', 'Hard: moving asteroids']]
            for i, label in enumerate(labels):
                self.text(label, 80, 170 + i * 65)
                self.button(choices[i][self.options[i]], (290, 155 + i * 65, 380, 45), lambda i=i: self.choose(i))
            notes = ['Light hull accelerates faster.', 'Larger tanks add fuel AND mass.',
                     'Powerful engines burn fuel faster.', 'Better shields tolerate more heat.',
                     'Releasing the booster saves mass but reduces thrust.']
            for i, note in enumerate(notes):
                self.text(note, 730, 170 + i * 55, GOLD, small=True)
            self.button('Continue', (420, 550, 320, 55), self.launch_rocket)
            self.text('Arcade model: not realistic orbital mechanics or spacecraft engineering.', 270, 635, small=True)
        elif self.state == 'BRIEFING':
            self.text('Mission briefing', 80, 160, large=True)
            self.text(self.dialog[self.dialog_index], 80, 260)
            self.text(f'{self.dialog_index + 1} / {len(self.dialog)}', 80, 320, GOLD)
            self.button('Next' if self.dialog_index < len(self.dialog) - 1 else 'Open planner',
                        (450, 420, 340, 60), self.next_dialogue)
        elif self.state in ('PLAN', 'FLIGHT', 'PAUSED', 'DOCKED'):
            self.draw_map()
            if self.state == 'PLAN':
                self.text('RETURN ROUTE' if self.returning else 'OUTBOUND ROUTE', 35, 590, GOLD)
                selected = self.points[self.selected] if self.selected is not None else None
                throttle = selected.throttle if selected else self.default_throttle
                stage = selected.stage if selected else self.default_stage
                self.button(f'Throttle: {int(throttle * 100)}%', (260, 585, 190, 42), self.change_throttle)
                self.button('Drop booster: ' + ('YES' if stage else 'NO'), (465, 585, 215, 42), self.toggle_stage)
                self.button('Clear route', (695, 585, 165, 42), self.clear_points)
                self.button('Launch route', (880, 585, 190, 42), self.start_flight)
                self.text('Left-click: add/select point | Right-click: delete point | Settings apply to selected point.', 35, 640, small=True)
                self.text(self.notice, 35, 670, GOLD, small=True)
            elif self.state == 'DOCKED':
                self.text('Docking confirmed. Depart to mirror the map and plan your return.', 50, 600, GREEN)
                self.button('Depart ISS', (900, 640, 250, 45), self.undock)
            else:
                self.text(self.notice, 35, 610, GOLD)
                self.text('Autopilot paused' if self.state == 'PAUSED' else f'Navigating to point {self.route_index + 1}', 35, 650)
            if self.flip_left > 0:
                self.text('MAP MIRRORED - PLAN YOUR RETURN', 300, 190, GOLD, large=True)
        elif self.state == 'REENTRY':
            pygame.draw.rect(self.screen, (35, 63, 102), (30, 135, 1220, 450))
            pygame.draw.rect(self.screen, (25, 95, 145), (30, 585, 1220, 70))
            pygame.draw.rect(self.screen, GREEN, (470, 585, 340, 14))
            y = 180 + (100 - self.altitude) * 3.8
            center = (round(self.capsule_x), round(y))
            pygame.draw.circle(self.screen, WHITE, center, 17)
            if self.parachute:
                canopy = pygame.Rect(center[0] - 45, center[1] - 90, 90, 65)
                pygame.draw.arc(self.screen, GOLD, canopy, 0, math.pi, 5)
                for dx in (-40, 40):
                    pygame.draw.line(self.screen, WHITE, (center[0] + dx, center[1] - 58), center, 1)
            else:
                pygame.draw.circle(self.screen, GOLD, (center[0], center[1] + 20), int(6 + self.heat / 10), 2)
            self.text(f'Altitude: {self.altitude:.1f} km   Descent: {self.descent:.2f} km/s   '
                      f'Heat: {self.heat:.0f}/{self.rocket.heat_limit}   Bank: {abs(self.bank):.0%}', 35, 95)
            self.text(self.notice, 35, 675, GOLD, small=True)
            self.text('RECOVERY ZONE', 550, 620, GREEN)
        elif self.state in ('WIN', 'FAIL'):
            self.text('MISSION COMPLETE' if self.state == 'WIN' else 'MISSION FAILED', 350, 220,
                      GREEN if self.state == 'WIN' else RED, large=True)
            self.text(self.result, 90, 330)
            self.button('Back to design', (450, 430, 340, 60), self.reset)
        pygame.display.flip()

    def handle(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif self.state in ('FLIGHT', 'PAUSED'):
                if event.key == pygame.K_SPACE:
                    self.state = 'PAUSED' if self.state == 'FLIGHT' else 'FLIGHT'
                elif event.key == pygame.K_j:
                    self.rocket.stage()
            elif self.state == 'REENTRY' and event.key == pygame.K_p:
                self.deploy_chute()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                for rect, callback in self.buttons:
                    if rect.collidepoint(event.pos):
                        callback()
                        return
                if self.state == 'PLAN' and SPACE.inflate(-32, -32).collidepoint(event.pos):
                    self.add_point(event.pos)
            elif event.button == 3 and self.state == 'PLAN':
                for i, point in enumerate(self.points):
                    if point.position.distance_to(event.pos) < 18:
                        self.points.pop(i)
                        self.selected = None
                        break

    def run(self):
        self.draw()
        while self.running:
            dt = min(self.clock.tick(60) / 1000, 0.04)
            for event in pygame.event.get():
                self.handle(event)
            self.update(dt)
            self.draw()
        pygame.quit()


if __name__ == '__main__':
    Game().run()
