"""Apply the shared-flight follow-up to original sources or the earlier update."""
from pathlib import Path
import ast
import shutil
import sys
from datetime import datetime

MARKER='# STARLINER_SHARED_FLIGHT_V1'

def patch_ui(text):
    if MARKER in text:return text
    tree=ast.parse(text)
    factory=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='make_game_class'),None)
    if factory is None:raise ValueError('make_game_class factory not found')
    target=next((n for n in reversed(factory.body) if isinstance(n,ast.Return) and isinstance(n.value,ast.Name) and n.value.id=='EngineeringGame'),None)
    if target is None:raise ValueError('Expected EngineeringGame factory return not found')
    lines=text.splitlines(keepends=True)
    indent=' '*target.col_offset
    lines[target.lineno-1:target.end_lineno]=[
        indent+'from starliner_shared_flight import wrap_engineering_game\n',
        indent+'return wrap_engineering_game(EngineeringGame, BaseGame, pg)\n']
    updated=MARKER+'\n'+''.join(lines)
    compile(updated,'starliner_campaign_ui.py','exec')
    return updated

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
    ui=root/'starliner_campaign_ui.py'
    base=root/'starliner_engineering.py'
    if not ui.is_file() or not base.is_file():raise SystemExit('Choose the existing game folder containing both source files.')
    tree=ast.parse(base.read_text(encoding='utf8'))
    game=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Game')
    methods={n.name for n in game.body if isinstance(n,ast.FunctionDef)}
    required={'start','tick_systems','update','draw','handle','undock','reentry','persist','open_design'}
    if required-methods:raise SystemExit('Unsupported base Game; missing '+', '.join(sorted(required-methods)))
    source=Path(__file__).resolve().parent/'payload'
    updates={ui:patch_ui(ui.read_text(encoding='utf8'))}
    for name in ('starliner_shared_flight.py','test_starliner_shared_flight.py'):
        updates[root/name]=(source/name).read_text(encoding='utf8')
    for path,text in updates.items():compile(text,str(path),'exec')
    backup=root/('starliner_shared_backup_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));backup.mkdir()
    changed=[]
    try:
        for path in updates:
            if path.exists():shutil.copy2(path,backup/path.name)
        for path,text in updates.items():
            temp=path.with_name(path.name+'.shared-update.tmp')
            temp.write_text(text,encoding='utf8');temp.replace(path);changed.append(path)
    except BaseException:
        for path in changed:
            previous=backup/path.name
            if previous.exists():shutil.copy2(previous,path)
            else:path.unlink(missing_ok=True)
        raise
    print('Shared legacy flight installed. Backup:',backup.name)
    print('Run: python -m unittest test_starliner_shared_flight -v')
    print('Launch: python starliner_engineering.py')

if __name__=='__main__':main()
