"""Install after the Shared Legacy Flight Update."""
from pathlib import Path
from datetime import datetime
import ast
import sys
import shutil

MARKER='# STARLINER_TRIAL_DESIGN_V1'

def patch_shared(text):
    if MARKER in text:return text
    tree=ast.parse(text)
    factory=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='wrap_engineering_game'),None)
    if factory is None:raise ValueError('Expected shared-flight factory was not found.')
    target=next((n for n in reversed(factory.body) if isinstance(n,ast.Return) and isinstance(n.value,ast.Name) and n.value.id=='SharedFlightGame'),None)
    if target is None:raise ValueError('Expected SharedFlightGame return was not found.')
    lines=text.splitlines(keepends=True);indent=' '*target.col_offset
    lines[target.lineno-1:target.end_lineno]=[
        indent+'from starliner_trial_design import wrap_trial_game\n',
        indent+'return wrap_trial_game(SharedFlightGame, BaseGame, pg)\n']
    updated=MARKER+'\n'+''.join(lines)
    compile(updated,'starliner_shared_flight.py','exec');return updated

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
    shared=root/'starliner_shared_flight.py'
    if not shared.is_file():raise SystemExit('Install the Shared Legacy Flight Update first, or choose its game folder.')
    payload=Path(__file__).resolve().parent/'payload'
    updates={shared:patch_shared(shared.read_text(encoding='utf8'))}
    for name in ('starliner_trial_design.py','test_starliner_trial_design.py'):
        updates[root/name]=(payload/name).read_text(encoding='utf8')
    for path,text in updates.items():compile(text,str(path),'exec')
    backup=root/('starliner_trial_backup_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));backup.mkdir()
    written=[]
    try:
        for path in updates:
            if path.exists():shutil.copy2(path,backup/path.name)
        for path,text in updates.items():
            temp=path.with_name(path.name+'.trial.tmp');temp.write_text(text,encoding='utf8');temp.replace(path);written.append(path)
    except BaseException:
        for path in written:
            if (backup/path.name).exists():shutil.copy2(backup/path.name,path)
            else:path.unlink(missing_ok=True)
        raise
    print('Trial design update installed; backup:',backup.name)
    print('Run: python -m unittest test_starliner_trial_design -v')
    print('Play: python starliner_engineering.py')

if __name__=='__main__':main()
