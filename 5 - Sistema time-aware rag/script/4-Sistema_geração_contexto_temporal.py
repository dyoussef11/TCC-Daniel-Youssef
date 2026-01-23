from langchain.chains import RetrievalQA
from langchain.llms import HuggingFacePipeline
from transformers import pipeline

class TimeAwareGenerator:
    def __init__(self, model_name="neuralmind/bert-base-portuguese-cased"):
        # Carregar modelo em português
        self.llm = self._load_portuguese_llm(model_name)
        self.qa_chain = None
        
    def create_chain(self, retriever):
        # Criar chain RAG com prompt temporal
        from langchain.prompts import PromptTemplate
        
        template = """
        Você é um especialista em análise temporal de produtos de tecnologia.
        
        Contexto temporal: {temporal_context}
        Pergunta: {question}
        
        Baseado nas discussões do período específico, responda:
        
        {context}
        
        Resposta (considere a perspectiva temporal):
        """
        
        prompt = PromptTemplate(
            template=template,
            input_variables=["temporal_context", "question", "context"]
        )
        
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=retriever,
            chain_type_kwargs={"prompt": prompt}
        )
    
    def generate(self, query, time_period):
        temporal_context = self._create_temporal_context(time_period)
        return self.qa_chain.run({
            "temporal_context": temporal_context,
            "question": query
        })