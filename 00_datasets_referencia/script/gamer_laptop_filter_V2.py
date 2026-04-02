import sys
import pandas as pd
import logging
from pathlib import Path

# Supondo que as importações do seu projeto continuem as mesmas
from core.paths import DATASET_FINAL_CSV

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class FiltradorGamer:
    """
    Classe responsável por filtrar e segmentar o dataset principal.
    Focada em isolar notebooks da categoria 'gamer' e remover duplicatas.
    """
    def __init__(self, caminho_input: Path, caminho_output: Path):
        self.caminho_input = caminho_input
        self.caminho_output = caminho_output

    def executar_filtro(self):
        """Lê o dataset unificado, filtra categoria gamer, normaliza e remove duplicatas."""
        try:
            if not self.caminho_input.exists():
                logger.error(f"Arquivo de entrada não encontrado: {self.caminho_input}")
                return

            # 1. Carregar o dataset completo
            logger.info("Carregando dataset unificado...")
            df = pd.read_csv(self.caminho_input)

            # 2. Aplicar o filtro de categoria
            logger.info("Filtrando notebooks da categoria 'gamer'...")
            df_gamer = df[df['categoria'] == 'gamer'].copy()

            # 3. Normalizar a coluna modelo_limpo para minúsculo
            if 'modelo_limpo' in df_gamer.columns:
                logger.info("Convertendo 'modelo_limpo' para minúsculo...")
                df_gamer['modelo_limpo'] = df_gamer['modelo_limpo'].str.lower()
            else:
                logger.warning("Coluna 'modelo_limpo' não encontrada para conversão.")

            # 4. REMOVER DUPLICATAS
            # Aqui removemos linhas onde TODOS os valores são idênticos. 
            # Se quiser remover baseado em colunas específicas (ex: id_unico), 
            # use df_gamer.drop_duplicates(subset=['id_unico'], keep='first')
            total_antes_dups = len(df_gamer)
            df_gamer = df_gamer.drop_duplicates()
            total_depois_dups = len(df_gamer)
            
            if total_antes_dups > total_depois_dups:
                logger.info(f"♻️ Removidas {total_antes_dups - total_depois_dups} duplicatas.")

            # 5. Salvar o resultado
            if not df_gamer.empty:
                self.caminho_output.parent.mkdir(parents=True, exist_ok=True)
                df_gamer.to_csv(self.caminho_output, index=False)
                
                logger.info("=" * 30)
                logger.info(f"✅ Filtro, normalização e limpeza concluídos!")
                logger.info(f"📊 Total Original: {len(df)}")
                logger.info(f"🔥 Total Gamer (Únicos): {len(df_gamer)}")
                logger.info(f"💾 Salvo em: {self.caminho_output}")
            else:
                logger.warning("Nenhum notebook 'gamer' foi encontrado no dataset.")

        except Exception as e:
            logger.error(f"Erro ao filtrar dados: {e}")

# ==================== EXECUÇÃO ====================

if __name__ == "__main__":
    # Caminhos baseados na estrutura do projeto
    INPUT = DATASET_FINAL_CSV / "dataset_laptops_UNICOS_V3.csv"
    OUTPUT = DATASET_FINAL_CSV / "dataset_laptops_GAMER_ONLY_V2.csv"

    # Instancia a classe e executa a ação
    filtrador = FiltradorGamer(INPUT, OUTPUT)
    filtrador.executar_filtro()