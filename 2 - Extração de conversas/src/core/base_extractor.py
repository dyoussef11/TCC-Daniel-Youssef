import json
from pathlib import Path

class BaseExtractor:
    def __init__(self, platform):
        self.platform = platform
        # Caminho: .../2 - Extração de conversas/
        self.root_dir = Path(__file__).resolve().parent.parent.parent
        self.config = self._load_config()
        self._setup_folders()

    def _load_config(self):
        config_path = self.root_dir / "config" / "extractor_settings.json"
        # CORREÇÃO: json.load(f) para LER o arquivo
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f) 

    def _setup_folders(self):
        pasta_bruta = self.root_dir / self.config["paths"]["output_bruto"]
        pasta_bruta.mkdir(parents=True, exist_ok=True)
        (self.root_dir / "logs").mkdir(exist_ok=True)