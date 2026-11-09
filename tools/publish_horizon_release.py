"""Publier uniquement les artefacts identifiés dans une demande approuvée."""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPOSITORY = 'omg59/commandes-cahpp'
NAMES = {
    'CommandesCAHPP-Horizon-Linux-x86_64',
    'CommandesCAHPP-Horizon-Windows',
    'CommandesCAHPP-Horizon-Installer-Windows',
}


def gh(*args, **kwargs):
    return subprocess.run(['gh', *map(str, args)], check=True, **kwargs)


def api(path, optional=False):
    result = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/{path}'],
                            capture_output=True, text=True)
    if result.returncode:
        if optional and '(HTTP 404)' in result.stderr:
            return None
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def find_release(tag):
    # L'endpoint releases/tags ne retourne que les versions publiées.
    page = 1
    while True:
        releases = api(f'releases?per_page=100&page={page}')
        for release in releases:
            if release['tag_name'] == tag:
                return release
        if len(releases) < 100:
            return None
        page += 1


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_request(request, run, artifacts, source):
    version = request['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?', version):
        raise ValueError('Version invalide')
    if request['tag'] != f'v{version}' or not re.fullmatch('[a-f0-9]{40}', request['commit']):
        raise ValueError('Tag ou commit invalide')
    if request['prerelease'] is not bool(re.search(r'a|b|rc', version)):
        raise ValueError('Statut préversion incohérent')
    if (run['id'] != request['run_id'] or run['head_sha'] != request['commit']
            or run['head_branch'] != 'feature/horizon-ui'
            or run['path'] != '.github/workflows/horizon.yml'
            or run['status'] != 'completed' or run['conclusion'] != 'success'
            or run['head_repository']['full_name'] != REPOSITORY):
        raise ValueError('Le workflow approuvé doit avoir réussi sur le commit prévu')
    versions = [ast.literal_eval(n.value) for n in ast.parse(source).body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in n.targets)]
    if versions != [version]:
        raise ValueError('La version des sources ne correspond pas')
    if {a['name'] for a in request['artifacts']} != NAMES or len(request['artifacts']) != 3:
        raise ValueError('Les trois artefacts sont requis')
    for expected in request['artifacts']:
        matches = [a for a in artifacts if a['id'] == expected['id']]
        if len(matches) != 1:
            raise ValueError('Artefact absent du workflow')
        actual = matches[0]
        if (actual['expired'] or actual['name'] != expected['name']
                or actual['digest'] != expected['digest']
                or not re.fullmatch('sha256:[a-f0-9]{64}', expected['digest'])):
            raise ValueError('Artefact expiré ou différent de celui approuvé')


def extract_member(archive, filename, output):
    # Aucun chemin de l'archive n'est utilisé comme destination.
    with zipfile.ZipFile(archive) as z:
        matches = [n for n in z.namelist() if n == filename]
        if len(matches) != 1:
            raise ValueError(f'Fichier attendu absent ou ambigu : {filename}')
        target = output / filename
        with z.open(matches[0]) as src, target.open('wb') as dst:
            shutil.copyfileobj(src, dst)
    return target


def prepare_assets(request, folder):
    output = folder / 'release'
    output.mkdir()
    version = request['version']
    assets = []
    for artifact in request['artifacts']:
        archive = folder / f"{artifact['id']}.zip"
        with archive.open('wb') as dst:
            gh('api', f"repos/{REPOSITORY}/actions/artifacts/{artifact['id']}/zip", stdout=dst)
        if 'sha256:' + sha256(archive) != artifact['digest']:
            raise ValueError('Empreinte ZIP différente de l’artefact approuvé')
        name = artifact['name']
        if name.endswith('Installer-Windows'):
            assets.append(extract_member(archive, f'CommandesCAHPP-Horizon-Setup-{version}.exe', output))
        elif name.endswith('Linux-x86_64'):
            for suffix in ('.AppImage', '.tar.gz', '.json'):
                assets.append(extract_member(archive, f'CommandesCAHPP-Horizon-{version}-x86_64{suffix}', output))
        else:
            with zipfile.ZipFile(archive) as z:
                if ('CommandesCAHPP-Horizon.exe' not in z.namelist()
                        or not any(n.startswith('_internal/') for n in z.namelist())):
                    raise ValueError('Portable Windows incomplet')
            target = output / f'CommandesCAHPP-Horizon-{version}-Windows-portable.zip'
            shutil.copyfile(archive, target)
            assets.append(target)
    checksums = output / 'SHA256SUMS'
    checksums.write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in sorted(assets)), encoding='utf-8')
    return assets + [checksums]


def verify_uploaded(release, assets):
    actual = {a['name']: a for a in release['assets']}
    if set(actual) != {p.name for p in assets}:
        raise ValueError('Liste de fichiers de la release incomplète ou inattendue')
    for path in assets:
        a = actual[path.name]
        if (a['state'] != 'uploaded' or a['size'] != path.stat().st_size
                or a.get('digest') != 'sha256:' + sha256(path)):
            raise ValueError(f'Fichier publié non conforme : {path.name}')


def main():
    if os.environ.get('GH_REPO') != REPOSITORY:
        raise ValueError('Dépôt de publication inattendu')
    request = json.loads(Path(sys.argv[1]).read_text())
    run = api(f"actions/runs/{request['run_id']}")
    artifacts = api(f"actions/runs/{request['run_id']}/artifacts?per_page=100")['artifacts']
    source = api(f"contents/cahpp_app/horizon/__init__.py?ref={request['commit']}")
    validate_request(request, run, artifacts, base64.b64decode(source['content']).decode())
    tag = request['tag']
    ref = api(f'git/ref/tags/{tag}', optional=True)
    if ref and (ref['object']['type'] != 'commit' or ref['object']['sha'] != request['commit']):
        raise ValueError('Un tag existant désigne un autre commit')
    release = find_release(tag)
    if release and (release['target_commitish'] != request['commit'] or not release['draft']):
        raise ValueError('La release existe déjà : aucun remplacement automatique')
    with tempfile.TemporaryDirectory() as temp:
        assets = prepare_assets(request, Path(temp))
        notes = Path(f'docs/releases/{request["version"]}.md')
        if not release:
            gh('release', 'create', tag, '--repo', REPOSITORY, '--target', request['commit'],
               '--title', request['title'], '--notes-file', notes, '--draft',
               f'--prerelease={str(request["prerelease"]).lower()}', '--latest=false')
        gh('release', 'upload', tag, *assets, '--repo', REPOSITORY, '--clobber')
        verify_uploaded(find_release(tag), assets)
        gh('release', 'edit', tag, '--repo', REPOSITORY, '--draft=false',
           f'--prerelease={str(request["prerelease"]).lower()}', '--latest=false')
        final = find_release(tag)
        if final['draft'] or final['prerelease'] != request['prerelease']:
            raise ValueError('Publication non confirmée')
        print(final['html_url'])


if __name__ == '__main__':
    main()
