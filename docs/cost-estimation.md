# Jobre — Infrastructure Sizing & Monthly Cost Estimation (10,000+ Sources)

## 1. Workload Profile at Target Scale

- **Monitored Sources:** `10,000` active career portals & job boards
- **Average Refresh Cadence:** Every `6 hours` (`40,000` ingestion runs/day ≈ `0.46` runs/sec average, `~2.5` runs/sec peak)
- **Active Canonical Jobs:** `~500,000 – 1,200,000` active jobs (`~3.5 GB` relational data + indexes in PostgreSQL)
- **Raw Compressed Snapshots (`.json.gz`):** `~40,000` runs/day × `~35 KB` compressed avg ≈ `1.4 GB/day` (`~42 GB/month` hot S3/R2 storage)

---

## 2. Lean Production Deployment (~$145–$260 / month)

Because Jobre uses a modular Python/FastAPI monolith, lightweight async HTTP (`httpx`) rather than headless browsers, and PostgreSQL 17 `GIN` FTS (or a single OpenSearch node), 10,000+ sources run comfortably without Kubernetes or Kafka:

| Component | Recommended Sizing | Est. Monthly Cost (USD) |
|---|---|---:|
| **API + Next.js Web Tier** | 2 × 2 vCPU / 4 GB RAM instances (Hetzner Cloud / AWS Lightsail / ECS Fargate) | $30 – $60 |
| **Async Ingestion Workers** | 2 × 2 vCPU / 4 GB RAM worker nodes (concurrency 12 async coroutines each) | $30 – $60 |
| **PostgreSQL 17 Primary + Backups** | 4 vCPU / 16 GB RAM, 160 GB NVMe SSD + daily PITR | $55 – $95 |
| **Redis 7 Queue & Rate-Limit Store** | 1 GB RAM instance / managed Redis | $10 – $15 |
| **Raw Snapshot Object Storage** | Cloudflare R2 / AWS S3 (`~150 GB` rolling 90-day `.json.gz` retention) | $3 – $8 |
| **Monitoring & Logs** | Prometheus + Grafana Cloud Free/Starter tier | $0 – $20 |
| **Total Lean Production** | **10,000+ Sources / ~1M Active Jobs** | **$128 – $258 / mo** |

---

## 3. High-Availability Enterprise Tier (~$650–$950 / month)

When scaling beyond `50,000+` sources or `>5M` active jobs with dedicated multi-AZ OpenSearch:
- Multi-AZ Managed PostgreSQL 17 (`db.m7g.large`): `~$260/mo`
- Dedicated 2-node OpenSearch cluster (`t3.medium.search` × 2): `~$150/mo`
- Managed Redis replication group: `~$45/mo`
- Autoscaled API/Web/Worker ECS/Kubernetes pool + ALB + NAT/egress: `~$220–$450/mo`
