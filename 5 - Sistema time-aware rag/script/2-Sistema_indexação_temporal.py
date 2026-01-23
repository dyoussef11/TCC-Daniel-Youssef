import faiss
import numpy as np
from datetime import datetime

class TemporalIndex:
    def __init__(self):
        # Índices separados por período
        self.indices = {}
        self.metadata = {}
        
    def build_index(self, documents, time_period):
        # Criar embeddings com dimensão aumentada para tempo
        embeddings = []
        metadata = []
        
        for doc in documents:
            # Embedding combinado (conteúdo + tempo)
            embed = self._create_combined_embedding(doc['text'], doc['timestamp'])
            embeddings.append(embed)
            metadata.append({
                'id': doc['id'],
                'timestamp': doc['timestamp'],
                'text': doc['text']
            })
        
        # Criar índice FAISS
        dimension = len(embeddings[0])
        index = faiss.IndexFlatL2(dimension)
        index.add(np.array(embeddings).astype('float32'))
        
        self.indices[time_period] = index
        self.metadata[time_period] = metadata
    
    def temporal_search(self, query, query_time, k=10, time_weight=0.3):
        # Pesquisar nos índices relevantes temporalmente
        relevant_periods = self._get_relevant_periods(query_time)
        
        results = []
        for period in relevant_periods:
            period_results = self._search_in_period(query, period, k)
            # Aplicar peso temporal
            for res in period_results:
                time_diff = abs(res['timestamp'] - query_time)
                time_score = 1 / (1 + time_diff.days / 365)  # Normalizar por ano
                res['score'] = res['score'] * (1 - time_weight) + time_score * time_weight
            results.extend(period_results)
        
        # Ordenar por score combinado
        return sorted(results, key=lambda x: x['score'], reverse=True)[:k]