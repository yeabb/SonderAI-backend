# SonderAI — Design Document
> Version 2.0 | April 2026

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
- The graph gets smarter the more you use it — behavioral signals continuously refine what you see

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
- View personal feed graph (semantic discovery)
- View profile graph (your own tweets as a graph)
- Click a node to read the tweet and see its connections
- Basic graph navigation (zoom, pan, node hover highlights neighbors)
- 2D/3D graph toggle
- Onboarding flow — interest selection to seed initial graph
- Global/trending graph for new users with no content yet
- Pin a node ("Add to my graph") — core interaction mechanic
- Save a tweet — strong explicit interest signal

### What's explicitly NOT in MVP (UI)

- Public like/retweet counts
- Comment threads
- Real-time graph updates
- Notifications
- Search
- Mobile app
- Follower graphs

### Data model built now, UI later

The following are built into the data model in Phase 1-3 but not exposed in the UI until later phases:

- Private likes (feed the algorithm, never shown as public counts)
- Traversal tracking (path sequences, dwell time, edge traversals)
- Graph session logging

### Why this scope

The MVP exists to answer one question: **is the graph a better way to discover content?** Everything outside that question is noise at this stage. Social signals are captured from day one so the algorithm can learn, but the UI stays focused on graph navigation until the core value prop is proven.

---

## 3. System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────┐
│                    User's Browser                        │
│              Next.js Frontend (Vercel)                   │
│      react-force-graph-2d/3d (Graph UI, toggleable)      │
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
| Next.js (Vercel) | UI rendering, graph visualization, user interactions, traversal tracking |
| Django API (Fargate) | Business logic, graph construction, embedding orchestration, signal processing |
| Postgres (RDS) | Source of truth for all tweets, users, graphs, interactions |
| Pinecone | Vector similarity search, embedding storage |
| Cognito | User identity, authentication tokens, session management |

### Key Design Decisions

- **Django is a pure API** — no templates, no server-side rendering of HTML, no PyVis
- **Frontend owns all rendering** — Django returns JSON, Next.js renders everything
- **Graph is built server-side** — the API constructs graph JSON and sends it to the frontend
- **Pinecone is not the source of truth** — Postgres is. Pinecone is a search index only
- **No real-time for v1** — graph is fetched on session start, stable within a session
- **Profile graph is precomputed** — rebuilt only on tweet create/delete, served as a cache hit
- **Feed graph rebuilds on session start** — not on every page load within a session

---

## 4. Tech Stack

| Concern | Technology | Reasoning |
|---|---|---|
| Frontend framework | Next.js | Production-standard React framework, SSR for public pages, Vercel-native |
| Frontend hosting | Vercel | Built by Next.js team, zero-config deployment, global CDN |
| Graph visualization | react-force-graph-2d + react-force-graph-3d | Same library, same API — 2D default, 3D toggle. d3-force physics, MIT licensed |
| Backend framework | Django + DRF | Team familiarity, mature ORM, solid REST framework |
| Backend hosting | AWS ECS Fargate | Managed containers, no server management, team has AWS experience |
| Primary database | PostgreSQL (AWS RDS) | Relational, managed, battle-tested for social data |
| Vector database | Pinecone | Already integrated, managed, serverless, strong ANN performance |
| Embeddings | OpenAI text-embedding-3-small (1536d) | Full dimensions — maximum expressiveness for short text |
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
- email             (email, unique)
- interest_tags     (array) — seeded at onboarding, informs initial graph anchor
- created_at        (datetime)
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
- parent_node       (FK → self, nullable)

# Social — data model ready, private signals only (no public counts)
- liked_by          (M2M → UserProfile) — private, feeds algorithm only
- saved_by          (M2M → UserProfile) — private, strong interest signal
- number_of_likes   (int, cached) — used internally, never surfaced in UI
```

### EmbeddingReference
```
EmbeddingReference
- tweet             (FK → TweetNode, unique)
- pinecone_vector_id (string, unique) — same as tweet UUID
- created_at        (datetime)
```

Pinecone stores:
```json
{
  "id": "<tweet_uuid>",
  "values": [...1536 floats...],
  "metadata": {
    "text": "<title> <content>",
    "user_id": "<user_id>",
    "created_at": "<timestamp>"
  }
}
```

### Personal Graph
The user's personal graph is a persistent data structure, not a recomputed artifact.

```
UserGraph
- user              (FK → UserProfile, unique) — one graph per user
- created_at        (datetime)
- updated_at        (datetime)

UserGraphNode
- graph             (FK → UserGraph)
- tweet             (FK → TweetNode)
- source            (enum: created | pinned | seeded) — how it entered the graph
- added_at          (datetime)

UserGraphEdge
- graph             (FK → UserGraph)
- source_node       (FK → UserGraphNode)
- target_node       (FK → UserGraphNode)
- weight            (float) — cosine similarity score
```

Delta updates: when a node is pinned or created, compute its similarity against existing graph nodes and insert new edges where weight ≥ threshold. Never rebuild the full graph — only extend it.

### Interaction Tracking
Captures behavioral signals for anchor embedding computation.

```
GraphSession
- user              (FK → UserProfile)
- started_at        (datetime)
- ended_at          (datetime, nullable)

NodeVisit
- session           (FK → GraphSession)
- tweet             (FK → TweetNode)
- visited_at        (datetime)
- dwell_seconds     (int) — time spent on node
- position_in_path  (int) — order within the session path

EdgeTraversal
- session           (FK → GraphSession)
- from_tweet        (FK → TweetNode)
- to_tweet          (FK → TweetNode)
- traversed_at      (datetime)
```

---

## 6. Two Graph Types

### Profile Graph
- Contains all tweets this user created
- Precomputed and stored as `UserGraph` with source=`created`
- Rebuilt only when user creates or deletes a tweet
- Served as a direct DB read — no computation on load
- Same for every viewer — not personalized per visitor

### Feed Graph (Personal Discovery Graph)
- The user's semantic content discovery surface
- Pulls from content across the entire platform
- Anchored on the user's interest profile (see Section 7)
- Rebuilt on session start, stable within a session
- Gets smarter over time as interaction signals accumulate

---

## 7. Graph Anchor — How We Determine What to Show

The anchor embedding is the starting vector used to query Pinecone for feed graph candidates.

### New users
Embed their `interest_tags` joined as a string: `"AI climate music"` → 1536d vector.

### Returning users
Weighted centroid of signals, in order of weight:

| Signal | Weight | Notes |
|---|---|---|
| Node pin ("Add to my graph") | Highest | Most intentional explicit action |
| Save | High | "I want to return to this" |
| Traversal path depth | High | Genuine interest, not performative |
| Dwell time | Medium | Did they actually read it |
| Node click | Medium | Passive interest |
| Edge traversal | Medium | Which semantic connections resonate |
| Private like | Lower | Useful signal but performative risk |
| Interest tags | Baseline | Always included, gradually down-weighted as behavioral data grows |

Each signal is weighted by **recency decay** (λ=0.01) — older interactions contribute less to the anchor. This keeps the anchor aligned with current interests rather than a stale historical average.

The anchor is a recency-decayed weighted centroid of all content the user has meaningfully interacted with. It is **cached on `UserGraph`** and updated incrementally — not recomputed from scratch on every session.

### Anchor caching and incremental updates

The anchor and its total weight are stored on `UserGraph`:
- `cached_anchor` — the 1536d vector
- `cached_total_weight` — the sum of all signal weights used to compute it
- `anchor_updated_at` — when it was last computed

**Incremental update formula** — when a new signal arrives, the anchor is nudged toward the new content without touching historical data:
```
new_anchor = (old_anchor * old_total_weight + new_vector * new_weight)
             / (old_total_weight + new_weight)
```
This requires only one Pinecone fetch (for the new signal's vector) and one vector math operation. No iteration over historical interactions.

**When incremental updates are triggered:**
- **Pin action** — immediately, synchronously. Strongest signal, should reflect right away.
- **Session end with significant activity** — asynchronously after the session closes. "Significant" means at least one pin, or 3+ node visits with dwell > 10s, or 2+ edge traversals.

**When full recomputes happen:**
- First session ever (no cached anchor exists yet)
- Daily scheduled background job — corrects accumulated floating point drift from many incremental updates and re-applies recency decay to all historical signals

### Anchor drift
As the user navigates the graph and follows edges into new semantic territory, their interaction history naturally shifts. The anchor drifts over time to reflect where the user has been exploring — meaning the feed graph self-refreshes through use without any explicit tuning. This is a first-class mechanism, not a side effect.

### Global / trending graph
For users with no content or signals: embed a representative string of broad topics as a fallback anchor. Replaced by real signals as soon as interaction data exists.

---

## 8. Graph Construction Algorithm

### Feed Graph Construction (on session start)

**Step 1 — Compute anchor embedding**
Derive the anchor vector from the user's interaction history (Section 7).

**Step 2 — Candidate retrieval**
Query Pinecone for top-100 candidates (larger pool to give re-ranking room to work), excluding tweets the user has already visited:
```python
visited_ids = NodeVisit.objects.filter(session__user=user).values_list("tweet_id", flat=True)

results = pinecone.query(
    vector=anchor_embedding,
    top_k=100,
    include_values=True,
    filter={"tweet_id": {"$nin": list(visited_ids)}}
)
```
Excluding seen content **inside the Pinecone query** (not post-filter) ensures the result set is always full-sized regardless of how much content the user has already seen. Post-filter would shrink the graph over time.

**Step 3 — Recency-boosted re-ranking**
Re-rank the 100 candidates by combining semantic similarity with a recency decay factor. Recent content gets a boost without completely burying highly relevant older content:
```python
final_score = similarity_score * e^(-λ * days_since_created)  # λ=0.01
```
Take the top-50 by final score. These are the nodes that enter the graph.

**Step 4 — Fetch tweet objects**
Bulk fetch from Postgres:
```python
tweet_nodes = TweetNode.objects.filter(id__in=top_50_ids)
```

**Step 5 — Edge construction (pairwise, in-memory)**
Do NOT re-query Pinecone per node. All vectors are already in memory from Step 2.
```python
for each pair (i, j) in candidates:
    similarity = cosine_similarity(embedding_i, embedding_j)
    if similarity >= EDGE_THRESHOLD:
        add edge(i, j, weight=similarity)
```

**Edge threshold:** Static `0.7` for MVP. Tunable.
**Complexity:** O(n²). At n=50 → 1,225 comparisons. Trivially fast.

**Step 6 — Return graph JSON**
```json
{
  "nodes": [
    {
      "id": "tweet-uuid",
      "title": "Tweet title",
      "content": "Tweet content...",
      "user": "username",
      "created_at": "2026-04-01T...",
      "source": "discovered"
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

### Profile Graph Construction (on tweet create/delete)

Triggered by tweet creation or deletion, not by page load.

1. Fetch all tweet UUIDs for the user from Postgres
2. Fetch all corresponding embedding vectors from Pinecone
3. Compute pairwise cosine similarity
4. Persist as `UserGraph` / `UserGraphNode` / `UserGraphEdge` records
5. On load: pure DB read, no computation

### Personal Graph Delta Update (on node pin)

When a user pins a node into their personal graph:
1. Fetch the new node's embedding from Pinecone
2. Fetch embeddings of all existing nodes in the user's `UserGraph`
3. Compute similarity between new node and all existing nodes
4. Insert `UserGraphNode` record (source=`pinned`)
5. Insert `UserGraphEdge` records for all pairs where weight ≥ threshold

Never rebuilds the full graph — only extends it.

### Clustering (v2)
Group nodes into topic clusters using HDBSCAN on embedding vectors. Used for visual grouping, not connectivity boundary — nodes in different clusters can still have edges.

---

## 9. Content Freshness Strategy

Content freshness is solved at multiple layers, each operating at a different timescale:

| Layer | Mechanism | Timescale |
|---|---|---|
| Seen-content exclusion | Visited tweet IDs excluded inside Pinecone query | Per session |
| Recency-boosted ranking | `similarity * e^(-λ * days_since_created)` re-ranks candidates | Per session |
| Anchor drift | Navigation shifts interaction history → anchor evolves naturally | Across sessions |
| Anchor recomputation | Triggered by significant interaction events + scheduled fallback | Across sessions |
| Content volume | New tweets upserted to Pinecone immediately, available in next query | Real-time |

### Content staleness — the honest picture
If no new relevant content has been created since the last session, the candidate pool from Pinecone is identical regardless of re-ranking. This is a **content supply problem**, not an algorithm problem. It is ultimately solved by platform growth and content volume. At MVP scale this is acceptable and expected.

### Serendipity injection (v2)
Reserve a portion of the graph for content slightly outside the user's current anchor — queried from a semantically adjacent vector. Accelerates discovery into new topic territory and naturally expands the anchor over time. Deferred until content volume makes it meaningful.

---

## 10. Graph UI — Lenses and Views

The underlying graph data is always complete. What the user sees at any moment is a **lens** over it.

### Default view
Depth-limited: show nodes within 2-3 hops of the current entry point. User chooses where to start and explores outward. Keeps the rendered graph manageable regardless of total graph size.

### Available lenses
- **Depth view** (default) — 2-3 hops from current node
- **Recency lens** — surface recently interacted nodes, fade out stale ones
- **Cluster lens** — topic clusters collapse into blobs, click to expand (v2, requires clustering)
- **Created filter** — show only tweets the user wrote
- **Pinned filter** — show only tweets the user pinned from elsewhere

### 2D / 3D toggle
Both views ship together. `react-force-graph-2d` and `react-force-graph-3d` share the same API — switching is a component swap. 2D is the default. User can toggle to 3D at any time.

### Visual distinction
Nodes the user **created** vs. nodes they **pinned** render with different visual treatment (color, shape, or border). Filterable but coexist in the same graph space so cross-connections are always visible.

---

## 11. API Design

All endpoints are prefixed with `/api/v1/`.

### Auth
Handled by Cognito. Django validates the Cognito JWT on every protected request.

### Tweets
```
POST   /api/v1/tweets/              — create a tweet
GET    /api/v1/tweets/{id}/         — get a single tweet
DELETE /api/v1/tweets/{id}/         — delete a tweet (owner only)
```

### Graph
```
GET    /api/v1/graph/feed/          — get the user's personal feed graph (session-scoped)
GET    /api/v1/graph/profile/{id}/  — get a user's profile graph (precomputed)
GET    /api/v1/graph/global/        — get the global/trending graph
GET    /api/v1/graph/node/{id}/     — get the local neighborhood graph for a node
```

### Personal Graph
```
POST   /api/v1/graph/pin/           — pin a node into the user's personal graph
DELETE /api/v1/graph/pin/{id}/      — unpin a node
GET    /api/v1/graph/personal/      — get the user's full personal graph
```

### Interactions
```
POST   /api/v1/interactions/like/   — private like (feeds algorithm, not surfaced in UI)
POST   /api/v1/interactions/save/   — save a tweet
POST   /api/v1/interactions/session/ — start a graph session
POST   /api/v1/interactions/visit/  — record a node visit + dwell time
POST   /api/v1/interactions/traverse/ — record an edge traversal
```

### Users
```
POST   /api/v1/users/onboarding/    — save interest tags after signup
GET    /api/v1/users/me/            — get current user profile
```

---

## 12. Frontend Architecture

### Pages (Next.js routes)
```
/                       — landing page (logged out)
/signup                 — sign up flow
/login                  — log in
/onboarding             — interest selection (post signup)
/home                   — feed graph view (protected)
/profile/[username]     — profile graph view (protected)
/tweet/[id]             — single tweet detail view (protected)
```

### Graph Component
Built on `react-force-graph-2d` / `react-force-graph-3d` with a toggle. Key behaviors:

- **On load**: fetch graph data, render with physics simulation, start session
- **Node hover**: highlight node + direct neighbors, dim everything else
- **Node click**: open tweet detail panel (slide in from side), record node visit + start dwell timer
- **Panel close / next node**: record dwell time, close panel
- **Edge click / follow**: record edge traversal, shift graph focus to target node
- **Background click**: collapse detail panel, return to full graph
- **Edge visibility**: opacity proportional to similarity weight
- **2D/3D toggle**: swap component, preserve graph state
- **Lens switcher**: UI control to switch between depth/recency/cluster/filter views
- **Zoom/pan**: built in

### Physics Configuration
Tuned to produce the Obsidian-like "alive" feeling:
- Node charge (repulsion): negative, so nodes naturally spread
- Link distance: proportional to inverse similarity (similar nodes sit closer)
- Collision radius: prevents node overlap
- Alpha decay: slow enough that the graph feels continuously alive, not snapped

### State Management
React state + fetch for MVP. No Redux needed at this scale.

---

## 13. Infrastructure

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

## 14. Open Decisions

| Decision | Options | Notes |
|---|---|---|
| Embedding content strategy | Content only vs content + metadata | Start with content only, measure quality |
| Edge threshold value | Static (0.7?) vs dynamic (percentile-based) | Start static, tune with real data |
| Top-K candidate count | 25, 50, 100 | Start at 50, adjust based on graph density |
| Clustering algorithm | HDBSCAN vs K-means | Defer to v2 entirely |
| Comment system design | Graph-native threading vs standard comments | Needs design thought — standard comments contradict the platform philosophy |
| Monetization | Subscription, B2B, creator tools | Post product-market fit |

---

## 15. What We Are Not Building (Explicit Anti-Patterns)

- **No infinite scroll** — intentional navigation only
- **No algorithmic feed** — the graph IS the discovery mechanism
- **No engagement optimization** — we do not optimize for time-on-platform
- **No opaque recommendations** — every connection is visible and traversable
- **No public engagement counts** — likes and saves are private signals, never shown as vanity metrics
- **No comment threads (for now)** — needs design thought before building; standard comment threads contradict intentional navigation
- **No PyVis** — removed entirely, replaced by react-force-graph-2d/3d
- **No Django templates** — pure API backend only

---

## 16. Future Roadmap

**v2 — Social Layer**
- Comment system (reimagined for graph-native context, not threaded replies)
- Follower graphs — who you follow influences feed graph anchor weighting
- Cluster-level filtering and lens (requires HDBSCAN)

**v3 — Personalization**
- Full interaction-weighted anchor embeddings replace interest-tag baseline
- Personalized edge thresholds per user
- Traversal path analysis — surface content along paths the user tends to explore

**v4 — Scale & Performance**
- Incremental graph updates (WebSocket) — live node additions without full reload
- Graph caching layer with smart invalidation
- Migrate graph rendering to d3-force + PixiJS if react-force-graph hits limits at scale

**Future**
- Mobile app (React Native)
- B2B / white-label graph tech
- Topic trend insights
- Creator monetization tools
