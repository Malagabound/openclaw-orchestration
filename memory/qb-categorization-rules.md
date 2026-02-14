# QuickBooks Categorization Rules

This file tracks Alan's categorization decisions so I never ask the same question twice.

## Properties by City

| City | Property | Notes |
|------|----------|-------|
| South Salt Lake | 150 E Garden | |
| West Valley City | 7085 W Cimmarron | WVC Utilities |
| Kearns | 4936 La Brea | Wasatch Front Waste |
| Salt Lake City | 287 N Center | Largest utility bills |
| Salt Lake City | 521-523 N 600 W | Duplex, 2nd largest bills |
| Salt Lake City | 217 N Reed Ave | 3rd largest bills |
| Salt Lake City | 183 Clinton | Smallest SLC bills |
| N/A | Winridge Hawthorne | Main entity, bank fees |
| N/A | Sequence Rentals | Automation app transfers |

## Salt Lake City Utility Bill Ranking (largest to smallest)

When multiple SLC utility bills come through at once, assign by size:
1. **287 N Center** - biggest bills
2. **521-523 N 600 W** (duplex) - 2nd biggest
3. **217 N Reed Ave** - 3rd
4. **183 Clinton** - smallest

**Strategy:** Wait until all 4 SLC utilities arrive, then rank and assign.

## Vendor → Category + Property Rules

| Vendor/Description Pattern | Category | Property | Notes |
|---------------------------|----------|----------|-------|
| Mr Cooper | Mortgage Payment | 521-523 N 600 W | Mortgage servicer |
| CARRINGTON MTG | Mortgage Payment | 183 Clinton | Mortgage servicer |
| Analysis Fee | Bank Charges | Winridge Hawthorne | Bank fee |
| Dividend/Interest | Interest Earned | Winridge Hawthorne | Bank interest |
| WVC UTILITIES | Utilities | 7085 W Cimmarron | West Valley City |
| Wasatch Front Waste | Utilities | 4936 La Brea Kearns | Trash - Kearns |
| Dominion Energy | Utilities | 287 N Center | Gas - Center Street |

## Utility Assignment by City in Memo

| Memo Contains | Property |
|---------------|----------|
| West Valley / WVC | 7085 W Cimmarron |
| Kearns | 4936 La Brea |
| South Salt Lake | 150 E Garden |
| Salt Lake (see ranking above) | Use bill size ranking |

## Account Structure (Important!)

- **Savings is NOT per-property** - Single savings account for all properties
- **Sequence Rentals** - ALL are TRANSFERS (never income/expense)
  - Routes excess rental income out
  - Splits to: Savings + Debt paydown account
- **Walker Hall Savings** - Also transfers, matches with Sequence Rentals
- **"Withdrawal Home A" to Sequence Rentals** = Routing excess for splitting
- **Look for matching pairs** between Sequence and Walker Hall Savings

## Transaction Patterns

| Pattern | Category | Class | Notes |
|---------|----------|-------|-------|
| Deposit from investment | Other Income | Winridge Hawthorne | Not rental income |
| Transfer to WH Savings | Transfer | Winridge Hawthorne | Internal transfer |
| Transfer to Sequence Rentals | Transfer | Winridge Hawthorne | Excess routing |

## Resolved Questions

- **$6,215.23 Deposit** - Investment disbursement (real estate investment, not rental) → Other Income, Winridge Hawthorne
- **$6,215.23 to Savings** - Transfer to savings → Transfer, Winridge Hawthorne  
- **$2,000 to Sequence Rentals** - Routing excess for splitting → Transfer, Winridge Hawthorne

## Decision Log

| Date | Decision | Made By |
|------|----------|---------|
| 2026-02-05 | File created | George |
| 2026-02-05 | Utility ranking for SLC properties | Alan |
| 2026-02-05 | Dominion Energy → 287 N Center | Alan |
| 2026-02-05 | City-based utility assignment rules | Alan |

---
*Updated: 2026-02-05*
| Enbridge Gas | Utilities | 287 N Center | Gas - Center Street |
