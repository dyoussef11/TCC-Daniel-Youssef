import json
import re
from pathlib import Path
from tqdm import tqdm
from core.paths import NER_DATA, NER_UTILS
# Importações dos seus utilitários (mantendo seus caminhos)
from utils.utils_ner import (
    RULES_PATH, CAMINHO_ENTRADA_JSON, CustomEncoder
)

# Definimos um caminho de saída específico para este teste
CAMINHO_TESTE_SAIDA = NER_DATA/ "reddit_50_notebooks_w_componentsV2.json"

class HardwareExtractor:
    def __init__(self, rules_path: Path):
        with open(rules_path, 'r', encoding='utf-8') as f:
            self.patterns = json.load(f)

    def extrair(self, text: str) -> dict:
        """Executa o motor de Regex para cada categoria do hardware_patterns.json"""
        entidades_encontradas = {}
        
        for categoria, pattern in self.patterns.items():
            # Buscamos todos os matches (removendo duplicatas com set)
            matches = list(set(re.findall(pattern, text, re.IGNORECASE)))
            
            if matches:
                # Tratamento para Regex que possuem grupos (tuplas)
                limpos = []
                for m in matches:
                    if isinstance(m, tuple):
                        # Pega o primeiro elemento não vazio da tupla
                        val = next((item for item in m if item), "")
                        if val: limpos.append(val.strip())
                    else:
                        limpos.append(m.strip())
                
                if limpos:
                    entidades_encontradas[categoria] = list(set(limpos))
        
        return entidades_encontradas

def executar_teste_regex():
    print(f"🔍 Iniciando extração técnica via Regex...")
    extractor = HardwareExtractor(RULES_PATH)
    
    # Criar diretório de saída se não existir
    CAMINHO_TESTE_SAIDA.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        # Garante que lidamos com lista de notebooks (estrutura do seu crawler)
        objetos = [dados] if isinstance(dados, dict) else dados
    except Exception as e:
        print(f"❌ Erro ao ler arquivo de entrada: {e}")
        return

    resultados = []

    for item in tqdm(objetos, desc="Modelos"):
        total_entidades_modelo = 0
        posts_processados = []

        for post in tqdm(item.get('posts', []), desc=" -> Extraindo Hardware", leave=False):
            # Combinamos Título e Conteúdo para a busca
            texto_completo = f"{post.get('titulo_limpo', '')} {post.get('conteudo_post_limpo', '')}"
            
            # Executa a extração
            componentes = extractor.extrair(texto_completo)
            
            # Adiciona os componentes achados ao dicionário do post
            post['detected_component'] = componentes
            post['qtd_component'] = sum(len(v) for v in componentes.values())
            
            total_entidades_modelo += post['qtd_component']
            posts_processados.append(post)

        item['posts'] = posts_processados
        item['stats_extracao'] = {"total_hardware_found": total_entidades_modelo}
        resultados.append(item)

    # Salva o arquivo final para conferência manual
    print(f"💾 Salvando resultados em: {CAMINHO_TESTE_SAIDA}")
    with open(CAMINHO_TESTE_SAIDA, 'w', encoding='utf-8') as f_out:
        json.dump(resultados, f_out, ensure_ascii=False, indent=4, cls=CustomEncoder)
    
    print(f"✅ Teste concluído! Verifique o arquivo para validar se o Regex capturou os modelos corretamente.")

if __name__ == "__main__":
    executar_teste_regex()