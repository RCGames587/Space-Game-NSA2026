"""Integrated campaign flight model; no graphics dependency."""
import math
import random

CATEGORIES=('Fuel','Navigation','Structure','Power','Communications','Lifetime')
PHASES=('CHECKS','LAUNCH','OUTBOUND','RESCUE','RETURN','REENTRY','VICTORY','FAILURE')

def segment_distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    q=dx*dx+dy*dy
    t=0 if not q else max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/q))
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)

class MissionFlight:
    def __init__(self,campaign,config,level,rng=None):
        if type(level) is not int or not 1<=level<=7: raise ValueError('Invalid level')
        errors=campaign.readiness(config,level)
        if errors: raise ValueError(errors[0])
        self.campaign,self.config,self.level=campaign,dict(config),level
        self.rng=rng or random.Random()
        self.systems=CATEGORIES[:min(level,6)]
        self.phase='CHECKS';self.check_index=0;self.checked=[];self.evidence={}
        self.offset_m=self.rng.choice(tuple(range(-95,-14,5))+tuple(range(15,96,5)))
        self.pos=[100.,660.];self.vel=[0.,0.];self.route=[]
        self.station=(590.,230.);self.home=(100.,660.)
        self.fuel=100.;self.energy=100.;self.oxygen=100.;self.heat=0.
        self.altitude=0.;self.elapsed=0.;self.phase_time=0.;self.bank=0.
        self.rescued=False;self.chute=False;self.link=False;self.saved=False
        self.message='Run each subsystem verification before ignition.'
        self._turn=0
        catalog=getattr(campaign,'catalog',{})
        def spec(cat,key,default):
            part=catalog.get(config.get(cat))
            return part.specifications.get(key,default) if part else default
        self.fuel_factor=300/max(1,spec('Fuel','capacity_l',300))
        self.acceleration=125*900/max(600,spec('Structure','structure_mass_kg',900)) if level>=3 else 125
        self.capture_radius=max(30,40-spec('Navigation','accuracy_error_m',10)) if level>=2 else 38
        self.power_factor=5/max(.1,spec('Power','output_kw',5)) if level>=4 else 1
        self.life_factor=210/max(1,spec('Lifetime','duration_days',210)) if level>=6 else 1

    @property
    def current_system(self):
        return self.systems[min(self.check_index,len(self.systems)-1)]

    def align(self,delta):
        if self.phase=='CHECKS' and self.current_system=='Navigation':
            self.offset_m=max(-100,min(100,self.offset_m+delta))

    def verify(self):
        if self.phase!='CHECKS': return False
        errors=self.campaign.readiness(self.config,self.level)
        if errors: self.message=errors[0];return False
        if self.current_system=='Navigation' and abs(self.offset_m)>10:
            self.message='Calibrate within +/-10 m using Left/Right or A/D.';return False
        self.checked.append(self.current_system);self.check_index+=1
        if self.check_index==len(self.systems):
            self.phase='LAUNCH';self.phase_time=0
            self.message='Checks complete. Press SPACE to ignite.'
        else: self.message='Verify '+self.current_system+'.'
        return True

    def fail(self,message):
        self.phase='FAILURE';self.message=message

    def transition(self,phase,message):
        self.phase=phase;self.phase_time=0.;self.message=message

    def action(self):
        if self.phase=='CHECKS': return self.verify()
        if self.phase=='LAUNCH' and self.phase_time==0:
            self.phase_time=.00001;self.message='Launch in progress.'
        elif self.phase=='RESCUE':
            if 'Communications' in self.systems and not self.link:
                self.message='Transmit telemetry (T) before the rescue.';return
            self.rescued=True
            self.evidence['Navigation']='Rendezvous corridor acquired' if self.level>=2 else 'Basic rescue guidance complete'
            self.evidence['Structure']='Launch and rescue loads sustained'
            self.route=[];self.vel=[0.,0.]
            self.transition('RETURN','Crew aboard. Plot a return route to the green entry gate.')
        elif self.phase=='REENTRY':
            if self.altitude>15:self.message='Wait until altitude is 15 km or lower to deploy.'
            else:self.chute=True;self.message='Parachute deployed.'

    def transmit(self):
        if 'Communications' in self.systems and self.phase in ('OUTBOUND','RESCUE','RETURN'):
            self.link=True;self.evidence['Communications']='Rescue telemetry received';self.message='NASA rescue telemetry confirmed.'

    def waypoint(self,x,y):
        if self.phase in ('OUTBOUND','RETURN') and 45<=x<=675 and 190<=y<=750:
            self.route.append((float(x),float(y)))

    def update(self,dt,bank=0):
        if not math.isfinite(dt) or dt<0: raise ValueError('Invalid elapsed time')
        remaining=min(dt,.25)
        while remaining>1e-9:
            h=min(1/120,remaining);remaining-=h;self._step(h,bank)

    def _step(self,dt,bank):
        if self.phase in ('CHECKS','VICTORY','FAILURE'):return
        if self.campaign.readiness(self.config,self.level):
            self.fail('A required subsystem is no longer verified.');return
        if self.phase=='LAUNCH' and self.phase_time==0:return
        self.phase_time+=dt;self.elapsed+=dt
        if self.phase in ('LAUNCH','OUTBOUND','RETURN'):
            self.fuel-=dt*(1.6 if self.phase=='LAUNCH' else (.23 if self.route else 0))*self.fuel_factor
            if self.fuel<=0:self.fail('Propellant exhausted before recovery.');return
        if 'Power' in self.systems:
            self.energy-=dt*.22*self.power_factor
            if self.energy<=0:self.fail('Electrical supply exhausted.');return
        if 'Lifetime' in self.systems:
            self.oxygen-=dt*.16*self.life_factor
            if self.oxygen<=0:self.fail('Crew life-support reserve exhausted.');return
        if self.elapsed>240:self.fail('Rescue mission time limit exceeded.');return
        if self.phase=='LAUNCH':
            self.altitude=min(100,self.phase_time/3.5*100)
            if self.altitude>=100:
                self.evidence['Fuel']='Launch and transfer reserve available'
                if 'Structure' in self.systems:self.evidence['Structure']='Launch loads sustained'
                self.transition('OUTBOUND','Click waypoints toward the gold station. SPACE rescues after arrival.')
        elif self.phase in ('OUTBOUND','RETURN'):
            old=tuple(self.pos)
            if self.route:
                target=self.route[0];dx,dy=target[0]-self.pos[0],target[1]-self.pos[1]
                length=math.hypot(dx,dy)
                if length:
                    desired=(dx/length*170,dy/length*170)
                    ax,ay=desired[0]-self.vel[0],desired[1]-self.vel[1]
                    amount=math.hypot(ax,ay);factor=min(1,self.acceleration*dt/max(amount,1e-9))
                    self.vel[0]+=ax*factor;self.vel[1]+=ay*factor
            self.pos[0]+=self.vel[0]*dt;self.pos[1]+=self.vel[1]*dt
            if self.route and segment_distance(self.route[0],old,self.pos)<30:
                self.route.pop(0)
            goal=self.station if self.phase=='OUTBOUND' else self.home
            if segment_distance(goal,old,self.pos)<self.capture_radius:
                if self.phase=='OUTBOUND':
                    self.pos=list(goal);self.vel=[0.,0.];self.route=[]
                    self.transition('RESCUE','Station captured. Press T for telemetry, SPACE to rescue.')
                else:
                    self.altitude=100.;self.heat=0.
                    self.transition('REENTRY','Bank Left/Right to manage heat. Deploy with SPACE below 15 km.')
            elif not(30<=self.pos[0]<=690 and 175<=self.pos[1]<=775):
                self.fail('Spacecraft left the flight corridor. Plan a wider turn.')
        elif self.phase=='REENTRY':
            self.bank=max(-1,min(1,bank))
            self.altitude=max(0,self.altitude-dt*(6 if self.chute else 4 if self.altitude<=15 else 14))
            self.heat=max(0,self.heat+dt*(-25 if self.chute else 25-32*abs(self.bank)))
            if self.heat>100:self.fail('Heat protection exceeded. Bank during reentry.');return
            if self.altitude<=0:
                if not self.chute:self.fail('Parachute not deployed before landing.');return
                if not self.rescued:self.fail('Rescue crew was not recovered.');return
                if 'Communications' in self.systems and not self.link:self.fail('Rescue telemetry missing.');return
                self.evidence['Fuel']='Launch, rescue and return reserve verified'
                for cat in self.systems:
                    self.evidence.setdefault(cat,'Verified through launch, rescue and safe recovery')
                self.transition('VICTORY','Crew rescued and safely returned. Mission verified.')

    def finish(self):
        if self.phase!='VICTORY':raise ValueError('Safe recovery is required before certification.')
        if not self.saved:
            self.campaign.commit(self.config,self.level);self.saved=True
