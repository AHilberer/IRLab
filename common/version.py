"""Version of the IRLab code, reported by the servers' /status endpoint."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_version() -> str:
    """Return '<branch>@<short commit hash>' read from the .git directory, without
    calling git (it may not be installed on the bench PCs); 'unknown' if unavailable."""
    git_dir = REPO_ROOT / '.git'
    try:
        head = (git_dir / 'HEAD').read_text().strip()
        if not head.startswith('ref: '):
            return head[:8]                      # detached HEAD
        ref = head[5:]
        branch = ref[len('refs/heads/'):] if ref.startswith('refs/heads/') else ref
        ref_file = git_dir / ref
        if ref_file.exists():
            commit = ref_file.read_text().strip()
        else:
            commit = None
            for line in (git_dir / 'packed-refs').read_text().splitlines():
                if line.endswith(' ' + ref):
                    commit = line.split()[0]
                    break
        return f'{branch}@{commit[:8]}' if commit else branch
    except Exception:
        return 'unknown'
