"""Empêcher la publication d'un autre build ou de fichiers incomplets."""
import copy
import hashlib
import json
import shutil
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from tools.publish_horizon_release import (
    NAMES, REPOSITORY, extract_member, find_release, main, prepare_assets, validate_request, verify_uploaded,
)


class HorizonReleaseTest(unittest.TestCase):
    def setUp(self):
        self.request = dict(enabled=True, version='3.0.0', tag='v3.0.0', title='Horizon 3.0.0',
                            prerelease=False, run_id=123, commit='1' * 40,
                            artifacts=[dict(id=i, name=name, digest='sha256:' + 'a' * 64)
                                       for i, name in enumerate(sorted(NAMES), 1)])
        r = self.request
        self.run = dict(id=r['run_id'], head_sha=r['commit'], head_branch='main',
                        path='.github/workflows/horizon.yml', status='completed', conclusion='success',
                        head_repository={'full_name': REPOSITORY})
        self.artifacts = [dict(a, expired=False) for a in r['artifacts']]
        self.source = f'VERSION = "{r["version"]}"'

    def validate(self):
        validate_request(self.request, self.run, self.artifacts, self.source)

    def test_draft_release_is_found_without_a_published_tag(self):
        draft = {'tag_name': 'v2.0.0b5', 'draft': True, 'id': 42}
        with patch('tools.publish_horizon_release.api', return_value=[draft]) as api:
            self.assertEqual(find_release('v2.0.0b5'), draft)
            api.assert_called_once_with('releases?per_page=100&page=1')

    def test_approved_build_is_accepted(self):
        self.validate()

    def test_failed_build_wrong_branch_or_commit_is_refused(self):
        for field, value in [('conclusion', 'failure'), ('head_branch', 'legacy'), ('head_sha', '0' * 40)]:
            with self.subTest(field=field):
                original = self.run[field]
                self.run[field] = value
                with self.assertRaises(ValueError):
                    self.validate()
                self.run[field] = original

    def test_wrong_version_or_changed_artifact_is_refused(self):
        self.source = 'VERSION = "1.6.0"'
        with self.assertRaises(ValueError):
            self.validate()
        self.source = f'VERSION = "{self.request["version"]}"'
        original = copy.deepcopy(self.artifacts)
        for field, value in [('expired', True), ('digest', 'sha256:' + '0' * 64), ('id', -1)]:
            self.artifacts = copy.deepcopy(original)
            self.artifacts[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate()

    def test_disabled_request_never_contacts_github(self):
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / 'request.json'
            request.write_text(json.dumps({'enabled': False}))
            with patch.dict('os.environ', {'GH_REPO': REPOSITORY}), patch('sys.argv', ['publish', str(request)]), patch('tools.publish_horizon_release.api') as api, patch('tools.publish_horizon_release.gh') as gh:
                main()
                api.assert_not_called()
                gh.assert_not_called()

    def test_validation_failure_never_calls_release_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / 'request.json'
            request.write_text(json.dumps(self.request))
            with patch.dict('os.environ', {'GH_REPO': REPOSITORY}), patch('sys.argv', ['publish', str(request)]), patch('tools.publish_horizon_release.api') as api, patch('tools.publish_horizon_release.gh') as gh:
                api.side_effect = [dict(self.run, conclusion='failure'), {'artifacts': self.artifacts}, {'content': 'VkVSU0lPTiA9ICIxLjYuMCI='}]
                with self.assertRaises(ValueError):
                    main()
                gh.assert_not_called()

    def test_missing_or_corrupt_upload_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'setup.exe'
            p.write_bytes(b'verified')
            asset = {'name': p.name, 'state': 'uploaded', 'size': p.stat().st_size,
                     'digest': 'sha256:' + hashlib.sha256(p.read_bytes()).hexdigest()}
            verify_uploaded({'assets': [asset]}, [p])
            with self.assertRaises(ValueError):
                verify_uploaded({'assets': []}, [p])
            with self.assertRaises(ValueError):
                verify_uploaded({'assets': [dict(asset, digest='sha256:' + '0' * 64)]}, [p])

    def test_extracts_only_the_expected_member(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / 'artifact.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('../unexpected.txt', b'ignored')
                z.writestr('setup.exe', b'installer')
            output = root / 'output'
            output.mkdir()
            self.assertEqual(extract_member(archive, 'setup.exe', output).read_bytes(), b'installer')
            self.assertEqual([p.name for p in output.iterdir()], ['setup.exe'])
            with self.assertRaises(ValueError):
                extract_member(archive, 'missing.exe', output)


    def test_installer_manifest_uses_the_verified_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / 'installer.zip'
            filename = 'CommandesCAHPP-Horizon-Setup-3.0.0.exe'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr(filename, b'verified-installer')
            artifact = dict(id=42, name='CommandesCAHPP-Horizon-Installer-Windows',
                            digest='sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest())
            request = dict(self.request, artifacts=[artifact])
            output = root / 'output'
            output.mkdir()

            def download(*args, stdout):
                with archive.open('rb') as source:
                    shutil.copyfileobj(source, stdout)

            with patch('tools.publish_horizon_release.gh', side_effect=download):
                assets = prepare_assets(request, output)
            manifest = json.loads(next(p for p in assets if p.suffix == '.json').read_text())
            self.assertEqual(manifest['file'], filename)
            self.assertEqual(manifest['sha256'], hashlib.sha256(b'verified-installer').hexdigest())
            self.assertEqual(manifest['source_commit'], request['commit'])
            self.assertEqual(manifest['artifact_digest'], artifact['digest'])
            self.assertEqual(len(assets), 3)
