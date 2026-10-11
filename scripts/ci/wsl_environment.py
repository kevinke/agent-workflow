"""CI-only clean WSL2 rootfs bootstrap/cache and real production preflight.

No third-party Python packages. Provisioning is restricted to GitHub Windows
jobs and a new, dedicated distro; probe can inspect an existing local distro.
Cache tar bytes are hashed, never decoded or extracted on the Windows host.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import posixpath
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
DEFINITION = ROOT / '.github/ci/wsl-environment.json'
RECIPE = Path(__file__).with_name('bootstrap-wsl.sh')


def cache_key(*inputs):
    digest = hashlib.sha256()
    for data in inputs:
        data = data.replace(b'\r\n', b'\n')
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
    return 'windows2025-x64-wsl2-v1-' + digest.hexdigest()


def check_definition(definition):
    if (definition.get('schema') != 1 or definition.get('architecture') != 'amd64'
            or definition.get('distro') != 'AgentWorkflow-CI-Ubuntu2404'
            or not re.fullmatch(r'https://cloud-images\.ubuntu\.com/wsl/releases/noble/\d{8}/[^/]+\.rootfs\.tar\.gz', definition.get('rootfs_url', ''))
            or not re.fullmatch(r'[0-9a-f]{64}', definition.get('rootfs_sha256', ''))
            or not re.fullmatch(r'\d{8}T\d{6}Z', definition.get('apt_snapshot', ''))
            or not definition.get('packages')
            or any(not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*', p) for p in definition['packages'])):
        raise ValueError('unsupported or unpinned WSL environment definition')


def owned_path(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError('CI path must be strictly inside RUNNER_TEMP')
    return path


def sha256(path):
    with Path(path).open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def prepare_base(download, archive):
    # The pinned public WSL image enables systemd/cloud-init. Configure this
    # owned CI distro before its first boot, rather than racing first-boot
    # provisioning and trying to remove whatever it writes afterwards.
    overrides = {'etc/wsl.conf': b'[boot]\nsystemd=false\n',
                 'etc/cloud/cloud-init.disabled': b''}
    with tarfile.open(download, 'r|gz') as source, tarfile.open(archive, 'w') as target:
        for entry in source:
            name = entry.name
            while name.startswith('./'):
                name = name[2:]
            if name not in overrides:
                target.addfile(entry, source.extractfile(entry) if entry.isfile() else None)
        for name, raw in overrides.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(raw)
            entry.mode = 0o644
            target.addfile(entry, io.BytesIO(raw))


def forbidden_path(name):
    parts = PurePosixPath(name).parts
    if '..' in parts:
        return True
    if parts and parts[0] in ('mnt', 'workspace', 'workspaces', '__w', 'tmp') and len(parts) > 1:
        return True
    if parts[:2] == ('var', 'tmp') and len(parts) > 2:
        return True
    if parts and parts[0] in ('home', 'root'):
        return any(p in ('.ssh', '.aws', '.azure', '.codex', '.git', '.git-credentials',
                         '.docker', '.kube', '.npmrc', '.pypirc',
                         '.bash_history', '.python_history', '.netrc', 'gcloud') for p in parts)
    return False


def scan_archive(path):
    with tarfile.open(path, 'r:') as archive:
        for entry in archive:
            name = entry.name
            while name.startswith('./'):
                name = name[2:]
            empty_mount_point = (entry.isdir() and PurePosixPath(name).parts[:1] == ('mnt',)
                                 and len(PurePosixPath(name).parts) <= 2)
            empty_mount_point |= entry.isdir() and name == 'tmp/.X11-unix'
            if name.startswith('/') or (forbidden_path(name) and not empty_mount_point):
                raise ValueError('rootfs contains a workspace, credential or unsafe path: ' + name)
            if entry.issym() or entry.islnk():
                # System links (/usr, /dev, /proc) are part of a Linux rootfs;
                # links into Windows mounts or user credentials are not.
                generated_resolver = (entry.issym() and name == 'etc/resolv.conf'
                                      and entry.linkname == '/mnt/wsl/resolv.conf')
                base = posixpath.dirname(name) if entry.issym() else ''
                target = posixpath.normpath(posixpath.join(base, entry.linkname))
                if forbidden_path(target.lstrip('/')) and not generated_resolver:
                    raise ValueError('rootfs link reaches a forbidden path: ' + name)


def seal_cache(cache, key, runtime):
    cache = Path(cache)
    scan_archive(cache / 'rootfs.tar')
    record = {'schema': 1, 'definition': key, 'sha256': sha256(cache / 'rootfs.tar'),
              'runtime': runtime}
    (cache / 'provenance.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def validate_cache(cache, key):
    cache = Path(cache)
    record = json.loads((cache / 'provenance.json').read_text(encoding='utf-8'))
    if record.get('schema') != 1 or record.get('definition') != key:
        raise ValueError('cached environment definition mismatch')
    if record.get('sha256') != sha256(cache / 'rootfs.tar'):
        raise ValueError('cached rootfs digest mismatch')
    scan_archive(cache / 'rootfs.tar')
    return record


def control_text(raw):
    # wsl.exe control commands can emit UTF-16LE; Linux --exec output is UTF-8.
    return raw.decode('utf-16' if raw.startswith(b'\xff\xfe') else 'utf-16le') if b'\0' in raw or raw.startswith(b'\xff\xfe') else raw.decode('utf-8', 'replace')


def command(argv, record, *, control=False, data=None, timeout=120):
    result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
    decode = control_text if control else lambda raw: raw.decode('utf-8', 'replace')
    stdout, stderr = decode(result.stdout), decode(result.stderr)
    record.setdefault('commands', []).append({'argv': argv, 'exit': result.returncode,
                                             'stdout': stdout, 'stderr': stderr})
    if result.returncode:
        raise RuntimeError('%s failed (%s): %s' % (argv[0], result.returncode, stderr or stdout))
    return stdout.strip()


def linux(distro, *args, user=None):
    return ['wsl.exe', '-d', distro] + (['--user', user] if user else []) + ['--exec', *args]


def probe(distro, definition, record, *, require_marker=False, key=None):
    if os.name != 'nt':
        raise RuntimeError('this preflight must be launched by Windows Python')
    if platform.python_version() != definition['windows_python']:
        raise RuntimeError('Windows Python must be ' + definition['windows_python'])
    record['windows'] = platform.platform()
    record['windows_python'] = platform.python_version()
    record['runner_image'] = {'os': os.getenv('ImageOS'), 'version': os.getenv('ImageVersion')}
    record['wsl_version'] = command(['wsl.exe', '--version'], record, control=True)
    record['wsl_distros'] = command(['wsl.exe', '--list', '--verbose'], record, control=True)
    code = '''import json,os,platform,subprocess
from pathlib import Path
print(json.dumps({"os_release":dict(line.split("=",1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line),"python":platform.python_version(),"kernel":platform.release(),"uid":os.getuid(),"bwrap":subprocess.check_output(["bwrap","--version"],text=True).strip(),"marker":json.loads(Path("/etc/agent-workflow-ci.json").read_text()) if Path("/etc/agent-workflow-ci.json").exists() else None,"packages":subprocess.check_output(["dpkg-query","-W","python3","git","bubblewrap","ca-certificates"],text=True)}))'''
    runtime = json.loads(command(linux(distro, 'python3', '-c', code), record))
    record['linux'] = runtime
    if (runtime['os_release'].get('VERSION_ID', '').strip('"') != definition['ubuntu_version']
            or not runtime['python'].startswith(definition['linux_python'] + '.')
            or 'microsoft-standard-WSL2' not in runtime['kernel'] or runtime['uid'] == 0):
        raise RuntimeError('expected Ubuntu 24.04 / Python 3.12 / non-root WSL2 runtime')
    if require_marker and (runtime['marker'] or {}).get('definition') != key:
        raise RuntimeError('imported distro environment definition mismatch')
    # Exercise the exact production profile, with temporary sentinel/context
    # directories, not a looser namespace smoke test or fixture supervisor.
    sys.path.insert(0, str(ROOT / 'scripts/ai-workflow'))
    import review_boundary
    import review_snapshot
    os.environ['AI_WORKFLOW_BWRAP_DISTRO'] = distro
    with tempfile.TemporaryDirectory(prefix='ci-wsl-preflight-') as context:
        for name in ('repo', 'scratch', 'meta'):
            (Path(context) / name).mkdir()
        manifest = {'format_version': review_snapshot.FORMAT_VERSION,
                    'ticket_id': 'CI-PREFLIGHT', 'live_root': str(ROOT),
                    'scope': {'paths': {}}, 'live_manifest': {},
                    'snapshot_manifest': {}, 'inputs': {}}
        (Path(context) / 'meta/context.json').write_text(json.dumps(manifest), encoding='utf-8')
        record['boundary'] = review_boundary.preflight(context)
    return runtime


def bootstrap(definition, key, cache, record):
    if os.name != 'nt' or os.getenv('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('provisioning is only allowed in an ephemeral GitHub Windows job; use probe locally')
    runner_temp = Path(os.environ['RUNNER_TEMP'])
    cache = owned_path(cache, runner_temp)
    install = owned_path(runner_temp / 'agent-workflow-ci-distro', runner_temp)
    distro = definition['distro']
    existing = command(['wsl.exe', '--list', '--quiet'], record, control=True)
    if distro.casefold() in [name.strip().casefold() for name in existing.splitlines()]:
        raise RuntimeError('refusing to replace an existing distro: ' + distro)
    # Use the runner's existing WSL. A mandatory online update can fail before
    # import (403), even on a host with a working WSL2 runtime. The real
    # non-root production preflight below remains the capability gate.
    record['wsl_version_at_bootstrap'] = command(['wsl.exe', '--version'], record, control=True)
    cache.mkdir(parents=True, exist_ok=True)
    restored = False
    try:
        validate_cache(cache, key)
        restored = True
        record['cache'] = 'validated-hit'
    except (OSError, ValueError, tarfile.TarError) as exc:
        record['cache'] = 'rebuild'
        record['cache_reason'] = str(exc)
    created = False
    started = time.monotonic()
    try:
        if restored:
            archive = cache / 'rootfs.tar'
        else:
            archive = owned_path(runner_temp / 'agent-workflow-base.tar', runner_temp)
            download = archive.with_suffix('.tar.gz')
            urllib.request.urlretrieve(definition['rootfs_url'], download)
            record['official_base_sha256'] = sha256(download)
            if record['official_base_sha256'] != definition['rootfs_sha256']:
                raise ValueError('official rootfs SHA256 mismatch; import refused')
            prepare_base(download, archive)
            record['prepared_base_sha256'] = sha256(archive)
        command(['wsl.exe', '--import', distro, str(install), str(archive), '--version', '2'], record, control=True, timeout=600)
        created = True
        if not restored:
            recipe = RECIPE.read_bytes().replace(b'\r\n', b'\n')
            command(linux(distro, 'bash', '-s', '--', definition['apt_snapshot'], key,
                          *definition['packages'], user='root'), record, data=recipe, timeout=900)
            command(['wsl.exe', '--terminate', distro], record, control=True)
            # Stop before export so no running process writes into the tar.
            command(['wsl.exe', '--export', distro, str(cache / 'rootfs.tar')], record, control=True, timeout=600)
            seal_cache(cache, key, {'apt_snapshot': definition['apt_snapshot']})
        # Probe starts the distro with its configured non-root default user.
        probe(distro, definition, record, require_marker=True, key=key)
        record['bootstrap_seconds'] = round(time.monotonic() - started, 3)
        record['cache_provenance'] = validate_cache(cache, key)
        # Explicit routing for the entire Windows test suite; no default-distro
        # mutation and no mixing this context with any pre-existing WSL distro.
        with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as file:
            file.write('AI_WORKFLOW_BWRAP_DISTRO=' + distro + '\n')
    except BaseException:
        if created:
            command(['wsl.exe', '--unregister', distro], record, control=True, timeout=120)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['key', 'plan', 'bootstrap', 'probe'])
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--distro')
    parser.add_argument('--diagnostics', type=Path)
    args = parser.parse_args(argv)
    definition = json.loads(DEFINITION.read_text(encoding='utf-8'))
    check_definition(definition)
    key = cache_key(DEFINITION.read_bytes(), RECIPE.read_bytes(), Path(__file__).read_bytes())
    if args.action == 'key':
        print(key)
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as file:
                file.write('key=' + key + '\n')
        return 0
    record = {'definition': definition, 'key': key, 'action': args.action,
              'host': {'platform': platform.platform(), 'python': platform.python_version(),
                       'runner_image_os': os.getenv('ImageOS'),
                       'runner_image_version': os.getenv('ImageVersion')}}
    try:
        if args.action == 'plan':
            record['reuse'] = 'clean rootfs only; Windows/WSL/kernel remain host supplied'
        elif args.action == 'probe':
            probe(args.distro or definition['distro'], definition, record)
        else:
            if args.cache is None:
                parser.error('bootstrap requires --cache')
            bootstrap(definition, key, args.cache, record)
        record['status'] = 'passed'
        return 0
    except Exception as exc:
        record['status'] = 'failed'
        record['error'] = str(exc)
        return 1
    finally:
        if args.diagnostics:
            args.diagnostics.parent.mkdir(parents=True, exist_ok=True)
            args.diagnostics.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(record, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8')
    sys.exit(main())
