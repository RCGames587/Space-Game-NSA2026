"""Headless regression tests for the integrated mission and installer."""
import math
import random
import unittest
from types import SimpleNamespace
from starliner_mission import MissionFlight,CATEGORIES,segment_distance

class CampaignStub:
    def __init__(self):self.commits=[];self.errors=[];self.catalog={}
    def readiness(self,config,level):return self.errors
    def commit(self,config,level):self.commits.append((dict(config),level))

class MissionTests(unittest.TestCase):
    def mission(self,level=1):
        c=CampaignStub();return MissionFlight(c,dict.fromkeys(CATEGORIES,'part'),level,random.Random(7))
    def preflight(self,f):
        while f.phase=='CHECKS':
            if f.current_system=='Navigation':f.align(-f.offset_m)
            self.assertTrue(f.verify())
        self.assertFalse(f.campaign.commits)
    def advance(self,f,seconds,bank=0):
        for _ in range(round(seconds*120)):f.update(1/120,bank)
    def launch(self,f):
        self.preflight(f);f.action();self.advance(f,3.6)
        self.assertEqual(f.phase,'OUTBOUND')
    def goal(self,f,point,phase):
        f.waypoint(*point)
        for _ in range(1800):
            f.update(1/120)
            if f.phase==phase:return
            self.assertNotEqual(f.phase,'FAILURE',f.message)
        self.fail('Destination not reached: '+f.phase)
    def recover(self,f):
        self.goal(f,f.station,'RESCUE')
        if 'Communications' in f.systems:f.transmit()
        f.action();self.assertEqual(f.phase,'RETURN')
        self.goal(f,f.home,'REENTRY')
        for _ in range(2400):
            if f.altitude<=15:f.action()
            f.update(1/120,1)
            if f.phase in ('VICTORY','FAILURE'):break
        self.assertEqual(f.phase,'VICTORY',f.message)

    def test_all_seven_full_missions(self):
        for level in range(1,8):
            with self.subTest(level=level):
                f=self.mission(level);self.launch(f);self.recover(f)
                self.assertFalse(f.campaign.commits);f.finish();f.finish()
                self.assertEqual(len(f.campaign.commits),1)
                self.assertEqual(set(f.checked),set(CATEGORIES[:min(level,6)]))
                self.assertTrue(all(c in f.evidence for c in f.systems))
    def test_no_certification_at_preflight(self):
        f=self.mission();self.preflight(f)
        with self.assertRaises(ValueError):f.finish()
    def test_random_calibration_outside_target(self):
        values={MissionFlight(CampaignStub(),{},2,random.Random(i)).offset_m for i in range(60)}
        self.assertGreater(len(values),12);self.assertTrue(all(abs(x)>10 for x in values))
    def test_calibration_gate(self):
        f=self.mission(2);f.verify();self.assertFalse(f.verify());f.align(-f.offset_m);self.assertTrue(f.verify())
    def test_checks_accumulate(self):
        for level in range(1,8):self.assertEqual(self.mission(level).systems,CATEGORIES[:min(level,6)])
    def test_launch_requires_explicit_ignition(self):
        f=self.mission();self.preflight(f);self.advance(f,5);self.assertEqual(f.altitude,0)
    def test_rescue_link_required(self):
        f=self.mission(5);self.launch(f);self.goal(f,f.station,'RESCUE');f.action()
        self.assertEqual(f.phase,'RESCUE');self.assertFalse(f.rescued)
        f.transmit();f.action();self.assertEqual(f.phase,'RETURN')
    def test_reentry_without_chute_fails(self):
        f=self.mission();f.phase='REENTRY';f.altitude=1;f.rescued=True
        self.advance(f,1,1);self.assertEqual(f.phase,'FAILURE')
    def test_heat_failure(self):
        f=self.mission();f.phase='REENTRY';f.altitude=100
        self.advance(f,4.1);self.assertEqual(f.phase,'FAILURE')
    def test_early_parachute_blocked(self):
        f=self.mission();f.phase='REENTRY';f.altitude=100;f.action();self.assertFalse(f.chute)
    def test_fuel_failure(self):
        f=self.mission();self.launch(f);f.fuel=.0001;f.waypoint(*f.station);f.update(.1);self.assertEqual(f.phase,'FAILURE')
    def test_power_failure(self):
        f=self.mission(4);self.launch(f);f.energy=.0001;f.update(.1);self.assertEqual(f.phase,'FAILURE')
    def test_life_support_failure(self):
        f=self.mission(6);self.launch(f);f.oxygen=.0001;f.update(.1);self.assertEqual(f.phase,'FAILURE')
    def test_midflight_revalidation(self):
        f=self.mission();self.launch(f);f.campaign.errors=['Fuel mismatch'];f.update(.01);self.assertEqual(f.phase,'FAILURE')
    def test_waypoint_does_not_stop_momentum(self):
        f=self.mission();self.launch(f);f.waypoint(220,660);f.waypoint(440,540)
        for _ in range(500):
            f.update(1/120)
            if len(f.route)==1:break
        self.assertEqual(len(f.route),1);self.assertGreater(math.hypot(*f.vel),100)
        self.assertNotEqual(tuple(f.pos),(220,660))
    def test_coasts_without_waypoints(self):
        f=self.mission();f.phase='OUTBOUND';f.pos=[300,400];f.vel=[100,0];f.update(.1)
        self.assertAlmostEqual(f.vel[0],100);self.assertGreater(f.pos[0],309)
    def test_route_bounds(self):
        f=self.mission();f.phase='OUTBOUND';f.waypoint(-1,400);self.assertFalse(f.route)
    def test_overshoot_segment_capture(self):
        self.assertEqual(segment_distance((5,0),(0,0),(10,0)),0)
    def test_invalid_time_and_level(self):
        for value in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):self.mission().update(value)
        for level in (0,8,True):
            with self.assertRaises(ValueError):self.mission(level)
    def test_failed_preflight(self):
        c=CampaignStub();c.errors=['invalid']
        with self.assertRaises(ValueError):MissionFlight(c,{},1)
    def test_specifications_affect_flight_without_mutation(self):
        c=CampaignStub();specs={'capacity_l':600};c.catalog={'tank':SimpleNamespace(specifications=specs)}
        config=dict.fromkeys(CATEGORIES);config['Fuel']='tank'
        f=MissionFlight(c,config,1);self.assertEqual(f.fuel_factor,.5);self.assertEqual(specs,{'capacity_l':600})

if __name__=='__main__':unittest.main()
