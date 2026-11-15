"""Reuse the original Game runtime for engineering missions."""
import math
import random
from starliner_engineering_data import BASELINE,CATEGORIES


def wrap_engineering_game(EngineeringGame,BaseGame,pg):
    class SharedFlightGame(EngineeringGame):
        _shared_active=False
        _shared_starting=False

        def test_design(self):
            errors=self.campaign.readiness(self.draft,self.campaign_level)
            if errors:self.notice=errors[0];return
            self._shared_config=self.draft.copy()
            self._shared_level=self.campaign_level
            self._shared_checks=0
            self._shared_systems=CATEGORIES[:min(self.campaign_level,6)]
            self._shared_offset=random.choice(tuple(range(-95,-14,5))+tuple(range(15,96,5)))
            self.state='ENG_SHARED_CHECKS'
            self.notice='Verify accumulated systems, then fly the original rescue mission.'

        def _shared_verify(self):
            errors=self.campaign.readiness(self._shared_config,self._shared_level)
            if errors:self.notice=errors[0];return
            cat=self._shared_systems[self._shared_checks]
            if cat=='Navigation' and abs(self._shared_offset)>10:
                self.notice='Align within +/-10 m using Left/Right or A/D.';return
            self._shared_checks+=1
            if self._shared_checks==len(self._shared_systems):self._begin_shared_flight()
            else:self.notice='Verified '+cat+'. Next: '+self._shared_systems[self._shared_checks]+'.'

        def _shared_align(self,delta):
            if self._shared_systems[self._shared_checks]=='Navigation':
                self._shared_offset=max(-100,min(100,self._shared_offset+delta))

        def _begin_shared_flight(self):
            errors=self.campaign.readiness(self._shared_config,self._shared_level)
            if errors:self.notice=errors[0];self.state='ENG_BUILD';return
            if self._shared_checks!=len(self._shared_systems):raise ValueError('Preflight incomplete')
            legacy=BaseGame.start.__globals__
            Rocket=legacy['Rocket']
            catalog=legacy['CATALOG']
            config=dict(BASELINE)
            for cat in self._shared_systems:config[cat]=self._shared_config[cat]
            if any(cid not in catalog or catalog[cid].category!=cat for cat,cid in config.items()):
                raise ValueError('Engineering component IDs must exist in the legacy catalog.')
            self._shared_starting=True
            try:BaseGame.start(self,'sandbox',False)
            finally:self._shared_starting=False
            self.config=config
            self.rocket=Rocket(config)
            self.energy=self.rocket.spec['battery']
            self.range_from_base=0.
            self.design_checked=False
            self._shared_active=True
            self._shared_rescued=False
            self._shared_reentered=False
            self._shared_committed=False
            self.notice='Engineering Level '+str(self._shared_level)+': fly the rescue mission. Active: '+', '.join(self._shared_systems)

        def start(self,mode,load=False):
            if self._shared_active and not self._shared_starting:
                self._shared_active=False
                return self._begin_shared_flight()
            return super().start(mode,load)

        def main_menu(self):
            self._shared_active=False
            return super().main_menu()

        def back_to_levels(self):
            self._shared_active=False
            return super().back_to_levels()

        def open_design(self):
            if self._shared_active:
                self.notice='Return to engineering design to change mission components.';return
            return super().open_design()

        def persist(self):
            if self._shared_active:return ''
            return super().persist()

        def tick_systems(self,dt):
            if not self._shared_active:return BaseGame.tick_systems(self,dt)
            errors=self.campaign.readiness(self._shared_config,self._shared_level)
            if errors:self.fail(errors[0]);return False
            original=self.rocket.spec
            spec=dict(original)
            level=self._shared_level
            if level<2:spec['nav_range']=math.inf
            if level<5:spec['comm_range']=math.inf
            if level<6:spec['lifetime']=math.inf
            old_energy=self.energy
            if level<4:
                spec['generation']=max(spec.get('generation',0),spec['demand']*4+1)
                spec['peak']=max(spec['peak'],spec['demand']+1)
                spec['battery']=max(spec['battery'],1000000.)
                self.energy=spec['battery']
            self.rocket.spec=spec
            try:result=BaseGame.tick_systems(self,dt)
            finally:
                self.rocket.spec=original
                if level<4:self.energy=old_energy;self.control=1.
            return result

        def undock(self):
            result=BaseGame.undock(self)
            if self._shared_active:self._shared_rescued=True
            return result

        def reentry(self):
            result=BaseGame.reentry(self)
            if self._shared_active and self.returning and self._shared_rescued:self._shared_reentered=True
            return result

        def update(self,dt):
            if not self._shared_active:return super().update(dt)
            BaseGame.update(self,dt)
            if self.state=='WIN' and not self._shared_committed:
                if not (self.launched and self.returning and self._shared_rescued and self._shared_reentered):
                    self.fail('Launch, rescue, return and safe reentry are all required.');return
                try:self.campaign.commit(self._shared_config,self._shared_level)
                except ValueError as exc:self.fail(str(exc));return
                self._shared_committed=True
                self.notice='Engineering mission verified.'+self.campaign_save_now()
                self._shared_active=False
                self.state='ENG_RESULT'

        def _shared_text(self,text,x,y,color=(228,236,250),size='normal'):
            font=self.big if size=='big' else self.small if size=='small' else self.font
            label=font.render(str(text),True,color)
            self.screen.blit(label,label.get_rect(center=(x,y)))

        def _draw_shared_checks(self):
            self.buttons=[];self.screen.fill((8,13,27))
            self._shared_text('ENGINEERING / PREFLIGHT',360,70,(80,215,240),'big')
            cat=self._shared_systems[self._shared_checks]
            self._shared_text('Level '+str(self._shared_level)+' / '+cat,360,145,(255,205,100))
            part=self.engineering_catalog[self._shared_config[cat]]
            self._shared_text(part.name,360,235)
            self._shared_text('Check '+str(self._shared_checks+1)+' / '+str(len(self._shared_systems)),360,295)
            if cat=='Navigation':
                pg.draw.line(self.screen,(228,236,250),(60,460),(660,460),2)
                pg.draw.rect(self.screen,(25,90,65),(330,435,60,50))
                pg.draw.circle(self.screen,(255,205,100),(int(360+self._shared_offset*3),460),12)
                self._shared_text(f'Calibration {self._shared_offset:+.0f} m | Target +/-10 m',360,540)
                self.button('Left / -5 m',(60,600,280,48),lambda:self._shared_align(-5))
                self.button('Right / +5 m',(380,600,280,48),lambda:self._shared_align(5))
            self._shared_text('Next: original launch, rescue, return and reentry.',360,720,size='small')
            self._shared_text(self.notice,360,825,(255,205,100),'small')
            self.button('Back to design',(25,920,270,48),lambda:setattr(self,'state','ENG_BUILD'))
            self.button('Verify / continue',(310,920,385,48),self._shared_verify)
            pg.transform.smoothscale(self.screen,self.window_size,self.window);pg.display.flip()

        def draw(self):
            if self._shared_active:return BaseGame.draw(self)
            if self.state=='ENG_SHARED_CHECKS':return self._draw_shared_checks()
            return super().draw()

        def handle(self,event):
            if self._shared_active:
                if event.type==pg.KEYDOWN and event.key==pg.K_ESCAPE:
                    self._shared_active=False;self.state='ENG_BUILD'
                    self.notice='Flight cancelled. No engineering progress saved.';return
                return BaseGame.handle(self,event)
            if self.state!='ENG_SHARED_CHECKS':return super().handle(event)
            if event.type==pg.QUIT:return self.quit()
            if event.type==pg.KEYDOWN:
                if event.key==pg.K_ESCAPE:self.state='ENG_BUILD'
                elif event.key==pg.K_SPACE:self._shared_verify()
                elif event.key in (pg.K_LEFT,pg.K_a):self._shared_align(-5)
                elif event.key in (pg.K_RIGHT,pg.K_d):self._shared_align(5)
            elif event.type==pg.MOUSEBUTTONDOWN and event.button==1:
                pos=self.mouse_position(event.pos)
                for rect,callback in self.buttons:
                    if rect.collidepoint(pos):callback();return
    return SharedFlightGame
