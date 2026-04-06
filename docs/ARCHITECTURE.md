# SonderAI — Architecture Diagrams

---

## 1. System Architecture

Infrastructure grouped by security zone and network boundary.

```mermaid
graph TB
    %% ── Public Internet ──────────────────────────────────────
    subgraph INTERNET["🌍 Public Internet"]
        Browser["User's Browser"]
    end

    %% ── CDN / Edge ───────────────────────────────────────────
    subgraph CDN["☁️ CDN & Edge (Vercel)"]
        NextJS["Next.js App<br/>react-force-graph-2d/3d"]
        VercelCDN["Vercel Edge Network<br/>static assets / SSR"]
    end

    %% ── AWS Public Subnet ────────────────────────────────────
    subgraph AWS_PUBLIC["🔶 AWS — Public Subnet"]
        Route53["Route 53<br/>DNS"]
        ALB["Application Load Balancer<br/>HTTPS termination"]
    end

    %% ── AWS Private Subnet — Compute ─────────────────────────
    subgraph AWS_COMPUTE["🔒 AWS — Private Subnet (Compute)"]
        Django["Django REST API<br/>ECS Fargate"]
        ECR["ECR<br/>Docker registry"]
    end

    %% ── AWS Private Subnet — Data ────────────────────────────
    subgraph AWS_DATA["🔒 AWS — Private Subnet (Data)"]
        RDS["RDS PostgreSQL<br/>source of truth"]
    end

    %% ── AWS Managed Services ─────────────────────────────────
    subgraph AWS_MANAGED["🛠️ AWS Managed Services"]
        Cognito["Cognito<br/>Identity & Auth"]
        Secrets["Secrets Manager<br/>API keys & credentials"]
        CloudWatch["CloudWatch<br/>Logs & Metrics"]
    end

    %% ── External SaaS ────────────────────────────────────────
    subgraph SAAS["🔌 External SaaS"]
        Pinecone["Pinecone<br/>Vector DB"]
        OpenAI["OpenAI<br/>Embeddings API"]
    end

    %% ── Connections ──────────────────────────────────────────
    Browser -->|"HTTPS"| NextJS
    Browser -->|"Auth"| Cognito
    NextJS --> VercelCDN
    NextJS -->|"REST API (HTTPS)"| ALB

    Route53 -->|"DNS resolution"| ALB
    ALB -->|"private network"| Django
    ECR -->|"image pull"| Django

    Django -->|"SQL (private subnet)"| RDS
    Django -->|"HTTPS"| Pinecone
    Django -->|"HTTPS"| OpenAI
    Django -->|"HTTPS"| Cognito
    Django -->|"HTTPS"| Secrets
    Django -->|"logs / metrics"| CloudWatch
```

---

## 2. System Workflow

End-to-end behavior across all major user journeys.

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

    %% ── AUTHENTICATION ───────────────────────────────────────
    rect rgb(230, 245, 255)
        note over User,OAI: Authentication
        User->>FE: Sign up / Sign in
        FE->>Cognito: Authenticate credentials
        Cognito-->>FE: JWT token
        FE->>API: POST /api/v1/users/onboarding/
        API->>Cognito: Validate JWT
        Cognito-->>API: Claims (cognito_id)
        API->>PG: INSERT UserProfile
        API-->>FE: 200 OK
    end

    %% ── TWEET CREATION ───────────────────────────────────────
    rect rgb(230, 255, 235)
        note over User,OAI: Tweet Creation
        User->>FE: Write and submit tweet
        FE->>API: POST /api/v1/tweets/
        API->>Cognito: Validate JWT
        API->>PG: INSERT TweetNode
        API->>OAI: embed(title + content)
        OAI-->>API: 1536d vector
        API->>PC: upsert(tweet_id, vector, metadata)
        API->>PG: INSERT EmbeddingReference
        API->>BG: spawn build_profile_graph(user)
        API-->>FE: 201 Created

        BG->>PC: fetch all user tweet vectors
        BG->>BG: pairwise cosine similarity
        BG->>PG: upsert UserGraph / UserGraphNode / UserGraphEdge
    end

    %% ── FEED GRAPH LOAD ──────────────────────────────────────
    rect rgb(255, 245, 220)
        note over User,OAI: Feed Graph Load (session start)
        User->>FE: Open app
        FE->>API: GET /api/v1/graph/feed/
        API->>Cognito: Validate JWT
        API->>PG: Read UserGraph.cached_anchor

        alt No cached anchor (first session)
            API->>PC: fetch vectors for all historical signals
            API->>API: full anchor recompute (weighted centroid)
            API->>PG: save cached_anchor + cached_total_weight
        else Cached anchor exists
            API->>API: use cached_anchor directly
        end

        API->>PG: get visited tweet IDs from NodeVisit
        API->>PC: query top-100 (anchor, exclude visited IDs)
        PC-->>API: 100 candidates with vectors + metadata
        API->>API: recency boost re-rank, take top-50
        API->>PG: bulk fetch TweetNode objects
        API->>API: pairwise cosine similarity, threshold 0.7
        API-->>FE: nodes + edges JSON
        FE->>FE: render graph
        FE->>API: POST /api/v1/interactions/session/
        API->>PG: INSERT GraphSession
    end

    %% ── GRAPH NAVIGATION ─────────────────────────────────────
    rect rgb(255, 230, 245)
        note over User,OAI: Graph Navigation (within session)
        User->>FE: Click a node
        FE->>API: POST /api/v1/interactions/visit/
        API->>PG: INSERT NodeVisit

        User->>FE: Read tweet, follow an edge
        FE->>API: POST /api/v1/interactions/visit/ (with dwell_seconds)
        API->>PG: UPDATE NodeVisit.dwell_seconds
        FE->>API: POST /api/v1/interactions/traverse/
        API->>PG: INSERT EdgeTraversal

        User->>FE: Close app
        FE->>API: POST /api/v1/interactions/session/end/
        API->>PG: UPDATE GraphSession.ended_at

        alt Significant activity (pin OR 3+ visits over 10s OR 2+ traversals)
            API->>BG: spawn incremental anchor update
            BG->>PC: fetch vectors for new signals only
            BG->>BG: new_anchor = (old x old_w + new_vec x new_w) / (old_w + new_w)
            BG->>PG: UPDATE cached_anchor + cached_total_weight
        end
    end

    %% ── NODE PIN ─────────────────────────────────────────────
    rect rgb(240, 230, 255)
        note over User,OAI: Pin a Node
        User->>FE: Pin a tweet
        FE->>API: POST /api/v1/graph/pin/
        API->>PG: INSERT UserGraphNode (source=pinned)
        API->>PC: fetch pinned tweet vector
        API->>PG: fetch existing UserGraph node vectors
        API->>API: compute similarity vs all existing nodes
        API->>PG: INSERT UserGraphEdge records
        API->>BG: spawn incremental anchor update (immediate)
        BG->>PC: fetch pinned tweet vector
        BG->>BG: weighted average update
        BG->>PG: UPDATE cached_anchor + cached_total_weight
        API-->>FE: 200 OK
    end

    %% ── PROFILE GRAPH LOAD ───────────────────────────────────
    rect rgb(235, 255, 245)
        note over User,OAI: Profile Graph Load
        User->>FE: Visit a user profile
        FE->>API: GET /api/v1/graph/profile/user_id/
        API->>PG: SELECT UserGraphNode + UserGraphEdge
        PG-->>API: nodes + edges
        API-->>FE: nodes + edges JSON
        FE->>FE: render profile graph
    end
```

---

## 3. Feed Graph Construction Flow

Detailed flowchart of the feed graph algorithm.

```mermaid
flowchart TD
    START(["Session Start — GET /api/v1/graph/feed/"])

    START --> ANCHOR_CHECK{"cached_anchor\nexists on UserGraph?"}

    subgraph ANCHOR_RESOLUTION["🧠 Anchor Resolution"]
        direction TB
        RECOMPUTE["Full recompute<br/>Fetch all historical signals from Pinecone + DB<br/>Apply recency decay weights across all signals"]
        SAVE_ANCHOR["Save cached_anchor + cached_total_weight<br/>to UserGraph"]
        USE_CACHE["Use cached anchor<br/>Single DB field read — no computation"]
        RECOMPUTE --> SAVE_ANCHOR --> USE_CACHE
    end

    ANCHOR_CHECK -->|"No — first session"| RECOMPUTE
    ANCHOR_CHECK -->|"Yes"| USE_CACHE

    subgraph CANDIDATE_RETRIEVAL["🔍 Candidate Retrieval"]
        direction TB
        VISITED["Load all visited tweet IDs<br/>from NodeVisit table"]
        PINECONE_QUERY["Query Pinecone top-100<br/>Anchor vector — exclude visited IDs inside query<br/>Result set always full-sized regardless of history"]
        RERANK["Recency boost re-rank<br/>score = similarity x e^(-λ x days_since_created)<br/>Take top-50"]
        VISITED --> PINECONE_QUERY --> RERANK
    end

    USE_CACHE --> VISITED

    subgraph GRAPH_CONSTRUCTION["🕸️ Graph Construction"]
        direction TB
        PG_FETCH["Bulk fetch TweetNode objects<br/>from Postgres"]
        EDGES["Pairwise cosine similarity<br/>50 nodes — 1,225 comparisons<br/>Create edge where similarity is above 0.7"]
        PG_FETCH --> EDGES
    end

    RERANK --> PG_FETCH

    EDGES --> RESPONSE(["Return nodes + edges JSON<br/>Frontend renders graph"])
```

---

## 4. Anchor Lifecycle

How the anchor embedding is created, cached, and kept fresh.

```mermaid
stateDiagram-v2
    [*] --> NoAnchor: New user

    state FullRecomputePath {
        [*] --> FetchAllSignals: Fetch all historical signals from Pinecone + DB
        FetchAllSignals --> ApplyDecay: Apply recency decay weights
        ApplyDecay --> ComputeCentroid: Compute weighted centroid
        ComputeCentroid --> PersistAnchor: Save cached_anchor + cached_total_weight
    }

    state IncrementalUpdatePath {
        [*] --> FetchOneVector: Fetch 1 vector from Pinecone
        FetchOneVector --> WeightedAverage: new = (old x old_w + new_vec x new_w) / total_w
        WeightedAverage --> UpdateFields: UPDATE cached_anchor + cached_total_weight
    }

    NoAnchor --> FullRecomputePath: First feed graph request
    FullRecomputePath --> Cached: Anchor ready

    Cached --> IncrementalUpdatePath: User pins a node (immediate, sync)
    Cached --> IncrementalUpdatePath: Session ends with significant activity (async)
    IncrementalUpdatePath --> Cached: Anchor updated

    Cached --> FullRecomputePath: Daily scheduled job — correct accumulated drift
```

---

## 5. Profile Graph vs Feed Graph

How the two graph types differ in construction, storage, and serving.

```mermaid
flowchart LR
    subgraph Profile["Profile Graph"]
        direction TB
        PT["Trigger: tweet created or deleted"]
        PB["fetch all user tweet vectors from Pinecone"]
        PE["pairwise cosine similarity across all tweets"]
        PS["persist to Postgres<br/>UserGraph / UserGraphNode / UserGraphEdge"]
        PR["Profile page load: pure DB read — no computation"]
        PT --> PB --> PE --> PS
        PS -->|"precomputed"| PR
    end

    subgraph Feed["Feed Graph"]
        direction TB
        FT["Trigger: session start"]
        FA["read cached anchor or full recompute"]
        FQ["Pinecone query top-100<br/>exclude visited nodes inside query"]
        FR["recency boost re-rank — take top-50"]
        FE["pairwise cosine similarity on top-50"]
        FJ["return graph JSON — not persisted"]
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
