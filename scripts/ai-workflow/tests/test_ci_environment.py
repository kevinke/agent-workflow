"""Real tar/provenance regression tests; no WSL or GitHub service is simulated."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / 'scripts/ci/wsl_environment.py'


class CIEnvironmentTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), 'versioned WSL environment helper is missing')
        spec = importlib.util.spec_from_file_location('ci_environment', HELPER)
        self.env = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.env)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)

    def archive(self, names):
        with tarfile.open(self.cache / 'rootfs.tar', 'w') as archive:
            for name in names:
                entry = tarfile.TarInfo(name)
                entry.size = 4
                archive.addfile(entry, io.BytesIO(b'test'))

    def test_cache_key_changes_when_bootstrap_inputs_change(self):
        original = self.env.cache_key(b'{"revision":1}', b'apt-get install bwrap\n')
        self.assertNotEqual(original, self.env.cache_key(
            b'{"revision":2}', b'apt-get install bwrap\n'))
        self.assertNotEqual(original, self.env.cache_key(
            b'{"revision":1}', b'apt-get install bwrap git\n'))

    def test_cache_roundtrip_and_raw_corruption_refusal(self):
        self.archive(['etc/os-release', 'usr/bin/python3', 'home/ci/.bashrc'])
        self.env.seal_cache(self.cache, 'key', {'python': '3.12.3'})
        self.assertEqual(self.env.validate_cache(self.cache, 'key')['runtime'],
                         {'python': '3.12.3'})
        with (self.cache / 'rootfs.tar').open('ab') as file:
            file.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'digest'):
            self.env.validate_cache(self.cache, 'key')

    def test_cache_definition_mismatch_refused(self):
        self.archive(['etc/os-release'])
        self.env.seal_cache(self.cache, 'old', {})
        with self.assertRaisesRegex(ValueError, 'definition'):
            self.env.validate_cache(self.cache, 'new')

    def test_workspaces_credentials_and_traversal_cannot_be_cached(self):
        for name in ['mnt/c/checkout/code.py', 'workspace/project',
                     'root/.ssh/id_rsa', 'home/ci/.aws/credentials',
                     'home/ci/.git-credentials', 'home/ci/.codex/auth.json',
                     'home/ci/.config/gcloud/credentials.db',
                     'tmp/checkout', 'root/.bash_history', '../escape', '/absolute']:
            with self.subTest(name=name):
                self.archive([name])
                with self.assertRaises(ValueError):
                    self.env.seal_cache(self.cache, 'key', {})

    def test_system_symlink_is_allowed_but_symlink_to_workspace_refused(self):
        with tarfile.open(self.cache / 'rootfs.tar', 'w') as archive:
            entry = tarfile.TarInfo('bin')
            entry.type = tarfile.SYMTYPE
            entry.linkname = 'usr/bin'
            archive.addfile(entry)
        self.env.seal_cache(self.cache, 'key', {})
        with tarfile.open(self.cache / 'rootfs.tar', 'w') as archive:
            entry = tarfile.TarInfo('home/ci/checkout')
            entry.type = tarfile.SYMTYPE
            entry.linkname = '/mnt/c/checkout'
            archive.addfile(entry)
        with self.assertRaises(ValueError):
            self.env.seal_cache(self.cache, 'key', {})

    def test_empty_mount_points_are_allowed_without_their_contents(self):
        with tarfile.open(self.cache / 'rootfs.tar', 'w') as archive:
            for name in ('mnt', 'mnt/c', 'mnt/wsl'):
                entry = tarfile.TarInfo(name)
                entry.type = tarfile.DIRTYPE
                archive.addfile(entry)
        self.env.seal_cache(self.cache, 'key', {})

    def test_only_wsl_generated_resolver_link_can_point_into_mnt(self):
        for target, allowed in [('/mnt/wsl/resolv.conf', True),
                                ('/mnt/c/credentials', False),
                                ('/mnt/wsl/private', False)]:
            with self.subTest(target=target):
                with tarfile.open(self.cache / 'rootfs.tar', 'w') as archive:
                    entry = tarfile.TarInfo('etc/resolv.conf')
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = target
                    archive.addfile(entry)
                if allowed:
                    self.env.seal_cache(self.cache, 'key', {})
                else:
                    with self.assertRaises(ValueError):
                        self.env.seal_cache(self.cache, 'key', {})

    def test_relative_system_links_resolve_inside_rootfs(self):
        for name, target, allowed in [
            ('usr/lib/systemd/system/sysinit.target.wants/service', '../service', True),
            ('usr/bin/tool', '../../mnt/c/secret', False),
            ('root/link', '../root/.aws/credentials', False),
            ('usr/link', '../../../escape', False),
        ]:
            with self.subTest(name=name, target=target):
                with tarfile.open(self.cache / 'rootfs.tar', 'w') as archive:
                    entry = tarfile.TarInfo(name)
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = target
                    archive.addfile(entry)
                if allowed:
                    self.env.seal_cache(self.cache, 'key', {})
                else:
                    with self.assertRaises(ValueError):
                        self.env.seal_cache(self.cache, 'key', {})

    def test_control_utf16_and_linux_utf8_are_distinct(self):
        self.assertEqual(self.env.control_text('Ubuntu-24.04\r\n'.encode('utf-16le')),
                         'Ubuntu-24.04\r\n')
        self.assertEqual(self.env.control_text('中文错误'.encode('utf-8')), '中文错误')

    def test_paths_outside_owned_runner_temp_are_rejected(self):
        parent = self.cache / 'runner-temp'
        parent.mkdir()
        self.assertEqual(self.env.owned_path(parent / 'wsl', parent), parent / 'wsl')
        for path in [parent, self.cache / 'user-distro', parent / '..' / 'escape']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.env.owned_path(path, parent)

    def test_mutable_rootfs_or_invalid_hash_refused(self):
        definition = json.loads((ROOT / '.github/ci/wsl-environment.json').read_text())
        self.env.check_definition(definition)
        for field, value in [('rootfs_url', 'https://cloud-images.ubuntu.com/wsl/current/image.tar.gz'),
                             ('rootfs_sha256', 'unknown'), ('apt_snapshot', 'latest'),
                             ('distro', 'Ubuntu-24.04')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.env.check_definition(dict(definition, **{field: value}))

    def test_local_provisioning_refusal_preserves_host_diagnostics(self):
        environment = dict(os.environ)
        environment.pop('GITHUB_ACTIONS', None)
        report = self.cache / 'failure.json'
        result = subprocess.run([sys.executable, str(HELPER), 'bootstrap',
                                 '--cache', str(self.cache), '--diagnostics', str(report)],
                                env=environment, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        evidence = json.loads(report.read_text(encoding='utf-8'))
        self.assertIn('ephemeral GitHub Windows job', evidence['error'])
        self.assertIn('python', evidence['host'])
        self.assertFalse(evidence.get('commands'), 'refusal must happen before WSL is invoked')


if __name__ == '__main__':
    unittest.main()
