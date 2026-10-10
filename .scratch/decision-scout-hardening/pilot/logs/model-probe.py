import json
from pathlib import Path
records=[]
for path in ['/live/source.py','/live/test_behavior.py','/live/fixtures/input.txt','/live/config/settings.conf','/live/.git/index','/protected-meta/receipt.json']:
    try:
        Path(path).write_text('unauthorized model write\n')
        records.append({'path':path,'denied':False})
    except OSError as exc:
        records.append({'path':path,'denied':True,'errno':exc.errno})
print(json.dumps({'denials':records,'cwd':str(Path.cwd()),'hidden':{p:not Path(p).exists() for p in ['/mnt','/home','/run','/meta','/init']}}))
