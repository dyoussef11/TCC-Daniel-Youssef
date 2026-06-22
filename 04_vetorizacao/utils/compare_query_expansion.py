# compare_embedding_scores.py
"""
Compara os scores de similaridade (BGE-M3) entre query original e query expandida.
Avalia se a expansão por sinônimos melhora a relevância semântica.
"""

import asyncio
import json
import sys
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import pandas as pd
from tqdm import tqdm

from core.paths import VETORIZATION_DATA, VALIDACAO_CONFIG, AVALIACAO_DATA, VALIDACAO_SCRIPT
sys.path.append(str(VALIDACAO_SCRIPT))

from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG
from ollama import Client

# Configurações
# DICT_PATH = VALIDACAO_CONFIG / 'dictionary_synonyms_flat.json'
DICT_PATH = VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v3.json'
MODELO_EMBEDDING = "bge-m3:latest"


class EmbeddingScoreComparator:
    """
    Compara scores de similaridade entre query original e expandida.
    """
    
    def __init__(self, base_path: Path, synonym_dict_path: Path):
        self.base_path = base_path
        self.synonym_dict = self._load_synonym_dict(synonym_dict_path)
        
        # Carrega a base e o índice FAISS
        self._load_base_and_index()
        
        # Cliente para embeddings
        self.embedding_client = Client()
        
        self.results = []
    
    def _load_synonym_dict(self, path: Path) -> Dict[str, List[str]]:
        """Carrega dicionário de sinônimos."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Dicionário não encontrado: {path}")
            return {}
    
    def _load_base_and_index(self):
        """Carrega a base de dados e os embeddings pré-computados."""
        import faiss
        import ijson
        
        print("📚 Carregando base de dados...")
        
        self.base_dados = []
        try:
            with open(self.base_path, 'rb') as f:
                for item in ijson.items(f, 'item'):
                    self.base_dados.append(item)
            print(f"   ✅ {len(self.base_dados)} documentos carregados")
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            self.base_dados = []
        
        # Cria índice FAISS
        self.dimension = 1024
        self.index = faiss.IndexFlatL2(self.dimension)
        if self.base_dados:
            vectors = np.array([d['vector'] for d in self.base_dados]).astype('float32')
            self.index.add(vectors)
            print(f"   ✅ Índice FAISS criado com {self.index.ntotal} vetores")
    
    def expand_query(self, query: str) -> Tuple[str, List[str]]:
        """
        Expande a query com sinônimos do dicionário.
        Retorna (query_expandida, termos_adicionados)
        """
        if not self.synonym_dict:
            return query, []
        
        query_lower = query.lower()
        expansions = set()
        
        for canonical, variants in self.synonym_dict.items():
            for variant in variants:
                if variant.lower() in query_lower:
                    expansions.add(canonical)
                    expansions.update(variants[:3])
                    break
        
        if expansions:
            # Remove termos que já estão na query
            clean_expansions = [e for e in expansions if e.lower() not in query_lower]
            if clean_expansions:
                expanded = f"{query} {' '.join(clean_expansions)}"
                return expanded, clean_expansions
        
        return query, []
    
    async def get_embedding(self, text: str) -> np.ndarray:
        """Obtém embedding via BGE-M3."""
        result = await asyncio.to_thread(
            self.embedding_client.embeddings,
            model=MODELO_EMBEDDING,
            prompt=text
        )
        return np.array(result['embedding'], dtype=np.float32)
    
    async def get_top_k_scores(self, query: str, k: int = 10) -> List[Dict]:
        """
        Retorna os top-k documentos com seus scores de similaridade.
        """
        # Obtém embedding da query
        query_vector = await self.get_embedding(query)
        query_vector = query_vector.reshape(1, -1)
        
        # Busca no FAISS
        distances, indices = self.index.search(query_vector, k=k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            
            doc = self.base_dados[idx]
            score = distances[0][i]  # Distância L2 (menor = mais similar)
            
            # Converte distância para similaridade (1/(1+distância))
            similarity = 1.0 / (1.0 + score)
            
            results.append({
                'doc_id': idx,
                'distance': float(score),
                'similarity': similarity,
                'title': doc.get('metadata', {}).get('title', 'Unknown'),
                'model': doc.get('metadata', {}).get('model', 'Unknown'),
                'date': doc.get('date_iso', 'Unknown')[:10]
            })
        
        return results
    
    async def compare_query(self, query: str, test_id: str = None, k: int = 10) -> Dict:
        """
        Compara os scores da query original vs expandida.
        """
        print(f"\n📝 [{test_id}] {query[:70]}...")
        
        # Expande a query
        expanded_query, expansion_terms = self.expand_query(query)
        expansion_applied = len(expansion_terms) > 0
        
        # Obtém top-k para ambas
        scores_original = await self.get_top_k_scores(query, k)
        scores_expanded = await self.get_top_k_scores(expanded_query, k) if expansion_applied else scores_original
        
        # Calcula métricas
        avg_sim_original = np.mean([s['similarity'] for s in scores_original]) if scores_original else 0
        avg_sim_expanded = np.mean([s['similarity'] for s in scores_expanded]) if scores_expanded else 0
        
        top1_sim_original = scores_original[0]['similarity'] if scores_original else 0
        top1_sim_expanded = scores_expanded[0]['similarity'] if scores_expanded else 0
        
        # Documentos no top-5
        top5_titles_original = [s['title'][:50] for s in scores_original[:5]]
        top5_titles_expanded = [s['title'][:50] for s in scores_expanded[:5]]
        
        # Documentos que aparecem/desaparecem com a expansão
        original_set = set(s['doc_id'] for s in scores_original[:5])
        expanded_set = set(s['doc_id'] for s in scores_expanded[:5])
        
        new_docs = expanded_set - original_set
        lost_docs = original_set - expanded_set
        
        # Calcula melhoria
        improvement_avg = avg_sim_expanded - avg_sim_original
        improvement_top1 = top1_sim_expanded - top1_sim_original
        improvement_percent = (improvement_avg / max(avg_sim_original, 0.001)) * 100
        
        result = {
            'test_id': test_id or f"Q_{len(self.results)+1}",
            'original_query': query,
            'expanded_query': expanded_query,
            'expansion_terms': expansion_terms,
            'expansion_applied': expansion_applied,
            
            # Métricas
            'avg_similarity_original': round(avg_sim_original, 4),
            'avg_similarity_expanded': round(avg_sim_expanded, 4),
            'improvement_avg': round(improvement_avg, 4),
            'improvement_percent': round(improvement_percent, 2),
            
            'top1_similarity_original': round(top1_sim_original, 4),
            'top1_similarity_expanded': round(top1_sim_expanded, 4),
            'improvement_top1': round(improvement_top1, 4),
            
            # Top documentos
            'top1_title_original': scores_original[0]['title'][:60] if scores_original else 'N/A',
            'top1_title_expanded': scores_expanded[0]['title'][:60] if scores_expanded else 'N/A',
            'top5_titles_original': top5_titles_original,
            'top5_titles_expanded': top5_titles_expanded,
            
            # Estatísticas de documentos
            'new_docs_count': len(new_docs),
            'lost_docs_count': len(lost_docs),
            
            # Scores completos
            'scores_original': scores_original,
            'scores_expanded': scores_expanded
        }
        
        self.results.append(result)
        
        # Print resumo
        if expansion_applied:
            arrow = "📈" if improvement_avg > 0 else "📉"
            print(f"   {arrow} Similaridade média: {avg_sim_original:.4f} → {avg_sim_expanded:.4f} ({improvement_avg:+.4f})")
            print(f"   {arrow} Top-1: {top1_sim_original:.4f} → {top1_sim_expanded:.4f} ({improvement_top1:+.4f})")
            print(f"   Termos adicionados: {', '.join(expansion_terms[:5])}")
        else:
            print(f"   ⏸️  Sem expansão (nenhum sinônimo encontrado)")
        
        return result
    
    def get_summary_stats(self) -> pd.DataFrame:
        """Gera DataFrame com estatísticas resumidas."""
        if not self.results:
            return pd.DataFrame()
        
        data = []
        for r in self.results:
            data.append({
                'ID': r['test_id'],
                'Query': r['original_query'][:50],
                'Expanded': '✅' if r['expansion_applied'] else '❌',
                'Terms': ', '.join(r['expansion_terms'][:3]) if r['expansion_terms'] else '-',
                'Avg_Orig': r['avg_similarity_original'],
                'Avg_Exp': r['avg_similarity_expanded'],
                'Δ_Avg': r['improvement_avg'],
                'Δ%': f"{r['improvement_percent']:+.1f}%",
                'Top1_Orig': r['top1_similarity_original'],
                'Top1_Exp': r['top1_similarity_expanded'],
                'Δ_Top1': r['improvement_top1'],
                'New_Docs': r['new_docs_count']
            })
        
        return pd.DataFrame(data)
    
    def print_detailed_report(self):
        """Imprime relatório detalhado."""
        if not self.results:
            print("Nenhum resultado para reportar.")
            return
        
        print("\n" + "=" * 80)
        print("📊 RELATÓRIO: IMPACTO DA EXPANSÃO DE QUERY NOS SCORES BGE-M3")
        print("=" * 80)
        
        # Separa queries que expandiram
        expanded_results = [r for r in self.results if r['expansion_applied']]
        non_expanded = [r for r in self.results if not r['expansion_applied']]
        
        print(f"\n📈 ESTATÍSTICAS GERAIS:")
        print(f"   Total de queries: {len(self.results)}")
        print(f"   Queries com expansão: {len(expanded_results)}/{len(self.results)} ({len(expanded_results)/len(self.results)*100:.1f}%)")
        
        if expanded_results:
            avg_improvement = np.mean([r['improvement_avg'] for r in expanded_results])
            avg_improvement_pct = np.mean([r['improvement_percent'] for r in expanded_results])
            positive_count = sum(1 for r in expanded_results if r['improvement_avg'] > 0)
            
            print(f"\n📊 MÉTRICAS (apenas queries que expandiram):")
            print(f"   Melhoria média na similaridade: {avg_improvement:+.4f} ({avg_improvement_pct:+.1f}%)")
            print(f"   Queries que melhoraram: {positive_count}/{len(expanded_results)} ({positive_count/len(expanded_results)*100:.1f}%)")
            
            # Melhores e piores
            best = max(expanded_results, key=lambda x: x['improvement_avg'])
            worst = min(expanded_results, key=lambda x: x['improvement_avg'])
            
            print(f"\n🏆 MAIOR MELHORIA:")
            print(f"   Query: {best['original_query'][:60]}...")
            print(f"   Termos: {', '.join(best['expansion_terms'][:5])}")
            print(f"   Similaridade: {best['avg_similarity_original']:.4f} → {best['avg_similarity_expanded']:.4f} (+{best['improvement_avg']:.4f})")
            
            print(f"\n⚠️ PIOR RESULTADO (ou menor melhoria):")
            print(f"   Query: {worst['original_query'][:60]}...")
            print(f"   Similaridade: {worst['avg_similarity_original']:.4f} → {worst['avg_similarity_expanded']:.4f} ({worst['improvement_avg']:+.4f})")
        
        # Tabela detalhada
        print(f"\n📋 TABELA DETALHADA:")
        print("-" * 100)
        print(f"{'ID':<12} {'Similaridade Média':<20} {'Δ':<10} {'Top-1':<12} {'Termos':<30}")
        print("-" * 100)
        
        for r in sorted(expanded_results, key=lambda x: x['improvement_avg'], reverse=True):
            terms_str = ', '.join(r['expansion_terms'][:2]) if r['expansion_terms'] else '-'
            print(f"{r['test_id']:<12} {r['avg_similarity_original']:.4f} → {r['avg_similarity_expanded']:.4f}  {r['improvement_avg']:+.4f}   {r['top1_similarity_expanded']:.4f}   {terms_str:<30}")
    
    def export_results(self, output_dir: Path = None):
        """Exporta resultados para CSV e JSON."""
        if output_dir is None:
            output_dir = AVALIACAO_DATA / 'embedding_scores_analysis'
        
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Exporta CSV
        df = self.get_summary_stats()
        csv_path = output_dir / f"embedding_scores_comparison_{timestamp}.csv"
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"\n📁 CSV salvo: {csv_path}")
        
        # Exporta JSON
        json_path = output_dir / f"embedding_scores_full_{timestamp}.json"
        export_data = {
            'timestamp': timestamp,
            'total_queries': len(self.results),
            'expanded_queries': sum(1 for r in self.results if r['expansion_applied']),
            'avg_improvement': float(np.mean([r['improvement_avg'] for r in self.results if r['expansion_applied']])) if any(r['expansion_applied'] for r in self.results) else 0,
            'results': [
                {
                    'test_id': r['test_id'],
                    'original_query': r['original_query'],
                    'expanded_query': r['expanded_query'],
                    'expansion_terms': r['expansion_terms'],
                    'avg_similarity_original': r['avg_similarity_original'],
                    'avg_similarity_expanded': r['avg_similarity_expanded'],
                    'improvement_avg': r['improvement_avg'],
                    'improvement_percent': r['improvement_percent'],
                    'top1_original': r['top1_title_original'],
                    'top1_expanded': r['top1_title_expanded']
                }
                for r in self.results
            ]
        }
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print(f"📁 JSON salvo: {json_path}")
        
        return csv_path, json_path


# ============================================================================
# TESTES ESPECÍFICOS
# ============================================================================

TEST_QUERIES = [
    # HP Victus - deve expandir para incluir códigos específicos
    {
        'id': 'VICTUS_01',
        'query': 'HP Victus 15',
        'expected_expansion': True
    },
    {
        'id': 'VICTUS_02',
        'query': 'victus 16',
        'expected_expansion': True
    },
    {
        'id': 'VICTUS_03',
        'query': 'HP Victus gaming laptop',
        'expected_expansion': True
    },
    
    # ASUS TUF
    {
        'id': 'TUF_01',
        'query': 'ASUS TUF Gaming F15',
        'expected_expansion': True
    },
    {
        'id': 'TUF_02',
        'query': 'TUF A15',
        'expected_expansion': True
    },
    
    # Lenovo
    {
        'id': 'LEGION_01',
        'query': 'Lenovo Legion 5 Pro',
        'expected_expansion': True
    },
    {
        'id': 'LEGION_02',
        'query': 'Legion Slim 7',
        'expected_expansion': True
    },
    {
        'id': 'LOQ_01',
        'query': 'Lenovo LOQ 15',
        'expected_expansion': True
    },
    
    # MSI
    {
        'id': 'KATANA_01',
        'query': 'MSI Katana 15',
        'expected_expansion': True
    },
    {
        'id': 'PULSE_01',
        'query': 'MSI Pulse GL66',
        'expected_expansion': True
    },
    
    # Acer
    {
        'id': 'NITRO_01',
        'query': 'Acer Nitro 5',
        'expected_expansion': True
    },
    {
        'id': 'NITROV_01',
        'query': 'Acer Nitro V 15',
        'expected_expansion': True
    },
    {
        'id': 'PREDATOR_01',
        'query': 'Predator Helios Neo 16',
        'expected_expansion': True
    },
    
    # ASUS ROG
    {
        'id': 'ZEPHYRUS_01',
        'query': 'ROG Zephyrus G14',
        'expected_expansion': True
    },
    {
        'id': 'STRIX_01',
        'query': 'ROG Strix G15',
        'expected_expansion': True
    },
    {
        'id': 'FLOW_01',
        'query': 'ROG Flow X13',
        'expected_expansion': True
    },
    
    # Dell
    {
        'id': 'G15_01',
        'query': 'Dell G15 5520',
        'expected_expansion': True
    },
    {
        'id': 'XPS_01',
        'query': 'Dell XPS 15',
        'expected_expansion': True
    },
    
    # Query que NÃO deve expandir
    {
        'id': 'GENERIC_01',
        'query': 'laptop superaquecendo durante jogos',
        'expected_expansion': False
    },
    {
        'id': 'GENERIC_02',
        'query': 'how to fix blue screen of death',
        'expected_expansion': False
    },
    
    # Queries com SKU específico
    {
        'id': 'SKU_01',
        'query': 'AN515-56 RAM upgrade',
        'expected_expansion': True
    },
    {
        'id': 'SKU_02',
        'query': 'G513QY charging issue',
        'expected_expansion': True
    },
]


async def run_comparison_suite(comparator: EmbeddingScoreComparator, queries: List[Dict], k: int = 10):
    """Executa suíte de testes completa."""
    print("\n" + "=" * 80)
    print("🚀 COMPARAÇÃO DE SCORES BGE-M3: ORIGINAL vs EXPANDIDA")
    print("=" * 80)
    print(f"📊 Buscando top-{k} documentos por query")
    print("-" * 80)
    
    for test in tqdm(queries, desc="Processando"):
        await comparator.compare_query(
            query=test['query'],
            test_id=test['id'],
            k=k
        )
    
    comparator.print_detailed_report()
    comparator.export_results()
    
    return comparator.results


async def run_batch_mode(batch_file: str = None):
    """Modo batch para processar múltiplas queries de um arquivo."""
    import csv
    
    if batch_file and Path(batch_file).exists():
        with open(batch_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            queries = [{'id': f"BATCH_{i:03d}", 'query': row[0].strip(), 'expected_expansion': True} 
                      for i, row in enumerate(reader) if row and row[0].strip()]
    else:
        # Usa o conjunto padrão
        queries = TEST_QUERIES
    
    base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    if not base_path.exists():
        base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV6_OTIMIZADO.json'
    
    comparator = EmbeddingScoreComparator(base_path, DICT_PATH)
    await run_comparison_suite(comparator, queries)


# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Compara scores BGE-M3 entre query original e expandida')
    parser.add_argument('--query', '-q', type=str, help='Query única para testar')
    parser.add_argument('--batch', '-b', type=str, help='Arquivo CSV com queries (uma por linha)')
    parser.add_argument('--k', type=int, default=10, help='Número de documentos a recuperar (padrão: 10)')
    parser.add_argument('--analyze', action='store_true', help='Apenas analisa cobertura do dicionário')
    
    args = parser.parse_args()
    
    base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    if not base_path.exists():
        base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV6_OTIMIZADO.json'
    
    if args.analyze:
        # Análise rápida do dicionário
        with open(DICT_PATH, 'r', encoding='utf-8') as f:
        # Mostra quantos embeddings serão gerados com/sem expansão
            dict_data = json.load(f)
            print(f"\n📖 Dicionário: {len(dict_data)} entradas canônicas")
            print(f"   Total de variantes: {sum(len(v) for v in dict_data.values())}")
        
    elif args.query:
        # Modo query única
        async def single():
            comparator = EmbeddingScoreComparator(base_path, DICT_PATH)
            await comparator.compare_query(args.query, test_id="SINGLE", k=args.k)
            comparator.print_detailed_report()
            comparator.export_results()
        asyncio.run(single())
    
    else:
        # Modo suíte
        async def main():
            await run_batch_mode(args.batch)
        asyncio.run(main())