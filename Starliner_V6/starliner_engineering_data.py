"""Simplified engineering game data. Never feeds the legacy arcade flight physics."""
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Mapping, Optional
import itertools
import json
import math
import hashlib

DISCLAIMER = ('Component prices and engineering specifications are simplified game values, '
              'not actual NASA procurement costs or engineering drawings.')
CATEGORIES = ('Fuel','Navigation','Structure','Power','Communications','Lifetime')
LEVELS = ('Fuel System','Distance / Navigation','Structural Mass','Electrical Power',
          'Communications','Mission Lifetime','Budget Optimization')
BASELINE = dict(zip(CATEGORIES,('F3','N3','M3','P3','C3','L3')))
CATALOG_VERSION = 2

@dataclass(frozen=True)
class Component:
    id: str
    category: str
    name: str
    cost_dollars: int
    specifications: Mapping
    capabilities: Mapping = field(default_factory=dict)
    assumption: Optional[str] = None
    def __post_init__(self):
        if type(self.cost_dollars) is not int or self.cost_dollars < 0:
            raise ValueError('Costs must be nonnegative integer dollars.')
        if any(v is not None and type(v) is not bool for v in self.capabilities.values()):
            raise ValueError('Capabilities must be true, false, or null.')
        object.__setattr__(self,'specifications',MappingProxyType(dict(self.specifications)))
        object.__setattr__(self,'capabilities',MappingProxyType(dict(self.capabilities)))

ROWS = {
 'Fuel': ('shape empty_mass_lb capacity_l',[
 ('F1','Compact Tank',2,('Cube',12,180)),('F2','Lightweight Tank',3,('Cylinder',15,250)),
 ('F3','Dragon Tank System',5,('Integrated',20,300)),('F4','Oversized Tank',8,('Rectangle',35,450))]),
 'Navigation': ('navigation_capability_km accuracy_error_m mass_kg',[
 ('N1','Basic GPS',1,(100,500,10)),('N2','Radar Navigation',3,(250,100,25)),
 ('N3','Dragon Navigation Suite',8,(400,10,35)),('N4','Advanced Navigation',20,(1000,1,100))]),
 'Structure': ('material structure_mass_kg payload_rating_kg',[
 ('M1','Steel Frame',10,('Steel',2400,8000)),('M2','Aluminum Frame',15,('Aluminum',1200,4000)),
 ('M3','Dragon Lightweight Structure',25,('Aluminum / composite',900,6000)),
 ('M4','Titanium Frame',50,('Titanium',1500,10000))]),
 'Power': ('technology output_kw mass_kg',[
 ('P1','Compact Solar Array',8,('Solar',2,60)),('P2','Battery Pack',14,('Battery',4,180)),
 ('P3','Dragon Solar Array',25,('Solar',5,120)),('P4','Oversized Solar Array',40,('Solar',12,500))]),
 'Communications': ('technology data_rate_mbps mass_kg',[
 ('C1','Basic Radio',1,('Radio',0.064,5)),('C2','Short-Range Antenna',4,('Radio',1,20)),
 ('C3','Dragon Communications Suite',12,('Radio / relay',10,40)),
 ('C4','Advanced Communications',30,('High-power radio',100,150))]),
 'Lifetime': ('crew_capacity duration_days mass_kg',[
 ('L1','Basic Life Support',15,(2,30,300)),('L2','Extended Life Support',35,(4,120,600)),
 ('L3','Dragon Life Support',60,(4,210,800)),('L4','Long-Duration System',120,(6,365,1800))])}
CAPABILITIES = {
 'Fuel': ('mmh_nto_compatible','propulsion_connection'),
 'Navigation': ('autonomous_docking','flight_computer_interface'),
 'Structure': ('launch_load_qualified','orbital_operations','pressure_vessel_interface'),
 'Power': ('electrical_distribution_interface','mission_power_energy_available'),
 'Communications': ('required_coverage','telemetry_support','spacecraft_interface'),
 'Lifetime': ('oxygen','co2_removal','temperature_regulation','pressure_control','spacecraft_interface')}

def make_catalog():
    parts = []
    for category,(keys,rows) in ROWS.items():
        for cid,name,cost,values in rows:
            specs = dict(zip(keys.split(),values))
            if cid == 'N3': specs['navigation_display'] = '400+ km'
            baseline = cid == BASELINE[category]
            parts.append(Component(cid,category,name,cost*1_000_000,specs,
                dict.fromkeys(CAPABILITIES[category],True if baseline else None),
                'Baseline GAME assumption, not a real engineering claim.' if baseline else None))
    if len({c.id for c in parts}) != len(parts): raise ValueError('Duplicate component IDs.')
    return MappingProxyType({c.id:c for c in parts})

CATALOG = make_catalog()
RULES = {
 'Fuel': (('capacity_l','min',300),('empty_mass_lb','max',25)),
 'Navigation': (('navigation_capability_km','min',400),('accuracy_error_m','max',10)),
 'Structure': (('payload_rating_kg','min',6000),('structure_mass_kg','max',1200)),
 'Power': (('mass_kg','max',200),),
 'Communications': (('data_rate_mbps','min',1),('mass_kg','max',100)),
 'Lifetime': (('crew_capacity','min',4),('duration_days','min',170),('mass_kg','max',1200))}

def finite(value):
    return type(value) in (int,float) and math.isfinite(value)

@dataclass(frozen=True)
class Mission:
    rules: Mapping = field(default_factory=lambda:RULES)
    required_capabilities: Mapping = field(default_factory=lambda:CAPABILITIES)
    budget_dollars: int = 200_000_000
    required_power_kw: float = 4
    require_generation: bool = True
    required_generation_kw: float = 4
    battery_duration_hours: Optional[float] = None
    external_support_allowed: bool = False
    recharge_allowed: bool = False
    coverage_description: str = 'Ground or relay coverage throughout required mission windows'
    def __post_init__(self):
        if type(self.budget_dollars) is not int or self.budget_dollars < 0: raise ValueError('Invalid budget.')
        for key in ('required_power_kw','required_generation_kw','battery_duration_hours'):
            v = getattr(self,key)
            if v is None and key == 'battery_duration_hours': continue
            if not finite(v) or v < 0: raise ValueError('Invalid '+key)
        for key in ('require_generation','external_support_allowed','recharge_allowed'):
            if type(getattr(self,key)) is not bool: raise ValueError('Invalid '+key)
        if not isinstance(self.coverage_description,str): raise ValueError('Invalid coverage description.')
        for category,rules in self.rules.items():
            if category not in CATEGORIES: raise ValueError('Unknown rule category.')
            for key,op,threshold in rules:
                if op not in ('min','max') or not finite(threshold) or threshold < 0:
                    raise ValueError('Invalid requirement rule.')
        object.__setattr__(self,'rules',MappingProxyType({k:tuple(tuple(r) for r in v) for k,v in self.rules.items()}))
        object.__setattr__(self,'required_capabilities',MappingProxyType({k:tuple(v) for k,v in self.required_capabilities.items()}))

@dataclass(frozen=True)
class Check:
    key: str
    kind: str
    status: str
    message: str
    actual: object = None
    required: object = None

@dataclass(frozen=True)
class Validation:
    component_id: str
    checks: tuple
    selectable: bool = True
    @property
    def status(self):
        if any(c.status == 'failing' for c in self.checks): return 'failing'
        if any(c.status == 'unverified' for c in self.checks): return 'unverified'
        return 'passing'
    @property
    def passed(self): return self.status == 'passing'
    @property
    def messages(self): return tuple(c.message for c in self.checks)

LABELS = {
 'capacity_l':'Capacity (L)','empty_mass_lb':'Empty mass (lb)',
 'navigation_capability_km':'Navigation capability (km)','accuracy_error_m':'Position error (m)',
 'structure_mass_kg':'Structure mass (kg)','payload_rating_kg':'Payload rating (kg)',
 'mass_kg':'System mass (kg)','output_kw':'Output (kW)','supply_kw':'Supply (kW)',
 'generation_kw':'Generation (kW)','data_rate_mbps':'Data rate (Mbps)',
 'crew_capacity':'Crew capacity','duration_days':'Duration (days)','usable_energy_kwh':'Usable energy (kWh)'}

def numeric(key,value,op,threshold):
    label = LABELS.get(key,key.replace('_',' '))
    if not finite(value) or value < 0:
        return Check(key,'quantitative','unverified',label+': needs verification.',value,threshold)
    passed = value >= threshold if op == 'min' else value <= threshold
    relation = '>=' if op == 'min' else '<='
    message = f'{label}: {value:g}; needs {relation} {threshold:g}'
    if not passed: message += f' (fails by {abs(value-threshold):g})'
    return Check(key,'quantitative','passing' if passed else 'failing',message,value,threshold)

def validate_component(component,mission=None):
    mission = mission or Mission()
    checks = [numeric(key,component.specifications.get(key),op,limit)
              for key,op,limit in mission.rules.get(component.category,())]
    for key in mission.required_capabilities.get(component.category,()):
        value = component.capabilities.get(key)
        status = 'passing' if value is True else 'failing' if value is False else 'unverified'
        description = key.replace('_',' ')
        if key == 'required_coverage': description = mission.coverage_description
        checks.append(Check(key,'compatibility',status,description+': '+
                            ('needs verification' if status == 'unverified' else status),value,True))
    if component.category == 'Power':
        s = component.specifications
        checks.append(numeric('supply_kw',s.get('output_kw'),'min',mission.required_power_kw))
        if mission.require_generation:
            generation = s.get('output_kw') if s.get('technology') == 'Solar' else 0
            checks.append(numeric('generation_kw',generation,'min',mission.required_generation_kw))
        if s.get('technology') == 'Battery':
            if mission.battery_duration_hours is None:
                checks.append(Check('battery_duration','quantitative','unverified',
                                    'Battery-supported duration: needs verification.'))
            else:
                checks.append(numeric('usable_energy_kwh',s.get('usable_energy_kwh'),'min',
                                      mission.required_power_kw*mission.battery_duration_hours))
            duration_days = next((limit for key,op,limit in mission.rules.get('Lifetime',())
                                  if key == 'duration_days' and op == 'min'),170)
            if mission.battery_duration_hours is not None and mission.battery_duration_hours < duration_days*24:
                supported = mission.external_support_allowed or mission.recharge_allowed
                checks.append(Check('remaining_mission_power','compatibility',
                    'passing' if supported else 'failing',
                    'Short battery interval requires explicitly allowed recharge/external power; '
                    'mission availability must also be verified.',supported,True))
            # Permission alone never proves energy availability; the explicit capability
            # and the energy/duration checks are still mandatory.
    return Validation(component.id,tuple(checks))

def validate_configuration(config,mission=None,catalog=None,partial=False):
    mission,catalog = mission or Mission(),CATALOG if catalog is None else catalog
    if not isinstance(config,dict) or set(config) != set(CATEGORIES):
        raise ValueError('A configuration needs exactly six categories.')
    results = {}
    cost = 0
    for category,cid in config.items():
        if cid is None and partial:
            results[category] = Validation('',(Check('selection','selection','unverified','No component selected.'),))
            continue
        if not isinstance(cid,str) or cid not in catalog or catalog[cid].category != category:
            raise ValueError(f'Unknown or wrong-category component: {category}={cid!r}')
        results[category] = validate_component(catalog[cid],mission)
        cost += catalog[cid].cost_dollars
    return dict(components=results,cost_dollars=cost,remaining_dollars=mission.budget_dollars-cost,
                savings_dollars=135_000_000-cost,budget_passed=cost<=mission.budget_dollars,
                passed=cost<=mission.budget_dollars and all(r.passed for r in results.values()))

def balance_report(mission=None,catalog=None):
    mission,catalog = mission or Mission(),CATALOG if catalog is None else catalog
    eligible = {cat:tuple(c.id for c in catalog.values() if c.category==cat and validate_component(c,mission).passed)
                for cat in CATEGORIES}
    solutions = []
    for ids in itertools.product(*(eligible[cat] for cat in CATEGORIES)):
        config = dict(zip(CATEGORIES,ids))
        result = validate_configuration(config,mission,catalog)
        if result['passed']: solutions.append((result['cost_dollars'],config))
    solutions.sort(key=lambda row:row[0])
    return dict(eligible=eligible,solutions=solutions,
                minimum_cost_dollars=solutions[0][0] if solutions else None)

def profile_fingerprint(mission,catalog):
    values = {k:(dict(v) if isinstance(v,Mapping) else v) for k,v in vars(mission).items()}
    values['catalog'] = [(c.id,c.cost_dollars,dict(c.specifications),dict(c.capabilities)) for c in catalog.values()]
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()

def load_profile(path=None):
    if path is None: return Mission(),CATALOG
    with open(path,encoding='utf8') as stream: raw = json.load(stream)
    if not isinstance(raw,dict) or set(raw)-{'mission','components'}: raise ValueError('Invalid profile object.')
    settings = raw.get('mission',{})
    if not isinstance(settings,dict): raise ValueError('Invalid mission settings.')
    # Engineering thresholds are deliberately fixed for this campaign. Scenarios can
    # specify power operations, coverage and budget, but cannot relax level rules.
    allowed = {'budget_dollars','required_power_kw','require_generation','required_generation_kw',
               'battery_duration_hours','external_support_allowed','recharge_allowed','coverage_description'}
    if set(settings)-allowed: raise ValueError('Profile cannot override fixed engineering requirements.')
    mission = Mission(**settings)
    if mission.required_power_kw < 4: raise ValueError('Supply cannot be relaxed below 4 kW.')
    if mission.require_generation and mission.required_generation_kw < 4:
        raise ValueError('Generation cannot be relaxed below 4 kW.')
    catalog = dict(CATALOG)
    overrides = raw.get('components',{})
    if not isinstance(overrides,dict): raise ValueError('Invalid component overrides.')
    for cid,override in overrides.items():
        if cid not in catalog or not isinstance(override,dict): raise ValueError('Unknown component override.')
        if set(override)-{'capabilities','usable_energy_kwh','assumption'}: raise ValueError('Immutable catalog specification.')
        if not isinstance(override.get('assumption'),str) or not override['assumption'].strip():
            raise ValueError('Every override needs a visible assumption/source note.')
        c = catalog[cid]
        caps = dict(c.capabilities)
        extra = override.get('capabilities',{})
        if not isinstance(extra,dict) or set(extra)-set(caps): raise ValueError('Unknown capability field.')
        caps.update(extra)
        specs = dict(c.specifications)
        if 'usable_energy_kwh' in override:
            energy = override['usable_energy_kwh']
            if cid != 'P2' or not finite(energy) or energy < 0: raise ValueError('Invalid battery energy override.')
            specs['usable_energy_kwh'] = energy
        catalog[cid] = replace(c,specifications=specs,capabilities=caps,assumption=override['assumption'])
    return mission,MappingProxyType(catalog)
