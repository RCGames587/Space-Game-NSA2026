"""Headless engineering campaign tests; graphical rendering still needs Pygame playtesting."""
import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from starliner_engineering_data import (CATALOG,CATEGORIES,BASELINE,ROWS,Mission,
    validate_component,validate_configuration,balance_report,load_profile)
from starliner_campaign import Campaign,Exercise
from starliner_campaign_ui import make_game_class


def run_exercise(campaign,config,level):
    ex=Exercise(campaign,config,level)
    while not ex.done:
        if ex.stage==2: ex.align(-ex.offset_m)
        assert ex.start_stage()
        for _ in range(9): ex.update(.25)
    ex.finish()
    return ex


def alternative_catalog():
    parts=dict(CATALOG)
    for cid,base in [('P2','P3'),('C2','C3')]:
        parts[cid]=replace(parts[cid],capabilities=parts[base].capabilities,
                           assumption='Explicit synthetic test scenario, NOT actual specifications.')
    parts['P2']=replace(parts['P2'],specifications=dict(parts['P2'].specifications,usable_energy_kwh=40))
    return parts

class DataTests(unittest.TestCase):
    def test_catalog_completeness(self):
        ids=[row[0] for keys,rows in ROWS.values() for row in rows]
        self.assertEqual(len(ids),24)
        self.assertEqual(len(set(ids)),24)
        for cat in CATEGORIES: self.assertEqual(sum(c.category==cat for c in CATALOG.values()),4)

    def test_all_supplied_numeric_values(self):
        expected={
          'F':[(12,180),(15,250),(20,300),(35,450)],
          'N':[(100,500,10),(250,100,25),(400,10,35),(1000,1,100)],
          'M':[(2400,8000),(1200,4000),(900,6000),(1500,10000)],
          'P':[(2,60),(4,180),(5,120),(12,500)],
          'C':[(.064,5),(1,20),(10,40),(100,150)],
          'L':[(2,30,300),(4,120,600),(4,210,800),(6,365,1800)]}
        keys={'F':['empty_mass_lb','capacity_l'], 'N':['navigation_capability_km','accuracy_error_m','mass_kg'],
              'M':['structure_mass_kg','payload_rating_kg'],'P':['output_kw','mass_kg'],
              'C':['data_rate_mbps','mass_kg'],'L':['crew_capacity','duration_days','mass_kg']}
        for prefix,values in expected.items():
            for index,row in enumerate(values,1):
                self.assertEqual(tuple(CATALOG[prefix+str(index)].specifications[k] for k in keys[prefix]),row)

    def test_exact_prices(self):
        prices=((2,3,5,8),(1,3,8,20),(10,15,25,50),(8,14,25,40),(1,4,12,30),(15,35,60,120))
        for cat,expected in zip(CATEGORIES,prices):
            self.assertEqual(tuple(c.cost_dollars for c in CATALOG.values() if c.category==cat),tuple(x*1_000_000 for x in expected))
        self.assertTrue(all(type(c.cost_dollars) is int for c in CATALOG.values()))

    def test_names_shapes_materials(self):
        self.assertEqual(CATALOG['F3'].name,'Dragon Tank System')
        self.assertEqual([CATALOG['F'+str(i)].specifications['shape'] for i in range(1,5)],['Cube','Cylinder','Integrated','Rectangle'])
        self.assertEqual(CATALOG['M3'].specifications['material'],'Aluminum / composite')
        self.assertEqual(CATALOG['N3'].specifications['navigation_display'],'400+ km')

    def test_baseline_assumptions(self):
        for c in CATALOG.values():
            self.assertEqual(c.assumption is not None,c.id in BASELINE.values())
            if c.id not in BASELINE.values(): self.assertTrue(all(v is None for v in c.capabilities.values()))
        self.assertTrue(validate_configuration(BASELINE)['passed'])

    def test_unknown_is_not_passing(self):
        r=validate_component(CATALOG['N4'])
        self.assertEqual(r.status,'unverified')
        self.assertTrue(r.selectable)
        self.assertFalse(r.passed)
        self.assertTrue(all(c.status=='passing' for c in r.checks if c.kind=='quantitative'))

    def test_n4_verified_can_pass(self):
        c=replace(CATALOG['N4'],capabilities=CATALOG['N3'].capabilities)
        self.assertTrue(validate_component(c).passed)

    def test_navigation_exact_thresholds(self):
        self.assertTrue(validate_component(CATALOG['N3']).passed)
        c=replace(CATALOG['N3'],specifications=dict(CATALOG['N3'].specifications,accuracy_error_m=10.01,navigation_capability_km=1000))
        self.assertFalse(validate_component(c).passed)
        c=replace(CATALOG['N3'],specifications=dict(CATALOG['N3'].specifications,navigation_capability_km=399.99))
        self.assertFalse(validate_component(c).passed)

    def test_missing_docking_or_interface(self):
        for key in CATALOG['N3'].capabilities:
            caps=dict(CATALOG['N3'].capabilities)
            del caps[key]
            self.assertEqual(validate_component(replace(CATALOG['N3'],capabilities=caps)).status,'unverified')

    def test_fuel_expected(self):
        for cid in ('F1','F2','F4'): self.assertEqual(validate_component(CATALOG[cid]).status,'failing')
        c=replace(CATALOG['F3'],specifications=dict(CATALOG['F3'].specifications,empty_mass_lb=25))
        self.assertTrue(validate_component(c).passed)
        self.assertFalse(validate_component(replace(c,specifications=dict(c.specifications,capacity_l=299.99))).passed)

    def test_structure_expected_and_boundary(self):
        for cid in ('M1','M2','M4'): self.assertFalse(validate_component(CATALOG[cid]).passed)
        c=replace(CATALOG['M3'],specifications=dict(CATALOG['M3'].specifications,structure_mass_kg=1200))
        self.assertTrue(validate_component(c).passed)
        self.assertFalse(validate_component(replace(c,specifications=dict(c.specifications,payload_rating_kg=5999))).passed)
        c=replace(c,specifications=dict(c.specifications,structure_mass_kg=1201,payload_rating_kg=10000))
        self.assertFalse(validate_component(c).passed)

    def test_power_numerical_failures(self):
        for cid in ('P1','P4'): self.assertEqual(validate_component(CATALOG[cid]).status,'failing')
        self.assertTrue(validate_component(CATALOG['P3']).passed)

    def test_battery_cannot_generate(self):
        c=alternative_catalog()['P2']
        self.assertFalse(validate_component(c).passed)
        self.assertTrue(any(x.key=='generation_kw' and x.status=='failing' for x in validate_component(c).checks))

    def test_battery_missing_inputs(self):
        c=replace(CATALOG['P2'],capabilities=CATALOG['P3'].capabilities)
        m=Mission(require_generation=False,external_support_allowed=True)
        self.assertEqual(validate_component(c,m).status,'unverified')
        self.assertEqual(validate_component(c,replace(m,battery_duration_hours=10)).status,'unverified')

    def test_battery_energy_and_remaining_mission(self):
        c=alternative_catalog()['P2']
        m=Mission(require_generation=False,battery_duration_hours=10,external_support_allowed=True)
        self.assertTrue(validate_component(c,m).passed)
        self.assertFalse(validate_component(c,replace(m,battery_duration_hours=10.01)).passed)
        self.assertFalse(validate_component(c,replace(m,external_support_allowed=False)).passed)
        c=replace(c,specifications=dict(c.specifications,usable_energy_kwh=16320))
        self.assertTrue(validate_component(c,Mission(require_generation=False,battery_duration_hours=4080)).passed)

    def test_communications_coverage_and_units(self):
        self.assertEqual(CATALOG['C1'].specifications['data_rate_mbps']*1000,64)
        self.assertEqual(validate_component(CATALOG['C2']).status,'unverified')
        self.assertTrue(validate_component(alternative_catalog()['C2']).passed)
        self.assertEqual(validate_component(CATALOG['C4']).status,'failing')
        self.assertEqual(validate_component(CATALOG['C1']).status,'failing')

    def test_lifetime_boundaries_and_all_options(self):
        for cid in ('L1','L2','L4'): self.assertFalse(validate_component(CATALOG[cid]).passed)
        c=replace(CATALOG['L3'],specifications={'crew_capacity':4,'duration_days':170,'mass_kg':1200})
        self.assertTrue(validate_component(c).passed)
        for key,value in [('crew_capacity',3),('duration_days',169),('mass_kg',1201)]:
            self.assertFalse(validate_component(replace(c,specifications=dict(c.specifications,**{key:value}))).passed)
        for key in c.capabilities:
            caps=dict(c.capabilities); del caps[key]
            self.assertFalse(validate_component(replace(c,capabilities=caps)).passed)

    def test_missing_and_invalid_numeric(self):
        for value in (None,True,-1,float('inf'),float('nan'),'300'):
            c=replace(CATALOG['F3'],specifications=dict(CATALOG['F3'].specifications,capacity_l=value))
            self.assertEqual(validate_component(c).status,'unverified')

    def test_boolean_and_immutable_data(self):
        for cost in (True,1.2,-1):
            with self.assertRaises(ValueError): replace(CATALOG['F3'],cost_dollars=cost)
        with self.assertRaises(ValueError): replace(CATALOG['F3'],capabilities={'mmh_nto_compatible':'yes'})
        with self.assertRaises(TypeError): CATALOG['F3'].specifications['capacity_l']=1
        c=replace(CATALOG['F3'],capabilities=dict(CATALOG['F3'].capabilities,propulsion_connection=False))
        self.assertEqual(validate_component(c).status,'failing')

    def test_budget_totals_and_boundaries(self):
        r=validate_configuration(BASELINE)
        self.assertEqual((r['cost_dollars'],r['remaining_dollars']),(135_000_000,65_000_000))
        self.assertTrue(validate_configuration(BASELINE,Mission(budget_dollars=135_000_000))['passed'])
        self.assertFalse(validate_configuration(BASELINE,Mission(budget_dollars=134_999_999))['passed'])

    def test_baseline_and_alternative_optimization(self):
        self.assertEqual(balance_report()['minimum_cost_dollars'],135_000_000)
        m=Mission(require_generation=False,battery_duration_hours=10,external_support_allowed=True)
        result=balance_report(m,alternative_catalog())
        self.assertEqual(result['minimum_cost_dollars'],116_000_000)
        config=result['solutions'][0][1]
        r=validate_configuration(config,m,alternative_catalog())
        self.assertEqual((r['savings_dollars'],r['remaining_dollars']),(19_000_000,84_000_000))

    def test_each_conditional_opportunity(self):
        parts=alternative_catalog()
        only_comms=dict(CATALOG,C2=parts['C2'])
        self.assertEqual(balance_report(catalog=only_comms)['minimum_cost_dollars'],127_000_000)
        only_power=dict(CATALOG,P2=parts['P2'])
        m=Mission(require_generation=False,battery_duration_hours=10,external_support_allowed=True)
        self.assertEqual(balance_report(m,only_power)['minimum_cost_dollars'],124_000_000)
        self.assertEqual(balance_report(Mission(budget_dollars=100_000_000))['solutions'],[])

    def test_invalid_cheaper_alternatives(self):
        for cat,cid in [('Fuel','F4'),('Navigation','N2'),('Structure','M4'),('Lifetime','L2')]:
            self.assertFalse(validate_configuration(dict(BASELINE,**{cat:cid}))['passed'])

    def test_unknown_and_partial_config(self):
        for config in ({},dict(BASELINE,Fuel='N3'),dict(BASELINE,Fuel=[]),dict(BASELINE,Fuel='F99')):
            with self.assertRaises(ValueError): validate_configuration(config)
        r=validate_configuration(dict.fromkeys(CATEGORIES),partial=True)
        self.assertFalse(r['passed']); self.assertEqual(r['cost_dollars'],0)

    def test_profile_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'profile.json'
            p.write_text(json.dumps({'components':{'N4':{'capabilities':dict(CATALOG['N3'].capabilities),'assumption':'Explicit game scenario.'}}}))
            m,c=load_profile(p)
            self.assertTrue(validate_component(c['N4'],m).passed)
            self.assertEqual(validate_component(CATALOG['N4']).status,'unverified')
            for raw in ({'mission':{'rules':{}}},{'mission':{'required_power_kw':3}},
                        {'components':{'P2':{'usable_energy_kwh':40}}},
                        {'components':{'F1':{'cost_dollars':0,'assumption':'not permitted'}}}):
                p.write_text(json.dumps(raw))
                with self.assertRaises(ValueError): load_profile(p)

class CampaignTests(unittest.TestCase):
    def test_full_sequential_playthrough(self):
        campaign=Campaign()
        draft=campaign.config.copy()
        for level,cat in enumerate(CATEGORIES,1):
            self.assertTrue(campaign.available(level))
            if level<7: self.assertFalse(campaign.available(level+1))
            draft[cat]=BASELINE[cat]
            ex=run_exercise(campaign,draft,level)
            self.assertEqual(ex.completed_stages,list(range(1,level+1)))
            self.assertIn(level,campaign.completed)
        self.assertTrue(campaign.available(7))
        campaign.commit(draft,7)
        self.assertEqual(campaign.completed,set(range(1,8)))
        self.assertTrue(campaign.report()['passed'])

    def test_level_one_no_later_mechanics(self):
        c=Campaign()
        ex=Exercise(c,dict(c.config,Fuel='F3'),1)
        self.assertEqual(ex.stages,(1,))
        self.assertEqual(c.completed,set())
        with self.assertRaises(ValueError): ex.finish()

    def test_docking_alignment_gate(self):
        c=Campaign(unlock_all=True)
        ex=Exercise(c,BASELINE,2)
        ex.start_stage()
        for _ in range(9): ex.update(.25)
        self.assertEqual(ex.stage,2)
        self.assertFalse(ex.start_stage())
        ex.align(-50)
        self.assertEqual(ex.offset_m,10)
        self.assertTrue(ex.start_stage())

    def test_invalid_selection_does_not_commit(self):
        c=Campaign()
        original=c.config.copy()
        for cid in ('F1','F2','F4'):
            with self.assertRaises(ValueError): c.commit(dict(c.config,Fuel=cid),1)
        self.assertEqual(c.config,original)

    def test_unlock_all_not_certification(self):
        c=Campaign(unlock_all=True)
        self.assertTrue(all(c.available(n) for n in range(1,8)))
        self.assertEqual(c.completed,set())
        with self.assertRaises(ValueError): c.commit(c.config,7)
        with self.assertRaises(ValueError): c.commit(dict(BASELINE,Power='P2'),7)
        self.assertFalse(c.available(8))

    def test_locked_commit_blocked(self):
        with self.assertRaises(ValueError): Campaign().commit(BASELINE,7)

    def test_revisit_retains_other_selections(self):
        c=Campaign(config=BASELINE.copy(),completed=set(range(1,8)))
        c.commit(BASELINE.copy(),1)
        self.assertEqual(c.completed,set(range(1,8)))
        self.assertEqual(c.config,BASELINE)

    def test_budget_immediately_revalidates(self):
        c=Campaign(config=BASELINE.copy(),completed=set(range(1,8)))
        original=c.config.copy()
        r=c.report(dict(original,Communications='C2'))
        self.assertFalse(r['passed']); self.assertEqual(r['cost_dollars'],127_000_000)
        self.assertEqual(c.config,original)

    def test_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'save.json'
            c=Campaign(config=BASELINE.copy(),completed=set(range(1,8)),unlock_all=True)
            c.save(p)
            loaded=Campaign.load(p)
            self.assertEqual(loaded.config,BASELINE)
            self.assertEqual(loaded.completed,c.completed)
            self.assertTrue(loaded.unlock_all)
            self.assertTrue(loaded.report()['passed'])

    def test_revalidate_saved_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'save.json'
            c=Campaign(config=BASELINE.copy(),completed=set(range(1,8)))
            c.save(p)
            raw=json.loads(p.read_text()); raw['components']['Fuel']='F4'
            p.write_text(json.dumps(raw))
            loaded=Campaign.load(p)
            self.assertEqual(loaded.completed,set())

    def test_profile_change_requires_retesting(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'save.json'
            Campaign(config=BASELINE.copy(),completed={1,2}).save(p)
            loaded=Campaign.load(p,Mission(budget_dollars=190_000_000))
            self.assertEqual(loaded.config,BASELINE)
            self.assertEqual(loaded.completed,set())
            self.assertIn('changed',loaded.notice)

    def test_corrupt_and_unknown_save_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'save.json'
            for raw in ('{broken',json.dumps({'schema_version':999}),json.dumps({'schema_version':True})):
                p.write_text(raw)
                with self.assertRaises(ValueError): Campaign.load(p)
                self.assertEqual(p.read_text(),raw)
            Campaign().save(p)
            raw=json.loads(p.read_text()); raw['components']['Fuel']='F999'
            p.write_text(json.dumps(raw)); before=p.read_bytes()
            with self.assertRaises(ValueError): Campaign.load(p)
            self.assertEqual(p.read_bytes(),before)

    def test_legacy_migration_no_trusted_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'legacy.json'
            raw={'schema_version':1,'catalog_version':1,'components':BASELINE,'unlocked_level':7}
            p.write_text(json.dumps(raw)); before=p.read_bytes()
            loaded=Campaign.load(p)
            self.assertEqual(loaded.config,BASELINE)
            self.assertEqual(loaded.completed,set())
            self.assertEqual(p.read_bytes(),before)

    def test_failed_save_preserves_previous(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'save.json'
            c=Campaign(); c.save(p); before=p.read_bytes()
            c.config['Fuel']='UNKNOWN'
            with self.assertRaises(ValueError): c.save(p)
            self.assertEqual(p.read_bytes(),before)

    def test_no_mutation_from_trial_preview(self):
        c=Campaign()
        draft=dict(c.config,Fuel='F3')
        ex=Exercise(c,draft,1)
        draft['Fuel']='F4'
        self.assertEqual(ex.config['Fuel'],'F3')
        self.assertIsNone(c.config['Fuel'])

# These stubs exercise UI routing and controls, NOT Pygame rendering.
class Rect:
    def __init__(self,*args): self.value=tuple(args[0]) if len(args)==1 else args
    def collidepoint(self,pos):
        x,y,w,h=self.value
        return x<=pos[0]<=x+w and y<=pos[1]<=y+h
class Surface:
    def fill(self,*args): pass
    def get_clip(self): return (0,0,720,1000)
    def set_clip(self,*args): pass
class StubBase:
    def __init__(self,save_path):
        self.save_path=save_path; self.screen=Surface(); self.window=Surface()
        self.window_size=(720,1000); self.state='MAIN_MENU'; self.modal=False
        self.background=SimpleNamespace(draw=lambda *a:None,update=lambda *a:None)
        self.buttons=[]; self.running=True; self.texts=[]
    def text(self,message,*args,**kwargs): self.texts.append(str(message))
    def wrap(self,message,x,y,width,*args):
        self.texts.append(str(message))
        return y+23*max(1,(len(str(message))+64)//65)
    def button(self,title,rect,callback,selected=False): self.buttons.append((Rect(rect),callback)); self.texts.append(title)
    def main_menu(self): self.state='MAIN_MENU'
    def mouse_position(self,pos): return pos
    def quit(self): self.running=False
    def start(self,mode,load=False): self.state='GROUND'; self.mode=mode
    def draw(self): pass
    def update(self,dt): pass
    def handle(self,event): pass

class UITests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.pg=SimpleNamespace(Rect=Rect,draw=SimpleNamespace(rect=lambda *a:None,line=lambda *a:None,circle=lambda *a:None),
            transform=SimpleNamespace(smoothscale=lambda *a:None),display=SimpleNamespace(flip=lambda:None),
            QUIT=1,KEYDOWN=2,MOUSEBUTTONDOWN=3,MOUSEWHEEL=4,
            K_ESCAPE=10,K_LEFT=11,K_a=12,K_RIGHT=13,K_d=14,K_SPACE=15,K_DOWN=16,K_UP=17)
        cls=make_game_class(StubBase,self.pg)
        self.game=cls(Path(self.folder.name)/'legacy.json',Mission(),CATALOG,Path(self.folder.name)/'campaign.json')

    def test_menu_unlock_top_right_and_persistence(self):
        self.game.draw()
        unlock=[(rect,cb) for rect,cb in self.game.buttons if rect.value[0]==475]
        self.assertEqual(len(unlock),1)
        unlock[0][1]()
        self.assertTrue(self.game.campaign.unlock_all)
        self.assertTrue(self.game.campaign_path.exists())
        self.assertFalse(Path(self.game.save_path).exists())

    def test_every_level_has_briefing(self):
        self.game.campaign.unlock_all=True
        for level in range(1,8):
            self.game.select_level(level)
            self.assertEqual(self.game.state,'ENG_BRIEF')
            self.game.draw()
            self.game.enter_design()
            self.assertEqual(self.game.state,'ENG_BUDGET' if level==7 else 'ENG_BUILD')
            self.game.draw()

    def test_design_cancel_no_mutation(self):
        self.game.campaign_start(False)
        self.game.select_level(1); self.game.enter_design()
        self.game.engineering_choose('F3')
        self.game.back_to_levels()
        self.assertIsNone(self.game.campaign.config['Fuel'])

    def test_invalid_confirm_stays_design(self):
        self.game.campaign_start(False)
        self.game.select_level(1); self.game.enter_design()
        self.game.engineering_choose('F4'); self.game.test_design()
        self.assertEqual(self.game.state,'ENG_BUILD')
        self.assertIn('mass',self.game.notice)

    def test_level_one_complete_and_save(self):
        self.game.campaign_start(False)
        self.game.select_level(1); self.game.enter_design()
        self.game.engineering_choose('F3'); self.game.test_design()
        self.assertEqual(self.game.state,'ENG_TRIAL')
        self.game.draw(); self.game.start_exercise_stage()
        for _ in range(9): self.game.update(.25)
        self.assertEqual(self.game.state,'ENG_RESULT')
        self.assertEqual(self.game.campaign.completed,{1})
        self.game.draw()
        self.assertTrue(self.game.campaign_path.exists())

    def test_all_exercise_stages_draw_and_controls(self):
        self.game.campaign.unlock_all=True
        self.game.campaign.config=BASELINE.copy()
        self.game.select_level(6); self.game.enter_design(); self.game.test_design()
        for stage in range(1,7):
            self.assertEqual(self.game.exercise.stage,stage)
            self.game.draw()
            if stage==2:
                for _ in range(10):
                    self.game.handle(SimpleNamespace(type=self.pg.KEYDOWN,key=self.pg.K_LEFT))
            self.game.start_exercise_stage()
            for _ in range(9): self.game.update(.25)
        self.assertEqual(self.game.state,'ENG_RESULT')

    def test_budget_unknown_blocked_and_certification(self):
        self.game.campaign.unlock_all=True; self.game.campaign.config=BASELINE.copy()
        self.game.select_level(7); self.game.enter_design(); self.game.draw()
        self.game.budget_category(4); self.game.draw(); self.game.engineering_choose('C2')
        self.game.state='ENG_BUDGET'; self.game.test_design()
        self.assertEqual(self.game.state,'ENG_BUDGET')
        self.assertNotIn(7,self.game.campaign.completed)
        self.game.engineering_choose('C3'); self.game.test_design()
        self.assertEqual(self.game.state,'ENG_RESULT'); self.game.draw()

    def test_unlock_corrupt_save_never_overwrites(self):
        self.game.campaign_path.write_text('{bad')
        self.game.unlock_everything()
        self.assertEqual(self.game.campaign_path.read_text(),'{bad')
        self.assertFalse(self.game.campaign.unlock_all)

    def test_back_and_scroll_events(self):
        self.game.campaign.unlock_all=True; self.game.select_level(4); self.game.enter_design()
        self.game.engineering_choose('P2'); self.game.draw()
        self.game.handle(SimpleNamespace(type=self.pg.MOUSEWHEEL,y=-5))
        self.assertGreaterEqual(self.game.detail_scroll,0)
        self.game.handle(SimpleNamespace(type=self.pg.KEYDOWN,key=self.pg.K_ESCAPE))
        self.assertEqual(self.game.state,'ENG_SELECT')

if __name__=='__main__': unittest.main()
