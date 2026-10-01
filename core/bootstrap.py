from pathlib import Path
import sys

def ensure_project_root_in_path(marker_files=("pyproject.toml", "requirements.txt", "README.md")):
    """
    Garante a raiz do projeto e pastas auxiliares no sys.path
    sem quebrar dependências externas.
    """
    current = Path(__file__).resolve()
    root = None

    # Busca a raiz
    for parent in [current] + list(current.parents):
        if any((parent / marker).exists() for marker in marker_files):
            root = parent
            break

    if not root:
        raise RuntimeError("Raiz do projeto não encontrada.")

    # Raiz no topo do sys.path
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # Injeta `utils` das pastas numeradas no FINAL (evita shadowing)
    for utils_path in root.glob("0*/utils"):
        if utils_path.is_dir() and str(utils_path) not in sys.path:
            sys.path.append(str(utils_path))

    # Injeta `src` das pastas numeradas no FINAL
    # (necessário para que `from extractors.xxx import ...` funcione)
    for src_path in root.glob("0*/src"):
        if src_path.is_dir() and str(src_path) not in sys.path:
            sys.path.append(str(src_path))

    return root