# Data Import Module API Endpoints

**Total Endpoints: 21**

## Summary by HTTP Method

| Method | Count |
|--------|-------|
| GET    | 6     |
| POST   | 13    |
| PATCH  | 2     |

## Endpoint Categories

| Category | Count |
|----------|-------|
| Main Import Routes | 11 |
| Error Management | 5 |
| QStash Workers | 5 |

---

## 1. Main Import Routes (`/api/data-imports/`)

### Import Operations

| Endpoint | Method | Description | Access |
|----------|--------|-------------|--------|
| `/api/data-imports/run` | POST | Trigger full 4-worker import pipeline | System Admin |
| `/api/data-imports/run-worker` | POST | Run single worker independently | System Admin |
| `/api/data-imports/preview` | POST | Preview import without DB changes | System Admin |
| `/api/data-imports/cancel` | POST | Cancel stuck import pipeline | System Admin |

### Import Status & History

| Endpoint | Method | Description | Access |
|----------|--------|-------------|--------|
| `/api/data-imports/status` | GET | Get current pipeline status | Admin |
| `/api/data-imports/activity` | GET | Get import activity log | Admin |
| `/api/data-imports/history` | GET | Get paginated import history | Admin |

### Import Instance Operations

| Endpoint | Method | Description | Access |
|----------|--------|-------------|--------|
| `/api/data-imports/[id]/retry` | POST | Retry failed pipeline from failure point | System Admin |
| `/api/data-imports/[id]/rollback` | POST | Destructive rollback of pipeline | System Admin |

---

## 2. Error Management Routes (`/api/data-imports/errors/`)

| Endpoint | Method | Description | Access |
|----------|--------|-------------|--------|
| `/api/data-imports/errors` | GET | List all import errors (paginated) | Admin |
| `/api/data-imports/errors` | PATCH | Batch update/dismiss errors | Admin |
| `/api/data-imports/errors/[id]` | GET | Get specific error details | Admin |
| `/api/data-imports/errors/[id]` | PATCH | Update error with orphan resolution | Admin |
| `/api/data-imports/errors/[id]/retry` | POST | Re-process failed import row | System Admin |

---

## 3. QStash Worker Endpoints (`/api/workers/`)

These are webhook endpoints called by QStash for scheduled/chained import operations:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workers/import-check-files` | POST | Scheduled file checker (detects new files) |
| `/api/workers/import-ignition-subscriptions` | POST | Worker 1: Import Ignition subscriptions |
| `/api/workers/import-taxdome-accounts` | POST | Worker 2: Import TaxDome accounts |
| `/api/workers/import-ignition-revenue` | POST | Worker 3: Import Ignition revenue |
| `/api/workers/import-stripe-payments` | POST | Worker 4: Import Stripe payments (final) |

---

## Import Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    IMPORT PIPELINE                              │
├─────────────────────────────────────────────────────────────────┤
│  File Check     → Detects new files in Google Drive            │
│       ↓                                                         │
│  Worker 1       → Ignition Subscriptions (client matching)      │
│       ↓                                                         │
│  Worker 2       → TaxDome Accounts (account linking)            │
│       ↓                                                         │
│  Worker 3       → Ignition Revenue (revenue transactions)       │
│       ↓                                                         │
│  Worker 4       → Stripe Payments (payment reconciliation)      │
│       ↓                                                         │
│  Complete       → Notifications sent                            │
└─────────────────────────────────────────────────────────────────┘
```

---

*Generated: 2026-01-02*
*Source: Analysis of `src/app/api/data-imports/` and `src/app/api/workers/` directories*
