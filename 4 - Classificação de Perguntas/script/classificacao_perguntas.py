import sys
from pathlib import Path

# Obtém o caminho absoluto da pasta do script atual.
# Exemplo: 'C:\...\Buscar_Web\1- WebScrapping\script'
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
# Exemplo: 'C:\...\Buscar_Web'
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' deve funcionar.
from config import DIRETORIO_DADOS_CLASSIFICACAO,DIRETORIO_DADOS_UNIFICACAO 


import pandas as pd
import re

# Define o caminho do arquivo unificado de perguntas
caminho_arquivo = DIRETORIO_DADOS_UNIFICACAO/ 'perguntas_combinadas_final.csv'

# Carrega o arquivo CSV em um DataFrame do pandas
try:
    df = pd.read_csv(caminho_arquivo)
    print("Arquivo de perguntas carregado com sucesso.")
except FileNotFoundError:
    print(f"Erro: O arquivo '{caminho_arquivo}' não foi encontrado.")
    exit()

# --- 1. Definir as palavras-chave para cada categoria (Expandida e com Negadores) ---

# Palavras-chave para a categoria 'Problema'
palavras_problema = [
    # Erros, falhas e mau funcionamento (Português)
    'erro', 'bug', 'falha', 'falhou', 'caiu', 'caindo', 'travou', 'travando', 'tela azul', 'congelou', 'congelando',
    'reiniciando', 'reinicia', 'não liga', 'não inicia', 'não carrega', 'não reconhece', 'corrompido', 'danificado',
    'quebrou', 'quebrado', 'parou', 'parando', 'fechando sozinho', 'sem sinal', 'sem imagem', 'não aparece',
    'lento', 'travando', 'engasgando', 'atraso', 'baixo fps', 'gargalo', 'gargalando', 'esquentando', 'superaquecimento',
    'estranho', 'bip', 'desliga', 'instável', 'conflito', 'defeito', 'defeituoso', 'artefatos', 'barulho', 'ruído',
    'chiado', 'zumbido', 'mau contato', 'sumiu', 'desapareceu', 'vazamento', 'trojan', 'vírus', 'malware', 'crash',
    'driver', 'sem som', 'sem áudio', 'sem video', 'está lento', 'não conecta', 'desconecta', 'cai a internet',
    'tela preta', 'tela piscando', 'artefato', 'congelada', 'não está funcionando', 'não abre', 'não reconhecendo',
    'falhas', 'danos', 'travamento', 'congelamento', 'lenteza', 'lentidão', 'desempenho', 'queda', 'caiu o fps',
    'tela congelada', 'código de erro', 'falha crítica', 'problemas', 'com problema', 'dando erro', 'não está ligando',
    'está desligando', 'fica preto', 'problema com', 'está corrompido', 'bugando', 'falhando', 'não está carregando',
    'não está detectando', 'mal funcionamento', 'tombou', 'caiu no chão', 'molhou', 'queimou', 'danificou', 'estragou',
    'pifou', 'deu pau', 'buguei', 'travou', 'parou', 'não detecta', 'não segura carga', 'drenando', 'sem carga',
    'não dá vídeo', 'não dá sinal', 'não liga', 'liga e desliga', 'liga sozinho', 'não está subindo', 'tela azul da morte',
    
    # Erros, falhas e mau funcionamento (Inglês)
    'error', 'bug', 'failure', 'failed', 'crashed', 'crashing', 'freezing', 'frozen', 'blue screen', 'bsod',
    'restarting', 'restarts', 'won\'t turn on', 'won\'t start', 'won\'t boot', 'won\'t charge', 'not charging',
    'corrupted', 'damaged', 'broken', 'busted', 'stopped working', 'won\'t stop', 'shutting down', 'no signal',
    'no image', 'missing', 'slow', 'stuttering', 'lag', 'lagging', 'low fps', 'bottleneck', 'bottlenecking',
    'overheating', 'overheating', 'throttling', 'artifacts', 'artifacts', 'noise', 'bizarre noise', 'beeping', 'shuts off',
    'unstable', 'conflict', 'defect', 'defective', 'glitching', 'glitch', 'not detected', 'no sound', 'no audio',
    'no video', 'black screen', 'flickering screen', 'freezing', 'won\'t turn on', 'wont turn on', 'won\'t open',
    'not recognizing', 'malfunction', 'dropped', 'got wet', 'spilled on', 'burnt', 'damaged', 'broke', 'not holding charge',
    'draining', 'no charge', 'no video', 'no display', 'turns on and off', 'turns on by itself', 'won\'t post',
    'dead', 'corrupted', 'unresponsive', 'no power', 'power loss', 'power issue', 'random shutdown', 'random restart'
]

# Palavras-chave para a categoria 'Upgrade/Compra'
palavras_upgrade_compra = [
    # Compra e upgrade (Português)
    'novo', 'comprar', 'compra', 'vendendo', 'venda', 'vender', 'venderia', 'vale a pena', 'compensa', 'preço', 'valor',
    'custo-benefício', 'barato', 'caro', 'promoção', 'black friday', 'oferta', 'desconto', 'upgrade', 'melhorar',
    'melhor', 'trocar', 'substituir', 'modernizar', 'montar', 'construir', 'planejar', 'futuro', 'pronta entrega',
    'customizado', 'personalizado', 'potente', 'potência', 'desempenho', 'desconto', 'orçamento', 'ajuda', 'ajuda para',
    'recomendação', 'recomendar', 'sugerir', 'sugestão', 'qual', 'qual escolher', 'qual pegar', 'opiniões', 'review',
    'comparação', 'comparar', 'vs', 'versus', 'preciso de um', 'quero um', 'qual é o', 'qual comprar',
    'qual é o melhor', 'indicação', 'indicar', 'proposta', 'negociar', 'vendo', 'procuro', 'procurando', 'gostaria de',
    'quero comprar', 'pensando em', 'dúvida', 'investir', 'investimento', 'ideal para', 'para jogos', 'para trabalho',
    'para faculdade', 'para uso', 'qual a melhor', 'melhores', 'nova', 'nova placa', 'novo processador', 'memória',
    'fonte', 'gabinete', 'pc gamer', 'pc de trabalho', 'notebook gamer', 'notebook', 'desktop', 'computador',
    
    # Compra e upgrade (Inglês)
    'new', 'buy', 'buying', 'selling', 'sell', 'worth it', 'is it worth', 'is it a good deal', 'price', 'value', 'cost-benefit',
    'cheap', 'expensive', 'sale', 'discount', 'upgrade', 'upgrading', 'upgrades', 'improve', 'better', 'replace',
    'build', 'building', 'planning', 'future-proof', 'custom build', 'powerful', 'performance', 'budget', 'help me choose',
    'recommendation', 'recommend', 'suggest', 'suggestion', 'which', 'which one', 'which is better', 'opinions', 'review',
    'comparison', 'compare', 'vs', 'versus', 'looking for', 'need advice', 'need help', 'want to buy', 'thinking about',
    'invest', 'investment', 'ideal for', 'for gaming', 'for work', 'for school', 'for college', 'what\'s the best',
    'best', 'best one', 'new gpu', 'new cpu', 'new motherboard', 'new ram', 'new ssd', 'new hdd', 'new psu', 'new case',
    'pc', 'gaming pc', 'workstation', 'gaming laptop', 'laptop', 'desktop', 'computer', 'gpu', 'cpu', 'ram', 'ssd', 'hdd',
    'psu', 'motherboard', 'case', 'cooler', 'monitor'
]

# --- Palavras de negação que podem anular o rótulo de "Problema" ---
palavras_negacao = [
    'não', 'sem', 'nenhum', 'nenhuma', 'sempre', 'nunca', 'evitei', 'não tive', 'no', 'without', 'not'
]

# --- 2. Função de classificação com lógica de contagem mais robusta ---
def classificar_post_robusto(titulo, conteudo):
    texto_completo = str(titulo).lower() + " " + str(conteudo).lower()
    
    # Inicia a contagem para cada categoria
    problema_count = 0
    upgrade_compra_count = 0
    
    # Usamos re.findall para encontrar todas as ocorrências de palavras inteiras
    # e uma janela de contexto para verificar negações.
    
    # Conta as ocorrências de palavras-chave de "Problema" e verifica negações
    for palavra in palavras_problema:
        matches = re.findall(r'\b' + re.escape(palavra) + r'\b', texto_completo)
        
        # Se encontrou a palavra, vamos verificar o contexto
        if matches:
            for match in re.finditer(r'\b' + re.escape(palavra) + r'\b', texto_completo):
                # Define uma janela de contexto antes da palavra
                contexto_antes = texto_completo[max(0, match.start() - 20):match.start()]
                
                # Verifica se há uma palavra de negação no contexto
                is_negated = any(negacao in contexto_antes.split() for negacao in palavras_negacao)
                
                # Adiciona ou subtrai da contagem com base na negação
                if is_negated:
                    problema_count -= 1
                else:
                    problema_count += 1
    
    # Conta as ocorrências de palavras-chave de "Upgrade/Compra"
    for palavra in palavras_upgrade_compra:
        upgrade_compra_count += len(re.findall(r'\b' + re.escape(palavra) + r'\b', texto_completo))
    
    # Garantir que a contagem não seja negativa
    problema_count = max(0, problema_count)

    # --- Lógica de decisão baseada em contagem e um limiar de certeza ---
    total_palavras_encontradas = problema_count + upgrade_compra_count
    
    # Limiar para considerar uma classificação como válida
    limiar_confianca = 2 

    if total_palavras_encontradas < limiar_confianca:
        return "Nenhum"
    elif problema_count > upgrade_compra_count:
        return "Problema"
    elif upgrade_compra_count > problema_count:
        return "Upgrade/Compra"
    else:
        # Retorna a categoria geral em caso de empate
        return "Problema"

# --- 3. Aplicar a classificação ao DataFrame ---

print("Classificando os posts usando a lógica de contagem robusta...")

df['Tipo_de_Post_Contagem'] = df.apply(
    lambda row: classificar_post_robusto(row['Titulo_Post'], row['Conteudo_Post']),
    axis=1
)

# --- 4. Salvar o arquivo de saída ---

caminho_saida = DIRETORIO_DADOS_CLASSIFICACAO/ 'perguntas_Classificadas_Contagem_final.csv'
df.to_csv(caminho_saida, index=False, encoding='utf-8')

print("\nProcesso concluído!")
print(f"O arquivo com os posts classificados foi salvo em: '{caminho_saida}'")
print("\nPrimeiras 5 linhas do DataFrame classificado:")
print(df.head())