"""Headless trial-design regression tests using a shared-flight double."""
import unittest
from types import SimpleNamespace
from starliner_engineering_data import BASELINE,CATEGORIES
from starliner_trial_design import wrap_trial_game,FlightAuthorization

class Campaign:
    def __init__(self):self.errors=[];self.commits=[];self.config=dict.fromkeys(CATEGORIES)
    def readiness(self,*args):return self.errors
    def available(self,n):return True
    def commit(self,config,level):
        if self.errors:raise ValueError(self.errors[0])
        self.commits.append((config,level))

class Font:
    def size(self,text):return (len(text)*8,20)
class Screen:
    def fill(self,*args):pass
    def get_clip(self):return None
    def set_clip(self,*args):pass

class Shared:
    _shared_active=False
    def __init__(self):
        self.campaign=Campaign();self.campaign_level=1;self.design_checked=False;self.texts=[]
        self.engineering_catalog={}
        for cat,cid in BASELINE.items():
            self.engineering_catalog[cid]=SimpleNamespace(id=cid,category=cat,name=cid,cost_dollars=1000000,specifications={'capacity_l':300})
        self.engineering_catalog['F1']=SimpleNamespace(id='F1',category='Fuel',name='Compact Tank',cost_dollars=2000000,specifications={'capacity_l':180,'empty_mass_lb':12})
        self.engineering_mission=SimpleNamespace(budget_dollars=200000000)
        self.small=Font();self.screen=Screen();self.view_category=0;self.detail_scroll=0;self.notice=''
    def enter_design(self):self.draft=self.campaign.config.copy();self.state='ENG_BUILD'
    def _begin_shared_flight(self):
        if self.campaign.readiness(self._shared_config,self._shared_level):return
        if self._shared_checks!=len(self._shared_systems):raise ValueError('Preflight incomplete')
        self.state='GROUND';self._shared_active=True;self.design_checked=False
    def tick_systems(self,dt):
        if self.campaign.readiness(self._shared_config,self._shared_level):self.state='FAIL';return False
        return True
    def _shared_text(self,text,*args,**kwargs):self.texts.append(str(text))
    def button(self,text,*args,**kwargs):self.texts.append(str(text))
    def back_to_levels(self):self.state='ENG_SELECT'
    def draw(self):pass
    def start(self,*args):pass
class Base:
    def start(self,*args):pass
    def ignite(self):
        if not self.design_checked:return
        self.state='ASCENT'

PG=SimpleNamespace(Rect=lambda *args:args,draw=SimpleNamespace(rect=lambda *args,**kwargs:None))
Game=wrap_trial_game(Shared,Base,PG)

class TrialTests(unittest.TestCase):
    def game(self,level=1):
        g=Game();g.campaign_level=level;g.enter_design()
        for cat in CATEGORIES[:min(level,6)]:g.draft[cat]=BASELINE[cat]
        return g
    def prepare(self,g):
        g.test_design()
        while g.state=='ENG_SHARED_CHECKS':
            if g._shared_systems[g._shared_checks]=='Navigation':g._shared_offset=0
            g._shared_verify()
    def test_authorized_before_native_ignition(self):
        g=self.game();self.prepare(g);self.assertTrue(g.design_checked);Base.ignite(g);self.assertEqual(g.state,'ASCENT')
    def test_every_level_background_auto_filled(self):
        for n in range(1,8):
            g=self.game(n)
            for cat in CATEGORIES[min(n,6):]:self.assertEqual(g.draft[cat],BASELINE[cat])
    def test_future_old_selections_replaced_with_baseline(self):
        g=Game();g.campaign.config['Navigation']='old';g.enter_design();self.assertEqual(g.draft['Navigation'],BASELINE['Navigation'])
    def test_bad_fuel_build_can_fly(self):
        g=self.game();g.engineering_choose('F1');g.campaign.errors=['Fuel capacity insufficient'];self.prepare(g)
        self.assertTrue(g.design_checked);self.assertEqual(g._shared_config['Fuel'],'F1');self.assertTrue(g.tick_systems(.1))
    def test_real_campaign_restored(self):
        g=self.game();campaign=g.campaign;self.prepare(g);self.assertIs(g.campaign,campaign);g.tick_systems(.1);self.assertIs(g.campaign,campaign)
    def test_authorization_does_not_certify(self):
        g=self.game();g.campaign.errors=['capacity'];self.prepare(g)
        with self.assertRaises(ValueError):g.campaign.commit(g._shared_config,1)
        self.assertEqual(g.campaign.commits,[])
    def test_missing_active_selection_still_blocked(self):
        g=self.game();g.draft['Fuel']=None;g.test_design();self.assertEqual(g.state,'ENG_BUILD');self.assertIn('Select',g.notice)
    def test_future_component_not_editable(self):
        g=self.game();g.engineering_choose(BASELINE['Navigation']);self.assertEqual(g.view_category,0)
        g.change_category(5);self.assertEqual(g.view_category,0)
    def test_prior_mechanics_remain_editable(self):
        g=self.game(3);self.assertEqual(g._editable(),CATEGORIES[:3]);g.engineering_choose('F1');self.assertEqual(g.draft['Fuel'],'F1')
    def test_preflight_still_requires_alignment(self):
        g=self.game(2);g.test_design();g._shared_verify();g._shared_offset=55;g._shared_verify()
        self.assertEqual(g.state,'ENG_SHARED_CHECKS');self.assertFalse(g.design_checked)
    def test_edit_invalidates_authorization(self):
        g=self.game();self.prepare(g);g.engineering_choose('F1');self.assertFalse(g.design_checked)
    def test_design_shows_numbers_not_outcomes(self):
        g=self.game();g.engineering_choose('F1');g.draw_build();text=' '.join(g.texts).lower()
        self.assertIn('180',text);self.assertIn('projected',text)
        for word in ('pass','fail','verify','certifiable','optimum'):self.assertNotIn(word,text)
    def test_budget_design_hides_solution(self):
        g=self.game(7);g.draw_budget();text=' '.join(g.texts).lower()
        self.assertIn('budget',text)
        for word in ('pass','fail','optimum','certifiable'):self.assertNotIn(word,text)
    def test_proxy_delegates_final_commit(self):
        c=Campaign();c.errors=['not certified'];proxy=FlightAuthorization(c)
        self.assertEqual(proxy.readiness({},1),[])
        with self.assertRaises(ValueError):proxy.commit({},1)
    def test_proxy_restored_after_exception(self):
        g=self.game();g.test_design();g._shared_checks=1;original=g.campaign;fn=Shared._begin_shared_flight
        def broken(self):raise RuntimeError('test')
        Shared._begin_shared_flight=broken
        try:
            with self.assertRaises(RuntimeError):g._begin_shared_flight()
            self.assertIs(g.campaign,original)
        finally:Shared._begin_shared_flight=fn

if __name__=='__main__':unittest.main()
