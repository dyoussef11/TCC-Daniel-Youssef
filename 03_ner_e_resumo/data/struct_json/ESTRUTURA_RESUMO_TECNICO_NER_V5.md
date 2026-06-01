# Estrutura do JSON (Resumo Tecnico NER): NER_acer_16_predator_neo.json

## 1. Hierarquia Visual
```text
└── modelo_original [str]
└── modelo_busca_utilizado [str]
└── id_notebook [str]
└── data_extracao [float]
└── config_time_filter [str]
└── api_health_at_extraction [dict]
│   └── restante [float]
│   └── reset_em [float]
└── total_posts_encontrados [int]
└── posts [list]
    └── [Exemplo de item na lista: dict]
        └── id [str]
        └── titulo [str]
        └── conteudo_post [str]
        └── subreddit [str]
        └── flair [str]
        └── score [int]
        └── upvote_ratio [float]
        └── num_comments [int]
        └── categoria [str]
        └── termos_especificos [list]
        │   └── [Exemplo de item na lista: str]
        └── url [str]
        └── data_post [float]
        └── comentarios [list]
        └── analise_ia [dict]
            └── summary [str]
            └── intent [str]
            └── detected_fault [str]
            └── suggested_solution [list]
            │   └── [Exemplo de item na lista: str]
            └── technical_severity [str]
            └── discussion_timeline [str]
            └── ancoragem_temporal [dict]
                └── data_post [str]
                └── periodo_referencia [str]
```

---

## 2. Dicionário de Campos
| Campo | Tipo | Descrição |
| :--- | :--- | :--- |
| `modelo_original` | `str` | |
| `modelo_busca_utilizado` | `str` | |
| `id_notebook` | `str` | |
| `data_extracao` | `float` | |
| `config_time_filter` | `str` | |
| `api_health_at_extraction` | `dict` | |
| `api_health_at_extraction.restante` | `float` | |
| `api_health_at_extraction.reset_em` | `float` | |
| `total_posts_encontrados` | `int` | |
| `posts` | `list` | |
| `posts[].id` | `str` | |
| `posts[].titulo` | `str` | |
| `posts[].conteudo_post` | `str` | |
| `posts[].subreddit` | `str` | |
| `posts[].flair` | `str` | |
| `posts[].score` | `int` | |
| `posts[].upvote_ratio` | `float` | |
| `posts[].num_comments` | `int` | |
| `posts[].categoria` | `str` | |
| `posts[].termos_especificos` | `list` | |
| `posts[].url` | `str` | |
| `posts[].data_post` | `float` | |
| `posts[].comentarios` | `list` | |
| `posts[].analise_ia` | `dict` | |
| `posts[].analise_ia.summary` | `str` | |
| `posts[].analise_ia.intent` | `str` | |
| `posts[].analise_ia.detected_fault` | `str` | |
| `posts[].analise_ia.suggested_solution` | `list` | |
| `posts[].analise_ia.technical_severity` | `str` | |
| `posts[].analise_ia.discussion_timeline` | `str` | |
| `posts[].analise_ia.ancoragem_temporal` | `dict` | |
| `posts[].analise_ia.ancoragem_temporal.data_post` | `str` | |
| `posts[].analise_ia.ancoragem_temporal.periodo_referencia` | `str` | |
