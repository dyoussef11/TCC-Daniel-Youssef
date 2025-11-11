
from langdetect import detect, DetectorFactory
import sys
from pathlib import Path
import pandas as pd
import torch
import re
from transformers import pipeline
from transformers import XLMRobertaTokenizer, XLMRobertaForSequenceClassification
import numpy as np
import time
from collections import defaultdict

# --- Configuração de Caminhos ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_MODELO_ZERO_SHOT, DIRETORIO_DADOS_LIMPEZA_DATASETS

caminho_entrada_resposta_pt_br = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_pt.csv'
caminho_entrada_resposta_en = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_en.csv'

caminho_saida_resposta_pt_br = DIRETORIO_DADOS_MODELO_ZERO_SHOT / 'dataset_rotulado_respostas_pt_br.csv'
caminho_saida_resposta_en = DIRETORIO_DADOS_MODELO_ZERO_SHOT / 'dataset_rotulado_respostas_en.csv'

# --- Configuração de Dispositivo GPU/CPU ---
if torch.cuda.is_available():
    DEVICE = 0
    print("GPU (CUDA) detectada e será utilizada.")
    # Limpa cache da GPU antes de começar
    torch.cuda.empty_cache()
else:
    DEVICE = -1
    print("GPU não detectada. Utilizando a CPU.")

def processar_lotes_massivo(textos, classifier, labels, hypothesis_template, batch_size=4):
    """Processamento em lotes com fallback automático"""
    resultados = []
    total_textos = len(textos)
    
    for i in range(0, total_textos, batch_size):
        batch_textos = textos[i:i + batch_size]
        
        # Mostra progresso a cada 100 batches
        if i % (batch_size * 100) == 0 and i > 0:
            print(f"Processados {i}/{total_textos} blocos ({i/total_textos*100:.1f}%)")
        
        try:
            batch_results = classifier(
                batch_textos,
                labels,
                multi_label=False,
                hypothesis_template=hypothesis_template
            )
            
            if not isinstance(batch_results, list):
                batch_results = [batch_results]
                
            resultados.extend(batch_results)
            
        except torch.cuda.OutOfMemoryError:
            print(f"⚠️  OutOfMemory no batch {i}. Reduzindo batch_size...")
            # Processa um por um
            for texto in batch_textos:
                try:
                    result = classifier(
                        [texto],
                        labels,
                        multi_label=False,
                        hypothesis_template=hypothesis_template
                    )
                    resultados.extend(result if isinstance(result, list) else [result])
                except Exception as e:
                    print(f"❌ Erro no texto individual: {e}")
                    # Resultado fallback
                    resultados.append({"labels": [labels[0]], "scores": [0.1]})
        
        except Exception as e:
            print(f"❌ Erro no batch {i}: {e}")
            # Fallback para batch individual
            for texto in batch_textos:
                try:
                    result = classifier(
                        [texto],
                        labels,
                        multi_label=False,
                        hypothesis_template=hypothesis_template
                    )
                    resultados.extend(result if isinstance(result, list) else [result])
                except:
                    resultados.append({"labels": [labels[0]], "scores": [0.1]})
    
    return resultados

def dividir_texto_eficiente(texto, tamanho_max=500):  # Aumentado para menos divisões
    """Versão ultra eficiente - minimiza divisões"""
    if not isinstance(texto, str) or len(texto.strip()) == 0:
        return []
    
    texto = texto.strip()
    if len(texto) <= tamanho_max:
        return [texto]
    
    # Divisão apenas se absolutamente necessário
    sentences = re.split(r'[.!?]+', texto)
    blocos = []
    bloco_atual = ""
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        if len(bloco_atual) + len(sentence) + 1 <= tamanho_max:
            bloco_atual = bloco_atual + " " + sentence if bloco_atual else sentence
        else:
            if bloco_atual:
                blocos.append(bloco_atual)
            bloco_atual = sentence
            # Se uma única frase for muito longa, força divisão
            if len(bloco_atual) > tamanho_max:
                # Divisão por palavras
                palavras = bloco_atual.split()
                sub_bloco = ""
                for palavra in palavras:
                    if len(sub_bloco) + len(palavra) + 1 <= tamanho_max:
                        sub_bloco = sub_bloco + " " + palavra if sub_bloco else palavra
                    else:
                        if sub_bloco:
                            blocos.append(sub_bloco)
                        sub_bloco = palavra
                if sub_bloco:
                    bloco_atual = sub_bloco
                else:
                    bloco_atual = ""
    
    if bloco_atual:
        blocos.append(bloco_atual)
    
    return blocos

def processar_em_lotes_eficiente(textos, classifier, labels, hypothesis_template, batch_size=8):
    """Processa múltiplos textos de uma vez em lotes"""
    todos_resultados = []
    
    for i in range(0, len(textos), batch_size):
        batch_textos = textos[i:i + batch_size]
        
        try:
            batch_results = classifier(
                batch_textos,
                labels,
                multi_label=False,
                hypothesis_template=hypothesis_template
            )
            
            # Garante que seja uma lista
            if not isinstance(batch_results, list):
                batch_results = [batch_results]
                
            todos_resultados.extend(batch_results)
            
        except torch.cuda.OutOfMemoryError:
            # Reduz batch size se estourar memória
            print(f"OutOfMemoryError: Reduzindo batch size para {batch_size//2}")
            if batch_size > 1:
                # Processa metade do batch
                mid = len(batch_textos) // 2
                results1 = processar_em_lotes_eficiente(
                    batch_textos[:mid], classifier, labels, hypothesis_template, batch_size//2
                )
                results2 = processar_em_lotes_eficiente(
                    batch_textos[mid:], classifier, labels, hypothesis_template, batch_size//2
                )
                todos_resultados.extend(results1)
                todos_resultados.extend(results2)
            else:
                # Processa um por um como fallback
                for texto in batch_textos:
                    try:
                        result = classifier(
                            texto,
                            labels,
                            multi_label=False,
                            hypothesis_template=hypothesis_template
                        )
                        todos_resultados.append(result)
                    except Exception as e:
                        print(f"Erro ao processar texto individual: {e}")
                        # Resultado dummy para manter o formato
                        todos_resultados.append({"labels": [labels[0]], "scores": [0.0]})
    
    return todos_resultados

def processar_dataset_completo(df, classifier, labels, hypothesis_template, nome_dataset):
    """Processa todo o dataset de forma otimizada"""
    print(f"Processando {nome_dataset}...")
    
    # Pré-processamento
    textos = df["Conteudo_Comentario_Limpo"].dropna().tolist()
    print(f"Total de textos para processar: {len(textos)}")
    
    resultados = []
    textos_para_processar = []
    textos_originais = []
    
    # Prepara todos os blocos para processamento em lote
    for i, texto in enumerate(textos):
        if not isinstance(texto, str) or not texto.strip():
            continue
            
        blocos = dividir_texto_eficiente(texto)
        
        for bloco in blocos:
            textos_para_processar.append(bloco)
            textos_originais.append(texto)
        
        # Progresso a cada 100 textos
        if (i + 1) % 100 == 0:
            print(f"Pré-processados {i + 1}/{len(textos)} textos...")
    
    print(f"Total de blocos para classificar: {len(textos_para_processar)}")
    
    # Processa todos os blocos em lotes
    predicoes_blocos = processar_em_lotes_eficiente(
        textos_para_processar,
        classifier,
        labels,
        hypothesis_template,
        batch_size=8  # Comece com 8, ajuste conforme necessidade
    )
    
    # Agrupa resultados por texto original
    from collections import defaultdict
    resultados_por_texto = defaultdict(list)
    
    for texto_original, predicao in zip(textos_originais, predicoes_blocos):
        resultados_por_texto[texto_original].append({
            'label': predicao['labels'][0],
            'score': predicao['scores'][0]
        })
    
    # Combina resultados para cada texto
    for texto_original, preds in resultados_por_texto.items():
        if not preds:
            continue
            
        # Encontra o label mais comum
        labels_list = [p['label'] for p in preds]
        label_final = max(set(labels_list), key=labels_list.count)
        
        # Calcula confiança média para o label vencedor
        scores_label = [p['score'] for p in preds if p['label'] == label_final]
        confianca_final = sum(scores_label) / len(scores_label)
        
        resultados.append({
            "Conteudo_Comentario_Limpo": texto_original,
            "label_predito": label_final,
            "confianca": round(confianca_final, 3),
            "num_blocos": len(preds)
        })
    
    print(f"Processamento de {nome_dataset} concluído. {len(resultados)} textos classificados.")
    return pd.DataFrame(resultados)

# ----------------- PARTE 1: PORTUGUÊS -----------------
print("=" * 50)
print("INICIANDO PROCESSAMENTO EM PORTUGUÊS")
print("=" * 50)

# Carrega os dados
df_pt_br = pd.read_csv(caminho_entrada_resposta_pt_br)
df_pt_br_no_dupl = df_pt_br.drop_duplicates(subset=['Conteudo_Comentario_Limpo'])
print(f"Dataset PT-BR carregado: {len(df_pt_br_no_dupl)} textos únicos")

# Configura o classifier para português
classifier_pt = pipeline(
    "zero-shot-classification",
    model="joeddav/xlm-roberta-large-xnli",
    device=DEVICE,
    batch_size=8,  # Batch size para inferência
    truncation=True
)

labels_pt_genericos = [
    "PROPOSTA DE SOLUÇÃO/AÇÃO",
    "DIAGNÓSTICO DE PROBLEMA TÉCNICO",
    "INFORMAÇÃO DE CONTEXTO/TUTORIAL",
    "PERGUNTA/DUVIDA SOBRE COMPATIBILIDADE",
    "COMENTÁRIO INVÁLIDO/PLACEHOLDER",
    "COMENTÁRIO DE OPINIÃO/DESABAFO",
    "MENSAGEM NÃO RELACIONADA AO TEMA",
    "FECHAMENTO DE TÓPICO/STATUS DE RESOLUÇÃO"
]

# Processa o dataset completo
df_resultado_pt = processar_dataset_completo(
    df_pt_br_no_dupl,
    classifier_pt,
    labels_pt_genericos,
    "O conteúdo desta resposta é melhor descrito como uma {}.",
    "Português"
)

# Salva resultados
df_resultado_pt.to_csv(caminho_saida_resposta_pt_br, index=False)
print(f"Resultados PT-BR salvos em: {caminho_saida_resposta_pt_br}")

# Limpa memória da GPU
if torch.cuda.is_available():
    torch.cuda.empty_cache()

# ----------------- PROCESSAMENTO ACELERADO PARA INGLÊS -----------------
print("🚀 INICIANDO PROCESSAMENTO ULTRA ACELERADO - INGLÊS")
print("=" * 60)

# 1. Carrega AMOSTRA para teste rápido
df_en = pd.read_csv(caminho_entrada_resposta_en)
df_en_no_dupl = df_en.drop_duplicates(subset=['Conteudo_Comentario_Limpo'])

# ⚡ AMOSTRAGEM TEMPORÁRIA
df_en_no_dupl = df_en_no_dupl.head(1000)
print(f"🔬 MODO TESTE: Processando apenas 1000 textos de {len(df_en)} totais")

# 2. Modelo ALTERNATIVO que funciona com PyTorch antigo
# Escolha UM destes modelos (teste na ordem):

modelos_para_tentar = [
    "facebook/bart-large-mnli",  # Seu modelo original
    "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",  # Multilíngue rápido
    "cross-encoder/nli-deberta-v3-base",  # Modelo eficiente
    "typeform/distilbert-base-uncased-mnli"  # Modelo leve
]

# Tenta carregar o pipeline com diferentes modelos
classifier_en = None
for modelo in modelos_para_tentar:
    try:
        print(f"🔄 Tentando carregar modelo: {modelo}")
        classifier_en = pipeline(
            "zero-shot-classification",
            model=modelo,
            device=DEVICE,
            batch_size=4,  # Comece conservador
            truncation=True,
            max_length=256
        )
        print(f"✅ Modelo {modelo} carregado com sucesso!")
        break
    except Exception as e:
        print(f"❌ Falha ao carregar {modelo}: {e}")
        continue

if classifier_en is None:
    # Fallback: use o modelo que já funcionou antes
    print("🔄 Usando fallback: facebook/bart-large-mnli com configuração mínima")
    classifier_en = pipeline(
        "zero-shot-classification",
        model="facebook/bart-large-mnli",
        device=DEVICE,
        batch_size=2,  # Batch menor para evitar problemas
        truncation=True
    )

labels_en_genericos = [
    "SOLUTION/ACTION PROPOSALL",
    "TECHNICAL PROBLEM DIAGNOSIS",
    "CONTEXTUAL INFORMATION/TUTORIAL",
    "COMPATIBILITY QUESTION/QUERY", 
    "INVALID COMMENT/PLACEHOLDER",
    "OPINION/VENTING COMMENT",
    "OFF-TOPIC MESSAGE/IRRELEVANT MESSAGE",
    "TOPIC CLOSURE/RESOLUTION STATUS"
]

# 3. Pré-processamento RÁPIDO
print("📋 Pré-processando textos...")
textos = df_en_no_dupl["Conteudo_Comentario_Limpo"].dropna().tolist()
print(f"📊 Total de textos: {len(textos)}")

textos_para_processar = []
textos_originais = []
blocos_por_texto = []

start_time = time.time()

for i, texto in enumerate(textos):
    if not isinstance(texto, str) or not texto.strip():
        continue
        
    blocos = dividir_texto_eficiente(texto, 500)
    
    for bloco in blocos:
        textos_para_processar.append(bloco)
        textos_originais.append(texto)
    
    blocos_por_texto.append(len(blocos))
    
    if (i + 1) % 500 == 0:
        elapsed = time.time() - start_time
        print(f"⚡ Pré-processados {i + 1}/{len(textos)} textos em {elapsed:.1f}s")

print(f"🎯 Total de blocos para classificar: {len(textos_para_processar)}")
print(f"📈 Média de blocos por texto: {np.mean(blocos_por_texto):.1f}")

# 4. Processamento em Lotes
print("🧠 Iniciando classificação em lotes...")
classification_start = time.time()

predicoes_blocos = processar_lotes_massivo(
    textos_para_processar,
    classifier_en,
    labels_en_genericos,
    "The content of this response is best described as a {}.",
    batch_size=4  # Comece com 4, aumente se funcionar
)

classification_time = time.time() - classification_start
print(f"⏱️  Tempo de classificação: {classification_time:.1f} segundos")
if classification_time > 0:
    print(f"🚀 Velocidade: {len(textos_para_processar)/classification_time:.1f} blocos/segundo")

# 5. Combinação dos resultados
print("🔄 Combinando resultados...")

resultados_por_texto = defaultdict(list)
for texto_original, predicao in zip(textos_originais, predicoes_blocos):
    resultados_por_texto[texto_original].append({
        'label': predicao['labels'][0],
        'score': predicao['scores'][0]
    })

resultados_finais = []
for texto_original, preds in resultados_por_texto.items():
    if not preds:
        continue
        
    labels_list = [p['label'] for p in preds]
    label_final = max(set(labels_list), key=labels_list.count)
    
    scores_label = [p['score'] for p in preds if p['label'] == label_final]
    confianca_final = sum(scores_label) / len(scores_label)
    
    resultados_finais.append({
        "Conteudo_Comentario_Limpo": texto_original,
        "label_predito": label_final,
        "confianca": round(confianca_final, 3),
        "num_blocos": len(preds)
    })

# 6. Salva resultados
df_resultado = pd.DataFrame(resultados_finais)
df_resultado.to_csv(caminho_saida_resposta_en, index=False)

total_time = time.time() - start_time
print(f"\n✅ PROCESSAMENTO CONCLUÍDO!")
print(f"⏰ Tempo total: {total_time:.1f} segundos")
print(f"📈 Textos processados: {len(resultados_finais)}")
print(f"💾 Resultados salvos em: {caminho_saida_resposta_en}")

# Estatísticas
if len(resultados_finais) > 0:
    confiancas = [r['confianca'] for r in resultados_finais]
    print(f"🎯 Confiança média: {np.mean(confiancas):.3f}")
    print(f"📊 Distribuição de labels:")
    labels_count = df_resultado['label_predito'].value_counts()
    for label, count in labels_count.items():
        print(f"   {label}: {count} textos")