import os
import ast
import csv
from collections import defaultdict

BASE_DIR = "/home/daniely/Documentos/Notebook-Forum-Sentimento"

PASTAS_ALVO = [
    "00_datasets_referencia",
    "01_extracao_conversas",
    "02_preprocessamento",
    "03_ner_e_resumo",
    "04_vetorizacao",
    "05_definicao_sistemas_rags",
    "06_avaliacao_quantitativa_deepval"
]

def extrair_declaracoes(caminho_arquivo):
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        try:
            arvore = ast.parse(f.read())
        except SyntaxError:
            return {"erro": "Sintaxe inválida"}

    class Extrator(ast.NodeVisitor):
        def __init__(self):
            self.globais = []   # cada item será: (nome, valor_str, tipo_classificacao)
            self.funcoes = []
            self._escopo_atual = []

        def classificar_global(self, node_valor):
            """Retorna 'Global Numeric' ou 'Global Config' baseado no valor"""
            try:
                # Tenta avaliar o valor de forma SEGURA (sem executar código)
                valor_avaliado = ast.literal_eval(node_valor)
                
                # CUIDADO: bool é subclasse de int, então teste booleano PRIMEIRO
                if isinstance(valor_avaliado, bool):
                    return "Global Config"
                elif isinstance(valor_avaliado, (int, float)):
                    return "Global Numeric"
                else:
                    return "Global Config"
            except (ValueError, SyntaxError):
                # Se não for um literal simples (ex: os.path.join(), chamada de função)
                return "Global Config"

        def visit_Assign(self, node):
            if len(self._escopo_atual) == 0:  # Escopo global
                for alvo in node.targets:
                    if isinstance(alvo, ast.Name):
                        try:
                            valor_str = ast.unparse(node.value)
                        except:
                            valor_str = "<expressão>"
                        
                        # Classifica o tipo
                        tipo = self.classificar_global(node.value)
                        self.globais.append((alvo.id, valor_str, tipo))
            self.generic_visit(node)

        def visit_FunctionDef(self, node):
            if node.name == "__init__":
                return  # IGNORA __init__
            
            # Extrai assinatura da função (com valores padrão)
            params = []
            defaults = []
            
            for arg in node.args.args:
                params.append(arg.arg)
            
            if hasattr(ast, 'unparse'):
                defaults = [ast.unparse(d) for d in node.args.defaults]
            
            if defaults:
                params_com_default = params.copy()
                for i, d in enumerate(defaults):
                    idx = len(params) - len(defaults) + i
                    if 0 <= idx < len(params):
                        params_com_default[idx] = f"{params[idx]}={d}"
                assinatura = f"{node.name}({', '.join(params_com_default)})"
            else:
                assinatura = f"{node.name}({', '.join(params)})"
            
            self.funcoes.append(assinatura)
            
            self._escopo_atual.append(node.name)
            self.generic_visit(node)
            self._escopo_atual.pop()

    extrator = Extrator()
    extrator.visit(arvore)
    
    # Converte globais para formato legível
    globais_formatadas = []
    for nome, valor, tipo in extrator.globais:
        globais_formatadas.append((f"{nome} = {valor}", tipo))
    
    return {
        "globais": globais_formatadas,
        "funcoes": extrator.funcoes
    }

def is_legacy(caminho):
    return "legacy" in caminho.lower()

# --- MAIN ---
if __name__ == "__main__":
    linhas_csv = []
    linhas_csv.append(["Pasta", "Arquivo", "Tipo", "Declaração"])

    for pasta in PASTAS_ALVO:
        caminho_pasta = os.path.join(BASE_DIR, pasta)
        if not os.path.exists(caminho_pasta):
            print(f"⚠️ Pasta não encontrada: {caminho_pasta}")
            continue

        for raiz, dirs, arquivos in os.walk(caminho_pasta):
            dirs[:] = [d for d in dirs if not is_legacy(d)]
            
            for arquivo in arquivos:
                if not arquivo.endswith(".py") or is_legacy(arquivo):
                    continue
                
                caminho_completo = os.path.join(raiz, arquivo)
                relativo = os.path.relpath(caminho_completo, BASE_DIR)
                
                dados = extrair_declaracoes(caminho_completo)
                if "erro" in dados:
                    continue
                
                # Adiciona variáveis globais (já vêm com a classificação)
                for declaracao, tipo in dados["globais"]:
                    linhas_csv.append([pasta, relativo, tipo, declaracao])
                
                # Adiciona funções
                for item in dados["funcoes"]:
                    linhas_csv.append([pasta, relativo, "Funcao", f"def {item}"])

    # --- SALVA CSV ---
    with open("catalogo_estruturado.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=",")
        writer.writerows(linhas_csv)
    print("✅ CSV salvo em 'catalogo_estruturado.csv'")

    # --- SALVA TSV ---
    with open("catalogo_estruturado.tsv", "w", encoding="utf-8") as f:
        for linha in linhas_csv:
            f.write("\t".join(linha) + "\n")
    print("✅ TSV salvo em 'catalogo_estruturado.tsv'")

    # --- EXIBE TABELA MARKDOWN NO TERMINAL ---
    print("\n" + "="*100)
    print("📋 CATÁLOGO DE PARÂMETROS (NUMÉRICOS vs CONFIGURAÇÕES)")
    print("="*100)
    
    print("| Pasta | Arquivo | Tipo | Declaração |")
    print("|-------|---------|------|------------|")
    
    for linha in linhas_csv[1:]:  # Pula cabeçalho
        linha_escapada = [str(celula).replace("|", "\\|") for celula in linha]
        print(f"| {' | '.join(linha_escapada)} |")

    print("\n" + "="*100)
    
    # Conta quantos de cada
    total = len(linhas_csv) - 1
    num_numericos = sum(1 for linha in linhas_csv[1:] if "Numeric" in linha[2])
    num_configs = sum(1 for linha in linhas_csv[1:] if "Config" in linha[2])
    num_funcoes = sum(1 for linha in linhas_csv[1:] if linha[2] == "Funcao")
    
    print(f"✅ Total de declarações: {total}")
    print(f"   🔢 Numéricas (hiperparâmetros): {num_numericos}")
    print(f"   ⚙️  Configurações (strings/paths/listas): {num_configs}")
    print(f"   🔧 Funções (assinaturas): {num_funcoes}")
    print("="*100)