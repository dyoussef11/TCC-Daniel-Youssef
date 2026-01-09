import pandas as pd
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re


# ==================== ENUMS E CONFIGURAÇÕES ====================

class EstrategiaDeduplicacao(Enum):
    """Estratégias disponíveis para desduplicação"""
    PRIMEIRO = "first"
    ULTIMO = "last"
    MAIS_COMPLETO = "most_complete"
    MAIS_RECENTE = "most_recent"
    MELHOR_ESPECIFICACAO = "best_spec"


@dataclass
class ConfiguracaoDeduplicacao:
    """Configuração centralizada para o processo de desduplicação"""
    
    # Colunas para considerar na desduplicação
    colunas_chave: List[str] = field(default_factory=lambda: ['Marca', 'Nome_Assinatura'])
    
    # Estratégia padrão de desduplicação
    estrategia: EstrategiaDeduplicacao = EstrategiaDeduplicacao.MAIS_COMPLETO
    
    # Colunas importantes para avaliar completude
    colunas_importantes: List[str] = field(default_factory=lambda: [
        'CPU', 'GPU', 'RAM', 'Storage', 'Tela', 'Ano_Lancamento'
    ])
    
    # Colunas para normalização antes da desduplicação
    colunas_para_normalizar: List[str] = field(default_factory=lambda: [
        'Marca', 'Nome_Assinatura', 'CPU', 'GPU', 'Tipo_Notebook', 'Subtipo_Modelo'
    ])
    
    # Pesos para cada componente na avaliação de "melhor especificação"
    pesos_componentes: Dict[str, float] = field(default_factory=lambda: {
        'CPU': 1.5,
        'GPU': 2.0,
        'RAM': 1.0,
        'Storage': 0.8,
        'Ano_Lancamento': 1.2
    })
    
    # Configurações de relatório
    gerar_relatorio_detalhado: bool = True
    mostrar_exemplos_duplicatas: int = 5


# ==================== CLASSE PRINCIPAL ====================

class DesduplicadorDataset:
    """Classe para desduplicação inteligente de datasets de laptops"""
    
    def __init__(self, config: ConfiguracaoDeduplicacao):
        self.config = config
        self.df_original = None
        self.df_deduplciado = None
        self.estatisticas = {}
        
    def carregar_dataset(self, caminho: str) -> pd.DataFrame:
        """Carrega o dataset do arquivo CSV"""
        try:
            df = pd.read_csv(caminho)
            print(f"✓ Dataset carregado com sucesso: {len(df)} registros")
            return df
        except FileNotFoundError:
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
        except Exception as e:
            raise Exception(f"Erro ao carregar dataset: {e}")
    
    def normalizar_colunas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normaliza colunas para comparação consistente"""
        df_normalizado = df.copy()
        
        for coluna in self.config.colunas_para_normalizar:
            if coluna in df_normalizado.columns:
                df_normalizado[coluna] = (
                    df_normalizado[coluna]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .replace(['NAN', 'NONE', ''], pd.NA)
                )
        
        return df_normalizado
    
    def calcular_completude(self, row: pd.Series) -> float:
        """Calcula score de completude de um registro (0 a 1)"""
        colunas_presentes = 0
        total_colunas = len(self.config.colunas_importantes)
        
        for coluna in self.config.colunas_importantes:
            if coluna in row.index and pd.notna(row[coluna]) and str(row[coluna]).upper() not in ['NAN', 'NONE', '']:
                colunas_presentes += 1
        
        return colunas_presentes / total_colunas if total_colunas > 0 else 0
    
    def calcular_score_especificacao(self, row: pd.Series) -> float:
        """Calcula score baseado na qualidade das especificações"""
        score = 0.0
        
        # Score baseado em CPU
        if pd.notna(row.get('CPU')):
            cpu = str(row['CPU']).upper()
            if 'I9' in cpu or 'RYZEN 9' in cpu or 'M3 MAX' in cpu or 'ULTRA 9' in cpu:
                score += 10 * self.config.pesos_componentes.get('CPU', 1.0)
            elif 'I7' in cpu or 'RYZEN 7' in cpu or 'M3 PRO' in cpu or 'ULTRA 7' in cpu:
                score += 8 * self.config.pesos_componentes.get('CPU', 1.0)
            elif 'I5' in cpu or 'RYZEN 5' in cpu or 'M3' in cpu or 'ULTRA 5' in cpu:
                score += 6 * self.config.pesos_componentes.get('CPU', 1.0)
        
        # Score baseado em GPU
        if pd.notna(row.get('GPU')):
            gpu = str(row['GPU']).upper()
            if 'RTX 4090' in gpu:
                score += 10 * self.config.pesos_componentes.get('GPU', 1.0)
            elif 'RTX 40' in gpu:
                score += 9 * self.config.pesos_componentes.get('GPU', 1.0)
            elif 'RTX 30' in gpu:
                score += 7 * self.config.pesos_componentes.get('GPU', 1.0)
            elif 'GTX' in gpu or 'RTX' in gpu:
                score += 5 * self.config.pesos_componentes.get('GPU', 1.0)
        
        # Score baseado em RAM
        if pd.notna(row.get('RAM')):
            try:
                ram_gb = int(re.search(r'\d+', str(row['RAM'])).group())
                score += (ram_gb / 4) * self.config.pesos_componentes.get('RAM', 1.0)
            except:
                pass
        
        # Score baseado em Storage
        if pd.notna(row.get('Storage')):
            storage = str(row['Storage']).upper()
            if 'TB' in storage:
                score += 5 * self.config.pesos_componentes.get('Storage', 1.0)
            elif 'GB' in storage and '512' in storage:
                score += 3 * self.config.pesos_componentes.get('Storage', 1.0)
        
        # Score baseado em ano (mais recente é melhor)
        if pd.notna(row.get('Ano_Lancamento')):
            try:
                ano = int(row['Ano_Lancamento'])
                score += (ano - 2015) * self.config.pesos_componentes.get('Ano_Lancamento', 1.0)
            except:
                pass
        
        return score
    
    def estrategia_primeiro(self, grupo: pd.DataFrame) -> pd.Series:
        """Mantém o primeiro registro encontrado"""
        return grupo.iloc[0]
    
    def estrategia_ultimo(self, grupo: pd.DataFrame) -> pd.Series:
        """Mantém o último registro encontrado"""
        return grupo.iloc[-1]
    
    def estrategia_mais_completo(self, grupo: pd.DataFrame) -> pd.Series:
        """Mantém o registro com mais campos preenchidos"""
        grupo['_score_completude'] = grupo.apply(self.calcular_completude, axis=1)
        melhor = grupo.loc[grupo['_score_completude'].idxmax()]
        return melhor.drop('_score_completude')
    
    def estrategia_mais_recente(self, grupo: pd.DataFrame) -> pd.Series:
        """Mantém o registro com ano mais recente"""
        if 'Ano_Lancamento' in grupo.columns:
            grupo_valido = grupo[pd.notna(grupo['Ano_Lancamento'])]
            if not grupo_valido.empty:
                return grupo_valido.loc[grupo_valido['Ano_Lancamento'].idxmax()]
        return grupo.iloc[0]
    
    def estrategia_melhor_especificacao(self, grupo: pd.DataFrame) -> pd.Series:
        """Mantém o registro com melhor combinação de especificações"""
        grupo['_score_spec'] = grupo.apply(self.calcular_score_especificacao, axis=1)
        melhor = grupo.loc[grupo['_score_spec'].idxmax()]
        return melhor.drop('_score_spec')
    
    def aplicar_estrategia(self, df: pd.DataFrame) -> pd.DataFrame:
        """Aplica a estratégia de desduplicação selecionada"""
        
        estrategias = {
            EstrategiaDeduplicacao.PRIMEIRO: self.estrategia_primeiro,
            EstrategiaDeduplicacao.ULTIMO: self.estrategia_ultimo,
            EstrategiaDeduplicacao.MAIS_COMPLETO: self.estrategia_mais_completo,
            EstrategiaDeduplicacao.MAIS_RECENTE: self.estrategia_mais_recente,
            EstrategiaDeduplicacao.MELHOR_ESPECIFICACAO: self.estrategia_melhor_especificacao
        }
        
        funcao_estrategia = estrategias.get(self.config.estrategia)
        
        if not funcao_estrategia:
            raise ValueError(f"Estratégia inválida: {self.config.estrategia}")
        
        # Agrupa por colunas chave e aplica estratégia
        df_deduplciado = (
            df.groupby(self.config.colunas_chave, dropna=False)
            .apply(funcao_estrategia)
            .reset_index(drop=True)
        )
        
        return df_deduplciado
    
    def gerar_relatorio_duplicatas(self, df_original: pd.DataFrame, 
                                   df_deduplciado: pd.DataFrame) -> Dict:
        """Gera relatório detalhado sobre as duplicatas removidas"""
        
        total_original = len(df_original)
        total_final = len(df_deduplciado)
        duplicatas_removidas = total_original - total_final
        
        relatorio = {
            'total_original': total_original,
            'total_final': total_final,
            'duplicatas_removidas': duplicatas_removidas,
            'percentual_reducao': (duplicatas_removidas / total_original * 100) if total_original > 0 else 0,
            'estrategia_usada': self.config.estrategia.value
        }
        
        # Identifica grupos com mais duplicatas
        if self.config.gerar_relatorio_detalhado:
            contagem_por_grupo = (
                df_original.groupby(self.config.colunas_chave)
                .size()
                .sort_values(ascending=False)
            )
            
            grupos_duplicados = contagem_por_grupo[contagem_por_grupo > 1]
            
            relatorio['total_grupos_duplicados'] = len(grupos_duplicados)
            relatorio['grupos_mais_duplicados'] = grupos_duplicados.head(10).to_dict()
            
            # Distribuição de duplicatas
            relatorio['distribuicao_duplicatas'] = {
                '2 duplicatas': (contagem_por_grupo == 2).sum(),
                '3-5 duplicatas': ((contagem_por_grupo >= 3) & (contagem_por_grupo <= 5)).sum(),
                '6-10 duplicatas': ((contagem_por_grupo >= 6) & (contagem_por_grupo <= 10)).sum(),
                '10+ duplicatas': (contagem_por_grupo > 10).sum()
            }
        
        return relatorio
    
    def imprimir_relatorio(self, relatorio: Dict):
        """Imprime relatório formatado"""
        print("\n" + "="*70)
        print("RELATÓRIO DE DESDUPLICAÇÃO".center(70))
        print("="*70)
        
        print(f"\n📊 Estatísticas Gerais:")
        print(f"   • Registros originais: {relatorio['total_original']:,}")
        print(f"   • Registros únicos: {relatorio['total_final']:,}")
        print(f"   • Duplicatas removidas: {relatorio['duplicatas_removidas']:,}")
        print(f"   • Redução: {relatorio['percentual_reducao']:.2f}%")
        print(f"   • Estratégia utilizada: {relatorio['estrategia_usada']}")
        
        if 'total_grupos_duplicados' in relatorio:
            print(f"\n🔍 Análise de Duplicatas:")
            print(f"   • Grupos com duplicatas: {relatorio['total_grupos_duplicados']}")
            
            print(f"\n   Distribuição:")
            for categoria, quantidade in relatorio['distribuicao_duplicatas'].items():
                print(f"      - {categoria}: {quantidade}")
            
            print(f"\n   🏆 Top 5 Modelos Mais Duplicados:")
            for i, (chave, qtd) in enumerate(list(relatorio['grupos_mais_duplicados'].items())[:5], 1):
                if isinstance(chave, tuple):
                    marca, modelo = chave
                    print(f"      {i}. {marca} - {modelo}: {qtd} ocorrências")
                else:
                    print(f"      {i}. {chave}: {qtd} ocorrências")
        
        print("\n" + "="*70 + "\n")
    
    def mostrar_exemplos_antes_depois(self, df_original: pd.DataFrame):
        """Mostra exemplos de registros duplicados antes da remoção"""
        print("\n📋 Exemplos de Duplicatas (antes da remoção):\n")
        
        # Agrupa e encontra duplicatas
        grupos = df_original.groupby(self.config.colunas_chave)
        grupos_duplicados = [nome for nome, grupo in grupos if len(grupo) > 1]
        
        for i, chave in enumerate(grupos_duplicados[:self.config.mostrar_exemplos_duplicatas]):
            if isinstance(chave, tuple):
                marca, modelo = chave
                print(f"\n{i+1}. {marca} - {modelo}:")
            else:
                print(f"\n{i+1}. {chave}:")
            
            grupo = grupos.get_group(chave)
            print(f"   Total de variações: {len(grupo)}")
            
            # Mostra diferenças nas colunas importantes
            for col in ['CPU', 'GPU', 'RAM', 'Ano_Lancamento']:
                if col in grupo.columns:
                    valores_unicos = grupo[col].dropna().unique()
                    if len(valores_unicos) > 1:
                        print(f"   {col}: {list(valores_unicos)}")
    
    def deduplicar(self, df: pd.DataFrame, 
                   mostrar_relatorio: bool = True,
                   mostrar_exemplos: bool = False) -> pd.DataFrame:
        """
        Método principal de desduplicação
        
        Args:
            df: DataFrame a ser deduplciado
            mostrar_relatorio: Se True, imprime relatório detalhado
            mostrar_exemplos: Se True, mostra exemplos de duplicatas
        
        Returns:
            DataFrame deduplciado
        """
        self.df_original = df.copy()
        
        print(f"🔄 Iniciando desduplicação...")
        print(f"   Estratégia: {self.config.estrategia.value}")
        print(f"   Colunas-chave: {', '.join(self.config.colunas_chave)}")
        
        # Normaliza colunas
        df_normalizado = self.normalizar_colunas(df)
        
        # Remove linhas onde as colunas-chave são todas nulas
        df_normalizado = df_normalizado.dropna(subset=self.config.colunas_chave, how='all')
        
        # Mostra exemplos antes da desduplicação
        if mostrar_exemplos:
            self.mostrar_exemplos_antes_depois(df_normalizado)
        
        # Aplica estratégia
        df_deduplciado = self.aplicar_estrategia(df_normalizado)
        
        self.df_deduplciado = df_deduplciado
        
        # Gera relatório
        relatorio = self.gerar_relatorio_duplicatas(df_normalizado, df_deduplciado)
        self.estatisticas = relatorio
        
        if mostrar_relatorio:
            self.imprimir_relatorio(relatorio)
        
        return df_deduplciado
    
    def salvar(self, caminho: str):
        """Salva o dataset deduplciado"""
        if self.df_deduplciado is None:
            raise ValueError("Execute deduplicar() antes de salvar")
        
        self.df_deduplciado.to_csv(caminho, index=False)
        print(f"✓ Dataset deduplciado salvo em: {caminho}")


# ==================== FUNÇÕES AUXILIARES ====================

def configurar_paths():
    """Configura paths do projeto com fallback"""
    try:
        caminho_script = Path(__file__).resolve().parent
        caminho_raiz_projeto = caminho_script.parent.parent
        sys.path.append(str(caminho_raiz_projeto))
        
        from config import DIRETORIO_CSV_DATASET_FINAL
        print("✓ Paths carregados do config.py")
        return DIRETORIO_CSV_DATASET_FINAL
        
    except (ImportError, NameError):
        print("⚠ config.py não encontrado. Usando paths locais.")
        return Path('data/final')


# ==================== EXECUÇÃO PRINCIPAL ====================

def main():
    """Função principal de execução"""
    
    # Configura paths
    diretorio_final = configurar_paths()
    arquivo_entrada = diretorio_final / 'dataset_laptops.csv'
    arquivo_saida = diretorio_final / 'dataset_laptops_UNICOS.csv'
    
    # Configura desduplicação
    config = ConfiguracaoDeduplicacao(
        estrategia=EstrategiaDeduplicacao.MELHOR_ESPECIFICACAO,  # Pode mudar aqui!
        gerar_relatorio_detalhado=True,
        mostrar_exemplos_duplicatas=5
    )
    
    # Inicializa desduplicador
    desduplicador = DesduplicadorDataset(config)
    
    try:
        # Carrega dataset
        df = desduplicador.carregar_dataset(str(arquivo_entrada))
        
        # Deduplica
        df_unico = desduplicador.deduplicar(
            df, 
            mostrar_relatorio=True,
            mostrar_exemplos=True  # Mude para False se não quiser ver exemplos
        )
        
        # Salva resultado
        desduplicador.salvar(str(arquivo_saida))
        
        # Mostra amostra do resultado
        print("\n📊 Amostra do Dataset Final (5 primeiros registros):")
        print(df_unico[['Marca', 'Nome_Assinatura', 'CPU', 'GPU', 'RAM']].head())
        
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()