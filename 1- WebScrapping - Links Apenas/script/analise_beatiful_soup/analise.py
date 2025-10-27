import requests
from bs4 import BeautifulSoup

url_ingles = "https://www.dell.com/community/en/categories/dell-community"

print(f"Fazendo requisição GET para: {url_ingles}")

# 1. Faz a requisição HTTP. O conteúdo retornado é o HTML estático inicial.
try:
    response = requests.get(url_ingles, timeout=10)
    response.raise_for_status() # Verifica se a requisição foi bem-sucedida
    
    # 2. Cria o objeto BeautifulSoup para análise
    soup = BeautifulSoup(response.text, 'html.parser')
    print("HTML analisado com sucesso.")

    # 3. Focando na análise de TODOS os elementos <input>
    inputs_encontrados = soup.find_all('input')

    print("\n" + "="*50)
    print(f"ANÁLISE DETALHADA DE TODOS OS {len(inputs_encontrados)} ELEMENTOS <input>")
    print("="*50)

    if inputs_encontrados:
        for i, input_tag in enumerate(inputs_encontrados):
            print(f"\n--- INPUT ELEMENTO {i+1} / {len(inputs_encontrados)} ---")
            
            # Imprime o HTML formatado (prettify)
            print(input_tag.prettify())
            
            # Detalha atributos importantes
            print("-" * 40)
            print(f"ID: {input_tag.get('id', 'N/A')}")
            print(f"Name: {input_tag.get('name', 'N/A')}")
            print(f"Type: {input_tag.get('type', 'N/A')}")
            print(f"Placeholder: {input_tag.get('placeholder', 'N/A')}")
            print(f"Aria-label: {input_tag.get('aria-label', 'N/A')}")
            print(f"Classes: {input_tag.get('class', 'N/A')}")
            
            # Verifica se é o campo de busca principal
            if 'search-input__input' in input_tag.get('class', []):
                 print("\n>>> ESTE É O CAMPO DE BUSCA PRINCIPAL (CONFIRMADO) <<<")
    else:
        print("Nenhum elemento <input> foi encontrado no HTML estático inicial.")
        
    print("\n" + "="*50)
    print("FIM DA ANÁLISE")
    print("="*50)

except requests.exceptions.RequestException as e:
    print(f"Erro ao fazer a requisição HTTP: {e}")