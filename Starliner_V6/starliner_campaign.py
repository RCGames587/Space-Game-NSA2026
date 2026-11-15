"""Pure-Python campaign state, progressive mission exercises, and isolated saves."""
from dataclasses import dataclass, field
from pathlib import Path
import json
import os
import tempfile
from starliner_engineering_data import (Mission,CATALOG,CATEGORIES,BASELINE,CATALOG_VERSION,
    validate_component,validate_configuration,profile_fingerprint,balance_report)

SAVE_PATH = Path.home()/'.starliner'/'engineering_campaign_v2.json'
BRIEFINGS = (
 ('Propellant packaging',
  'A tank must hold enough compatible propellant without exceeding its empty-mass limit. '
  'Extra capacity cannot compensate for excessive tank mass. Select a tank, then run its valve check.',
  'Tank selection and a propellant/interface check only. No navigation, power, or life-support controls yet.'),
 ('Precision rendezvous',
  'Reaching the station and docking accurately are separate requirements. Smaller position error is better. '
  'After the fuel check, align the approach marker within +/-10 m and engage autonomous docking.',
  'Adds approach alignment and autonomous docking after the fuel-system check.'),
 ('Payload versus structure mass',
  'Payload rating is the supported load; structure mass is the weight of the frame itself. '
  'A stronger but overweight frame still fails. Apply the 6000 kg payload test after rendezvous.',
  'Adds a payload/load qualification check to fuel and navigation.'),
 ('Power is not energy',
  'kW measures power; kWh measures stored energy. A 4 kW battery is not automatically able to power '
  'a long mission. Strict generation and supply-based scenarios have different checks.',
  'Adds electrical supply, generation, interface and energy-availability monitoring.'),
 ('A continuous information link',
  'Data rate does not establish coverage. Telemetry must reach the required ground or relay network '
  'during mission windows, with compatible spacecraft interfaces.',
  'Adds a telemetry transmission and verified coverage check.'),
 ('Keeping four people alive',
  'Crew capacity, duration and system mass must all pass. Oxygen, carbon dioxide removal, temperature '
  'and pressure control must also be supported. These are simplified game ratings, not vehicle endurance claims.',
  'Adds a four-person, 170-day life-support exercise; no station support is assumed.'),
 ('Engineering within a budget',
  'The baseline already fits $200M. Certification proves every requirement; optimization measures savings '
  'without weakening those requirements. Unverified cheaper parts cannot be certified.',
  'Reuses all six systems. Compare substitutions and certify the complete configuration.')
)

@dataclass
class Campaign:
    mission: Mission = field(default_factory=Mission)
    catalog: object = field(default_factory=lambda:CATALOG)
    config: dict = field(default_factory=lambda:dict.fromkeys(CATEGORIES))
    completed: set = field(default_factory=set)
    unlock_all: bool = False
    notice: str = ''

    def report(self,config=None):
        return validate_configuration(self.config if config is None else config,self.mission,self.catalog,partial=True)

    def current_level(self):
        for level in range(1,8):
            if level not in self.completed: return level
        return 7

    def available(self,level):
        return type(level) is int and 1 <= level <= 7 and (
            self.unlock_all or level in self.completed or level == self.current_level())

    def readiness(self,draft,level):
        if type(level) is not int or not 1 <= level <= 7: raise ValueError('Invalid level.')
        result = self.report(draft)
        relevant = CATEGORIES[:min(level,6)]
        errors = []
        for cat in relevant:
            r = result['components'][cat]
            if not r.passed:
                errors.extend(cat+': '+c.message for c in r.checks if c.status!='passing')
        if level == 7 and not result['budget_passed']: errors.append('Construction budget exceeded.')
        return errors

    def commit(self,draft,level):
        if not self.available(level): raise ValueError('This level is locked.')
        errors = self.readiness(draft,level)
        if errors: raise ValueError(errors[0])
        self.config = draft.copy()
        self.completed.add(level)
        # Any recorded success must still satisfy the current mission.
        self.completed = {n for n in self.completed if not self.readiness(self.config,n)}

    def revalidate(self):
        self.report()  # Reject unknown IDs and wrong-category data.
        self.completed = {n for n in self.completed if not self.readiness(self.config,n)}

    def save(self,path=SAVE_PATH):
        self.revalidate()
        target = Path(path)
        target.parent.mkdir(parents=True,exist_ok=True)
        raw = dict(schema_version=2,catalog_version=CATALOG_VERSION,
                   profile=profile_fingerprint(self.mission,self.catalog),
                   components=self.config,completed=sorted(self.completed),unlock_all=self.unlock_all)
        fd,temp = tempfile.mkstemp(prefix=target.name+'.',suffix='.tmp',dir=target.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf8') as stream:
                json.dump(raw,stream,indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp,target)
        finally:
            if os.path.exists(temp): os.unlink(temp)

    @classmethod
    def load(cls,path=SAVE_PATH,mission=None,catalog=None):
        mission,catalog = mission or Mission(),CATALOG if catalog is None else catalog
        with Path(path).open(encoding='utf8') as stream: raw = json.load(stream)
        if not isinstance(raw,dict): raise ValueError('Save root must be an object.')
        schema = raw.get('schema_version')
        if type(schema) is not int or schema not in (1,2): raise ValueError('Unsupported save version; save unchanged.')
        version = raw.get('catalog_version')
        if type(version) is not int or version not in (1,CATALOG_VERSION): raise ValueError('Unsupported catalog version.')
        config = raw.get('components')
        validate_configuration(config,mission,catalog,partial=schema==2)
        if schema == 1:
            # Legacy arcade IDs can be imported, but its pass flags/units are not engineering progress.
            return cls(mission,catalog,config.copy(),notice='Legacy selections imported; engineering levels require revalidation.')
        completed = raw.get('completed')
        if not isinstance(completed,list) or any(type(n) is not int or not 1<=n<=7 for n in completed):
            raise ValueError('Invalid saved progress.')
        if type(raw.get('unlock_all')) is not bool: raise ValueError('Invalid unlock-all setting.')
        campaign = cls(mission,catalog,config.copy(),set(completed),raw['unlock_all'])
        if raw.get('profile') != profile_fingerprint(mission,catalog):
            campaign.completed.clear()
            campaign.notice = 'Mission/profile changed; selections retained, exercises must be repeated.'
        campaign.revalidate()
        return campaign

class Exercise:
    """Cumulative teaching exercises, NOT an orbital/energy/structural simulation.

    Each level adds exactly one subsystem exercise. Time is animation time, not
    physical mission time. Passing engineering checks remains mandatory.
    """
    def __init__(self,campaign,draft,level):
        if level not in range(1,7): raise ValueError('Budget uses certification, not a flight exercise.')
        errors = campaign.readiness(draft,level)
        if errors: raise ValueError(errors[0])
        self.level = level
        self.stages = tuple(range(1,level+1))
        self.index = 0
        self.progress = 0.
        self.active = False
        self.done = False
        self.offset_m = 60.
        self.completed_stages = []
        self.config = draft.copy()
        self.campaign = campaign

    @property
    def stage(self): return self.stages[min(self.index,len(self.stages)-1)]

    def align(self,delta):
        if self.stage == 2 and not self.active:
            self.offset_m = max(-100.,min(100.,self.offset_m+delta))

    def start_stage(self):
        if self.done: return False
        if self.stage == 2 and abs(self.offset_m)>10: return False
        self.active = True
        return True

    def update(self,dt):
        if not self.active or self.done: return
        if dt < 0: raise ValueError('Negative exercise time.')
        self.progress = min(1.,self.progress+min(dt,.25)/2.0)
        if self.progress >= 1.:
            self.completed_stages.append(self.stage)
            self.index += 1
            self.active = False
            self.progress = 0.
            self.done = self.index == len(self.stages)

    def finish(self):
        if not self.done: raise ValueError('Complete all exercise stages first.')
        # Revalidate against current data even if it changed during a test.
        self.campaign.commit(self.config,self.level)
