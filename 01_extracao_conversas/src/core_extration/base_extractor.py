import json
from pathlib import Path


from core.paths import (

EXTRACAO_CONFIG, EXTRACAO, EXTRACAO_SRC_CORE, EXTRACAO_SRC_EXTRACTORS

)

class BaseExtractor:
    def __init__(self, platform):
        self.platform = platform

        self.root_dir: Path = EXTRACAO
        self.extractors_dir: Path = EXTRACAO_SRC_EXTRACTORS
        self.core_extration_dir: Path = EXTRACAO_SRC_CORE

        self.config = self._load_config()
        self._setup_folders()

    def _load_config(self):
        
        # config_path: Path = EXTRACAO_CONFIG / "extractor_settings_extendedV2.json"
        # config_path: Path = EXTRACAO_CONFIG / "extractor_settings_extendedV3.json"
        # config_path: Path = EXTRACAO_CONFIG / "extractor_settings_extendedV4.json"
        # config_path: Path = EXTRACAO_CONFIG / "extractor_settings_extendedV5.json"
        config_path: Path = EXTRACAO_CONFIG / "extractor_settings_extendedV6.json"
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f) 

    def _setup_folders(self):
        pasta_bruta: Path = self.root_dir / self.config["paths"]["output_bruto"]
        pasta_bruta.mkdir(parents=True, exist_ok=True)
        (self.root_dir / "logs").mkdir(exist_ok=True)