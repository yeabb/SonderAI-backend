# SonderAI — Design Document
> Version 1.0 | April 2026

---

## 1. Problem & Vision

### The Problem

Current social media platforms sit at two extremes:

**Social platforms (Twitter, Instagram, TikTok)**
- Optimized for passive, compulsive consumption
- Infinite scroll removes the user's decision to stop
- Black-box algorithms decide what you see next
- Zero transparency into why content is recommended
- Users are passengers, not navigators

**Knowledge tools (Obsidian, Notion, Roam)**
- Great for structured thinking and graph visualization
- Not social — no real-time content discovery or community
- Private by default, not designed for content sharing at scale

**The gap:** No platform exists that combines the social, discovery, and sharing aspects of Twitter with the intentional, graph-based, relationship-driven navigation of Obsidian.

### The Vision

SonderAI is a **graph-native social platform** where:

- Content is created like Twitter (short posts, called tweets)
- The primary interface is an **interactive semantic graph**, not a feed
- Every piece of content becomes a **node**
- Relationships between content are made **visible as edges**
- Users navigate content **intentionally** — they choose where to go next
- The algorithm is **transparent** — the graph IS the recommendation system
- Users can **go deep** on topics by following semantic connections

### Core Principles

1. **Intentionality over passivity** — users navigate, not scroll
2. **Transparency over black-boxes** — the graph shows why content is related
3. **Depth over volume** — explore a topic thoroughly, not superficially
4. **Control over manipulation** — users decide what they engage with

### The Name

"Sonder" — the realization that each passerby has a life as vivid and complex as your own. Applied here: every piece of content has its own web of connections, ideas, and relationships waiting to be discovered.

---

## 2. MVP Scope

### What's in MVP

- User authentication (sign up, sign in, sign out)
- Create tweets (title + content)
- View personal semantic graph
- Click a node to read the tweet and see its connections
- Basic graph navigation (zoom, pan, node hover highlights neighbors)
- Onboarding flow — interest selection to seed initial graph
- Global/trending graph for new users with no content yet

### What's explicitly NOT in MVP

- Likes, retweets, replies (data model supports them, UI does not expose them yet)
- Real-time graph updates
- Notifications
- User profiles / follower graphs
- Search
- Mobile app

### Why this scope

The MVP exists to answer one question: **is the graph a better way to discover content?** Everything outside that question is noise at this stage. Social features are added in v2, and when they are, they feed back into the recommendation weights — but that complexity comes after the core value prop is proven.

---

## 3. System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────┐
│                    User's Browser                        │
│              Next.js Frontend (Vercel)                   │
│         react-force-graph-2d (Graph UI)                  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS (REST API)
┌──────────────────────▼──────────────────────────────────┐
│                  AWS Application Layer                    │
│            Django REST API (ECS Fargate)                 │
│                  behind ALB                              │
└──────┬───────────────┬──────────────────┬───────────────┘
       │               │                  │
┌──────▼──────┐ ┌──────▼──────┐ ┌────────▼──────┐
│  AWS RDS    │ │  Pinecone   │ │  AWS Cognito  │
│ (Postgres)  │ │ (Vector DB) │ │    (Auth)     │
└─────────────┘ └─────────────┘ └───────────────┘
```

### Separation of Concerns

| Layer | Responsibility |
|---|---|
| Next.js (Vercel) | UI rendering, graph visualization, user interactions |
| Django API (Fargate) | Business logic, graph construction, embedding orchestration |
| Postgres (RDS) | Source of truth for all tweets, users, relationships |
| Pinecone | Vector similarity search, embedding storage |
| Cognito | User identity, authentication tokens, session management |

### Key Design Decisions

- **Django is a pure API** — no templates, no server-side rendering of HTML, no PyVis
- **Frontend owns all rendering** — Django returns JSON, Next.js renders everything
- **Graph is built server-side** — the API constructs graph JSON and sends it to the frontend
- **Pinecone is not the source of truth** — Postgres is. Pinecone is a search index only
- **No real-time for v1** — graph is fetched on load, refreshed on demand

---

## 4. Tech Stack

| Concern | Technology | Reasoning |
|---|---|---|
| Frontend framework | Next.js | Production-standard React framework, SSR for public pages, Vercel-native |
| Frontend hosting | Vercel | Built by Next.js team, zero-config deployment, global CDN |
| Graph visualization | react-force-graph-2d | d3-force physics (same engine as Obsidian-like tools), actively maintained, MIT licensed |
| Backend framework | Django + DRF | Team familiarity, mature ORM, solid REST framework |
| Backend hosting | AWS ECS Fargate | Managed containers, no server management, team has AWS experience |
| Primary database | PostgreSQL (AWS RDS) | Relational, managed, battle-tested for social data |
| Vector database | Pinecone | Already integrated, managed, serverless, strong ANN performance |
| Embeddings | OpenAI text-embedding-3-small (1024d) | Already integrated, strong semantic quality |
| Authentication | AWS Cognito | AWS-native, integrates with existing infra, handles OAuth/email auth |
| Container registry | AWS ECR | Native Fargate integration |
| Load balancer | AWS ALB | Standard, integrates with ECS |
| DNS | AWS Route 53 | AWS-native, reliable |
| Secrets management | AWS Secrets Manager | API keys, DB credentials — never in code |
| Logging & monitoring | AWS CloudWatch | Native to Fargate, centralized logs |

---

## 5. Data Model

### User
Handled by AWS Cognito for identity. A lightweight mirror record in Postgres stores app-specific user data.

```
UserProfile
- cognito_id        (string, unique) — links to Cognito identity
- username          (string, unique)
- created_at        (datetime)
- interest_tags     (array) — seeded at onboarding, informs initial graph
```

### TweetNode
The core content entity.

```
TweetNode
- id                (uuid, primary key)
- user              (FK → UserProfile, CASCADE)
- title             (string, max 25 chars)
- content           (text, max 280 chars)
- created_at        (datetime, auto)
- updated_at        (datetime, auto)

# Threading (future)
- parent_node       (FK → self, nullable) — for thread replies

# Social (data model ready, not exposed in MVP UI)
- liked_by          (M2M → UserProfile)
- retweeted_by      (M2M → UserProfile)
- number_of_likes   (int, cached count)
- number_of_retweets (int, cached count)
- is_retweet        (bool)
- original_tweet    (FK → self, nullable)
- replies           (M2M → self, asymmetric)
```

### Embedding
Embeddings live in Pinecone. The Postgres record is a lightweight reference.

```
EmbeddingReference (Postgres)
- tweet_id          (FK → TweetNode, unique)
- pinecone_vector_id (string) — the ID used to query Pinecone
- created_at        (datetime)
```

Pinecone stores:
```
{
  id: "<tweet_id>",
  values: [...1024 floats...],
  metadata: {
    text: "<title> <content>",
    user_id: "<user_id>",
    created_at: "<timestamp>"
  }
}
```

---

## 6. Graph Construction Algorithm

This is the core of the system. It runs server-side per request.

### Step 1 — Anchor Embedding
Determine the query vector to seed the graph with:
- **Returning user**: derive from their interest profile / interaction history (v2)
- **New user / MVP**: use the embedding of their stated interest tags from onboarding
- **Fallback**: use a global trending embedding

### Step 2 — Candidate Retrieval
Query Pinecone for top-K most semantically similar tweets:
```
top_k = 50  # tunable
results = pinecone.query(vector=anchor_embedding, top_k=50, include_values=True)
```
Returns: list of `{ tweet_id, embedding_vector, similarity_score }`

### Step 3 — Fetch Tweet Objects
Bulk fetch from Postgres:
```python
tweet_nodes = TweetNode.objects.filter(id__in=list_of_ids)
tweet_map = { str(tweet.id): tweet for tweet in tweet_nodes }
```

### Step 4 — Edge Construction (Pairwise, In-Memory)
**Critical:** do NOT re-query Pinecone per node. All vectors are already in memory from Step 2. Compute pairwise cosine similarity within the candidate set:

```python
for each pair (i, j) in candidates:
    similarity = cosine_similarity(embedding_i, embedding_j)
    if similarity >= EDGE_THRESHOLD:
        add edge(i, j, weight=similarity)
```

**Edge threshold:** Static value for MVP (e.g. `0.7`). Higher = fewer, stronger edges. Lower = denser graph. This is tunable.

**Complexity:** O(n²) where n = top_k. At n=50, that's 1,225 comparisons — trivially fast. At n=200, it's 19,900 — still fast. This only becomes a concern at n > 1000.

### Step 5 — Clustering (v2)
Group nodes into topic clusters using HDBSCAN or K-means on the embedding vectors. Used for visual grouping in the UI, not as a connectivity boundary — nodes in different clusters can still have edges.

### Step 6 — Graph Output
Return JSON to frontend:

```json
{
  "nodes": [
    {
      "id": "tweet-uuid",
      "title": "Tweet title",
      "content": "Tweet content...",
      "user": "username",
      "created_at": "2026-04-01T...",
      "cluster_id": 2
    }
  ],
  "edges": [
    {
      "source": "tweet-uuid-1",
      "target": "tweet-uuid-2",
      "weight": 0.87
    }
  ]
}
```

---

## 7. API Design

All endpoints are prefixed with `/api/v1/`.

### Auth
Handled by Cognito. Django validates the Cognito JWT on every protected request.

### Tweets
```
POST   /api/v1/tweets/          — create a tweet
GET    /api/v1/tweets/{id}/     — get a single tweet
DELETE /api/v1/tweets/{id}/     — delete a tweet (owner only)
```

### Graph
```
GET    /api/v1/graph/home/      — get the user's personal graph
GET    /api/v1/graph/global/    — get the global/trending graph
GET    /api/v1/graph/node/{id}/ — get the local neighborhood graph for a node
```

### Users
```
POST   /api/v1/users/onboarding/ — save interest tags after signup
GET    /api/v1/users/me/         — get current user profile
```

---

## 8. Frontend Architecture

### Pages (Next.js routes)
```
/                   — landing page (logged out)
/signup             — sign up flow
/login              — log in
/onboarding         — interest selection (post signup)
/home               — main graph view (protected)
/tweet/[id]         — single tweet detail view (protected)
```

### Graph Component
Built on `react-force-graph-2d`. Key behaviors:

- **On load**: fetch `/api/v1/graph/home/`, render graph with physics simulation
- **Node hover**: highlight node + direct neighbors, dim everything else
- **Node click**: open tweet detail panel (slide in from side, no page navigation)
- **Background click**: collapse detail panel, return to full graph
- **Edge visibility**: edges shown with opacity proportional to similarity weight
- **Zoom/pan**: built in via react-force-graph-2d

### Physics Configuration
Tuned to produce the Obsidian-like "alive" feeling:
- Node charge (repulsion): negative, so nodes naturally spread
- Link distance: proportional to inverse similarity (similar nodes sit closer)
- Collision radius: prevents node overlap
- Alpha decay: slow enough that the graph feels continuously alive, not snapped

### State Management
Simple for MVP — React state + fetch. No Redux needed at this scale.

---

## 9. Infrastructure

### AWS Setup

```
Route 53 (DNS)
    │
    ▼
CloudFront (CDN for API — optional at launch)
    │
    ▼
ALB (Application Load Balancer)
    │
    ▼
ECS Fargate (Django API containers)
    │
    ├── RDS Postgres (private subnet)
    ├── Pinecone (external, via HTTPS)
    └── Cognito (external, via HTTPS)

ECR — stores Docker images
Secrets Manager — stores all API keys and DB credentials
CloudWatch — logs and basic metrics
```

### Environments
- `production` — live, AWS
- `staging` — AWS (same infra, smaller sizing)
- `local` — Docker Compose (Django + Postgres locally, Pinecone dev index)

### CI/CD
GitHub Actions:
1. Push to `main` → run tests
2. On merge to `main` → build Docker image → push to ECR → deploy to ECS Fargate
3. Frontend: Vercel auto-deploys on push to `main`

---

## 10. Open Decisions

These are explicitly deferred — do not block building MVP on these.

| Decision | Options | Notes |
|---|---|---|
| Embedding content strategy | Content only vs content + metadata vs user-weighted | Start with content only, measure quality |
| Edge threshold value | Static (0.7?) vs dynamic (percentile-based) | Start static, tune with real data |
| Top-K candidate count | 25, 50, 100 | Start at 50, adjust based on graph density |
| Clustering algorithm | HDBSCAN vs K-means | Defer to v2 entirely |
| 2D vs 3D graph | 2D default, 3D prototype | User test both before deciding |
| Social feature design | Standard vs reimagined (no public counts, etc.) | Deliberate design decision for v2 |
| Monetization | Subscription, B2B, creator tools | Post product-market fit |

---

## 11. What We Are Not Building (Explicit Anti-Patterns)

- **No infinite scroll** — intentional navigation only
- **No algorithmic feed** — the graph IS the discovery mechanism
- **No engagement optimization** — we do not optimize for time-on-platform
- **No opaque recommendations** — every connection is visible and traversable
- **No PyVis** — removed entirely, replaced by react-force-graph-2d
- **No Django templates** — pure API backend only

---

## 12. Future Roadmap (Post-MVP)

**v2 — Social Layer**
- Likes, replies, retweets (reimagined for intentional use)
- Social signals feed back into edge weights and graph ordering
- User profiles and follower graphs

**v3 — Personalization**
- True user interest embeddings derived from interaction history
- Personalized edge thresholds
- Cluster-level filtering and navigation

**v4 — Scale & Performance**
- Graph caching layer (pre-built graphs, invalidated on new content)
- Incremental graph updates (WebSocket, no full reload)
- Migrate graph rendering to d3-force + PixiJS if react-force-graph-2d hits limits

**Future**
- Mobile app (React Native)
- B2B / white-label graph tech
- Topic trend insights
- Creator monetization tools
