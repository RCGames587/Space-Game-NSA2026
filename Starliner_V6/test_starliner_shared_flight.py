"""Headless adapter tests; original Pygame flight needs a local playtest."""
from types import SimpleNamespace
import unittest
from starliner_engineering_data import BASELINE,CATEGORIES
from starliner_shared_flight import wrap_engineering_game

class Rocket:
    def __init__(self,config):
        self.config=dict(config)
        self.spec=dict(battery=80.,demand=3.,generation=5.,peak=8.,nav_range=5000.,comm_range=5000.,lifetime=200.)
CATALOG={cid:SimpleNamespace(category=cat) for cat,cid in BASELINE.items()}

class Base:
    def start(self,mode,load=False):
        self.mode=mode;self.config={};self.state='GROUND';self.launched=False;self.returning=False
    def persist(self):return 'legacy save'
    def open_design(self):self.modal=True
    def tick_systems(self,dt):
        self.seen=dict(self.rocket.spec);self.energy-=dt;self.control=.8
        self.ticks=getattr(self,'ticks',0)+1;return True
    def update(self,dt):
        self.updates=getattr(self,'updates',0)+1;self.tick_systems(dt)
        if getattr(self,'land',False):self.state='WIN'
    def draw(self):self.draws=getattr(self,'draws',0)+1
    def handle(self,event):self.events=getattr(self,'events',0)+1
    def undock(self):self.returning=True
    def reentry(self):self.state='REENTRY'
    def fail(self,message):self.state='FAIL';self.result=message

class Campaign:
    def __init__(self):self.errors=[];self.commits=[]
    def readiness(self,config,level):return self.errors
    def commit(self,config,level):
        if self.errors:raise ValueError(self.errors[0])
        self.commits.append((dict(config),level))

class ExistingUI(Base):
    def __init__(self):
        self.campaign=Campaign();self.draft=dict(BASELINE);self.campaign_level=1
        self.engineering_catalog=CATALOG;self.state='ENG_BUILD';self.modal=False;self.save_count=0
    def update(self,dt):self.old_ui_updates=getattr(self,'old_ui_updates',0)+1
    def draw(self):self.old_ui_draws=getattr(self,'old_ui_draws',0)+1
    def handle(self,event):self.old_ui_events=getattr(self,'old_ui_events',0)+1
    def main_menu(self):self.state='MAIN_MENU'
    def back_to_levels(self):self.state='ENG_SELECT'
    def campaign_save_now(self):self.save_count+=1;return ' saved'

PG=SimpleNamespace(KEYDOWN=1,K_ESCAPE=27)
Game=wrap_engineering_game(ExistingUI,Base,PG)

class AdapterTests(unittest.TestCase):
    def game(self,level=1):
        g=Game();g.campaign_level=level;g.test_design();return g
    def fly(self,level=1):
        g=self.game(level)
        while g.state=='ENG_SHARED_CHECKS':
            if g._shared_systems[g._shared_checks]=='Navigation':g._shared_align(-g._shared_offset)
            g._shared_verify()
        return g
    def test_all_levels_enter_actual_base_runtime(self):
        for n in range(1,8):
            g=self.fly(n);self.assertTrue(g._shared_active);self.assertEqual(g.state,'GROUND')
            self.assertEqual(g.mode,'sandbox');self.assertEqual(g._shared_systems,CATEGORIES[:min(n,6)])
    def test_native_update_draw_and_controls(self):
        g=self.fly();g.update(.1);g.draw();g.handle(SimpleNamespace(type=99))
        self.assertEqual((g.updates,g.draws,g.events),(1,1,1));self.assertFalse(hasattr(g,'old_ui_updates'))
    def test_early_levels_do_not_apply_later_system_failures(self):
        g=self.fly();original=dict(g.rocket.spec);energy=g.energy;g.tick_systems(.1)
        self.assertEqual(g.seen['nav_range'],float('inf'));self.assertEqual(g.seen['comm_range'],float('inf'))
        self.assertEqual(g.seen['lifetime'],float('inf'));self.assertGreater(g.seen['battery'],1000)
        self.assertEqual(g.rocket.spec,original);self.assertEqual(g.energy,energy);self.assertEqual(g.control,1)
    def test_level_two_enables_navigation(self):
        g=self.fly(2);g.tick_systems(.1);self.assertEqual(g.seen['nav_range'],5000)
    def test_level_four_enables_power(self):
        g=self.fly(4);e=g.energy;g.tick_systems(.1);self.assertLess(g.energy,e);self.assertEqual(g.seen['battery'],80)
    def test_level_five_enables_communications(self):
        g=self.fly(5);g.tick_systems(.1);self.assertEqual(g.seen['comm_range'],5000)
        self.assertEqual(g.seen['lifetime'],float('inf'))
    def test_level_six_all_native_systems(self):
        g=self.fly(6);original=dict(g.rocket.spec);g.tick_systems(.1);self.assertEqual(g.seen,original)
    def test_no_progress_for_preflight_or_failure(self):
        g=self.fly();self.assertFalse(g.campaign.commits);g.fail('collision');g.update(.1);self.assertFalse(g.campaign.commits)
    def test_native_safe_recovery_commits_once(self):
        g=self.fly(7);g.launched=True;g.undock();g.reentry();g.land=True;g.update(.1);g.update(.1)
        self.assertEqual(len(g.campaign.commits),1);self.assertEqual(g.state,'ENG_RESULT');self.assertEqual(g.save_count,1)
    def test_bogus_win_rejected(self):
        g=self.fly();g.land=True;g.update(.1);self.assertEqual(g.state,'FAIL');self.assertFalse(g.campaign.commits)
    def test_cancel_no_progress(self):
        g=self.fly();g.handle(SimpleNamespace(type=1,key=27));self.assertEqual(g.state,'ENG_BUILD')
        self.assertFalse(g._shared_active);self.assertFalse(g.campaign.commits)
    def test_native_design_and_save_cannot_bypass_engineering(self):
        g=self.fly();g.open_design();self.assertFalse(g.modal);self.assertEqual(g.persist(),'')
    def test_native_retry_stays_engineering(self):
        g=self.fly(3);g.start('sandbox');self.assertTrue(g._shared_active);self.assertEqual(g._shared_level,3)
    def test_calibration_is_random_and_gated(self):
        values=set()
        for _ in range(50):
            g=self.game(2);values.add(g._shared_offset);g._shared_verify();g._shared_verify()
            self.assertEqual(g._shared_checks,1)
        self.assertGreater(len(values),5);self.assertTrue(all(abs(v)>10 for v in values))
    def test_revalidation_blocks_changed_requirements(self):
        g=self.fly();g.campaign.errors=['Fuel mismatch'];self.assertFalse(g.tick_systems(.1));self.assertEqual(g.state,'FAIL')
    def test_other_modes_keep_original_behavior(self):
        g=Game();g.start('sandbox');g.update(.1);g.draw();self.assertFalse(g._shared_active)
        self.assertEqual(g.old_ui_updates,1);self.assertEqual(g.old_ui_draws,1)
    def test_spec_restored_even_if_tick_raises(self):
        g=self.fly();original=g.rocket.spec;fn=Base.tick_systems
        def broken(self,dt):raise RuntimeError('test')
        Base.tick_systems=broken
        try:
            with self.assertRaises(RuntimeError):g.tick_systems(.1)
            self.assertIs(g.rocket.spec,original)
        finally:Base.tick_systems=fn

if __name__=='__main__':unittest.main()
