import spacy
from spacy.language import Language
from spacy.pipeline import EntityRuler

# --- CONFIGURAÇÃO E INSTALAÇÃO ---
# Para rodar este código, você precisa instalar o spaCy e o modelo em português:
# pip install spacy
# python -m spacy download pt_core_news_sm

def setup_hardware_pipeline():
    """
    Configura o pipeline de NLP combinando o modelo estatístico (PT)
    com regras rígidas para hardware (EntityRuler).
    """
    print("🔄 Carregando modelo base em Português...")
    
    # 1. Carrega o modelo pequeno de português (sabe o que é verbo, substantivo, etc.)
    try:
        nlp = spacy.load("pt_core_news_sm")
    except OSError:
        print("❌ Erro: Modelo não encontrado. Rode: python -m spacy download pt_core_news_sm")
        return None

    # 2. Adiciona o EntityRuler (O "Especialista" de Hardware)
    # Colocamos 'before="ner"' para que nossas regras ganhem do modelo padrão.
    # Se o modelo achar que "3080" é um número, nossa regra dirá que é HARDWARE antes.
    ruler = nlp.add_pipe("entity_ruler", before="ner")

    # 3. Definindo os Padrões (Patterns)
    # Aqui é onde "ensinamos" o vocabulário do fórum para a IA.
    patterns = [
        # --- HARDWARE (GPUs e CPUs) ---
        # Ex: "RTX 3080", "GTX 1060", "Ryzen 5"
        {"label": "HARDWARE", "pattern": [{"LOWER": "rtx"}, {"SHAPE": "dddd"}]}, 
        {"label": "HARDWARE", "pattern": [{"LOWER": "rtx"}, {"SHAPE": "dddd"}, {"LOWER": "ti"}]},
        {"label": "HARDWARE", "pattern": [{"LOWER": "gtx"}, {"SHAPE": "dddd"}]},
        {"label": "HARDWARE", "pattern": [{"LOWER": "ryzen"}, {"SHAPE": "d"}]},
        {"label": "HARDWARE", "pattern": [{"LOWER": "i9"}, {"SHAPE": "ddddk"}]}, # Ex: i9 9900k

        # --- VERSÕES DE DRIVER ---
        # Ex: "531.18", "23.4.1", "v531"
        {"label": "DRIVER_VER", "pattern": [{"TEXT": {"REGEX": r"^\d{3}\.\d{2}$"}}]}, # 531.18
        {"label": "DRIVER_VER", "pattern": [{"LOWER": "v"}, {"TEXT": {"REGEX": r"^\d{3}$"}}]}, # v531
        
        # --- SINTOMAS ---
        # Ex: "tela azul", "coil whine", "crashou"
        {"label": "SYMPTOM", "pattern": [{"LOWER": "tela"}, {"LOWER": "azul"}]},
        {"label": "SYMPTOM", "pattern": [{"LOWER": "tela"}, {"LOWER": "preta"}]},
        {"label": "SYMPTOM", "pattern": [{"LOWER": "coil"}, {"LOWER": "whine"}]},
        {"label": "SYMPTOM", "pattern": [{"LOWER": "crashou"}]},
        {"label": "SYMPTOM", "pattern": [{"LOWER": "travando"}]},
    ]

    ruler.add_patterns(patterns)
    print("✅ Pipeline configurado com sucesso!")
    return nlp

def process_comment(nlp, text):
    """
    Processa um comentário e extrai as entidades estruturadas.
    """
    doc = nlp(text)
    
    results = {
        "texto_original": text,
        "entidades_detectadas": []
    }

    # Itera sobre as entidades encontradas
    for ent in doc.ents:
        results["entidades_detectadas"].append({
            "texto": ent.text,
            "categoria": ent.label_,
            "inicio": ent.start_char,
            "fim": ent.end_char
        })
        
    return results

# --- TESTE PRÁTICO ---

if __name__ == "__main__":
    nlp = setup_hardware_pipeline()
    
    if nlp:
        # Simulações de comentários reais do Adrenaline/Clube do Hardware
        comentarios_teste = [
            "Depois que instalei o 531.18, minha RTX 3080 começou a dar tela preta.",
            "Alguém com problemas no Ryzen 5 travando em jogos?",
            "A GTX 1060 não aguenta mais, vive dando crashou no driver antigo."
        ]

        print("\n--- RESULTADOS DA EXTRAÇÃO ---\n")
        
        for comentario in comentarios_teste:
            resultado = process_comment(nlp, comentario)
            
            # Print Bonito
            print(f"📝 Post: '{resultado['texto_original']}'")
            if not resultado['entidades_detectadas']:
                print("   ⚠️ Nenhuma entidade encontrada.")
            for ent in resultado['entidades_detectadas']:
                icon = "🔹"
                if ent['categoria'] == "HARDWARE": icon = "💻"
                if ent['categoria'] == "DRIVER_VER": icon = "💿"
                if ent['categoria'] == "SYMPTOM": icon = "🔥"
                
                print(f"   {icon} {ent['categoria']}: {ent['texto']}")
            print("-" * 50)