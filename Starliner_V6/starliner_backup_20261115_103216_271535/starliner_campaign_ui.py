"""Engineering campaign UI layered over the preserved arcade sandbox."""
from pathlib import Path
from starliner_engineering_data import (CATEGORIES,LEVELS,BASELINE,LABELS,DISCLAIMER,
    validate_component,balance_report)
from starliner_campaign import Campaign,Exercise,BRIEFINGS,SAVE_PATH

WHITE=(228,236,250)
CYAN=(80,215,240)
GOLD=(255,205,100)
GREEN=(100,230,160)
RED=(250,105,110)
STATUS_COLOR={'passing':GREEN,'failing':RED,'unverified':GOLD}

def money(value): return f'${value/1_000_000:,.3f}M'.replace('.000M','M')

def make_game_class(BaseGame,pg):
    class EngineeringGame(BaseGame):
        def __init__(self,save_path,mission,catalog,campaign_save=SAVE_PATH):
            super().__init__(save_path)
            self.engineering_mission=mission
            self.engineering_catalog=catalog
            self.campaign_path=Path(campaign_save)
            self.campaign=Campaign(mission,catalog)
            self.campaign_loaded=False
            self.detail_scroll=0
            self.campaign_level=1
            self.notice='Seven progressive engineering missions, or the original arcade flight sandbox.'
            self.best=balance_report(mission,catalog)

        def campaign_save_now(self):
            try:
                self.campaign.save(self.campaign_path)
                return ' Progress saved.'
            except (OSError,ValueError) as exc:
                return ' Save failed: '+str(exc)

        def campaign_start(self,load=False):
            if load:
                try:
                    self.campaign=Campaign.load(self.campaign_path,self.engineering_mission,self.engineering_catalog)
                except FileNotFoundError:
                    if not self.campaign_loaded:
                        self.campaign=Campaign(self.engineering_mission,self.engineering_catalog)
                    self.notice='No engineering save yet. Choose Level 1 to begin.'
                except (OSError,ValueError,TypeError,KeyError) as exc:
                    self.notice='Cannot load engineering save: '+str(exc)+'. File left unchanged.'
                    return
                else:
                    self.notice=self.campaign.notice or 'Engineering campaign loaded and revalidated.'
            else:
                self.campaign=Campaign(self.engineering_mission,self.engineering_catalog)
                self.notice='New campaign. Your old save changes only when you complete an exercise.'
            self.campaign_loaded=True
            self.state='ENG_SELECT'
            self.modal=False

        def unlock_everything(self):
            if not self.campaign_loaded and self.campaign_path.exists():
                try:
                    self.campaign=Campaign.load(self.campaign_path,self.engineering_mission,self.engineering_catalog)
                except (OSError,ValueError,TypeError,KeyError) as exc:
                    self.notice='Unlock cancelled; existing save was not changed: '+str(exc)
                    return
            self.campaign_loaded=True
            self.campaign.unlock_all=True
            self.notice='All level screens unlocked. Engineering checks are NOT bypassed.'+self.campaign_save_now()

        def select_level(self,level):
            if not self.campaign.available(level):
                self.notice='Complete the current mission to unlock this level.'
                return
            self.campaign_level=level
            self.state='ENG_BRIEF'
            self.detail_scroll=0

        def enter_design(self):
            self.draft=self.campaign.config.copy()
            self.view_category=min(self.campaign_level-1,5)
            self.detail_scroll=0
            self.notice='Choose a component. Failed/unverified options may be inspected, not certified.'
            self.state='ENG_BUDGET' if self.campaign_level==7 else 'ENG_BUILD'

        def engineering_choose(self,cid):
            component=self.engineering_catalog[cid]
            self.draft[component.category]=cid
            self.detail_scroll=0
            self.notice='Preview updated; confirmed selections are unchanged until this mission succeeds.'

        def budget_category(self,index):
            self.view_category=index
            self.detail_scroll=0
            self.state='ENG_BUILD'

        def test_design(self):
            errors=self.campaign.readiness(self.draft,self.campaign_level)
            if errors:
                self.notice=errors[0]
                return
            if self.campaign_level==7:
                try:
                    self.campaign.commit(self.draft,7)
                except ValueError as exc:
                    self.notice=str(exc)
                    return
                self.state='ENG_RESULT'
                self.notice='Mission certified.'+self.campaign_save_now()
            else:
                self.exercise=Exercise(self.campaign,self.draft,self.campaign_level)
                self.state='ENG_TRIAL'
                self.notice='Each stage is a teaching exercise, not a physical spacecraft simulation.'

        def start_exercise_stage(self):
            if not self.exercise.start_stage():
                self.notice='Align within +/-10 m before engaging autonomous docking.'
            else:
                self.notice='Running the verified subsystem check.'

        def finish_exercise(self):
            try:
                self.exercise.finish()
            except ValueError as exc:
                self.notice=str(exc)
                self.state='ENG_BUILD'
                return
            self.state='ENG_RESULT'
            self.notice='Mission complete.'+self.campaign_save_now()

        def engineering_header(self,title):
            self.screen.fill((8,13,27))
            self.text('STARLINER / ENGINEERING',25,24,CYAN,'big')
            self.text(title,25,83,GOLD)

        def engineering_footer(self,back,back_title='Level selection',forward=None,forward_title='Continue'):
            self.wrap(self.notice,30,835,650,GOLD)
            self.button(back_title,(25,910,265,48),back)
            if forward:
                self.button(forward_title,(310,910,385,48),forward)
            self.text('ESC: back | Engineering specifications are simplified game values.',25,978,size='small')

        def back_to_levels(self):
            self.state='ENG_SELECT'
            self.notice='Choose any completed/current level. Uncommitted previews are discarded.'

        def main_menu(self):
            super().main_menu()
            self.notice='Engineering campaign saves separately from the original arcade game.'

        def draw_engineering_menu(self):
            self.background.draw(self.screen)
            self.text('STARLINER',240,155,CYAN,'big')
            self.text('Engineering campaign + flight sandbox',175,216)
            self.button('Unlock All Levels',(475,25,220,44),self.unlock_everything)
            self.text('Debug access: '+('ON' if self.campaign.unlock_all else 'OFF'),480,79,GOLD,'small')
            self.button('Engineering / Continue',(170,370,380,58),lambda:self.campaign_start(True))
            self.button('New Engineering Campaign',(170,447,380,58),lambda:setattr(self,'state','ENG_NEW_CONFIRM'))
            self.button('Arcade Flight Sandbox',(170,524,380,58),lambda:self.start('sandbox'))
            self.button('Legacy Arcade Campaign',(170,601,380,58),lambda:self.start('campaign',True))
            self.button('Quit',(170,678,380,58),self.quit)
            self.wrap(self.notice,45,775,630,GOLD)
            self.wrap(DISCLAIMER,45,904,630)

        def draw_level_select(self):
            self.engineering_header('Select a mission')
            self.text('Unlocked: completed/current missions'+(' | DEBUG: all screens' if self.campaign.unlock_all else ''),25,129,size='small')
            for level,name in enumerate(LEVELS,1):
                available=self.campaign.available(level)
                label='DONE' if level in self.campaign.completed else 'OPEN' if available else 'LOCKED'
                self.button(f'{level}. {name} [{label}]',(30,180+(level-1)*82,660,64),
                            lambda n=level:self.select_level(n),level==self.campaign.current_level())
            self.notice=self.notice or 'Choose a mission to read its engineering briefing.'
            self.engineering_footer(self.main_menu,'Main menu')

        def draw_briefing(self):
            level=self.campaign_level
            title,significance,mechanics=BRIEFINGS[level-1]
            self.engineering_header(f'Level {level}/7 - {LEVELS[level-1]}')
            self.text(title,35,180,CYAN,'big')
            y=self.wrap(significance,35,255,645)
            self.text('New mechanics',35,y+45,GOLD)
            y=self.wrap(mechanics,35,y+82,645)
            self.wrap('Earlier subsystem exercises remain active as levels advance. '
                      'No later-system mechanics appear in Level 1. Unlock All opens screens, '
                      'not valid components or automatic completion.',35,y+45,645)
            self.engineering_footer(self.back_to_levels,forward=self.enter_design,forward_title='Start engineering design')

        def component_lines(self,c):
            s=c.specifications
            if c.category=='Fuel':
                return [f"{s['shape']} | Empty {s['empty_mass_lb']:g} lb | Capacity {s['capacity_l']:g} L"]
            if c.category=='Navigation':
                return [f"Capability {s.get('navigation_display',str(s['navigation_capability_km'])+' km')} | Error +/-{s['accuracy_error_m']:g} m | Mass {s['mass_kg']:g} kg"]
            if c.category=='Structure':
                return [f"{s['material']} | Structure {s['structure_mass_kg']:g} kg | Payload {s['payload_rating_kg']:g} kg"]
            if c.category=='Power':
                return [f"{s['technology']} | Output {s['output_kw']:g} kW | Mass {s['mass_kg']:g} kg"]
            if c.category=='Communications':
                return [f"{s['technology']} | {s['data_rate_mbps']:g} Mbps | Mass {s['mass_kg']:g} kg"]
            return [f"{s['crew_capacity']} crew | {s['duration_days']:g} days | Mass {s['mass_kg']:g} kg"]

        def detail_lines(self,c):
            result=validate_component(c,self.engineering_mission)
            lines=[]
            if c.category=='Navigation': lines.append(('Smaller position error is better.',CYAN))
            if c.category=='Structure': lines.append(('Payload rating does not override the structure-mass limit.',CYAN))
            if c.category=='Power':
                m=self.engineering_mission
                lines.append(('Mode: '+('strict generation' if m.require_generation else 'electrical supply'),CYAN))
                lines.append(('kW = power; kWh = stored energy.',CYAN))
                if c.id=='P2':
                    lines.append(('Potential saving: $11M, ONLY if all conditions pass.',GOLD))
                    lines.append(('Battery duration: '+str(m.battery_duration_hours)+' h',WHITE))
                    lines.append(('Usable energy: '+str(c.specifications.get('usable_energy_kwh','unverified'))+' kWh',WHITE))
                    lines.append((f'Recharge allowed: {m.recharge_allowed}; external support: {m.external_support_allowed}',WHITE))
            if c.id=='C2': lines.append(('Potential saving: $8M; coverage is not proven by data rate.',GOLD))
            if c.id=='C1': lines.append(('64 kbps = 0.064 Mbps.',CYAN))
            if c.category=='Lifetime': lines.append(('No station support is assumed for this rating.',CYAN))
            lines.extend((('PASS: ' if check.status=='passing' else 'FAIL: ' if check.status=='failing' else 'VERIFY: ')+check.message,
                          STATUS_COLOR[check.status]) for check in result.checks)
            if c.assumption: lines.append((c.assumption,GOLD))
            return lines

        def draw_build(self):
            cat=CATEGORIES[self.view_category]
            level=self.campaign_level
            self.engineering_header(f'Level {level}/7 - '+(cat+' comparison' if level==7 else LEVELS[level-1]))
            r=self.campaign.report(self.draft)
            self.text(f"Preview {money(r['cost_dollars'])} | Remaining {money(r['remaining_dollars'])}",30,133,CYAN)
            self.text('Total is partial until all six categories are selected.',30,166,size='small')
            parts=[c for c in self.engineering_catalog.values() if c.category==cat]
            for i,c in enumerate(parts):
                y=207+i*77
                result=validate_component(c,self.engineering_mission)
                status={'passing':'PASS','failing':'FAIL','unverified':'VERIFY'}[result.status]
                self.button(f'{c.id}  {c.name}  {money(c.cost_dollars)}  [{status}]',
                    (25,y,670,36),lambda cid=c.id:self.engineering_choose(cid),self.draft[cat]==c.id)
                for j,line in enumerate(self.component_lines(c)):
                    self.text(line,34,y+40+j*21,STATUS_COLOR[result.status],'small')
            cid=self.draft[cat]
            self.text('Requirement checklist (scroll for all checks)',30,533,GOLD)
            pg.draw.rect(self.screen,(15,25,43),(25,563,670,248))
            old_clip=self.screen.get_clip()
            self.screen.set_clip(pg.Rect(30,568,660,238))
            if cid:
                lines=self.detail_lines(self.engineering_catalog[cid])
                # Measure wrapping so long assumption/coverage notes are never hidden horizontally.
                y=574-self.detail_scroll
                for line,color in lines:
                    y=self.wrap(line,35,y,640,color)+2
                content_height=y+self.detail_scroll-574
                self.max_detail_scroll=max(0,content_height-225)
            else:
                self.text('Select a component to inspect every requirement.',35,580)
                self.max_detail_scroll=0
            self.screen.set_clip(old_clip)
            self.detail_scroll=max(0,min(self.detail_scroll,self.max_detail_scroll))
            if level==7:
                self.engineering_footer(lambda:setattr(self,'state','ENG_BUDGET'),'Budget overview',
                    lambda:setattr(self,'state','ENG_BUDGET'),'Keep preview / overview')
            else:
                self.engineering_footer(self.back_to_levels,forward=self.test_design,forward_title='Validate / run mission exercise')

        def draw_budget(self):
            self.engineering_header('Level 7/7 - Budget Optimization')
            r=self.campaign.report(self.draft)
            self.text('All six selections (click a row to compare)',30,125,CYAN)
            self.text('Baseline: $135M | Original cap: $200M | Baseline remainder: $65M',30,153,size='small')
            for i,cat in enumerate(CATEGORIES):
                cid=self.draft[cat]
                result=r['components'][cat]
                name=self.engineering_catalog[cid].name if cid else 'Not selected'
                cost=money(self.engineering_catalog[cid].cost_dollars) if cid else '--'
                self.button(f'{cid or cat} {name} | {cost} [{result.status.upper()}]',
                    (25,178+i*66,670,50),lambda index=i:self.budget_category(index))
            self.text(f"Total {money(r['cost_dollars'])} / {money(self.engineering_mission.budget_dollars)} cap",30,588,CYAN)
            self.text(f"Remaining {money(r['remaining_dollars'])} | Savings {money(r['savings_dollars'])}",30,620)
            minimum=self.best['minimum_cost_dollars']
            self.text('Lowest-cost verified solution: '+(money(minimum) if minimum is not None else 'None for this profile'),30,652,GOLD)
            best_ids=' / '.join(self.best['solutions'][0][1][cat] for cat in CATEGORIES) if self.best['solutions'] else '--'
            self.text('Verified optimum: '+best_ids,30,684,size='small')
            self.text('Configuration: '+('CERTIFIABLE' if r['passed'] else 'NOT CERTIFIABLE'),30,716,GREEN if r['passed'] else RED)
            self.wrap('Conditional opportunities: P2 saves $11M only with valid energy/mission conditions; '
                      'C2 saves $8M only with verified coverage and interfaces. Requirements are never relaxed automatically.',30,752,650)
            self.engineering_footer(self.back_to_levels,forward=self.test_design,forward_title='Certify spacecraft')

        def draw_trial(self):
            ex=self.exercise
            self.engineering_header(f'Level {ex.level}: integrated teaching exercise')
            self.text('Active systems: '+', '.join(CATEGORIES[:ex.level]),30,135,CYAN,'small')
            self.text(f'Stage {ex.index+1}/{len(ex.stages)} - {LEVELS[ex.stage-1]}',30,190,GOLD)
            stage=ex.stage
            c=self.engineering_catalog[ex.config[CATEGORIES[stage-1]]]
            self.text(c.id+' '+c.name,30,235)
            notes={
              1:'Open the valve to verify capacity, empty mass, propellant compatibility and connection.',
              2:'Align the approach marker within +/-10 m, then engage autonomous docking. Left/right or A/D: 5 m steps.',
              3:'Apply the 6000 kg payload check. Payload rating and frame mass remain separate requirements.',
              4:'Run the electrical check. Verified capability and energy conditions govern passing, not animation time.',
              5:'Transmit telemetry using the selected data rate and verified ground/relay coverage.',
              6:'Run the four-person, 170-day life-support exercise. Days shown are accelerated display time only.'}
            self.wrap(notes[stage],30,290,650)
            if stage==2:
                pg.draw.line(self.screen,WHITE,(60,475),(660,475),2)
                pg.draw.rect(self.screen,(25,90,65),(330,450,60,50))
                x=360+ex.offset_m*3
                pg.draw.circle(self.screen,GOLD,(int(x),475),12)
                self.text(f'Approach offset {ex.offset_m:+.0f} m (target +/-10 m)',80,530,CYAN)
                self.button('Left / -5 m',(100,580,230,45),lambda:ex.align(-5))
                self.button('Right / +5 m',(370,580,230,45),lambda:ex.align(5))
            else:
                lines=self.component_lines(c)
                self.wrap(lines[0],30,435,650,CYAN)
                if stage==6:
                    self.text(f'Exercise day {170*ex.progress:.0f} / 170 | Crew: 4',30,530)
                if stage==4:
                    self.wrap('Baseline availability flags are explicit game assumptions, '
                              'not an eclipse or battery-discharge simulation.',30,510,650,GOLD)
            pg.draw.rect(self.screen,(30,45,65),(35,690,650,22))
            pg.draw.rect(self.screen,GREEN,(35,690,int(650*ex.progress),22))
            self.text('Completed checks: '+(', '.join(str(n) for n in ex.completed_stages) or 'none yet'),30,745,size='small')
            labels={1:'Open valve / check tank',2:'Engage autonomous docking',3:'Apply 6000 kg payload',
                    4:'Run power check',5:'Transmit telemetry',6:'Run 170-day exercise'}
            self.engineering_footer(lambda:setattr(self,'state','ENG_BUILD'),'Back to design',
                                    self.start_exercise_stage,labels[stage] if not ex.active else 'Checking...')

        def draw_result(self):
            self.engineering_header('Mission complete / '+LEVELS[self.campaign_level-1])
            self.text('ENGINEERING CHECK PASSED',70,230,GREEN,'big')
            r=self.campaign.report()
            self.wrap('Your selected components and progress were revalidated. '
                      'You can revisit earlier levels without resetting unrelated selections.',40,330,640)
            self.text(f"Selected cost: {money(r['cost_dollars'])}",40,445,CYAN)
            if self.campaign_level==7:
                minimum=self.best['minimum_cost_dollars']
                self.text('Certification: '+('PASS' if r['passed'] else 'FAIL'),40,500,GREEN if r['passed'] else RED)
                self.text(f"Savings vs baseline: {money(r['savings_dollars'])}",40,545)
                self.text('Minimum verified cost: '+(money(minimum) if minimum is not None else 'none'),40,590,GOLD)
                self.wrap('Certification and optimization are separate results. '
                          'If the baseline is the cheapest verified solution, it still completes the mission.',40,650,640)
            else:
                self.wrap('The next level adds '+(CATEGORIES[self.campaign_level]+' checks.' if self.campaign_level<6 else 'whole-spacecraft budget optimization.'),40,520,640)
            self.engineering_footer(self.main_menu,'Main menu',self.back_to_levels,'Choose next / revisit level')

        def draw(self):
            if self.state!='MAIN_MENU' and not self.state.startswith('ENG_'):
                return super().draw()
            self.buttons=[]
            self.screen.fill((8,13,27))
            if self.state=='MAIN_MENU': self.draw_engineering_menu()
            elif self.state=='ENG_SELECT': self.draw_level_select()
            elif self.state=='ENG_BRIEF': self.draw_briefing()
            elif self.state=='ENG_BUILD': self.draw_build()
            elif self.state=='ENG_BUDGET': self.draw_budget()
            elif self.state=='ENG_TRIAL': self.draw_trial()
            elif self.state=='ENG_RESULT': self.draw_result()
            elif self.state=='ENG_NEW_CONFIRM':
                self.engineering_header('Start a new engineering campaign?')
                self.wrap('This starts an empty design. The previous engineering save will be replaced '
                          'only when you complete a mission or explicitly use Unlock All. '
                          'The legacy arcade save is separate.',40,280,640)
                self.engineering_footer(self.main_menu,'Cancel',lambda:self.campaign_start(False),'Start new campaign')
            pg.transform.smoothscale(self.screen,self.window_size,self.window)
            pg.display.flip()

        def update(self,dt):
            if self.state=='MAIN_MENU':
                self.background.update(dt)
            elif self.state=='ENG_TRIAL':
                self.exercise.update(dt)
                if self.exercise.done: self.finish_exercise()
            elif not self.state.startswith('ENG_'):
                super().update(dt)

        def handle(self,event):
            if self.state!='MAIN_MENU' and not self.state.startswith('ENG_'):
                return super().handle(event)
            if event.type==pg.QUIT:
                self.quit()
            elif event.type==pg.KEYDOWN:
                if event.key==pg.K_ESCAPE:
                    if self.state=='MAIN_MENU': self.quit()
                    elif self.state in ('ENG_SELECT','ENG_NEW_CONFIRM'): self.main_menu()
                    elif self.state=='ENG_TRIAL': self.state='ENG_BUILD'
                    elif self.state=='ENG_BUILD' and self.campaign_level==7: self.state='ENG_BUDGET'
                    else: self.back_to_levels()
                elif self.state=='ENG_TRIAL':
                    if event.key in (pg.K_LEFT,pg.K_a): self.exercise.align(-5)
                    elif event.key in (pg.K_RIGHT,pg.K_d): self.exercise.align(5)
                    elif event.key==pg.K_SPACE: self.start_exercise_stage()
                elif self.state=='ENG_BUILD' and event.key in (pg.K_DOWN,pg.K_UP):
                    self.detail_scroll=max(0,min(getattr(self,'max_detail_scroll',0),
                        self.detail_scroll+(45 if event.key==pg.K_DOWN else -45)))
            elif event.type==pg.MOUSEWHEEL and self.state=='ENG_BUILD':
                self.detail_scroll=max(0,min(getattr(self,'max_detail_scroll',0),self.detail_scroll-event.y*35))
            elif event.type==pg.MOUSEBUTTONDOWN and event.button==1:
                position=self.mouse_position(event.pos)
                for rect,callback in self.buttons:
                    if rect.collidepoint(position):
                        callback()
                        return
    return EngineeringGame
