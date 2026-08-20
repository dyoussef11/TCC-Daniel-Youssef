# Estrutura do JSON (Resumo Tecnico NER): NER_15_fc0028au_na_na_na.json

## 1. Hierarquia Visual
```text
└── modelo_original [str]
└── modelo_generico [str]
└── query_usada [str]
└── id_notebook [str]
└── total_posts [int]
└── posts [list]
    └── [Exemplo de item na lista: dict]
        └── id [str]
        └── titulo [str]
        └── selftext [str]
        └── subreddit [str]
        └── num_comments [int]
        └── data_post [float]
        └── categoria [str]
        └── comentarios [list]
        │   └── [Exemplo de item na lista: dict]
        │       └── id [str]
        │       └── conteudo [str]
        │       └── score [int]
        │       └── data_comentario [float]
        └── conteudo_post [str]
        └── analise_ia [dict]
            └── summary [str]
            └── intent [str]
            └── detected_fault [str]
            └── suggested_solution [list]
            │   └── [Exemplo de item na lista: str]
            └── technical_severity [str]
            └── discussion_timeline [str]
            └── ancoragem_temporal [dict]
                └── data_processamento [str]
                └── data_post_original [str]
                └── data_ultimo_comentario [str]
```

---

## 2. Dicionário de Campos
| Campo | Tipo | Descrição |
| :--- | :--- | :--- |
| `modelo_original` | `str` | |
| `modelo_generico` | `str` | |
| `query_usada` | `str` | |
| `id_notebook` | `str` | |
| `total_posts` | `int` | |
| `posts` | `list` | |
| `posts[].id` | `str` | |
| `posts[].titulo` | `str` | |
| `posts[].selftext` | `str` | |
| `posts[].subreddit` | `str` | |
| `posts[].num_comments` | `int` | |
| `posts[].data_post` | `float` | |
| `posts[].categoria` | `str` | |
| `posts[].comentarios` | `list` | |
| `posts[].comentarios[].id` | `str` | |
| `posts[].comentarios[].conteudo` | `str` | |
| `posts[].comentarios[].score` | `int` | |
| `posts[].comentarios[].data_comentario` | `float` | |
| `posts[].conteudo_post` | `str` | |
| `posts[].analise_ia` | `dict` | |
| `posts[].analise_ia.summary` | `str` | |
| `posts[].analise_ia.intent` | `str` | |
| `posts[].analise_ia.detected_fault` | `str` | |
| `posts[].analise_ia.suggested_solution` | `list` | |
| `posts[].analise_ia.technical_severity` | `str` | |
| `posts[].analise_ia.discussion_timeline` | `str` | |
| `posts[].analise_ia.ancoragem_temporal` | `dict` | |
| `posts[].analise_ia.ancoragem_temporal.data_processamento` | `str` | |
| `posts[].analise_ia.ancoragem_temporal.data_post_original` | `str` | |
| `posts[].analise_ia.ancoragem_temporal.data_ultimo_comentario` | `str` | |
