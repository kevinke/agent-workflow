"""Private experimental CLI container; not the linux-bwrap-v1 verifier profile."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(sys.argv[1]).resolve()

def manifest(directory):
    return {str(p.relative_to(directory)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
            'mode': p.stat().st_mode & 0o777}
            for p in sorted(directory.rglob('*')) if p.is_file()}

def argv(command):
    args = ['/usr/bin/bwrap', '--unshare-all', '--share-net', '--new-session',
            '--die-with-parent', '--clearenv', '--tmpfs', '/', '--dev', '/dev',
            '--proc', '/proc', '--ro-bind', '/usr', '/usr']
    for name in ['bin','lib','lib64','sbin']:
        args += ['--symlink', 'usr/'+name, '/'+name]
    args += ['--tmpfs', '/tmp', '--dir', '/etc', '--ro-bind', str(ROOT/'etc'), '/etc',
             '--dir', '/etc/ssl', '--ro-bind', '/etc/ssl/certs', '/etc/ssl/certs',
             '--dir', '/opt', '--ro-bind', str(ROOT/'runtime'/'codex'), '/opt/codex',
             '--ro-bind', str(ROOT/'runtime'/'codex-code-mode-host'), '/opt/codex-code-mode-host',
             '--bind', str(ROOT/'snapshot'), '/snapshot',
             '--bind', str(ROOT/'scratch'), '/scratch',
             '--ro-bind', str(ROOT/'protected'), '/live',
             '--ro-bind', str(ROOT/'supervisor'), '/protected-meta',
             '--chdir', '/snapshot', '--setenv', 'HOME', '/tmp',
             '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'LC_CTYPE', 'C.UTF-8',
             '--setenv', 'CODEX_HOME', '/scratch/runtime/codex',
             '--setenv', 'PWD', '/snapshot', '--']
    return args + command

if __name__ == '__main__':
    before = {d:manifest(ROOT/d) for d in ['protected','supervisor']}
    result = subprocess.run(argv(sys.argv[2:]), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    after = {d:manifest(ROOT/d) for d in ['protected','supervisor']}
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    print(json.dumps({'protected_host_bytes_and_modes_unchanged':before==after,
                      'exit_code':result.returncode}))
    if before != after:
        raise SystemExit('STOP: protected bytes/modes changed')
    raise SystemExit(result.returncode)
