"""Private one-session model client enclosure; frozen verifier remains unchanged."""
from pathlib import Path
import sys

def argv(root, context, command):
    root=Path(root);context=Path(context)
    args=['/usr/bin/bwrap','--unshare-all','--share-net','--new-session','--die-with-parent','--clearenv','--tmpfs','/','--dev','/dev','--proc','/proc','--ro-bind','/usr','/usr']
    for name in ['bin','lib','lib64','sbin']:args+=['--symlink','usr/'+name,'/'+name]
    args+=['--tmpfs','/tmp','--dir','/etc','--ro-bind',str(root/'etc'),'/etc','--dir','/etc/ssl','--ro-bind','/etc/ssl/certs','/etc/ssl/certs','--dir','/opt',
        '--ro-bind',str(root/'runtime/codex'),'/opt/codex','--ro-bind',str(root/'runtime/codex-code-mode-host'),'/opt/codex-code-mode-host',
        '--ro-bind',str(root/'kit'),'/opt/kit','--ro-bind',str(root/'bin'),'/opt/bin',
        '--bind',str(context/'repo'),'/snapshot','--bind',str(context/'scratch'),'/scratch',
        '--bind',str(root/'client-home'),'/client-home','--ro-bind',str(root/'readback'),'/readback',
        '--ro-bind',str(root/'protected'),'/live','--ro-bind',str(root/'supervisor'),'/protected-meta',
        '--chdir','/snapshot','--setenv','HOME','/tmp','--setenv','PATH','/opt/bin:/usr/bin:/bin','--setenv','LC_CTYPE','C.UTF-8','--setenv','CODEX_HOME','/client-home','--setenv','PWD','/snapshot','--']
    return args+command

if __name__ == '__main__':
    import subprocess
    # Supply a prepared private runtime root, prepared review context, and argv.
    raise SystemExit(subprocess.run(argv(sys.argv[1], sys.argv[2], sys.argv[3:]), stdin=subprocess.DEVNULL).returncode)
