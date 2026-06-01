
import json
import re

def verificar_checkpoint_valido(checkpoint_path):
    try:
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return True, data
    except:
        return False, "Erro ao ler checkpoint"