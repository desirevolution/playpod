import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release', root/'scripts/release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_release_versions_are_consistent():
    assert release.version(root) == '1.0.0'


def test_release_tags_keep_debian_separate_and_main_never_updates_latest():
    assert release.image_tags('ghcr.io/Owner/PlayPod','alpine','release','1.0.0') == [
        'ghcr.io/owner/playpod:1.0.0','ghcr.io/owner/playpod:1.0.0-alpine',
        'ghcr.io/owner/playpod:1.0','ghcr.io/owner/playpod:1','ghcr.io/owner/playpod:latest']
    assert release.image_tags('ghcr.io/o/p','debian','release','1.0.0') == [
        'ghcr.io/o/p:1.0.0-debian','ghcr.io/o/p:1.0-debian','ghcr.io/o/p:1-debian','ghcr.io/o/p:debian']
    assert release.image_tags('ghcr.io/o/p','alpine','main','1.0.0') == ['ghcr.io/o/p:main','ghcr.io/o/p:main-alpine']
    assert release.image_tags('ghcr.io/o/p','alpine','release','1.1.0-rc.1',True) == ['ghcr.io/o/p:1.1.0-rc.1','ghcr.io/o/p:1.1.0-rc.1-alpine']
