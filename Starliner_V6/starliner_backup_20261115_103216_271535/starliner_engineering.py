"""Starliner -- Florida engineering campaign and sandbox (Python 3.9+).

Run: python starliner_engineering.py
Engineering campaign uses starliner_campaign*.py and starliner_engineering_data.py.
Original flight game remains available through the sandbox and --legacy-game.
Tests (no Pygame needed): python starliner_engineering.py --self-test
Balance report: python starliner_engineering.py --balance-report

User-supplied component IDs, names and prices are retained. ALL engineering
specifications below are invented, tunable ARCADE values, NOT vehicle data.
Yes/No labels are intentionally ignored. The original Florida file is untouched.
Only Pygame is an external dependency; tests/model/persistence use the stdlib.
"""
import argparse
import itertools
import json
import math
import os
import random
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

TITLE = 'Starliner'
W, H = 720, 1000
CATEGORIES = ('Fuel', 'Navigation', 'Structure', 'Power', 'Communications', 'Lifetime')
LEVELS = ('Fuel System', 'Distance / Navigation', 'Structural Mass',
          'Electrical Power', 'Communications', 'Mission Lifetime', 'Budget Optimization')
SHORT = ('FUEL', 'NAV', 'MASS', 'POWER', 'COMMS', 'LIFE', 'COST')
WHITE, CYAN, GOLD = (228, 236, 250), (80, 215, 240), (255, 205, 100)
GREEN, RED = (100, 230, 160), (250, 105, 110)
SCHEMA_VERSION, CATALOG_VERSION = 1, 1
MISSION = dict(id='florida_engineering', title=TITLE, distance_km=4000.,
               duration_h=96., budget_m=119, min_reserve=35., max_dry_mass=25.,
               atmosphere_km=100., clock_h_per_s=.25, solar_duty=.75)
SAVE_PATH = Path.home() / '.starliner' / 'engineering_save.json'
ENGINE_POWER, ENGINE_BURN, BASE_MASS, BOOSTER_MASS = 250., 2.3, 4., 5.
THRUST_SCALE, FUEL_MASS = 1.9, .045
pygame = None


@dataclass(frozen=True)
class Component:
    id: str
    category: str
    name: str
    cost_m: int
    mass: float
    specs: dict
    explanation: str


def component(cid, cat, name, price, mass, explanation, **specs):
    return Component(cid, cat, name, price, mass, specs, explanation)


# Costs are in millions of dollars; mass/thrust/fuel are arcade units.
# Electrical quantities are kW/kWh; range is km; life support uses mission hours.
COMPONENTS = (
    component('F1','Fuel','Compact Tank',2,1.,'Low mass; too little mission reserve.',fuel=80.),
    component('F2','Fuel','Lightweight Tank',3,.5,'Efficient packaging, limited reserve.',fuel=120.),
    component('F3','Fuel','Dragon Tank System',5,2.,'Balanced capacity and launch mass.',fuel=185.),
    component('F4','Fuel','Oversized Tank',8,7.,'More fuel, but a slower and heavier launch.',fuel=260.),
    component('N1','Navigation','Basic GPS',1,.2,'Limited operating range and guidance.',range_km=600.,draw=.15,guidance=.45),
    component('N2','Navigation','Radar Navigation',3,.4,'Better guidance, still short range.',range_km=1500.,draw=.35,guidance=.7),
    component('N3','Navigation','Dragon Navigation Suite',8,.7,'Mission-range guidance.',range_km=5000.,draw=.7,guidance=1.),
    component('N4','Navigation','Advanced Navigation',20,1.3,'Faster guidance; more electrical demand.',range_km=9000.,draw=1.4,guidance=1.15),
    component('M1','Structure','Steel Frame',10,16.,'Heavy hull with limited supported wet mass.',support=22.,heat=110.),
    component('M2','Structure','Aluminum Frame',15,11.,'Lighter hull, modest load capacity.',support=27.,heat=125.),
    component('M3','Structure','Dragon Lightweight Structure',25,7.,'Low dry mass and strong support.',support=44.,heat=145.),
    component('M4','Structure','Titanium Frame',50,15.,'Strong and heat resistant, but heavy.',support=55.,heat=175.),
    component('P1','Power','Compact Solar Array',8,.8,'Small output and little stored energy.',generation=1.,battery=8.,peak=2.),
    component('P2','Power','Battery Pack',14,2.,'Finite stored energy; no solar recharge.',generation=0.,battery=400.,peak=8.),
    component('P3','Power','Dragon Solar Array',25,1.5,'Sustained solar generation and reserve.',generation=6.5,battery=80.,peak=8.),
    component('P4','Power','Oversized Solar Array',40,7.,'High generation, high mass and cost.',generation=10.,battery=60.,peak=12.),
    component('C1','Communications','Basic Radio',1,.2,'Low power, limited communications range.',range_km=500.,draw=.1),
    component('C2','Communications','Short-Range Antenna',4,.4,'Mission-capable range, modest power.',range_km=4500.,draw=.3),
    component('C3','Communications','Dragon Communications Suite',12,.5,'Additional range and power demand.',range_km=6000.,draw=.8),
    component('C4','Communications','Advanced Communications',30,2.,'Longest range; substantial electrical load.',range_km=10000.,draw=2.),
    component('L1','Lifetime','Basic Life Support',15,1.,'Short-duration provisions.',hours=24.,draw=1.),
    component('L2','Lifetime','Extended Life Support',35,1.8,'Improved but below mission duration.',hours=72.,draw=1.5),
    component('L3','Lifetime','Dragon Life Support',60,2.5,'Mission-duration provisions.',hours=120.,draw=2.),
    component('L4','Lifetime','Long-Duration System',120,5.,'Long endurance, high load and mass.',hours=240.,draw=3.),
)
CATALOG = {c.id: c for c in COMPONENTS}
BY_CATEGORY = {cat: tuple(c for c in COMPONENTS if c.category == cat) for cat in CATEGORIES}
DEFAULT = dict(zip(CATEGORIES, ('F1','N1','M1','P1','C1','L1')))
SANDBOX_DEFAULT = dict(zip(CATEGORIES, ('F3','N3','M3','P3','C3','L3')))


def check_config(config):
    if not isinstance(config, dict) or set(config) != set(CATEGORIES):
        raise ValueError('A build needs exactly the six component categories.')
    for cat, cid in config.items():
        if not isinstance(cid, str) or cid not in CATALOG or CATALOG[cid].category != cat:
            raise ValueError(f'Unknown or wrong-category component: {cat}={cid!r}')


def ascent_step(altitude, speed, fuel, dry_mass, throttle, dt, control=1.):
    mass = dry_mass + fuel * FUEL_MASS + BOOSTER_MASS
    used = min(fuel, ENGINE_BURN * throttle * dt)
    actual = used / (ENGINE_BURN * dt)
    thrust = ENGINE_POWER / mass * THRUST_SCALE * actual * control
    gravity = 9.81 * (6371 / (6371 + max(0., altitude))) ** 2
    drag = .8 * speed * abs(speed) * math.exp(-max(0., altitude) / 24)
    speed += (thrust - gravity - drag) * .018 * dt
    return altitude + speed * dt, speed, max(0., fuel - used)


@lru_cache(maxsize=1024)
def ascent_forecast(dry_mass, fuel):
    altitude = speed = elapsed = 0.
    initial = fuel
    while elapsed < 180:
        altitude, speed, fuel = ascent_step(altitude, speed, fuel, dry_mass, 1., .08)
        elapsed += .08
        if altitude >= MISSION['atmosphere_km']:
            return True, fuel, elapsed
        if altitude < -.002 or fuel <= 0 and speed <= 0:
            break
    return False, fuel, elapsed


def metrics(config):
    check_config(config)
    parts = {cat: CATALOG[config[cat]] for cat in CATEGORIES}
    f,n,m,p,c,l = (parts[cat] for cat in CATEGORIES)
    dry = BASE_MASS + sum(part.mass for part in parts.values())
    wet = dry + f.specs['fuel'] * FUEL_MASS + BOOSTER_MASS
    demand = .8 + n.specs['draw'] + c.specs['draw'] + l.specs['draw']
    average = p.specs['generation'] * MISSION['solar_duty']
    reach, reserve, launch_seconds = ascent_forecast(dry, f.specs['fuel'])
    ascent_hours = launch_seconds * MISSION['clock_h_per_s']
    launch_energy = p.specs['battery'] - demand * ascent_hours
    end_energy = launch_energy + min(0., average - demand) * max(0., MISSION['duration_h'] - ascent_hours)
    return dict(cost_m=sum(part.cost_m for part in parts.values()), dry=dry, wet=wet,
                fuel=f.specs['fuel'], support=m.specs['support'], heat=m.specs['heat'],
                nav_range=n.specs['range_km'], comm_range=c.specs['range_km'],
                guidance=n.specs['guidance'], demand=demand, generation=p.specs['generation'],
                average_generation=average, battery=p.specs['battery'], peak=p.specs['peak'],
                end_energy=end_energy, launch_energy=launch_energy, lifetime=l.specs['hours'],
                lift=ENGINE_POWER * THRUST_SCALE / (wet * 9.81))


@dataclass(frozen=True)
class Result:
    level: int
    passed: bool
    message: str


def validate(config, include_budget=True):
    v = metrics(config)
    reach, reserve, elapsed = ascent_forecast(v['dry'], v['fuel'])
    distance, hours = MISSION['distance_km'], MISSION['duration_h']
    results = [
        Result(1, reach and reserve >= MISSION['min_reserve'],
               f"100 km: {'YES' if reach else 'NO'}; reserve {reserve:.1f} / {MISSION['min_reserve']:.0f} required"),
        Result(2, v['nav_range'] >= distance, f"Navigation {v['nav_range']:.0f} / {distance:.0f} km required"),
        Result(3, v['wet'] <= v['support'] and v['dry'] <= MISSION['max_dry_mass'],
               f"Wet {v['wet']:.1f} / support {v['support']:.0f}; dry {v['dry']:.1f} / {MISSION['max_dry_mass']:.0f}"),
        Result(4, v['peak'] >= v['demand'] and v['launch_energy'] >= 0 and v['end_energy'] >= 0,
               f"Load {v['demand']:.1f} / peak {v['peak']:.1f} kW; {hours:.0f}h energy margin {v['end_energy']:.1f} kWh"),
        Result(5, v['comm_range'] >= distance, f"Communications {v['comm_range']:.0f} / {distance:.0f} km required"),
        Result(6, v['lifetime'] >= hours, f"Life support {v['lifetime']:.0f} / {hours:.0f} hours required"),
    ]
    if include_budget:
        results.append(Result(7, v['cost_m'] <= MISSION['budget_m'],
                              f"Total ${v['cost_m']}M / ${MISSION['budget_m']}M budget"))
    return results


def valid_through(config, level):
    return all(r.passed for r in validate(config) if r.level <= level)


def feasible_builds():
    builds = []
    for ids in itertools.product(*(tuple(c.id for c in BY_CATEGORY[cat]) for cat in CATEGORIES)):
        config = dict(zip(CATEGORIES, ids))
        if metrics(config)['cost_m'] > MISSION['budget_m']:
            continue
        if all(r.passed for r in validate(config)):
            builds.append(config)
    return builds


def energy_step(value, energy, hours, phase):
    # Panels are stowed during ascent; average sunlight otherwise includes eclipse.
    generation = 0. if phase == 'ASCENT' else value['average_generation']
    supply = min(value['peak'], generation + (value['peak'] if energy > 0 else 0))
    ratio = min(1., supply / value['demand'])
    energy = max(0., min(value['battery'], energy + (generation - value['demand']) * hours))
    return energy, ratio


def load_save(path=SAVE_PATH):
    with Path(path).open(encoding='utf8') as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError('Save root must be an object.')
    if data.get('schema_version') != SCHEMA_VERSION or data.get('catalog_version') != CATALOG_VERSION:
        raise ValueError('Unsupported save/catalog version; original save was not changed.')
    if data.get('mission_id') != MISSION['id']:
        raise ValueError('This save belongs to another mission.')
    check_config(data.get('components'))
    unlocked = data.get('unlocked_level')
    if type(unlocked) is not int or not 1 <= unlocked <= 7:
        raise ValueError('Invalid saved progression.')
    # Progress is historical, validity is always recomputed from component IDs.
    return data['components'].copy(), unlocked


def save_config(config, unlocked, path=SAVE_PATH):
    check_config(config)
    if type(unlocked) is not int or not 1 <= unlocked <= 7:
        raise ValueError('Invalid progression.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(schema_version=SCHEMA_VERSION, catalog_version=CATALOG_VERSION,
                mission_id=MISSION['id'], components=config, unlocked_level=unlocked)
    # Same-directory replacement, only for explicit campaign commits.
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            json.dump(data, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass
class Waypoint:
    position: object
    throttle: float
    stage: bool = False


class MenuBackground:
    def __init__(self, size):
        self.width, self.height = size
        rng = random.Random(12)
        self.stars = [[rng.uniform(0,self.width),rng.uniform(0,self.height),rng.uniform(15,65)] for _ in range(100)]
        self.time = 0.

    def update(self, dt):
        self.time += dt
        for star in self.stars:
            star[1] = (star[1] + star[2] * dt) % self.height

    def draw(self, surface):
        surface.fill((7,12,28))
        for x,y,speed in self.stars:
            pygame.draw.circle(surface,(100,140,190),(int(x),int(y)),2 if speed>45 else 1)
        pygame.draw.circle(surface,(22,55,89),(590,870),230)
        pygame.draw.circle(surface,(40,100,130),(590,870),230,5)
        x,y = 350+math.sin(self.time*.6)*90,360+math.cos(self.time*.8)*20
        pygame.draw.polygon(surface,WHITE,[(x,y-40),(x-17,y+25),(x+17,y+25)])
        pygame.draw.polygon(surface,GOLD,[(x-10,y+27),(x,y+60+math.sin(self.time*18)*8),(x+10,y+27)])


class Rocket:
    def __init__(self, config):
        self.spec = metrics(config)
        self.pos, self.vel = pygame.Vector2(360,720), pygame.Vector2()
        self.fuel = self.capacity = self.spec['fuel']
        self.dry_mass = self.spec['dry']
        self.power, self.burn = ENGINE_POWER, ENGINE_BURN
        self.booster, self.angle = True, -90.
        self.heat_limit = self.spec['heat']

    @property
    def mass(self):
        return self.dry_mass + self.fuel*FUEL_MASS + (BOOSTER_MASS if self.booster else 0)

    @property
    def rect(self):
        return pygame.Rect(round(self.pos.x)-12,round(self.pos.y)-12,24,24)

    def fly(self, point, dt, control=1.):
        delta = point.position-self.pos
        distance = delta.length()
        if distance < 5:
            self.vel *= 0
            return True
        acceleration = self.power/self.mass*(1 if self.booster else .58)*control
        guidance = .55+.45*self.spec['guidance']
        speed = min((65+self.power*.34)*point.throttle*guidance,
                    math.sqrt(2*acceleration*max(0,distance-2)))
        change = delta.normalize()*speed-self.vel
        limit = acceleration*point.throttle*guidance*dt
        if change.length() > limit:
            change.scale_to_length(limit)
        self.vel += change
        self.fuel = max(0.,self.fuel-self.burn*point.throttle*dt)
        step = self.vel*dt
        reached = step.length() >= distance and step.dot(delta)>0
        self.pos = point.position.copy() if reached else self.pos+step
        if self.vel.length_squared():
            self.angle = math.degrees(math.atan2(self.vel.y,self.vel.x))
        if reached:
            self.vel *= 0
        return reached


class Game:
    def __init__(self, save_path=SAVE_PATH):
        pygame.init()
        self.window_size = (468,650)
        self.window = pygame.display.set_mode(self.window_size)
        self.screen = pygame.Surface((W,H))
        pygame.display.set_caption(TITLE+' - Florida Mission Planner')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None,26)
        self.small = pygame.font.Font(None,22)
        self.big = pygame.font.Font(None,46)
        self.background = MenuBackground((W,H))
        self.map = pygame.Rect(20,140,680,630)
        self.running, self.modal, self.hard = True, False, False
        self.buttons = []
        self.state, self.mode = 'MAIN_MENU', 'campaign'
        self.config = DEFAULT.copy()
        self.save_path = Path(save_path)
        self.notice = 'Campaign saves design and progress; sandbox never overwrites it.'
        self.level, self.unlocked = 1,1
        self.time = 0.

    def text(self,message,x,y,color=WHITE,size='normal'):
        font = self.big if size=='big' else self.small if size=='small' else self.font
        self.screen.blit(font.render(str(message),True,color),(x,y))

    def wrap(self,message,x,y,width,color=WHITE):
        line = ''
        for word in message.split():
            test = (line+' '+word).strip()
            if self.small.size(test)[0] > width and line:
                self.text(line,x,y,color,'small')
                y += 23
                line = word
            else:
                line = test
        self.text(line,x,y,color,'small')
        return y+23

    def mouse_position(self,position=None):
        position = pygame.mouse.get_pos() if position is None else position
        return position[0]*W/self.window_size[0],position[1]*H/self.window_size[1]

    def button(self,title,rect,callback,selected=False):
        rect = pygame.Rect(rect)
        hover = rect.collidepoint(self.mouse_position())
        pygame.draw.rect(self.screen,(55,90,120) if hover or selected else (30,50,76),rect,border_radius=7)
        pygame.draw.rect(self.screen,GOLD if selected else CYAN,rect,2 if selected else 1,border_radius=7)
        font = self.small if self.font.size(title)[0]>rect.width-12 else self.font
        label = font.render(title,True,WHITE)
        self.screen.blit(label,label.get_rect(center=rect.center))
        self.buttons.append((rect,callback))

    def persist(self):
        if self.mode != 'campaign':
            return ''
        try:
            save_config(self.config,self.unlocked,self.save_path)
            return ''
        except OSError as exc:
            return ' Save failed: '+str(exc)

    def start(self,mode,load=False):
        config = SANDBOX_DEFAULT.copy() if mode=='sandbox' else DEFAULT.copy()
        unlocked, status = 1,''
        if load:
            try:
                config,unlocked = load_save(self.save_path)
            except FileNotFoundError:
                status = 'No campaign save yet. Starting a new build.'
            except (OSError,ValueError,TypeError) as exc:
                self.notice = 'Cannot load: '+str(exc)+'. Save left untouched; choose New Campaign to reset.'
                return
        self.mode, self.config, self.unlocked = mode,config,unlocked
        self.level = unlocked if mode=='campaign' else 1
        self.state, self.modal = 'GROUND',False
        self.launched = self.returning = False
        self.time = self.altitude = self.ascent_speed = self.elapsed = self.mission_hours = 0.
        self.ascent_throttle = self.control = 1.
        self.station = pygame.Rect(275,170,170,65)
        self.entry = pygame.Rect(280,170,160,65)
        self.asteroids = [[pygame.Vector2(220,580),43,.2], [pygame.Vector2(480,450),50,1.8], [pygame.Vector2(280,330),38,3.]]
        self.rocket = Rocket(self.config)
        self.energy = self.rocket.spec['battery']
        self.range_from_base = 0.
        self.design_checked = mode=='campaign' and unlocked==7 and valid_through(config,7)
        self.notice = status or ('Complete the engineering campaign here at Florida Base.' if mode=='campaign' else 'Sandbox: any build may launch. Engineering failures still apply.')

    def open_design(self):
        if self.state != 'GROUND' or self.launched:
            self.notice = 'Design is locked after ignition.'
            return
        self.draft = self.config.copy()
        self.view_category = min(self.level-1,5) if self.mode=='campaign' else 0
        self.modal = True
        self.notice = 'All specifications are arcade balancing values; component names/prices are supplied.'

    def choose_component(self,cid):
        item = CATALOG[cid]
        self.draft[item.category] = cid

    def choose_tab(self,index):
        if self.mode=='sandbox':
            self.view_category=index
        elif index+1<=self.unlocked:
            self.level=index+1
            self.view_category=min(index,5)
        else:
            self.notice = 'Complete the current engineering check first.'

    def close_design(self,apply=False):
        if apply:
            if self.mode=='campaign' and not valid_through(self.draft,self.level):
                failed=[r for r in validate(self.draft) if r.level<=self.level and not r.passed]
                self.notice='Fix level '+str(failed[0].level)+': '+failed[0].message
                return
            self.config=self.draft.copy()
            self.rocket=Rocket(self.config)
            self.energy=self.rocket.spec['battery']
            self.design_checked=True
            save_message=''
            if self.mode=='campaign':
                self.unlocked=max(self.unlocked,min(7,self.level+1))
                save_message=self.persist()
                if self.level<7:
                    self.level+=1
                    self.view_category=min(5,self.level-1)
                    self.notice='Selection committed. Next requirement: '+LEVELS[self.level-1]+save_message
                    return
            self.notice='Design applied. Review the forecast, then ignite.'+save_message
        self.modal=False

    def ignite(self):
        if not self.design_checked:
            self.notice='Open Engineering Design and apply a build before ignition.'
            return
        if self.mode=='campaign' and (self.unlocked<7 or not valid_through(self.config,7)):
            self.notice='Complete all seven checks, including the budget, before campaign launch.'
            return
        self.rocket=Rocket(self.config)
        self.energy=self.rocket.spec['battery']
        self.state,self.launched='ASCENT',True
        self.altitude=self.ascent_speed=self.elapsed=self.mission_hours=0.
        self.ascent_throttle=1.
        self.notice='UP/W: more throttle. DOWN/S: less. Reach 100 km.'

    def planner(self):
        self.state='PLAN'
        self.points,self.selected=[],None
        self.default_throttle,self.default_stage=.65,False
        self.notice='Click to plot a route. The destination is added automatically.'

    def briefing_next(self):
        self.brief_index+=1
        if self.brief_index>=3:
            self.planner()

    def change_throttle(self):
        target=self.points[self.selected] if self.selected is not None else None
        values=[.4,.65,1.]
        value=values[(values.index(target.throttle if target else self.default_throttle)+1)%3]
        self.default_throttle=value
        if target:
            target.throttle=value

    def toggle_stage(self):
        if self.selected is None:
            self.default_stage=not self.default_stage
        else:
            self.points[self.selected].stage=not self.points[self.selected].stage

    def clear(self):
        self.points,self.selected=[],None

    def launch_route(self):
        destination=self.entry.center if self.returning else self.station.center
        self.route=[Waypoint(p.position.copy(),p.throttle,p.stage) for p in self.points]
        self.route.append(Waypoint(pygame.Vector2(destination),.65))
        self.route_index=0
        self.state='FLIGHT'

    def asteroid_pos(self,asteroid):
        pos,radius,phase=asteroid
        offset=math.sin(self.time*.8+phase)*35 if self.hard else 0
        return pos+pygame.Vector2(offset,0)

    def fail(self,message):
        self.result,self.state=message,'FAIL'

    def undock(self):
        self.rocket.pos.y=810-self.rocket.pos.y
        self.rocket.angle=-90
        self.station.y=810-self.station.bottom
        for asteroid in self.asteroids:
            asteroid[0].y=810-asteroid[0].y
        self.returning=True
        self.planner()
        self.notice='Map flipped vertically. Plot your return to the entry zone.'

    def reentry(self):
        self.state='REENTRY'
        self.rocket.booster=False
        self.altitude,self.descent,self.heat=100.,4.,10.
        self.bank,self.capsule_x=0.,360.
        self.parachute=False
        self.notice='A/D or arrows: bank and steer. P: parachute.'

    def deploy(self):
        if self.altitude>25:
            self.notice='Too high: deploy at or below 25 km.'
        elif self.descent>2.5:
            self.notice='Too fast: bank to slow below 2.5 km/s.'
        else:
            self.parachute=True
            self.notice='Steer into the green recovery zone.'

    def toggle_pause(self):
        if self.state=='PAUSED':
            self.state=self.pause_from
        elif self.state in ('ASCENT','FLIGHT','REENTRY'):
            self.pause_from,self.state=self.state,'PAUSED'

    def tick_systems(self,dt):
        v=self.rocket.spec
        hours=dt*MISSION['clock_h_per_s']
        self.mission_hours+=hours
        self.energy,ratio=energy_step(v,self.energy,hours,self.state)
        self.control=.55+.45*ratio
        if ratio<.25:
            self.fail('Electrical outage: insufficient battery or solar output for avionics and life support.')
        elif self.mission_hours>v['lifetime']:
            self.fail('Life support exhausted. Choose a longer-duration system.')
        elif self.range_from_base>v['comm_range']:
            self.fail('Communications link lost beyond antenna range.')
        elif self.range_from_base>v['nav_range']:
            self.fail('Navigation solution lost beyond system range.')
        return self.state!='FAIL'

    def update(self,dt):
        if self.state=='MAIN_MENU':
            self.background.update(dt)
            return
        if self.modal or self.state=='PAUSED':
            return
        if self.state=='GROUND':
            self.time+=dt
        if self.state not in ('ASCENT','FLIGHT','REENTRY'):
            return
        if not self.tick_systems(dt):
            return
        self.time+=dt
        if self.state=='ASCENT':
            keys=pygame.key.get_pressed()
            direction=int(keys[pygame.K_UP] or keys[pygame.K_w])-int(keys[pygame.K_DOWN] or keys[pygame.K_s])
            self.ascent_throttle=max(.4,min(1.,self.ascent_throttle+direction*.4*dt))
            self.elapsed+=dt
            self.altitude,self.ascent_speed,self.rocket.fuel=ascent_step(
                self.altitude,self.ascent_speed,self.rocket.fuel,self.rocket.dry_mass,self.ascent_throttle,dt,self.control)
            self.range_from_base=max(0,self.altitude)
            if self.altitude>.5 and self.rocket.mass>self.rocket.spec['support']:
                self.fail('Structural overload during ascent. Reduce wet mass or choose a stronger frame.')
                return
            if self.altitude>=MISSION['atmosphere_km']:
                self.rocket.pos=pygame.Vector2(360,720)
                self.rocket.vel*=0
                self.rocket.angle=-90
                self.brief_index,self.state=0,'BRIEFING'
            elif self.altitude<0:
                if self.ascent_speed<-.12 or self.elapsed>2:
                    self.fail('Launch failed: too little lift. Reduce mass or use a different component combination.')
                else:
                    self.altitude,self.ascent_speed=0.,0.
            elif self.rocket.fuel<=0 and self.ascent_speed<=0:
                self.fail('Ascent stalled below 100 km. Increase fuel or reduce mass.')
            if self.state=='ASCENT' and self.elapsed>180:
                self.fail('Launch timed out. Review mass and throttle.')
        elif self.state=='FLIGHT':
            old=self.rocket.pos.copy()
            point=self.route[self.route_index]
            reached=self.rocket.fly(point,dt,self.control)
            if not self.returning:
                progress=max(0.,min(1.,(720-self.rocket.pos.y)/(720-self.station.centery)))
                self.range_from_base=max(100.,progress*MISSION['distance_km'])
            else:
                progress=max(0.,min(1.,(self.rocket.pos.y-self.entry.centery)/(self.station.centery-self.entry.centery)))
                self.range_from_base=100.+progress*(MISSION['distance_km']-100.)
            for asteroid in self.asteroids:
                center=self.asteroid_pos(asteroid)
                segment=self.rocket.pos-old
                t=max(0.,min(1.,(center-old).dot(segment)/segment.length_squared())) if segment.length_squared() else 0.
                if (old+segment*t).distance_to(center)<asteroid[1]+12:
                    self.fail('Asteroid collision. Give your route more clearance.')
                    return
            target=self.entry if self.returning else self.station
            crossed=bool(target.inflate(24,24).clipline(tuple(old),tuple(self.rocket.pos)))
            if self.rocket.rect.colliderect(target) or crossed:
                self.rocket.vel*=0
                if self.returning:
                    self.reentry()
                else:
                    self.rocket.pos=pygame.Vector2(self.station.center)
                    self.range_from_base=MISSION['distance_km']
                    # Validate the final link even if docking occurs in this frame.
                    if self.range_from_base>min(self.rocket.spec['nav_range'],self.rocket.spec['comm_range']):
                        self.fail('Mission destination is outside navigation or communications range.')
                    else:
                        self.state='DOCKED'
                return
            if not self.map.collidepoint(self.rocket.pos):
                self.fail('Rocket left the navigation area.')
                return
            if self.rocket.fuel<=0:
                self.fail('Fuel exhausted. Save ascent fuel or plot a shorter route.')
                return
            if reached:
                if point.stage:
                    self.rocket.booster=False
                self.route_index+=1
                if self.route_index>=len(self.route):
                    self.fail('Destination missed. Plot a different final approach.')
        elif self.state=='REENTRY':
            keys=pygame.key.get_pressed()
            direction=int(keys[pygame.K_RIGHT] or keys[pygame.K_d])-int(keys[pygame.K_LEFT] or keys[pygame.K_a])
            self.bank+=(direction*self.control-self.bank)*min(1,dt*4)
            self.capsule_x=max(65,min(655,self.capsule_x+self.bank*90*dt))
            if self.parachute:
                self.descent=max(.65,self.descent-3*dt)
                self.heat=max(0,self.heat-18*dt)
            else:
                # Original arcade banking/drag behavior; structure now sets heat limit.
                drag=.06+.15*abs(self.bank)+.08*(1-self.altitude/100)
                self.descent=max(1.2,self.descent-drag*dt)
                heating=self.descent**2*.65*(1-.7*abs(self.bank))
                self.heat=max(0,self.heat+(heating-1.5)*dt)
            self.altitude=max(0,self.altitude-self.descent*dt)
            self.range_from_base=self.altitude
            if self.heat>self.rocket.heat_limit:
                self.fail('Structure/heat protection failed. Bank more or choose a more heat-tolerant structure.')
            elif self.altitude<=0:
                if not self.parachute:
                    self.fail('Hard impact: deploy the parachute before landing.')
                elif not 240<=self.capsule_x<=480:
                    self.fail('Missed recovery zone. Steer toward the green marker.')
                else:
                    self.state,self.result='WIN','Splashdown successful. Crew recovered!'

    def component_stats(self,c):
        s=c.specs
        if c.category=='Fuel':
            return f"Fuel {s['fuel']:.0f} | Added dry mass {c.mass:g}"
        if c.category=='Navigation':
            return f"Range {s['range_km']:.0f} km | {s['draw']:g} kW | Guidance {s['guidance']:.0%} | Mass {c.mass:g}"
        if c.category=='Structure':
            return f"Hull {c.mass:g} | Supports {s['support']:g} wet mass | Heat limit {s['heat']:g}"
        if c.category=='Power':
            return f"Solar {s['generation']:g} kW | Battery {s['battery']:g} kWh | Peak {s['peak']:g} kW | Mass {c.mass:g}"
        if c.category=='Communications':
            return f"Range {s['range_km']:.0f} km | Draw {s['draw']:g} kW | Mass {c.mass:g}"
        return f"Endurance {s['hours']:g} hours | Draw {s['draw']:g} kW | Mass {c.mass:g}"

    def draw_design(self):
        self.buttons=[]
        shade=pygame.Surface((W,H),pygame.SRCALPHA)
        shade.fill((0,0,0,210))
        self.screen.blit(shade,(0,0))
        pygame.draw.rect(self.screen,(18,30,51),(20,55,680,930),border_radius=14)
        pygame.draw.rect(self.screen,CYAN,(20,55,680,930),2,border_radius=14)
        self.text('FLORIDA / ENGINEERING',40,75,CYAN,'big')
        campaign=self.mode=='campaign'
        header=f'Level {self.level}/7 - {LEVELS[self.level-1]}' if campaign else 'SANDBOX - unrestricted component selection'
        self.text(header,40,126,GOLD)
        if not campaign or self.level==7:
            for i,cat in enumerate(CATEGORIES):
                self.button(SHORT[i],(35+i*109,164,103,34),lambda i=i:setattr(self,'view_category',i),i==self.view_category)
        else:
            self.text('Choose a '+CATEGORIES[self.view_category]+' component. All selections affect the full build.',40,171,size='small')
        cat=CATEGORIES[self.view_category]
        for i,c in enumerate(BY_CATEGORY[cat]):
            y=214+i*88
            selected=self.draft[cat]==c.id
            self.button(f'{c.id}  {c.name}  ${c.cost_m}M',(35,y,650,35),lambda cid=c.id:self.choose_component(cid),selected)
            self.text(self.component_stats(c),45,y+40,WHITE,'small')
            self.text(c.explanation,45,y+61,GOLD if selected else (135,160,185),'small')
        values=metrics(self.draft)
        reach,reserve,duration=ascent_forecast(values['dry'],values['fuel'])
        self.text(f"Dry {values['dry']:.1f} | Wet {values['wet']:.1f} | Lift {values['lift']:.2f} | Cost ${values['cost_m']}M",40,580,CYAN)
        self.text(f"Full-throttle 100 km: {duration:.0f}s / reserve {reserve:.1f}" if reach else 'Full-throttle forecast: cannot reach 100 km',40,610,GREEN if reach else RED)
        if campaign and self.level==7:
            for i,r in enumerate(validate(self.draft)):
                # Compact feedback checklist; details for the active category appear below.
                self.text(('PASS ' if r.passed else 'FAIL ')+SHORT[i],40+(i%4)*162,646+(i//4)*27,GREEN if r.passed else RED,'small')
            self.wrap(validate(self.draft)[self.view_category].message,40,707,635)
            self.text(f"Budget cap ${MISSION['budget_m']}M. No minimum-cost requirement.",40,755,GOLD)
        else:
            r=validate(self.draft)[self.view_category]
            self.text(('PASS: ' if r.passed else 'FAIL: ')+LEVELS[self.view_category],40,650,GREEN if r.passed else RED)
            self.wrap(r.message,40,683,635)
            self.text(f"Load {values['demand']:.1f} kW | Battery {values['battery']:.0f} kWh | Life {values['lifetime']:.0f} h",40,730)
            self.text('More mass slows ascent; guidance affects steering and speed.',40,760,size='small')
        if campaign:
            for i in range(7):
                label=SHORT[i] if i+1<=self.unlocked else 'LOCK'
                self.button(label,(35+i*93,804,87,34),lambda i=i:self.choose_tab(i),self.level==i+1)
        self.wrap(self.notice,40,852,635,GOLD)
        self.button('Cancel / close',(40,916,220,45),lambda:self.close_design(False))
        self.button('Apply design' if not campaign or self.level==7 else 'Confirm / next',(280,916,390,45),lambda:self.close_design(True))
        self.text('ARCADE specifications, not real spacecraft data. Prices in $M.',40,966,size='small')

    def draw_launch(self):
        ground=self.state=='GROUND'
        altitude=0 if ground else self.altitude
        fade=max(0.,min(1.,altitude/100))
        color=tuple(round(a+(b-a)*fade) for a,b in zip((45,120,180),(6,10,27)))
        pygame.draw.rect(self.screen,color,(20,150,680,530),border_radius=10)
        if altitude>25:
            rng=random.Random(8)
            for _ in range(65):
                pygame.draw.circle(self.screen,(150,175,200),(rng.randrange(30,690),rng.randrange(165,665)),1)
        if altitude<12:
            pad_y=int(620+altitude*40)
            pygame.draw.rect(self.screen,(28,95,110),(20,pad_y,680,60))
            pygame.draw.rect(self.screen,(55,104,71),(20,pad_y,460,60))
            pygame.draw.rect(self.screen,(110,120,132),(280,pad_y-8,165,16))
            pygame.draw.rect(self.screen,(65,75,92),(285,pad_y-155,20,150))
            for dy in range(20,155,30):
                pygame.draw.line(self.screen,(155,165,175),(285,pad_y-dy),(305,pad_y-dy-25),3)
            self.text('FLORIDA BASE',40,min(648,pad_y+20),WHITE,'small')
        x=370
        y=560 if ground else 400+max(0,1-altitude/5)*160
        if not ground and self.rocket.fuel>0:
            length=40+self.ascent_throttle*65+math.sin(self.time*45)*10
            pygame.draw.polygon(self.screen,GOLD,[(x-15,y+28),(x,y+length),(x+15,y+28)])
        pygame.draw.polygon(self.screen,WHITE,[(x,y-75),(x-18,y-35),(x-18,y+30),(x+18,y+30),(x+18,y-35)])
        pygame.draw.polygon(self.screen,CYAN,[(x-18,y),(x-34,y+35),(x-18,y+28)])
        pygame.draw.polygon(self.screen,CYAN,[(x+18,y),(x+34,y+35),(x+18,y+28)])
        pygame.draw.circle(self.screen,(35,80,110),(x,int(y-25)),9)
        v=self.rocket.spec
        self.text(f'{self.mode.upper()} / FLORIDA BASE' if ground else 'ASCENT / LEAVING EARTH',30,90,GOLD)
        if ground:
            reach,reserve,duration=ascent_forecast(v['dry'],v['fuel'])
            passed=sum(r.passed for r in validate(self.config))
            self.text(f"Checks {passed}/7 | Cost ${v['cost_m']}M | Budget ${MISSION['budget_m']}M",30,704,CYAN)
            self.text(f"Lift {v['lift']:.2f} | Wet mass {v['wet']:.1f} | Fuel {v['fuel']:.0f}",30,739)
            self.text(f'100 km forecast: {duration:.0f}s / {reserve:.1f} fuel left' if reach else 'Forecast: cannot clear atmosphere',30,774,GREEN if reach else RED)
            self.text('Sandbox has no budget/check gates; system limits still apply.' if self.mode=='sandbox' else 'Seven design checks, then ignition and the ISS mission.',30,810,size='small')
            self.button('Engineering Design',(25,851,330,48),self.open_design)
            self.button('Ignition / Take off',(375,851,320,48),self.ignite)
            self.button('Asteroids: '+('HARD' if self.hard else 'NORMAL'),(25,914,330,40),lambda:setattr(self,'hard',not self.hard))
            self.button('Main menu',(375,914,320,40),self.main_menu)
            self.wrap(self.notice,30,954,660,GOLD)
        else:
            self.text(f'Altitude {altitude:.1f}/100 km | Climb {self.ascent_speed:.2f} km/s',30,705)
            self.text(f'Throttle {self.ascent_throttle:.0%} | Fuel {self.rocket.fuel:.1f}/{self.rocket.capacity:.0f}',30,744,GOLD)
            pygame.draw.rect(self.screen,(35,48,67),(30,790,660,16))
            pygame.draw.rect(self.screen,CYAN,(30,790,round(660*min(1,max(0,altitude)/100)),16))
            self.draw_systems(835)
            self.wrap(self.notice,30,918,660,GOLD)
            self.text('SPACE: pause | ESC: main menu | Design locked',30,973,size='small')

    def draw_systems(self,y):
        self.text(f'Battery {self.energy:.1f} kWh | Mission {self.mission_hours:.1f}h',25,y,CYAN,'small')
        self.text(f"Life limit {self.rocket.spec['lifetime']:.0f}h | Link distance {self.range_from_base:.0f} km",25,y+26,WHITE,'small')

    def draw_map(self):
        pygame.draw.rect(self.screen,(12,21,40),self.map)
        for x in range(40,700,40):
            pygame.draw.line(self.screen,(20,32,50),(x,self.map.top),(x,self.map.bottom))
        for y in range(150,770,40):
            pygame.draw.line(self.screen,(20,32,50),(self.map.left,y),(self.map.right,y))
        for a in self.asteroids:
            pygame.draw.circle(self.screen,(105,96,100),self.asteroid_pos(a),a[1])
        pygame.draw.rect(self.screen,(35,100,125),self.station)
        pygame.draw.rect(self.screen,CYAN,self.station,3)
        self.text('ISS: docking area',self.station.x+10,self.station.y+22)
        if self.returning:
            pygame.draw.rect(self.screen,(95,73,32),self.entry)
            pygame.draw.rect(self.screen,GOLD,self.entry,3)
            self.text('ENTRY ZONE',self.entry.x+20,self.entry.y+22,GOLD)
        if self.state in ('PLAN','FLIGHT'):
            points=self.points if self.state=='PLAN' else self.route[self.route_index:]
            positions=[self.rocket.pos]+[p.position for p in points]
            if len(positions)>1:
                pygame.draw.lines(self.screen,(65,145,145),False,positions,2)
            for i,p in enumerate(points):
                color=GOLD if self.state=='PLAN' and i==self.selected else CYAN
                pygame.draw.circle(self.screen,color,p.position,9,2)
                self.text(f'{i+1}: {p.throttle:.0%}'+(' DROP' if p.stage else ''),min(p.position.x+12,570),p.position.y-20,color,'small')
        f=pygame.Vector2(1,0).rotate(self.rocket.angle)
        side=pygame.Vector2(-f.y,f.x)
        pos=self.rocket.pos
        pygame.draw.polygon(self.screen,WHITE,[pos+f*18,pos-f*12+side*10,pos-f*12-side*10])
        if self.rocket.booster:
            pygame.draw.circle(self.screen,GOLD,pos-f*15,6)
        self.text(f'Fuel {self.rocket.fuel:.1f}/{self.rocket.capacity:.0f} | Mass {self.rocket.mass:.1f}',25,85)
        self.text('Booster: '+('attached' if self.rocket.booster else 'released'),25,112,GOLD,'small')

    def draw(self):
        self.buttons=[]
        self.screen.fill((8,13,27))
        if self.state=='MAIN_MENU':
            self.background.draw(self.screen)
            self.text('STARLINER',245,135,CYAN,'big')
            self.text('Engineer. Launch. Dock. Return.',230,205)
            self.button('Campaign / Continue',(180,490,360,56),lambda:self.start('campaign',True))
            self.button('New Campaign',(180,565,360,56),lambda:self.start('campaign'))
            self.button('Sandbox',(180,640,360,56),lambda:self.start('sandbox'))
            self.button('Quit',(180,715,360,56),self.quit)
            self.wrap(self.notice,65,835,590,GOLD)
            self.text('Arcade engineering values - not real spacecraft data',155,965,size='small')
        elif self.state=='PAUSED':
            self.text('MISSION PAUSED',205,260,CYAN,'big')
            self.text('Simulation and resource clock stopped.',175,350)
            self.button('Resume',(180,450,360,60),self.toggle_pause)
            self.button('Main menu',(180,535,360,60),self.main_menu)
        else:
            self.text('STARLINER / '+self.state,25,25,CYAN,'big')
            if self.state in ('GROUND','ASCENT'):
                self.draw_launch()
            elif self.state=='BRIEFING':
                lines=[f'Atmosphere cleared with {self.rocket.fuel:.1f} fuel. Your engineering selections stay active during the rest of the mission.',
                       'Plot a route to the ISS. Touch any part of its rectangle to dock. Waypoints control throttle and booster release. Guidance and mass affect acceleration.',
                       'After docking, depart and plot your return on the flipped map. Bank during reentry and deploy P at or below 25 km, below 2.5 km/s.']
                self.wrap(lines[self.brief_index],65,300,590)
                self.text(f'{self.brief_index+1}/3',65,450,GOLD)
                self.button('Next' if self.brief_index<2 else 'Open map',(180,520,360,60),self.briefing_next)
                self.draw_systems(650)
            elif self.state in ('PLAN','FLIGHT','DOCKED'):
                self.draw_map()
                if self.state=='PLAN':
                    point=self.points[self.selected] if self.selected is not None else None
                    throttle=point.throttle if point else self.default_throttle
                    stage=point.stage if point else self.default_stage
                    self.button(f'Throttle {throttle:.0%}',(20,790,210,45),self.change_throttle)
                    self.button('Drop: '+('YES' if stage else 'NO'),(245,790,210,45),self.toggle_stage)
                    self.button('Clear',(470,790,230,45),self.clear)
                    self.text('Design locked after takeoff',25,860,GOLD,'small')
                    self.button('Launch route',(365,850,335,50),self.launch_route)
                    self.text('Left-click add/select | Right-click delete',25,912,size='small')
                    self.wrap(self.notice,25,941,665,GOLD)
                elif self.state=='DOCKED':
                    self.wrap('Docking confirmed. Depart to flip the map and plan your return.',35,795,650,GREEN)
                    self.button('Depart ISS',(180,850,360,55),self.undock)
                    self.draw_systems(932)
                else:
                    self.wrap('SPACE: pause | J: release booster | ESC: main menu',25,805,665,GOLD)
                    self.text('Autopilot active',25,855)
                    self.draw_systems(910)
            elif self.state=='REENTRY':
                pygame.draw.rect(self.screen,(30,60,100),(20,160,680,650))
                pygame.draw.rect(self.screen,(25,95,145),(20,810,680,90))
                pygame.draw.rect(self.screen,GREEN,(240,810,240,15))
                self.text(f'Altitude {self.altitude:.1f} km | Speed {self.descent:.2f} km/s',25,90)
                self.text(f'Heat {self.heat:.0f}/{self.rocket.heat_limit:.0f} | Bank {abs(self.bank):.0%}',25,120,GOLD)
                center=round(self.capsule_x),round(220+(100-self.altitude)*5.7)
                pygame.draw.circle(self.screen,WHITE,center,16)
                if self.parachute:
                    pygame.draw.arc(self.screen,GOLD,(center[0]-45,center[1]-90,90,65),0,math.pi,5)
                    for dx in (-40,40):
                        pygame.draw.line(self.screen,WHITE,(center[0]+dx,center[1]-58),center)
                self.text('RECOVERY ZONE',285,850,GREEN)
                self.wrap(self.notice,25,917,665,GOLD)
                self.text(f'Battery {self.energy:.1f} kWh | Mission {self.mission_hours:.1f}h',25,974,CYAN,'small')
            elif self.state in ('WIN','FAIL'):
                self.text('MISSION COMPLETE' if self.state=='WIN' else 'MISSION FAILED',155,260,GREEN if self.state=='WIN' else RED,'big')
                self.wrap(self.result,65,370,590)
                self.button('Retry same build',(180,510,360,60),self.retry)
                self.button('Main menu',(180,595,360,60),self.main_menu)
        if self.modal:
            self.draw_design()
        pygame.transform.smoothscale(self.screen,self.window_size,self.window)
        pygame.display.flip()

    def retry(self):
        config,mode,unlocked=self.config.copy(),self.mode,self.unlocked
        self.start(mode)
        self.config,self.unlocked=config,unlocked
        self.level=unlocked
        self.rocket=Rocket(config)
        self.energy=self.rocket.spec['battery']
        self.design_checked=True

    def main_menu(self):
        self.modal=False
        self.state='MAIN_MENU'
        self.notice='Campaign saves your engineering build. Sandbox is independent.'

    def quit(self):
        self.running=False

    def handle(self,event):
        if event.type==pygame.QUIT:
            self.quit()
        elif event.type==pygame.KEYDOWN:
            if event.key==pygame.K_ESCAPE:
                if self.modal:
                    self.close_design(False)
                elif self.state=='MAIN_MENU':
                    self.quit()
                else:
                    self.main_menu()
            elif not self.modal:
                if event.key==pygame.K_SPACE:
                    self.toggle_pause()
                elif self.state=='FLIGHT' and event.key==pygame.K_j:
                    self.rocket.booster=False
                elif self.state=='REENTRY' and event.key==pygame.K_p:
                    self.deploy()
        elif event.type==pygame.MOUSEBUTTONDOWN:
            position=self.mouse_position(event.pos)
            if event.button==1:
                for rect,callback in self.buttons:
                    if rect.collidepoint(position):
                        callback()
                        return
            if self.modal:
                return
            if self.state=='PLAN' and self.map.inflate(-30,-30).collidepoint(position):
                for i,point in enumerate(self.points):
                    if point.position.distance_to(position)<18:
                        if event.button==1:
                            self.selected=i
                        elif event.button==3:
                            self.points.pop(i)
                            self.selected=None
                        return
                if event.button==1 and len(self.points)<12:
                    self.points.append(Waypoint(pygame.Vector2(position),self.default_throttle,self.default_stage))
                    self.selected=len(self.points)-1

    def run(self):
        self.draw()
        while self.running:
            dt=min(self.clock.tick(60)/1000,.04)
            for event in pygame.event.get():
                self.handle(event)
                if self.running and event.type in (pygame.MOUSEBUTTONDOWN,pygame.KEYDOWN):
                    self.draw()
            if not self.running:
                break
            self.update(dt)
            self.draw()
        pygame.quit()


def run_tests():
    import tempfile
    import unittest

    from types import SimpleNamespace
    from unittest.mock import patch

    class TestVector:
        """Small math double for model tests; does NOT test Pygame rendering."""
        def __init__(self,x=0.,y=0.):
            self.x,self.y=float(x),float(y)
        def copy(self):
            return TestVector(self.x,self.y)
        def __add__(self,other):
            return TestVector(self.x+other.x,self.y+other.y)
        def __sub__(self,other):
            return TestVector(self.x-other.x,self.y-other.y)
        def __mul__(self,value):
            return TestVector(self.x*value,self.y*value)
        __rmul__=__mul__
        def length_squared(self):
            return self.x*self.x+self.y*self.y
        def length(self):
            return math.sqrt(self.length_squared())
        def normalize(self):
            return self*(1/self.length())
        def scale_to_length(self,size):
            value=self.normalize()*size
            self.x,self.y=value.x,value.y
        def dot(self,other):
            return self.x*other.x+self.y*other.y

    class ModelTests(unittest.TestCase):
        def setUp(self):
            self.good=dict(zip(CATEGORIES,('F3','N3','M3','P2','C2','L3')))

        def test_catalog(self):
            self.assertEqual(len(CATALOG),24)
            self.assertTrue(all(len(BY_CATEGORY[c])==4 for c in CATEGORIES))
            self.assertTrue(all(c.cost_m>0 for c in COMPONENTS))

        def test_names_prices(self):
            expected=((2,3,5,8),(1,3,8,20),(10,15,25,50),(8,14,25,40),(1,4,12,30),(15,35,60,120))
            self.assertEqual(tuple(tuple(c.cost_m for c in BY_CATEGORY[cat]) for cat in CATEGORIES),expected)
            self.assertEqual(CATALOG['F3'].name,'Dragon Tank System')
            self.assertEqual(TITLE,'Starliner')

        def test_good(self):
            self.assertTrue(valid_through(self.good,7))
            self.assertEqual(metrics(self.good)['cost_m'],116)

        def test_exactly_two_budget_solutions(self):
            actual={tuple(b[c] for c in CATEGORIES) for b in feasible_builds()}
            self.assertEqual(actual,{('F3','N3','M3','P2','C2','L3'),('F4','N3','M3','P2','C2','L3')})

        def test_all_dragon_over_budget(self):
            r=validate(SANDBOX_DEFAULT)
            self.assertTrue(all(x.passed for x in r[:6]))
            self.assertFalse(r[6].passed)
            self.assertEqual(metrics(SANDBOX_DEFAULT)['cost_m'],135)

        def test_bad_categories(self):
            with self.assertRaises(ValueError):
                metrics(dict(self.good,Fuel='N3'))
            with self.assertRaises(ValueError):
                metrics({})

        def test_requirement_failures(self):
            for category,cid,level in [('Fuel','F1',1),('Navigation','N1',2),('Structure','M1',3),('Power','P1',4),('Communications','C1',5),('Lifetime','L1',6)]:
                with self.subTest(category=category):
                    self.assertFalse(validate(dict(self.good,**{category:cid}))[level-1].passed)

        def test_budget_boundary(self):
            b=dict(self.good,Fuel='F4')
            self.assertEqual(metrics(b)['cost_m'],MISSION['budget_m'])
            self.assertTrue(validate(b)[6].passed)
            self.assertFalse(validate(dict(b,Communications='C3'))[6].passed)

        def test_forecast_physics(self):
            light=metrics(self.good)
            heavy=metrics(dict(self.good,Structure='M4'))
            self.assertGreater(light['lift'],heavy['lift'])
            a,s,f=ascent_step(0,0,185,light['dry'],1,.04)
            self.assertGreater(a,0)
            self.assertLess(f,185)
            for config in feasible_builds():
                v=metrics(config)
                ok,reserve,duration=ascent_forecast(v['dry'],v['fuel'])
                self.assertTrue(ok)
                self.assertGreaterEqual(reserve,35)

        def test_resource_accounting(self):
            v=metrics(self.good)
            energy,ratio=energy_step(v,400,1,'FLIGHT')
            self.assertAlmostEqual(energy,400-v['demand'])
            self.assertEqual(ratio,1)
            energy,ratio=energy_step(v,0,1,'FLIGHT')
            self.assertEqual(energy,0)
            self.assertEqual(ratio,0)
            solar=metrics(SANDBOX_DEFAULT)
            self.assertLess(energy_step(solar,10,1,'ASCENT')[0],10)
            self.assertGreater(energy_step(solar,10,1,'FLIGHT')[0],10)

        def test_save_roundtrip(self):
            with tempfile.TemporaryDirectory() as folder:
                p=Path(folder)/'save.json'
                save_config(self.good,7,p)
                restored,level=load_save(p)
                self.assertEqual(restored,self.good)
                self.assertEqual(level,7)
                self.assertTrue(valid_through(restored,7))

        def test_corrupt_and_unknown_save_untouched(self):
            with tempfile.TemporaryDirectory() as folder:
                p=Path(folder)/'save.json'
                p.write_text('{broken',encoding='utf8')
                with self.assertRaises(ValueError):
                    load_save(p)
                self.assertEqual(p.read_text(encoding='utf8'),'{broken')
                save_config(self.good,7,p)
                data=json.loads(p.read_text(encoding='utf8'))
                data['components']['Fuel']='F999'
                p.write_text(json.dumps(data),encoding='utf8')
                before=p.read_bytes()
                with self.assertRaises(ValueError):
                    load_save(p)
                self.assertEqual(p.read_bytes(),before)

        def test_revalidation_and_no_mutation(self):
            old=self.good.copy()
            self.assertTrue(valid_through(old,7))
            changed=dict(old,Power='P1')
            self.assertFalse(valid_through(changed,7))
            self.assertEqual(self.good,old)
            validate(old)
            self.assertEqual(old,self.good)

        def test_unknown_schema_and_missing(self):
            with tempfile.TemporaryDirectory() as folder:
                p=Path(folder)/'save.json'
                with self.assertRaises(FileNotFoundError):
                    load_save(p)
                save_config(self.good,7,p)
                data=json.loads(p.read_text(encoding='utf8'))
                data['schema_version']=999
                p.write_text(json.dumps(data),encoding='utf8')
                with self.assertRaises(ValueError):
                    load_save(p)

        def test_sequential_campaign_is_solvable(self):
            current=DEFAULT.copy()
            for index,(cat,cid) in enumerate(self.good.items(),1):
                current[cat]=cid
                self.assertTrue(valid_through(current,index),(index,validate(current)))
            self.assertTrue(valid_through(current,7))

        def test_healthy_power_through_ascent(self):
            for config in feasible_builds()+[SANDBOX_DEFAULT]:
                v=metrics(config)
                ok,reserve,seconds=ascent_forecast(v['dry'],v['fuel'])
                energy=v['battery']
                for _ in range(math.ceil(seconds/.04)):
                    energy,ratio=energy_step(v,energy,.04*MISSION['clock_h_per_s'],'ASCENT')
                    self.assertEqual(ratio,1.)
                self.assertGreater(energy,0.)

        def test_roundtrip_navigation_fuel(self):
            with patch.dict(globals(),pygame=SimpleNamespace(Vector2=TestVector)):
                for config in feasible_builds():
                    ship=Rocket(config)
                    ok,ship.fuel,seconds=ascent_forecast(ship.dry_mass,ship.capacity)
                    self.assertTrue(ok)
                    for start,end in ((720.,202.5),(607.5,202.5)):
                        ship.pos=TestVector(360,start)
                        ship.vel=TestVector()
                        point=Waypoint(TestVector(360,end),.65)
                        for _ in range(15000):
                            if ship.fly(point,.02):
                                break
                            self.assertGreater(ship.fuel,0.)
                        else:
                            self.fail('Waypoint was not reached.')
                    self.assertGreater(ship.fuel,0.)

        def test_guidance_changes_flight(self):
            with patch.dict(globals(),pygame=SimpleNamespace(Vector2=TestVector)):
                basic=Rocket(dict(self.good,Navigation='N1'))
                advanced=Rocket(dict(self.good,Navigation='N4'))
                target=Waypoint(TestVector(360,200),1.)
                basic.fly(target,1.)
                advanced.fly(target,1.)
                self.assertGreater(advanced.vel.length(),basic.vel.length())

        def test_pause_and_modal_freeze_resources(self):
            game=Game.__new__(Game)
            game.state,game.modal='ASCENT',False
            game.mission_hours=7.
            game.energy=25.
            game.toggle_pause()
            game.update(1.)
            self.assertEqual(game.mission_hours,7.)
            self.assertEqual(game.energy,25.)
            game.toggle_pause()
            self.assertEqual(game.state,'ASCENT')
            game.modal=True
            game.update(1.)
            self.assertEqual(game.mission_hours,7.)

        def test_campaign_apply_cancel_and_unlock(self):
            with patch.dict(globals(),pygame=SimpleNamespace(Vector2=TestVector)):
                game=Game.__new__(Game)
                game.mode,game.state,game.launched='campaign','GROUND',False
                game.config=DEFAULT.copy()
                game.level=game.unlocked=1
                game.persist=lambda:''
                game.open_design()
                game.choose_component('F3')
                game.close_design(False)
                self.assertEqual(game.config['Fuel'],'F1')
                game.open_design()
                for i,(cat,cid) in enumerate(self.good.items(),1):
                    self.assertEqual(game.level,i)
                    game.choose_component(cid)
                    game.close_design(True)
                    self.assertEqual(game.config[cat],cid)
                self.assertEqual(game.level,7)
                game.close_design(True)
                self.assertFalse(game.modal)
                self.assertEqual(game.config,self.good)
                self.assertTrue(game.design_checked)
                game.open_design()
                game.level=4
                game.choose_component('P1')
                committed=game.config.copy()
                game.close_design(True)
                self.assertTrue(game.modal)
                self.assertEqual(game.config,committed)

        def test_sandbox_never_saves_campaign(self):
            with patch.dict(globals(),pygame=SimpleNamespace(Vector2=TestVector)):
                game=Game.__new__(Game)
                game.mode,game.state,game.launched='sandbox','GROUND',False
                game.config=DEFAULT.copy()
                game.level=game.unlocked=1
                def forbidden():
                    self.fail('Sandbox attempted a campaign save.')
                game.persist=forbidden
                game.open_design()
                game.choose_component('F4')
                game.close_design(True)
                self.assertFalse(game.modal)
                self.assertEqual(game.config['Fuel'],'F4')
                self.assertTrue(game.design_checked)


        def test_reentry_math_can_recover(self):
            keys={0:False,1:False,2:False,3:False}
            fake=SimpleNamespace(Vector2=TestVector,K_RIGHT=0,K_d=1,K_LEFT=2,K_a=3,
                                 key=SimpleNamespace(get_pressed=lambda:keys))
            with patch.dict(globals(),pygame=fake):
                game=Game.__new__(Game)
                game.rocket=Rocket(self.good)
                game.modal=False
                game.time=0.
                game.mission_hours=30.
                game.range_from_base=100.
                game.energy=400.-game.rocket.spec['demand']*game.mission_hours
                game.reentry()
                direction=1
                for _ in range(10000):
                    if game.parachute:
                        direction=1 if game.capsule_x<350 else -1 if game.capsule_x>370 else 0
                    elif game.capsule_x>460:
                        direction=-1
                    elif game.capsule_x<260:
                        direction=1
                    keys[0]=direction>0
                    keys[2]=direction<0
                    if game.altitude<=25 and game.descent<=2.5:
                        game.deploy()
                    game.update(.02)
                    if game.state in ('WIN','FAIL'):
                        break
                self.assertEqual(game.state,'WIN',getattr(game,'result','Did not land'))

        def test_runtime_resource_failure(self):
            game=Game.__new__(Game)
            game.rocket=SimpleNamespace(spec=metrics(self.good))
            game.state='ASCENT'
            game.energy=0.
            game.mission_hours=0.
            game.range_from_base=0.
            self.assertFalse(game.tick_systems(.04))
            self.assertEqual(game.state,'FAIL')
            self.assertIn('Electrical',game.result)
            game.state='FLIGHT'
            game.energy=100.
            game.mission_hours=game.rocket.spec['lifetime']+1
            self.assertFalse(game.tick_systems(.04))
            self.assertIn('Life support',game.result)

    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ModelTests)
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true',help='Run arcade regression and engineering campaign tests without Pygame')
    parser.add_argument('--balance-report',action='store_true',help='Report engineering mission feasibility and optimization')
    parser.add_argument('--engineering-report',action='store_true',help='Alias for --balance-report')
    parser.add_argument('--arcade-balance-report',action='store_true',help='Report preserved legacy arcade mission balance')
    parser.add_argument('--save-file',type=Path,default=SAVE_PATH,help='Legacy arcade save; not the engineering campaign save')
    parser.add_argument('--campaign-save-file',type=Path,default=Path.home()/'.starliner'/'engineering_campaign_v2.json')
    parser.add_argument('--profile',type=Path,help='Explicit engineering mission/capability JSON profile')
    parser.add_argument('--legacy-game',action='store_true',help='Open the unmodified legacy arcade UI')
    args=parser.parse_args()
    if args.self_test:
        import unittest
        old_ok=run_tests()
        suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_starliner_campaign.py')
        new_ok=unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
        return 0 if old_ok and new_ok else 1
    if args.arcade_balance_report:
        builds=feasible_builds()
        for config in builds:
            v=metrics(config)
            print(' / '.join(config[c] for c in CATEGORIES),f"${v['cost_m']}M",ascent_forecast(v['dry'],v['fuel']))
        print(f'{len(builds)} qualifying arcade builds; cap ${MISSION["budget_m"]}M.')
        return 0
    from starliner_engineering_data import load_profile, balance_report, DISCLAIMER
    try:
        mission,catalog=load_profile(args.profile)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        parser.error('Invalid engineering profile: '+str(exc))
    if args.balance_report or args.engineering_report:
        from starliner_engineering_data import validate_component, CATEGORIES as engineering_categories
        print(DISCLAIMER)
        report=balance_report(mission,catalog)
        for cid,part in catalog.items():
            result=validate_component(part,mission)
            print(cid,part.name,result.status)
            for check in result.checks:
                if check.status!='passing': print('  '+check.message)
        for cost,config in report['solutions']:
            print(' / '.join(config[c] for c in engineering_categories),f'${cost:,}')
        print('Verified solutions:',len(report['solutions']))
        print('Minimum verified cost:',report['minimum_cost_dollars'])
        print('Budget:',mission.budget_dollars)
        return 0
    global pygame
    try:
        import pygame as pg
    except ImportError:
        print('Pygame is required for the window. Install: python -m pip install pygame',file=sys.stderr)
        return 1
    pygame=pg
    if args.legacy_game:
        Game(args.save_file).run()
    else:
        from starliner_campaign_ui import make_game_class
        make_game_class(Game,pg)(args.save_file,mission,catalog,args.campaign_save_file).run()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
