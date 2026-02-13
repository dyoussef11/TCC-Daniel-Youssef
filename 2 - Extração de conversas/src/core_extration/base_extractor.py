import json
from pathlib import Path
import sys

# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (

EXTRACAO_CONFIG,
EXTRACAO

)



class BaseExtractor:
    def __init__(self, platform):
        self.platform = platform

        self.root_dir = EXTRACAO
        self.config = self._load_config()
        self._setup_folders()

    def _load_config(self):
        config_path = EXTRACAO_CONFIG / "extractor_settings_alternative copy.json"
        # CORREÇÃO: json.load(f) para LER o arquivo
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f) 

    def _setup_folders(self):
        pasta_bruta = self.root_dir / self.config["paths"]["output_bruto"]
        pasta_bruta.mkdir(parents=True, exist_ok=True)
        (self.root_dir / "logs").mkdir(exist_ok=True)