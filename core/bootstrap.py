from pathlib import Path
import sys


def ensure_project_root_in_path(marker_files=("requirements.txt", "README.md")):
    """
    Garante que a raiz do projeto esteja no sys.path,
    independente de onde o script foi executado.
    """

    current = Path(__file__).resolve()

    for parent in [current] + list(current.parents):
        if any((parent / marker).exists() for marker in marker_files):
            root = parent
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            return root

    raise RuntimeError("Raiz do projeto não encontrada.")
