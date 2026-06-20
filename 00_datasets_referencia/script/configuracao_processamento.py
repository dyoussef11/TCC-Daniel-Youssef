import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)

@dataclass
class ConfiguracaoModelos:
    COLUNAS_PADRAO: List[str] = field(default_factory=list)
    PADROES_HARDWARE: Dict[str, str] = field(default_factory=dict)
    CATEGORIAS: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def carregar(cls, caminho: Path):
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                return cls(**json.load(f))
        except Exception as e:
            logger.error(f"Erro ao carregar configuração de hardware: {e}")
            raise