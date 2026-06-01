import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# 1. INICIALIZAÇÃO E CALIBRAÇÃO
analyzer = SentimentIntensityAnalyzer()

# Adicionamos pesos negativos para termos que o VADER original 
# pode considerar "neutros", mas que em hardware são críticos.
lexico_tecnico = {
    'stuttering': -3.0,
    'bottleneck': -2.5,
    'overheating': -3.5,
    'throttling': -3.0,
    'flickering': -2.5,
    'bsod': -4.0,
    'crash': -3.5,
    'freeze': -3.0,
    'drop': -1.5,
    'unacceptable': -3.0,
    'broken': -3.5
}
analyzer.lexicon.update(lexico_tecnico)

def simular_analise(texto, keyword, threshold=-0.15):
    # Simula a captura de contexto do seu script original (janela de 100 chars)
    match = re.search(rf'\b{re.escape(keyword)}\b', texto, re.IGNORECASE)
    if not match: return None
    
    start = max(0, match.start() - 100)
    end = min(len(texto), match.end() + 100)
    contexto = texto[start:end]
    
    scores = analyzer.polarity_scores(contexto)
    compound = scores['compound']
    
    # Lógica de decisão
    status = "🔴 PROBLEMA" if compound < threshold else "⚪ NEUTRO/SOLUÇÃO"
    
    return {
        "KW": keyword,
        "Score": compound,
        "Status": status,
        "Contexto": contexto.strip()
    }

# 2. CASOS DE TESTE (Exemplos do que existe nos seus 267M de caracteres)
testes = [
    ("My laptop is overheating and reaching 100C while gaming.", "overheating"),
    ("I solved the thermal throttling by applying a new repaste.", "thermal throttling"),
    ("The backlight bleed on this screen is terrible and distracting.", "backlight bleed"),
    ("You can fix the stuttering if you disable the overlay.", "stuttering"),
    ("Random bsod while watching youtube, help!", "bsod"),
    ("The battery health is 95%, which is normal for this age.", "battery health"),
    ("Massive fps drop during intense fights in Cyberpunk.", "fps drop")
]

# 3. EXECUÇÃO
print(f"{'KEYWORD':<18} | {'SCORE':<6} | {'STATUS':<12} | {'CONTEXTO EXTRATADO'}")
print("-" * 90)
for texto, kw in testes:
    res = simular_analise(texto, kw)
    if res:
        print(f"{res['KW']:<18} | {res['Score']:>6.2f} | {res['Status']:<12} | {res['Contexto'][:60]}...")