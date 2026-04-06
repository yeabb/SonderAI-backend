# SonderAI — Architecture Diagrams

---

## 1. System Architecture

Components grouped by layer and function.

```mermaid
graph TB
    subgraph CLIENT["🖥️ Client Layer"]
        Browser["User's Browser"]
        NextJS["Next.js App (Vercel)\nreact-force-graph-2d/3d"]
    end

    subgraph EDGE["🌐 Edge & Network Layer"]
        VercelCDN["Vercel CDN\n(Frontend static assets)"]
        ALB["AWS ALB\n(Load Balancer)"]
    end

    subgraph APP["⚙️ Application Layer"]
        Django["Django REST API\n(ECS Fargate containers)"]
        ECR["AWS ECR\n(Docker image registry)"]
    end

    subgraph DATA["🗄️ Data Layer"]
        RDS["AWS RDS\nPostgreSQL\n(source of truth)"]
        Pinecone["Pinecone\nVector DB\n(semantic search)"]
    end

    subgraph EXTERNAL["🔌 External Services"]
        Cognito["AWS Cognito\n(Identity & Auth)"]
        OpenAI["OpenAI API\n(text-embedding-3-small)"]
    end

    subgraph OPS["🔧 Ops & Config"]
        Secrets["AWS Secrets Manager\n(API keys, DB credentials)"]
        CloudWatch["AWS CloudWatch\n(Logs & Metrics)"]
        Route53["AWS Route 53\n(DNS)"]
    end

    Browser --> NextJS
    NextJS --> VercelCDN
    NextJS -->|"HTTPS REST API calls"| ALB
    Route53 -->|"DNS routing"| ALB
    ALB --> Django
    ECR -->|"pulls image"| Django

    Django -->|"read/write"| RDS
    Django -->|"upsert/query vectors"| Pinecone
    Django -->|"validate JWT"| Cognito
    Django -->|"generate embeddings"| OpenAI
    Django -->|"read secrets"| Secrets
    Django -->|"emit logs"| CloudWatch

    Browser -->|"sign in/out, tokens"| Cognito
```

---

## 2. System Workflow

End-to-end behavior across all major user journeys. Shows how every layer participates in each flow.

```mermaid
sequenceDiagram
    actor User
    participant FE as Next.js Frontend
    participant API as Django API
    participant Cognito as AWS Cognito
    participant PG as PostgreSQL
    participant PC as Pinecone
    participant OAI as OpenAI
    participant BG as Background Thread

    %% ─────────────────────────────────
    %% AUTHENTICATION
    %% ─────────────────────────────────
    rect rgb(230, 245, 255)
        note over User,OAI: Authentication
        User->>FE: Sign up / Sign in
        FE->>Cognito: Authenticate credentials
        Cognito-->>FE: JWT token
        FE->>API: POST /api/v1/users/onboarding/ (JWT + interest tags)
        API->>Cognito: Validate JWT
        Cognito-->>API: Claims (cognito_id)
        API->>PG: INSERT UserProfile (cognito_id, interest_tags)
        API-->>FE: 200 OK
    end

    %% ─────────────────────────────────
    %% TWEET CREATION
    %% ─────────────────────────────────
    rect rgb(230, 255, 235)
        note over User,OAI: Tweet Creation
        User->>FE: Write and submit tweet
        FE->>API: POST /api/v1/tweets/ (JWT + title + content)
        API->>Cognito: Validate JWT
        API->>PG: INSERT TweetNode (uuid, title, content)
        API->>OAI: embed(title + content) → 1536d vector
        OAI-->>API: vector
        API->>PC: upsert(tweet_id, vector, metadata)
        API->>PG: INSERT EmbeddingReference
        API->>BG: spawn → build_profile_graph(user)
        API-->>FE: 201 Created { id, title, content }

        BG->>PC: fetch(all user tweet vectors)
        BG->>BG: pairwise cosine similarity
        BG->>PG: upsert UserGraph / UserGraphNode / UserGraphEdge
    end

    %% ─────────────────────────────────
    %% FEED GRAPH LOAD
    %% ─────────────────────────────────
    rect rgb(255, 245, 220)
        note over User,OAI: Feed Graph Load (session start)
        User->>FE: Open app / home page
        FE->>API: GET /api/v1/graph/feed/ (JWT)
        API->>Cognito: Validate JWT
        API->>PG: Read UserGraph.cached_anchor

        alt No cached anchor (first session)
            API->>PC: fetch vectors for all pinned nodes + visits + traversals
            API->>API: _full_anchor_recompute\n(recency-decayed weighted centroid)
            API->>PG: Save cached_anchor + cached_total_weight
        else Cached anchor exists
            API->>API: Use cached_anchor directly
        end

        API->>PG: Get visited tweet IDs (NodeVisit)
        API->>PC: query top-100\n(anchor vector, exclude visited IDs)
        PC-->>API: 100 candidates with vectors + metadata
        API->>API: _recency_boost\n(re-rank by similarity × e^-λt, take top-50)
        API->>PG: Bulk fetch TweetNode objects
        API->>API: _compute_edges\n(pairwise cosine similarity, threshold=0.7)
        API-->>FE: { nodes: [...], edges: [...] }
        FE->>FE: Render graph (react-force-graph-2d/3d)
        FE->>API: POST /api/v1/interactions/session/ → start GraphSession
    end

    %% ─────────────────────────────────
    %% GRAPH NAVIGATION
    %% ─────────────────────────────────
    rect rgb(255, 230, 245)
        note over User,OAI: Graph Navigation (within session)
        User->>FE: Click a node
        FE->>API: POST /api/v1/interactions/visit/\n(tweet_id, position_in_path)
        API->>PG: INSERT NodeVisit (start dwell timer)

        User->>FE: Read tweet, follow an edge
        FE->>API: POST /api/v1/interactions/visit/ (dwell_seconds)
        API->>PG: UPDATE NodeVisit.dwell_seconds
        FE->>API: POST /api/v1/interactions/traverse/\n(from_tweet_id, to_tweet_id)
        API->>PG: INSERT EdgeTraversal

        User->>FE: Close app / end session
        FE->>API: POST /api/v1/interactions/session/end/
        API->>PG: UPDATE GraphSession.ended_at

        alt Significant activity this session\n(pin OR 3+ visits >10s OR 2+ traversals)
            API->>BG: spawn → incremental anchor update
            BG->>PC: fetch vectors for new signals only
            BG->>BG: new_anchor = (old × old_w + new_vec × new_w) / (old_w + new_w)
            BG->>PG: UPDATE cached_anchor, cached_total_weight
        end
    end

    %% ─────────────────────────────────
    %% NODE PIN
    %% ─────────────────────────────────
    rect rgb(240, 230, 255)
        note over User,OAI: Pin a Node ("Add to my graph")
        User->>FE: Pin a tweet
        FE->>API: POST /api/v1/graph/pin/ (tweet_id)
        API->>PG: INSERT UserGraphNode (source=pinned)
        API->>PC: fetch(tweet vector)
        API->>PG: fetch vectors for existing UserGraph nodes
        API->>API: compute similarity vs all existing nodes
        API->>PG: INSERT UserGraphEdge records (weight ≥ 0.7)
        API->>BG: spawn → _incremental_anchor_update (pin signal, immediate)
        BG->>PC: fetch(pinned tweet vector)
        BG->>BG: weighted average update
        BG->>PG: UPDATE cached_anchor, cached_total_weight
        API-->>FE: 200 OK
    end

    %% ─────────────────────────────────
    %% PROFILE GRAPH LOAD
    %% ─────────────────────────────────
    rect rgb(235, 255, 245)
        note over User,OAI: Profile Graph Load
        User->>FE: Visit a user's profile
        FE->>API: GET /api/v1/graph/profile/{user_id}/
        API->>PG: SELECT UserGraphNode + UserGraphEdge\n(pure DB read, no computation)
        PG-->>API: nodes + edges
        API-->>FE: { nodes: [...], edges: [...] }
        FE->>FE: Render profile graph
    end
```

---

## 3. Feed Graph Construction Flow

Detailed flowchart of the feed graph algorithm.

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
    H --> I[_compute_edges\npairwise cosine similarity\nO n² — at n=50, 1225 comparisons\nthreshold = 0.7]
    I --> J[Return graph JSON\n{ nodes, edges }]
    J --> K([Frontend renders graph\nreact-force-graph-2d/3d])
```

---

## 4. Anchor Lifecycle

How the anchor embedding is created, cached, and kept fresh.

```mermaid
stateDiagram-v2
    [*] --> NoAnchor: New user

    NoAnchor --> FullRecompute: First feed graph request
    FullRecompute --> Cached: Save anchor + total_weight\nto UserGraph

    Cached --> IncrementalUpdate: User pins a node\n(immediate, sync)
    Cached --> IncrementalUpdate: Session ends with\nsignificant activity\n(async background)
    IncrementalUpdate --> Cached: new_anchor =\n(old × old_w + new_vec × new_w)\n÷ (old_w + new_w)

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
    subgraph Profile["Profile Graph"]
        direction TB
        PT["Trigger:\nTweet created or deleted"]
        PB["build_profile_graph\nfetch all user tweet vectors\nfrom Pinecone in one batch"]
        PE["Pairwise cosine similarity\nacross all user's tweets"]
        PS["Persist to Postgres\nUserGraph / UserGraphNode\nUserGraphEdge"]
        PR["Profile page load:\npure DB read\nno computation"]
        PT --> PB --> PE --> PS
        PS -->|"precomputed"| PR
    end

    subgraph Feed["Feed Graph"]
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

Core models and their relationships.

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
