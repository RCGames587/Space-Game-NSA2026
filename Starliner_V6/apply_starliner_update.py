"""Install beside your existing sources: python apply_starliner_update.py [game_folder]."""
from pathlib import Path
import ast
import re
import sys
import shutil
import tempfile
from datetime import datetime

FLY = """def fly(self, point, dt, control=1.):
    delta = point.position-self.pos
    distance = delta.length()
    radius = max(22., self.vel.length()*.20)
    if distance <= radius:
        return True
    acceleration = self.power/self.mass*(1 if self.booster else .58)*control
    guidance = .55+.45*self.spec['guidance']
    speed = (65+self.power*.34)*point.throttle*guidance
    desired = delta.normalize()*speed
    change = desired-self.vel
    limit = acceleration*point.throttle*guidance*dt
    if change.length() > limit:
        change.scale_to_length(limit)
    self.vel += change
    self.fuel = max(0.,self.fuel-self.burn*point.throttle*dt)
    old = self.pos.copy()
    self.pos += self.vel*dt
    segment = self.pos-old
    fraction = max(0.,min(1.,(point.position-old).dot(segment)/segment.length_squared())) if segment.length_squared() else 0.
    reached = (point.position-(old+segment*fraction)).length() <= radius
    if self.vel.length_squared():
        self.angle = math.degrees(math.atan2(self.vel.y,self.vel.x))
    return reached
"""

DISCLAIMER_PATTERNS=(
    r'[^.!?]*(?:arcade (?:balancing )?(?:values|units)|simplified game (?:values|ratings)|not (?:a |actual |real )?(?:physical spacecraft simulation|vehicle endurance claims|engineering claim|engineering drawings))[^.!?]*[.!?]?',
    r'Baseline GAME assumption, not a real engineering claim\.',
)

class Update(ast.NodeTransformer):
    def __init__(self):self.class_name='';self.function_name=''
    def visit_ClassDef(self,node):
        old=self.class_name;self.class_name=node.name
        self.generic_visit(node);self.class_name=old;return node
    def visit_FunctionDef(self,node):
        old=self.function_name;self.function_name=node.name
        self.generic_visit(node)
        if self.class_name=='Rocket' and node.name=='fly':node=ast.parse(FLY).body[0]
        if self.class_name=='Game' and node.name=='update':
            node.name='_original_update_v3'
        self.function_name=old;return node
    def visit_Constant(self,node):
        if isinstance(node.value,str):
            text=re.sub('spacex','NASA',node.value,flags=re.I)
            if self.function_name and 'menu' not in self.function_name.lower():
                for pattern in DISCLAIMER_PATTERNS:text=re.sub(pattern,'',text,flags=re.I)
            node.value=text
        return node

def patch_main(text):
    if '# STARLINER_MISSION_UPDATE_V3' in text:return text
    tree=Update().visit(ast.parse(text))
    game=next((n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Game'),None)
    if game is None or not any(isinstance(n,ast.FunctionDef) and n.name=='_original_update_v3' for n in game.body):
        raise ValueError('Expected Game.update method was not found; no files changed.')
    wrapper=ast.parse("""def update(self,dt):
    remaining = max(0.,min(dt,.1))*(4. if self.state=='REENTRY' else 1.65)
    while remaining > 1e-9:
        step = min(remaining,1/120)
        self._original_update_v3(step)
        remaining -= step
""").body[0]
    game.body.append(wrapper)
    ast.fix_missing_locations(tree)
    result='# STARLINER_MISSION_UPDATE_V3\n'+ast.unparse(tree)+'\n'
    compile(result,'starliner_engineering.py','exec')
    return result

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
    required=('starliner_engineering.py','starliner_engineering_data.py','starliner_campaign.py')
    for name in required:
        if not (root/name).is_file():raise SystemExit('Missing '+str(root/name))
    payload=Path(__file__).resolve().parent/'payload'
    pending={root/'starliner_engineering.py':patch_main((root/'starliner_engineering.py').read_text(encoding='utf8'))}
    for name in ('starliner_campaign.py','starliner_engineering_data.py'):
        text=(root/name).read_text(encoding='utf8')
        pending[root/name]=re.sub('spacex','NASA',text,flags=re.I)
    for name in ('starliner_campaign_ui.py','starliner_mission.py','test_starliner_mission.py'):
        pending[root/name]=(payload/name).read_text(encoding='utf8')
    for path,text in pending.items():compile(text,str(path),'exec')
    backup=root/('starliner_backup_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup.mkdir()
    written=[]
    try:
        for path in pending:
            if path.exists():shutil.copy2(path,backup/path.name)
        for path,text in pending.items():
            with tempfile.NamedTemporaryFile('w',encoding='utf8',dir=root,delete=False) as stream:
                stream.write(text);temp=Path(stream.name)
            temp.replace(path);written.append(path)
    except BaseException:
        for path in written:
            if (backup/path.name).exists():shutil.copy2(backup/path.name,path)
            else:path.unlink(missing_ok=True)
        raise
    print('Update installed. Backup:',backup.name)
    print('Run: python -m unittest test_starliner_mission -v')
    print('Then: python starliner_engineering.py')

if __name__=='__main__':main()
