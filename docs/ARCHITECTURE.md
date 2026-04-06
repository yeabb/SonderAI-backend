# SonderAI — Architecture Diagrams

---

## 1. System Architecture

High-level infrastructure. Shows how the major components connect.

```mermaid
graph TD
    Browser["User's Browser\nNext.js (Vercel)\nreact-force-graph-2d/3d"]

    subgraph AWS
        ALB["Application Load Balancer"]
        Django["Django REST API\n(ECS Fargate)"]
        RDS["PostgreSQL\n(AWS RDS)"]
        Cognito["AWS Cognito\n(Auth)"]
        Secrets["Secrets Manager"]
        CloudWatch["CloudWatch\n(Logs & Metrics)"]
    end

    Pinecone["Pinecone\n(Vector DB)"]
    OpenAI["OpenAI\n(Embeddings)"]

    Browser -->|"HTTPS REST"| ALB
    ALB --> Django
    Django -->|"Read/Write"| RDS
    Django -->|"Vector upsert/query"| Pinecone
    Django -->|"Validate JWT"| Cognito
    Django -->|"Generate embeddings"| OpenAI
    Django -->|"Read secrets"| Secrets
    Django -->|"Emit logs"| CloudWatch
    Browser -->|"Auth tokens"| Cognito
```

---

## 2. Tweet Creation Flow

What happens end-to-end when a user creates a tweet.

```mermaid
sequenceDiagram
    participant Client as Next.js Frontend
    participant API as Django API
    participant PG as PostgreSQL
    participant OAI as OpenAI
    participant PC as Pinecone
    participant BG as Background Thread

    Client->>API: POST /api/v1/tweets/
    API->>API: Validate input (title ≤25, content ≤280)
    
    rect rgb(240, 240, 255)
        note over API,PC: Atomic transaction
        API->>PG: INSERT TweetNode
        API->>OAI: text-embedding-3-small(title + content)
        OAI-->>API: 1536d vector
        API->>PC: upsert(tweet_id, vector, metadata)
        API->>PG: INSERT EmbeddingReference
    end

    API->>BG: spawn thread → build_profile_graph(user)
    API-->>Client: 201 Created { id, title, content, user, created_at }

    BG->>PC: fetch(all user tweet vectors)
    BG->>BG: pairwise cosine similarity
    BG->>PG: upsert UserGraph / UserGraphNode / UserGraphEdge
```

---

## 3. Feed Graph Construction Flow

What happens when a user opens the app and their feed graph is built.

```mermaid
flowchart TD
    A([Session Start\nGET /api/v1/graph/feed/]) --> B{UserGraph.cached_anchor\nexists?}

    B -->|Yes| D[Use cached anchor]
    B -->|No| C[_full_anchor_recompute\nfetch all historical signals\nfrom Pinecone + DB]
    C --> C2[Save anchor + total_weight\nto UserGraph]
    C2 --> D

    D --> E[Get all visited tweet IDs\nfrom NodeVisit table]
    E --> F[Query Pinecone top-100\nwith visited IDs excluded\ninside the query]
    F --> G[_recency_boost\nre-rank by similarity × e^\(-λ × days\)\ntake top-50]
    G --> H[Bulk fetch TweetNode\nobjects from Postgres]
    H --> I[_compute_edges\npairwise cosine similarity\nO n² at n=50 = 1225 comparisons\nthreshold = 0.7]
    I --> J[Return graph JSON\n{ nodes, edges }]
    J --> K([Frontend renders graph\nreact-force-graph-2d/3d])
```

---

## 4. Anchor Lifecycle

How the anchor embedding is created, cached, and kept fresh over time.

```mermaid
stateDiagram-v2
    [*] --> NoAnchor: New user

    NoAnchor --> FullRecompute: First feed graph request
    FullRecompute --> Cached: Save anchor + total_weight\nto UserGraph

    Cached --> IncrementalUpdate: User pins a node\n(immediate, sync)
    Cached --> IncrementalUpdate: Session ends with\nsignificant activity\n(async background)
    IncrementalUpdate --> Cached: new_anchor = \n(old × old_weight + new_vec × new_weight)\n÷ (old_weight + new_weight)

    Cached --> FullRecompute: Daily scheduled job\n(correct drift, re-apply decay)

    state IncrementalUpdate {
        [*] --> FetchNewVector: Pinecone fetch\n(1 vector only)
        FetchNewVector --> UpdateMath: Weighted average\n(1 operation)
        UpdateMath --> SaveToDB: Update cached_anchor\ncached_total_weight\nanchor_updated_at
    }
```

---

## 5. Profile Graph vs Feed Graph

How the two graph types differ in construction, storage, and serving.

```mermaid
flowchart LR
    subgraph Profile Graph
        direction TB
        PT["Trigger:\nTweet created or deleted"]
        PB["build_profile_graph\nfetch all user tweet vectors\nfrom Pinecone in one batch"]
        PE["Pairwise cosine similarity\nacross all user's tweets"]
        PS["Persist to Postgres\nUserGraph / UserGraphNode\nUserGraphEdge"]
        PR["Profile page load:\npure DB read\nno computation"]
        PT --> PB --> PE --> PS
        PS -->|"precomputed"| PR
    end

    subgraph Feed Graph
        direction TB
        FT["Trigger:\nSession start"]
        FA["_get_or_compute_anchor\nread cache or full recompute"]
        FQ["Pinecone query top-100\nexclude visited nodes\ninside the query"]
        FR["Recency boost re-rank\ntake top-50"]
        FE["Pairwise cosine similarity\non top-50 candidates"]
        FJ["Return graph JSON\nnot persisted"]
        FT --> FA --> FQ --> FR --> FE --> FJ
    end
```

---

## 6. Data Model

How the core models relate to each other.

```mermaid
erDiagram
    UserProfile {
        int id
        string cognito_id
        string username
        string email
        json interest_tags
    }

    TweetNode {
        uuid id
        string title
        string content
        datetime created_at
    }

    EmbeddingReference {
        int id
        string pinecone_vector_id
    }

    UserGraph {
        int id
        json cached_anchor
        float cached_total_weight
        datetime anchor_updated_at
    }

    UserGraphNode {
        int id
        string source
        datetime added_at
    }

    UserGraphEdge {
        int id
        float weight
    }

    GraphSession {
        int id
        datetime started_at
        datetime ended_at
    }

    NodeVisit {
        int id
        int dwell_seconds
        int position_in_path
        datetime visited_at
    }

    EdgeTraversal {
        int id
        datetime traversed_at
    }

    UserProfile ||--o{ TweetNode : "creates"
    UserProfile ||--|| UserGraph : "has one"
    UserProfile ||--o{ GraphSession : "has many"

    TweetNode ||--|| EmbeddingReference : "has one"
    TweetNode ||--o{ UserGraphNode : "referenced by"
    TweetNode ||--o{ NodeVisit : "visited in"
    TweetNode ||--o{ EdgeTraversal : "from/to"

    UserGraph ||--o{ UserGraphNode : "contains"
    UserGraph ||--o{ UserGraphEdge : "contains"

    UserGraphNode ||--o{ UserGraphEdge : "source"
    UserGraphNode ||--o{ UserGraphEdge : "target"

    GraphSession ||--o{ NodeVisit : "contains"
    GraphSession ||--o{ EdgeTraversal : "contains"
```
