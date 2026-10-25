#!/usr/bin/env python3
"""Validate release versions and emit Docker tags without network access."""
import argparse
import json
from pathlib import Path
import re

VERSION_RE = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?')


def version(root):
    text = (root / 'app/__init__.py').read_text()
    backend = re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)
    frontend = json.loads((root / 'frontend/package.json').read_text())['version']
    lock = json.loads((root / 'frontend/package-lock.json').read_text())
    assert backend == frontend == lock['version'] == lock['packages']['']['version'], 'Version mismatch'
    assert VERSION_RE.fullmatch(backend), 'Invalid version'
    return backend


def image_tags(image, variant, event, release_version, prerelease=False):
    assert variant in ('alpine', 'debian')
    assert event in ('main', 'release')
    if event == 'main':
        names = ['main', 'main-alpine'] if variant == 'alpine' else ['main-debian']
    else:
        assert VERSION_RE.fullmatch(release_version), 'Invalid release version'
        suffix = '' if variant == 'alpine' else '-debian'
        names = [release_version + suffix]
        if variant == 'alpine':
            names.append(release_version + '-alpine')
        if not prerelease and '-' not in release_version:
            major, minor, _ = release_version.split('.')
            names.extend([f'{major}.{minor}{suffix}', f'{major}{suffix}'])
            names.append('latest' if variant == 'alpine' else 'debian')
    return [f'{image.lower()}:{tag}' for tag in names]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-tag')
    parser.add_argument('--image')
    parser.add_argument('--variant', choices=['alpine', 'debian'])
    parser.add_argument('--event', choices=['main', 'release'], default='main')
    parser.add_argument('--prerelease', action='store_true')
    args = parser.parse_args()
    current = version(Path(__file__).resolve().parents[1])
    if args.release_tag is not None:
        assert args.release_tag == 'v' + current, f'Release tag must be v{current}'
    if args.image:
        assert args.variant, '--variant required'
        print('\n'.join(image_tags(args.image, args.variant, args.event, current, args.prerelease)))
    else:
        print(current)


if __name__ == '__main__':
    main()
