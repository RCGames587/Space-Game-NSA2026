STARLINER - SEVEN-LEVEL ENGINEERING CAMPAIGN
==========================================

This package applies NSA2026-Game-Pitch.txt to the uploaded project. The original
arcade game classes, physics and tests are retained; the new engineering campaign
is the default UI. No original uploaded file was overwritten in this environment.
A byte-for-byte copy of the original is included inside the ZIP under backup/.

SETUP
-----
Extract the complete ZIP into a new folder. Keep these files together:
  starliner_engineering.py        Entry point; original game plus new CLI routing
  starliner_engineering_data.py   Exact 24-component engineering catalog/validator
  starliner_campaign.py           Campaign state, saves and cumulative exercises
  starliner_campaign_ui.py        New screens layered over the original Game class
  test_starliner_campaign.py      Engineering/data/persistence/UI-routing tests

Use Python 3.9+ and the project's existing Pygame dependency.
If Pygame is not already installed:
  python -m pip install pygame

Launch:
  python starliner_engineering.py

Windows users may use `py -3` in place of `python`.
No art, fonts, network services or additional game dependencies are needed.

MENU AND PROGRESSION
--------------------
Engineering / Continue loads the separate engineering save, or begins Level 1.
New Engineering Campaign asks for confirmation before creating an empty design.
The existing save is not replaced until an exercise completes or Unlock All is
explicitly used. Main-menu Unlock All Levels is at the top right and persists
screen access. It does NOT fill selections, pass requirements or mark levels done.
The level selector opens completed/current missions, or all screens in debug mode.
Every mission opens with the significance of its engineering challenge and the
mechanics it adds. Revisited levels show their briefings again.

Level 1: select a compatible >=300 L, <=25 lb tank; open the valve/check it.
Level 2: adds approach alignment and autonomous docking. A/D or left/right arrows
         move in 5 m steps. Align within +/-10 m, then engage docking.
Level 3: adds the 6000 kg payload qualification check.
Level 4: adds electrical output, generation, energy and availability checks.
Level 5: adds telemetry and required communications coverage.
Level 6: adds the four-person, 170-day life-support exercise.
Level 7: compares all six selections, validates the entire configuration, shows
         baseline savings and the computed cheapest verified configuration.

Each exercise repeats the earlier subsystem stages in order, adding only its new
stage. Select an engineering-valid build before running. SPACE or the displayed
button starts a stage. The short progress animations and accelerated day display
are teaching exercises, NOT physical fuel-burn, orbital, structure, eclipse or
life-support simulations. Stage completion is always backed by the validator.
Fuel-only Level 1 has no later-system controls. Full arcade launch, route plotting,
asteroids, docking and reentry remain playable separately in the flight sandbox.

In design screens:
- Inspect all four components, including failures and unverified options.
- Select a card to see its checklist and specifications.
- Scroll the checklist with the wheel or up/down arrows.
- Preview total component cost before confirmation.
- Cancel/ESC discards uncommitted previews.
- Success commits component IDs and progress; unrelated selections remain.
- In Level 7, click a summary row to compare that category. Keep preview returns
  to the overview; only successful certification commits those substitutions.

VALIDATION AND BALANCE
----------------------
All supplied numbers are retained with explicit units and integer-dollar costs.
F4 fails tank mass; N4 passes numerical navigation checks but needs verified
interfaces; M4 is $50M and fails structure mass. L2 still fails mission duration.
P2 cannot generate power in the default strict-generation profile. Output kW is
never used as battery capacity kWh. C2 data rate never substitutes for coverage.
Unverified interface/capability fields remain unknown, not true.
The baseline components' passing capability flags are labeled GAME assumptions.
No real-world endurance or proprietary engineering claims are made.

Default engineering balance:
  F3 / N3 / M3 / P3 / C3 / L3 = $135M
  Budget = $200M; remaining = $65M; verified savings = $0M
This is the only fully verified default solution. Level 7 still completes: mission
certification is distinct from optimization, and no artificial savings target is
imposed. The optimizer calculates results from active requirements/catalog data.
Test-only scenarios with verified P2/C2 conditions demonstrate the expected
$116M optimum, $19M savings and $84M remaining. Those hypothetical settings are
NOT installed in the production catalog.

EXPLICIT MISSION PROFILES
-------------------------
  python starliner_engineering.py --profile mission_profile.example.json

The supplied profile is intentionally unverified for P2 and C2. It preserves the
default engineering results. Edit a COPY only when the scenario author has chosen
or established the missing conditions. Component overrides require an explanatory
assumption/source note, which is displayed with the requirement checklist.
Fixed prices, supplied specifications and level thresholds cannot be overridden
through profiles. Allowed settings include power operations, battery interval,
coverage description, budget and explicit compatibility/availability assertions.
Allowed new battery data is usable_energy_kwh; it is never inferred automatically.

For supply-based battery operation, require_generation must explicitly be false,
usable energy must satisfy required_power_kw * battery_duration_hours, and the
power/interface capabilities must pass. If the battery interval is shorter than
the 170-day mission, explicit recharge/external-power permission AND a verified
mission availability capability are required. Permission alone is insufficient.
This is a simplified scenario declaration, not a detailed recharge scheduler.
C2 requires explicit coverage, telemetry and spacecraft-interface verification.
Changing profiles clears exercise completion on load while retaining selections.

SAVES AND LEGACY MODE
--------------------
Engineering saves default to your home .starliner folder, engineering_campaign_v2.json.
The original arcade engineering_save.json is separate and is not overwritten by
the new campaign. Save writes are atomic; loads reject malformed/unknown data and
recompute validation from IDs. Unsupported saves are left untouched.
The loader supports version-1 component-ID selections without trusting old arcade
progress. To test migration, use --campaign-save-file with a COPY of a legacy save.
Do not point it at your only backup: completing a new mission writes schema 2.
--save-file controls only the original arcade save location.

Legacy menu and original campaign:
  python starliner_engineering.py --legacy-game
The default menu also exposes Arcade Flight Sandbox and Legacy Arcade Campaign.
Legacy arcade specifications and its $119M budget intentionally remain unchanged.
They are labeled as a separate mode; do not mix their unitless values with the
engineering campaign's exact database.

TESTS AND REPORTS
-----------------
  python starliner_engineering.py --self-test
  python -m unittest -v test_starliner_campaign
  python starliner_engineering.py --balance-report
  python starliner_engineering.py --engineering-report
  python starliner_engineering.py --arcade-balance-report

--balance-report now reports the NEW engineering campaign. The original report
is preserved under --arcade-balance-report. --engineering-report is an alias.

Verification in the build environment:
- 23 existing arcade regression tests passed.
- 49 new engineering/campaign/UI-routing tests passed.
- Both balance reports and the example mission profile completed successfully.
- All delivered Python source files compiled.
Pygame was not installed here. UI tests use explicit stubs and verify navigation,
callbacks, stage progression, cancellation, saves and certification gates. They
DO NOT verify actual rendering, keyboard focus, visual fit or mouse gameplay.

MANUAL PLAYTEST CHECKLIST
-------------------------
1. Launch; inspect main menu disclaimer and top-right Unlock All button.
2. Start a new campaign; confirm only Level 1 is initially available.
3. Read each briefing and check all four component cards/checklist scrolling.
4. Verify invalid/unverified builds cannot begin a successful exercise.
5. Complete F3, N3, M3, P3, C3, L3 in order; align docking markers within 10 m.
6. Check that each successive mission adds exactly one subsystem stage.
7. On Level 7, confirm $135M total/$65M remaining; inspect cheaper invalid options.
8. Certify baseline without requiring positive savings; revisit previous levels.
9. Restart/Continue and verify selections/completion persist.
10. Use Unlock All and confirm it opens screens but does not bypass validation.
11. Try sandbox launch/waypoints/docking/reentry; confirm campaign save isolation.
12. Check wrapped text/button labels at your display scale, especially checklists.

The patch shows entry-point changes relative to the uploaded source. Added modules
are delivered directly. See verification_results.txt for the actual test/report log.
