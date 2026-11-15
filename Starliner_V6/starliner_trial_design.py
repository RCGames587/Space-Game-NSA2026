"""Trial-and-error design over the shared native flight adapter."""
from starliner_engineering_data import BASELINE,CATEGORIES,LABELS

class FlightAuthorization:
    """Suppress preflight prediction gates, never final certification checks."""
    def __init__(self,campaign):self.original=campaign
    def readiness(self,*args,**kwargs):return []
    def __getattr__(self,key):return getattr(self.original,key)


def wrap_trial_game(SharedFlightGame,BaseGame,pg):
    class TrialGame(SharedFlightGame):
        def _editable(self):return CATEGORIES[:min(self.campaign_level,6)]

        def _fill_background(self,config):
            result=dict(config)
            for cat in CATEGORIES:
                if cat not in self._editable():result[cat]=BASELINE[cat]
            return result

        def enter_design(self):
            super().enter_design()
            self.draft=self._fill_background(self.draft)
            self.state='ENG_BUILD';self.detail_scroll=0;self.design_checked=False
            self.notice='Compare projected values, choose a build, and learn from the test flight.'

        def engineering_choose(self,cid):
            component=self.engineering_catalog.get(cid)
            if component is None or component.category not in self._editable():return
            self.draft[component.category]=cid;self.detail_scroll=0;self.design_checked=False
            self.notice='Design updated. Test flight will determine the outcome.'

        def change_category(self,n):
            if type(n) is int and 0<=n<len(self._editable()):self.view_category=n;self.detail_scroll=0

        def budget_category(self,n):self.change_category(n);self.state='ENG_BUILD'

        def test_design(self):
            config=self._fill_background(self.draft)
            for cat in CATEGORIES:
                cid=config.get(cat)
                if cid not in self.engineering_catalog or self.engineering_catalog[cid].category!=cat:
                    self.notice='Select a component for '+cat+'.';return
            if not self.campaign.available(self.campaign_level):
                self.notice='This mission is locked.';return
            self.draft=config.copy();self._shared_config=config.copy();self._shared_level=self.campaign_level
            self._shared_systems=self._editable();self._shared_checks=0
            import random
            self._shared_offset=random.choice(tuple(range(-95,-14,5))+tuple(range(15,96,5)))
            self.state='ENG_SHARED_CHECKS'
            self.design_checked=False
            self.notice='Complete preflight procedures to authorize the test flight.'

        def _shared_verify(self):
            cat=self._shared_systems[self._shared_checks]
            if cat=='Navigation' and abs(self._shared_offset)>10:
                self.notice='Align within +/-10 m using Left/Right or A/D.';return
            self._shared_checks+=1
            if self._shared_checks==len(self._shared_systems):self._begin_shared_flight()
            else:self.notice=cat+' procedure complete. Next: '+self._shared_systems[self._shared_checks]+'.'

        def _begin_shared_flight(self):
            campaign=self.campaign
            self.campaign=FlightAuthorization(campaign)
            try:super()._begin_shared_flight()
            finally:self.campaign=campaign
            if self._shared_active:
                self.design_checked=True
                self.notice='Test flight authorized. Use the launch controls to begin.'

        def tick_systems(self,dt):
            if not self._shared_active:return super().tick_systems(dt)
            campaign=self.campaign
            self.campaign=FlightAuthorization(campaign)
            try:return super().tick_systems(dt)
            finally:self.campaign=campaign

        def detail_lines(self,c):
            return [(LABELS.get(key,key.replace('_',' '))+': '+str(value),(228,236,250))
                    for key,value in c.specifications.items()]

        def _projected_lines(self):
            key=(self.campaign_level,tuple(self.draft.get(cat) for cat in CATEGORIES))
            if getattr(self,'_projection_key',None)==key:return self._projection_value
            editable=self._editable()
            fixed=[f'{cat}: {BASELINE[cat]}' for cat in CATEGORIES if cat not in editable]
            lines=['Automatic baseline equipment: '+(', '.join(fixed) if fixed else 'all systems selected by player')]
            legacy=BaseGame.start.__globals__
            metrics=legacy.get('metrics');catalog=legacy.get('CATALOG',{})
            if metrics and all(self.draft.get(cat) in catalog for cat in CATEGORIES):
                values=metrics(self.draft)
                for key,label in (('dry','Dry mass'),('wet','Launch mass'),('fuel','Propellant'),
                                  ('demand','Electrical demand (kW)'),('generation','Generation (kW)'),('battery','Stored energy (kWh)')):
                    if key in values:lines.append('Flight projection / '+label+': '+format(values[key],'.2f'))
            self._projection_key=key;self._projection_value=lines
            return lines

        def draw_build(self):
            self.buttons=[];self.screen.fill((8,13,27))
            white=(228,236,250);cyan=(80,215,240);gold=(255,205,100)
            self._shared_text('ENGINEERING / PROJECTED VALUES',360,55,cyan,'big')
            self._shared_text('Level '+str(self.campaign_level)+' / Design and test',360,103,gold)
            editable=self._editable()
            self.view_category=max(0,min(self.view_category,len(editable)-1))
            cat=CATEGORIES[self.view_category];count=len(editable);width=670//count
            for i,name in enumerate(editable):
                self.button(name[:8],(25+i*width,135,width-4,36),lambda n=i:self.change_category(n),i==self.view_category)
            cost=sum(self.engineering_catalog[cid].cost_dollars for cid in self.draft.values() if cid in self.engineering_catalog)
            budget=self.engineering_mission.budget_dollars
            self._shared_text(f'Projected cost ${cost/1000000:g}M | Budget ${budget/1000000:g}M',360,197,cyan,'small')
            parts=[c for c in self.engineering_catalog.values() if c.category==cat]
            for i,c in enumerate(parts):
                y=225+i*80
                visual=getattr(self,'part_visual',None)
                if visual:visual(c,(25,y,83,70))
                left=120 if visual else 25
                self.button(c.id+'  '+c.name,(left,y,695-left,37),lambda cid=c.id:self.engineering_choose(cid),self.draft[cat]==c.id)
                self._shared_text(f'Price ${c.cost_dollars/1000000:g}M',400,y+57,white,'small')
            pg.draw.rect(self.screen,(15,25,43),(25,555,670,250))
            old=self.screen.get_clip();self.screen.set_clip(pg.Rect(30,560,660,240))
            cid=self.draft.get(cat);lines=[]
            if cid in self.engineering_catalog:lines.extend(text for text,color in self.detail_lines(self.engineering_catalog[cid]))
            else:lines.append('Select a component to see its projected specifications.')
            lines.extend(self._projected_lines())
            y=575-self.detail_scroll
            for text in lines:
                words=text.split();line=''
                for word in words:
                    candidate=(line+' '+word).strip()
                    if self.small.size(candidate)[0]>625 and line:
                        self._shared_text(line,360,y,white,'small');y+=26;line=word
                    else:line=candidate
                if line:self._shared_text(line,360,y,white,'small');y+=26
            self.max_detail_scroll=max(0,y+self.detail_scroll-790)
            self.detail_scroll=max(0,min(self.detail_scroll,self.max_detail_scroll));self.screen.set_clip(old)
            self._shared_text(self.notice,360,845,gold,'small')
            self.button('Level selection',(25,920,270,48),self.back_to_levels)
            self.button('Prepare test flight',(310,920,385,48),self.test_design)

        def draw_budget(self):return self.draw_build()

        def draw(self):
            if not self._shared_active and self.state in ('ENG_BUILD','ENG_BUDGET'):
                self.draw_build();pg.transform.smoothscale(self.screen,self.window_size,self.window);pg.display.flip();return
            return super().draw()
    return TrialGame
