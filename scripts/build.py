#!/usr/bin/env python3
"""Build a checksum-verified, deterministic offline theme ZIP (Python 3.9+)."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inside(root, relative):
    p = PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\' in relative:
        raise ValueError('Unsafe relative path: ' + relative)
    result = root.joinpath(*p.parts).resolve()
    result.relative_to(root.resolve())
    return result


def verify_file(path, entry):
    if not path.is_file() or digest(path) != entry['sha256']:
        raise ValueError('Missing or checksum-mismatched file: ' + str(path))
    if 'size' in entry and path.stat().st_size != entry['size']:
        raise ValueError('Incorrect file size: ' + str(path))


def css_dependencies(root, allowed_missing=()):
    """Require every CSS import and URL to remain inside the theme directory."""
    theme = root / 'theme'
    for css in theme.rglob('*.css'):
        source = re.sub(r'/\*.*?\*/', '', css.read_text(), flags=re.S)
        refs = re.findall(r'@import\s+[\"\']([^\"\']+)', source)
        refs += re.findall(r'url\(\s*[\"\']?([^\"\')\s]+)', source)
        for ref in refs:
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', ref) or ref.startswith(('/', '\\')):
                raise ValueError('Non-local CSS dependency: ' + ref)
            target = (css.parent / ref).resolve()
            target.relative_to(theme.resolve())
            relative = target.relative_to(root.resolve()).as_posix()
            if not target.is_file() and relative not in allowed_missing:
                raise ValueError(f'{css}: missing {ref}')


def download(url, destination, expected):
    if not url.startswith('https://'):
        raise ValueError('Only HTTPS sources are accepted')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.part')
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'alto-macchiato-builder/0.1'})
            with urllib.request.urlopen(request, timeout=90) as response, temporary.open('wb') as out:
                shutil.copyfileobj(response, out)
            verify_file(temporary, {'sha256': expected})
            temporary.replace(destination)
            return
        except (OSError, http.client.HTTPException) as error:
            if attempt == 2:
                raise OSError(f'Download failed after 3 attempts: {url}: {error}') from error
            print(f'Network retry {attempt + 1}/2: {url}', flush=True)
        finally:
            temporary.unlink(missing_ok=True)


def font_file(entry, cache, offline):
    target = cache / 'fonts' / entry['sha256']
    if target.exists():
        verify_file(target, entry)  # Fail closed on corrupted cache, even online.
        return target
    if offline:
        raise ValueError('Offline cache missing: ' + entry['path'])
    target.parent.mkdir(parents=True, exist_ok=True)
    print('Fetching ' + Path(entry['path']).name, flush=True)
    if 'archive_sha256' in entry:
        archive = cache / 'downloads' / (entry['archive_sha256'] + '.zip')
        if not archive.exists():
            download(entry['url'], archive, entry['archive_sha256'])
        verify_file(archive, {'sha256': entry['archive_sha256']})
        with zipfile.ZipFile(archive) as z:
            members = [n for n in z.namelist() if PurePosixPath(n).name == entry['member_basename']]
            if len(members) != 1:
                raise ValueError('Expected exactly one archive member: ' + entry['member_basename'])
            data = z.read(members[0])  # Never extract untrusted archive paths.
            if len(data) != entry['size'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('Archive member checksum mismatch: ' + members[0])
            target.write_bytes(data)
    else:
        download(entry['url'], target, entry['sha256'])
    verify_file(target, entry)
    return target


def check_source(root, lock):
    for item in lock['upstream_snapshots'] + lock['licenses']:
        verify_file(inside(root, item['path']), item)
    for font in lock['fonts']:
        inside(root, font['path'])
        if not inside(root, font['license']).is_file():
            raise ValueError('Missing font license: ' + font['license'])
    css_dependencies(root, {x['path'] for x in lock['fonts']})


def build(root, lock, cache, output, offline):
    version = (root / 'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?', version):
        raise ValueError('Invalid VERSION')
    name = 'alto-macchiato-theme'
    archive_name = 'alto-macchiato-theme-' + version
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='alto-build-') as temp:
        stage = Path(temp) / name
        stage.mkdir()
        shutil.copytree(root / 'theme', stage / 'theme',
                        ignore=shutil.ignore_patterns('.DS_Store', '__pycache__'))
        shutil.copyfile(root / 'LICENSE', stage / 'theme/alto-macchiato/LICENSE')
        for entry in lock['fonts']:
            destination = inside(stage, entry['path'])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(font_file(entry, cache, offline), destination)
        css_dependencies(stage)
        package = stage / 'theme'
        files = sorted(p for p in package.rglob('*') if p.is_file())
        expected = {name + '/' + p.relative_to(package).as_posix(): digest(p) for p in files}
        target = output / (archive_name + '.zip')
        temporary = target.with_suffix('.part')
        try:
            with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                for path in files:
                    info = zipfile.ZipInfo(name + '/' + path.relative_to(package).as_posix(), (2026, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    z.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            # Read every archived byte back, including fonts, before publishing output.
            with zipfile.ZipFile(temporary) as z:
                if len(z.namelist()) != len(expected) or set(z.namelist()) != set(expected):
                    raise ValueError('Unexpected package contents')
                for member, checksum in expected.items():
                    if hashlib.sha256(z.read(member)).hexdigest() != checksum:
                        raise ValueError('Package checksum mismatch: ' + member)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    checksum = target.with_suffix('.zip.sha256')
    checksum.write_text(digest(target) + '  ' + target.name + '\n')
    print(f'Built {target} ({target.stat().st_size / 1024 / 1024:.1f} MiB)')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Use only verified cached font files')
    parser.add_argument('--check', action='store_true', help='Validate tracked source and dependency paths only')
    parser.add_argument('--cache', type=Path, default=ROOT / '.cache')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'dependencies.lock.json').read_text())
    try:
        check_source(ROOT, lock)
        if args.check:
            print('Source, upstream snapshots, licenses and CSS dependency paths are valid.')
        else:
            build(ROOT, lock, args.cache.resolve(), args.output.resolve(), args.offline)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
