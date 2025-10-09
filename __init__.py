import sys
from pathlib import Path

# Get the absolute path of the script's parent directory (e.g., /1- WebScrapping/script/)
script_dir = Path(__file__).resolve().parent

# Find the project's root directory by navigating up two levels
project_root = script_dir.parent.parent

# Add the project's root to the Python path
sys.path.append(str(project_root))

# Now, the 'config' module will be found
from config import DIRETORIO_DADOS_LINKS