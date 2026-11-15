"""NASA rescue campaign interface; no agency logos or insignia."""
from pathlib import Path
import json
import math
from starliner_engineering_data import CATEGORIES,LEVELS,DISCLAIMER,LABELS,validate_component
from starliner_campaign import Campaign,BRIEFINGS,SAVE_PATH
from starliner_mission import MissionFlight

WHITE=(228,236,250);CYAN=(80,215,240);GOLD=(255,205,100)
GREEN=(100,230,160);RED=(250,105,110)
COLORS={'passing':GREEN,'failing':RED,'unverified':GOLD}

def money(n):return f'${n/1000000:,.3f}M'.replace('.000M','M')

def make_game_class(BaseGame,pg):
    class EngineeringGame(BaseGame):
        def __init__(self,save_path,mission,catalog,campaign_save=SAVE_PATH):
            super().__init__(save_path)
            self.engineering_mission=mission;self.engineering_catalog=catalog
            self.campaign_path=Path(campaign_save);self.campaign=Campaign(mission,catalog)
            self.campaign_level=1;self.campaign_loaded=False;self.detail_scroll=0
            self.font=pg.font.SysFont('dejavusans,arial',23)
            self.small=pg.font.SysFont('dejavusans,arial',18)
            self.big=pg.font.SysFont('dejavusans,arial',32,bold=True)
            self.notice='NASA rescue operations | Seven cumulative engineering missions'
            self.asset_root=Path(__file__).resolve().parent
            self.asset_manifest={};self.asset_cache={}
            manifest=self.asset_root/'assets'/'parts.json'
            if manifest.exists():
                with manifest.open(encoding='utf8') as stream:self.asset_manifest=json.load(stream)

        def centered(self,text,y,color=WHITE,size='normal',left=25,width=670):
            font=self.big if size=='big' else self.small if size=='small' else self.font
            text=str(text).replace('SpaceX','NASA').replace('SPACEX','NASA').replace('spacex','NASA')
            while font.size(text)[0]>width and len(text)>2:text=text[:-2]+'…' if not text.endswith('…') else text[:-2]+'…'
            rendered=font.render(text,True,color)
            self.screen.blit(rendered,(left+(width-rendered.get_width())//2,y))

        def button(self,title,rect,callback,selected=False):
            rect=pg.Rect(rect)
            pg.draw.rect(self.screen,(28,68,85) if selected else (22,37,57),rect,border_radius=8)
            pg.draw.rect(self.screen,CYAN if selected else (65,95,120),rect,2,border_radius=8)
            title=str(title).replace('SpaceX','NASA')
            font=self.font
            for size in range(22,12,-1):
                font=pg.font.SysFont('dejavusans,arial',size)
                if font.size(title)[0]<=rect.w-20:break
            image=font.render(title,True,WHITE)
            self.screen.blit(image,image.get_rect(center=rect.center))
            self.buttons.append((rect,callback))

        def paragraph(self,text,y,width=650,color=WHITE):
            words=str(text).replace('SpaceX','NASA').split();line=''
            for word in words:
                candidate=(line+' '+word).strip()
                if self.font.size(candidate)[0]>width and line:
                    self.centered(line,y,color,left=(720-width)//2,width=width);y+=31;line=word
                else:line=candidate
            if line:self.centered(line,y,color,left=(720-width)//2,width=width);y+=31
            return y

        def header(self,title):
            self.screen.fill((8,13,27));self.centered('STARLINER / NASA RESCUE',25,CYAN,'big')
            self.centered(title,80,GOLD)

        def footer(self,back,back_title='Level selection',forward=None,forward_title='Continue'):
            self.paragraph(self.notice,825,color=GOLD)
            self.button(back_title,(25,920,270,48),back)
            if forward:self.button(forward_title,(310,920,385,48),forward)
            self.centered('ESC: back',977,size='small')

        def campaign_save_now(self):
            try:self.campaign.save(self.campaign_path);return ' Progress saved.'
            except (OSError,ValueError) as exc:return ' Save failed: '+str(exc)

        def campaign_start(self,load=False):
            try:self.campaign=Campaign.load(self.campaign_path,self.engineering_mission,self.engineering_catalog) if load else Campaign(self.engineering_mission,self.engineering_catalog)
            except FileNotFoundError:self.campaign=Campaign(self.engineering_mission,self.engineering_catalog)
            except (ValueError,OSError,TypeError,KeyError) as exc:self.notice=str(exc);return
            self.campaign_loaded=True;self.state='ENG_SELECT';self.modal=False
            self.notice='Every mission ends with launch, rescue, return and safe reentry.'

        def back_to_levels(self):self.state='ENG_SELECT';self.notice='Select a mission.'

        def unlock_everything(self):
            if not self.campaign_loaded and self.campaign_path.exists():
                try:self.campaign=Campaign.load(self.campaign_path,self.engineering_mission,self.engineering_catalog)
                except (OSError,ValueError,TypeError,KeyError) as exc:self.notice='Unlock cancelled: '+str(exc);return
            self.campaign_loaded=True;self.campaign.unlock_all=True
            self.notice='All missions unlocked; verification is still required.'+self.campaign_save_now()

        def select_level(self,n):
            if not self.campaign.available(n):self.notice='Complete the previous mission first.';return
            self.campaign_level=n;self.state='ENG_BRIEF';self.notice='Read the significance, then design your spacecraft.'

        def enter_design(self):
            self.draft=self.campaign.config.copy();self.view_category=min(5,self.campaign_level-1)
            self.detail_scroll=0;self.state='ENG_BUILD';self.notice='Select parts, inspect requirements, then begin verification.'

        def engineering_choose(self,cid):
            self.draft[self.engineering_catalog[cid].category]=cid;self.detail_scroll=0
            self.notice='Preview updated. Progress saves only after safe recovery.'

        def test_design(self):
            try:self.flight=MissionFlight(self.campaign,self.draft,self.campaign_level)
            except ValueError as exc:self.notice=str(exc);return
            self.state='ENG_FLIGHT';self.notice=self.flight.message

        def part_visual(self,c,rect):
            rect=pg.Rect(rect);pg.draw.rect(self.screen,(18,33,52),rect,border_radius=9)
            peers=[p for p in self.engineering_catalog.values() if p.category==c.category]
            variant=peers.index(c);palette=((110,195,240),(230,175,90),(125,225,180),(205,150,240))
            color=palette[variant%len(palette)]
            item=self.asset_manifest.get(c.id,self.asset_manifest.get(c.category,{}))
            if isinstance(item,str):item={'file':item}
            name=item.get('file') if isinstance(item,dict) else None
            if not name:
                for stem in (c.id.lower(),c.category.lower()+str(variant+1), 'hull'+str(variant+1) if c.category=='Structure' else ''):
                    if stem and (self.asset_root/'assets'/'parts'/(stem+'.png')).exists():name='parts/'+stem+'.png';break
            if name:
                try:
                    path=(self.asset_root/'assets'/name).resolve()
                    if self.asset_root not in path.parents:raise ValueError('Asset path must remain inside game directory')
                    key=(str(path),tuple(item.get('tint',color)))
                    if key not in self.asset_cache:
                        image=pg.image.load(str(path)).convert_alpha()
                        tint=pg.Surface(image.get_size(),pg.SRCALPHA);tint.fill((*key[1][:3],255));image.blit(tint,(0,0),special_flags=pg.BLEND_RGBA_MULT)
                        self.asset_cache[key]=image
                    image=self.asset_cache[key];scale=min((rect.w-12)/image.get_width(),(rect.h-12)/image.get_height())
                    image=pg.transform.smoothscale(image,(max(1,int(image.get_width()*scale)),max(1,int(image.get_height()*scale))))
                    self.screen.blit(image,image.get_rect(center=rect.center));return
                except (OSError,ValueError,pg.error):pass
            cx,cy=rect.center;w=min(rect.w-18,65);h=min(rect.h-16,65)
            if c.category in ('Fuel','Structure','Lifetime'):
                pg.draw.rect(self.screen,color,(cx-w//3,cy-h//2,w*2//3,h),border_radius=8+variant*2)
                pg.draw.line(self.screen,WHITE,(cx-w//3,cy),(cx+w//3,cy),2)
                if c.category=='Structure':pg.draw.polygon(self.screen,color,[(cx-w//3,cy-h//2),(cx,cy-h//2-9),(cx+w//3,cy-h//2)])
            elif c.category=='Power':
                for sign in (-1,1):
                    pg.draw.rect(self.screen,color,(cx+sign*24-17,cy-23,34,46),2)
                    pg.draw.line(self.screen,color,(cx+sign*24,cy-23),(cx+sign*24,cy+23),2)
                pg.draw.rect(self.screen,WHITE,(cx-5,cy-16,10,32))
            elif c.category=='Communications':
                pg.draw.arc(self.screen,color,(cx-25,cy-26,50,45),math.pi,2*math.pi,5)
                pg.draw.line(self.screen,WHITE,(cx,cy),(cx,cy+25),3)
                pg.draw.circle(self.screen,color,(cx,cy-20),4)
            else:
                pg.draw.circle(self.screen,color,(cx,cy),27,3)
                pg.draw.line(self.screen,WHITE,(cx-32,cy),(cx+32,cy),2)
                pg.draw.line(self.screen,WHITE,(cx,cy-32),(cx,cy+32),2)
            self.centered(c.id,rect.bottom-22,color,'small',rect.x,rect.w)

        def draw_build(self):
            self.header(f'Level {self.campaign_level} / Rocket design')
            count=min(self.campaign_level,6);cat=CATEGORIES[self.view_category]
            for i in range(count):
                self.button(CATEGORIES[i][:7],(25+i*(670//count),125,670//count-4,36),lambda n=i:self.change_category(n),i==self.view_category)
            report=self.campaign.report(self.draft)
            self.centered(f"Selected {money(report['cost_dollars'])} | Remaining {money(report['remaining_dollars'])}",175,CYAN,'small')
            parts=[c for c in self.engineering_catalog.values() if c.category==cat]
            for i,c in enumerate(parts):
                y=215+i*91;status=validate_component(c,self.engineering_mission)
                self.part_visual(c,(25,y,88,82))
                self.button(f'{c.id}  {c.name}',(125,y,570,39),lambda cid=c.id:self.engineering_choose(cid),self.draft[cat]==c.id)
                self.centered(f'{money(c.cost_dollars)} | {status.status.upper()}',y+48,COLORS[status.status],'small',125,570)
            pg.draw.rect(self.screen,(15,25,43),(25,590,670,217))
            old=self.screen.get_clip();self.screen.set_clip(pg.Rect(30,595,660,207))
            y=600-self.detail_scroll;cid=self.draft[cat]
            if cid:
                c=self.engineering_catalog[cid]
                for key,value in c.specifications.items():y=self.paragraph(LABELS.get(key,key.replace('_',' '))+': '+str(value),y,630)
                for check in validate_component(c,self.engineering_mission).checks:y=self.paragraph(check.message,y,630,COLORS[check.status])
                if c.assumption and not any(term in c.assumption.lower() for term in ('game assumption','not a real','arcade values')):
                    y=self.paragraph(c.assumption,y,630,GOLD)
            else:y=self.paragraph('Choose a component to inspect requirements.',y)
            self.max_detail_scroll=max(0,y+self.detail_scroll-790);self.screen.set_clip(old)
            self.footer(self.back_to_levels,forward=self.test_design,forward_title='Verify and fly mission')

        def change_category(self,n):self.view_category=n;self.detail_scroll=0

        def draw_flight(self):
            f=self.flight;self.header(f'Level {f.level} / '+f.phase.replace('_',' '))
            self.centered('Active: '+', '.join(f.systems),126,CYAN,'small')
            if f.phase=='CHECKS':
                self.centered('Preflight: '+f.current_system,220,GOLD,'big')
                cid=f.config[f.current_system];self.part_visual(self.engineering_catalog[cid],(280,300,160,120))
                if f.current_system=='Navigation':
                    pg.draw.line(self.screen,WHITE,(60,490),(660,490),2);pg.draw.rect(self.screen,(25,90,65),(330,467,60,46))
                    pg.draw.circle(self.screen,GOLD,(int(360+f.offset_m*3),490),12)
                    self.centered(f'Calibration offset {f.offset_m:+.0f} m | Target +/-10 m',545,CYAN)
                    self.button('Left / -5 m',(70,600,260,44),lambda:f.align(-5));self.button('Right / +5 m',(390,600,260,44),lambda:f.align(5))
                self.paragraph('Verified: '+(', '.join(f.checked) or 'none'),690)
            elif f.phase in ('OUTBOUND','RETURN','RESCUE'):
                pg.draw.rect(self.screen,(13,25,42),(35,180,650,600),border_radius=10)
                pg.draw.circle(self.screen,GOLD,tuple(map(int,f.station)),32,3)
                pg.draw.circle(self.screen,GREEN,tuple(map(int,f.home)),32,3)
                route=[tuple(f.pos)]+f.route
                if len(route)>1:pg.draw.lines(self.screen,CYAN,False,route,2)
                for point in f.route:pg.draw.circle(self.screen,CYAN,tuple(map(int,point)),7,2)
                x,y=f.pos;angle=math.atan2(f.vel[1],f.vel[0]) if any(f.vel) else -math.pi/2
                points=[(x+18*math.cos(angle),y+18*math.sin(angle)),(x+12*math.cos(angle+2.5),y+12*math.sin(angle+2.5)),(x+12*math.cos(angle-2.5),y+12*math.sin(angle-2.5))]
                pg.draw.polygon(self.screen,WHITE,points)
                self.centered('Gold: rescue station | Green: return gate | T: telemetry',789,size='small')
            elif f.phase in ('LAUNCH','REENTRY'):
                self.centered(f'Altitude {f.altitude:.1f} km',230,CYAN,'big')
                x=360+int(f.bank*80);y=660-int(f.altitude*3)
                pg.draw.polygon(self.screen,WHITE,[(x,y-25),(x-15,y+20),(x+15,y+20)])
                if f.chute:pg.draw.arc(self.screen,GOLD,(x-45,y-70,90,55),0,math.pi,4)
                self.centered(f'Heat {f.heat:.0f} / 100 | Parachute: '+('deployed' if f.chute else 'stowed'),720,GOLD)
            else:
                self.centered('SAFE RECOVERY' if f.phase=='VICTORY' else 'MISSION FAILED',240,GREEN if f.phase=='VICTORY' else RED,'big')
                y=340
                for cat,proof in f.evidence.items():y=self.paragraph(cat+': '+proof,y,640)
            if f.phase not in ('CHECKS','VICTORY','FAILURE'):
                self.centered(f'Fuel {f.fuel:.0f}% | Power {f.energy:.0f}% | Life support {f.oxygen:.0f}%',160,size='small')
            self.notice=f.message
            labels={'CHECKS':'Run verification','LAUNCH':'Ignite','RESCUE':'Rescue crew','REENTRY':'Deploy parachute','VICTORY':'Mission debrief','FAILURE':'Retry design'}
            self.footer(self.back_to_levels,forward=self.flight_action if f.phase in labels else None,forward_title=labels.get(f.phase,'Continue'))

        def flight_action(self):
            if self.flight.phase=='VICTORY':self.state='ENG_RESULT'
            elif self.flight.phase=='FAILURE':self.state='ENG_BUILD'
            else:self.flight.action()

        def draw(self):
            if self.state!='MAIN_MENU' and not self.state.startswith('ENG_'):return super().draw()
            self.buttons=[];self.screen.fill((8,13,27))
            if self.state=='MAIN_MENU':
                self.background.draw(self.screen);self.centered('STARLINER',155,CYAN,'big');self.centered('NASA rescue engineering',215)
                for i,(label,fn) in enumerate((('Engineering / Continue',lambda:self.campaign_start(True)),('New Engineering Campaign',lambda:setattr(self,'state','ENG_NEW_CONFIRM')),('Flight Sandbox',lambda:self.start('sandbox')),('Legacy Flight Campaign',lambda:self.start('campaign',True)),('Unlock All Levels',self.unlock_everything),('Quit',self.quit))):self.button(label,(160,280+i*72,400,55),fn)
                self.paragraph(self.notice,755,color=GOLD);self.paragraph(DISCLAIMER,890)
            elif self.state=='ENG_SELECT':
                self.header('Select a mission')
                for n,name in enumerate(LEVELS,1):
                    status='DONE' if n in self.campaign.completed else 'OPEN' if self.campaign.available(n) else 'LOCKED'
                    self.button(f'{n}. {name} [{status}]',(25,160+(n-1)*89,670,65),lambda level=n:self.select_level(level))
                self.footer(self.main_menu,'Main menu')
            elif self.state=='ENG_BRIEF':
                self.header(LEVELS[self.campaign_level-1]);self.centered(BRIEFINGS[self.campaign_level-1][0],180,CYAN)
                significance=BRIEFINGS[self.campaign_level-1][1].replace('These are simplified game ratings, not vehicle endurance claims.','')
                y=self.paragraph(significance,245)
                self.paragraph('Choose parts, run all accumulated system checks, launch, navigate for rescue, return and survive reentry. Each later level retains earlier mechanics.',y+45)
                self.paragraph('Failure: depleted resources, missed flight corridor, lost telemetry, excessive reentry heat or landing without a parachute.',y+210,color=GOLD)
                self.footer(self.back_to_levels,forward=self.enter_design,forward_title='Design spacecraft')
            elif self.state in ('ENG_BUILD','ENG_BUDGET'):self.draw_build()
            elif self.state=='ENG_FLIGHT':self.draw_flight()
            elif self.state=='ENG_RESULT':
                self.header('Mission complete / '+LEVELS[self.campaign_level-1]);self.centered('RESCUE MISSION VERIFIED',230,GREEN,'big')
                report=self.campaign.report();self.paragraph('All active systems passed preflight and the full launch, rescue, return and recovery mission.',340)
                self.centered('Selected cost: '+money(report['cost_dollars']),480,CYAN)
                if self.campaign_level==7:self.centered('Savings vs baseline: '+money(report['savings_dollars']),540,GOLD)
                self.footer(self.main_menu,'Main menu',self.back_to_levels,'Next / revisit mission')
            elif self.state=='ENG_NEW_CONFIRM':
                self.header('Start new engineering campaign?');self.paragraph('Your existing save is replaced only after a completed mission or explicit Unlock All.',300)
                self.footer(self.main_menu,'Cancel',lambda:self.campaign_start(False),'Start new campaign')
            pg.transform.smoothscale(self.screen,self.window_size,self.window);pg.display.flip()

        def update(self,dt):
            if self.state=='ENG_FLIGHT':
                keys=pg.key.get_pressed();bank=int(keys[pg.K_RIGHT] or keys[pg.K_d])-int(keys[pg.K_LEFT] or keys[pg.K_a])
                self.flight.update(dt,bank)
                if self.flight.phase=='VICTORY' and not self.flight.saved:
                    try:self.flight.finish();self.flight.message+=self.campaign_save_now()
                    except ValueError as exc:self.flight.fail(str(exc))
            elif self.state=='MAIN_MENU':self.background.update(dt)
            elif not self.state.startswith('ENG_'):super().update(dt)

        def handle(self,event):
            if self.state!='MAIN_MENU' and not self.state.startswith('ENG_'):return super().handle(event)
            if event.type==pg.QUIT:self.quit()
            elif event.type==pg.KEYDOWN:
                if event.key==pg.K_ESCAPE:
                    if self.state=='MAIN_MENU':self.quit()
                    elif self.state in ('ENG_SELECT','ENG_NEW_CONFIRM'):self.main_menu()
                    elif self.state=='ENG_FLIGHT':self.state='ENG_BUILD'
                    else:self.back_to_levels()
                elif self.state=='ENG_FLIGHT':
                    if event.key==pg.K_SPACE:self.flight_action()
                    elif event.key==pg.K_t:self.flight.transmit()
                    elif event.key in (pg.K_LEFT,pg.K_a):self.flight.align(-5)
                    elif event.key in (pg.K_RIGHT,pg.K_d):self.flight.align(5)
                elif self.state=='ENG_BUILD' and event.key in (pg.K_UP,pg.K_DOWN):
                    self.detail_scroll=max(0,min(getattr(self,'max_detail_scroll',0),self.detail_scroll+(40 if event.key==pg.K_DOWN else -40)))
            elif event.type==pg.MOUSEWHEEL and self.state=='ENG_BUILD':self.detail_scroll=max(0,min(getattr(self,'max_detail_scroll',0),self.detail_scroll-event.y*35))
            elif event.type==pg.MOUSEBUTTONDOWN:
                position=self.mouse_position(event.pos)
                if event.button==1:
                    for rect,fn in self.buttons:
                        if rect.collidepoint(position):fn();return
                    if self.state=='ENG_FLIGHT':self.flight.waypoint(*position)
                elif event.button==3 and self.state=='ENG_FLIGHT':self.flight.route.clear()
    return EngineeringGame
