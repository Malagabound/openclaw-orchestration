# Email Agent

Automated email triage for Alan's 3 Gmail accounts via Maton gateway.

## Accounts
| Email | Maton Connection ID |
|-------|-------------------|
| george@originutah.com | 26429363-7040-4bdc-b7b2-26a040d06a96 |
| alan@originutah.com | 84a9a500-ccea-4a27-9bd8-38cb811904ad |
| alan@roccoriley.com | 5fbd0b9d-1f06-4b12-a791-657279ae14b2 |

## Usage

```bash
# Dry run (no actions taken, just logs what it would do)
node skills/email-agent/scripts/check-email.js --dry-run

# Live run
node skills/email-agent/scripts/check-email.js
```

## Classification Rules (priority order)
1. **Utility bills** (alan@originutah only) → process + update spreadsheet + Label_106 + archive
2. **PM rent breakdowns** (alan@originutah only) → process + update cash flow + archive
3. **Jotform Pinnacle Chiro** (alan@originutah) → archive immediately
4. **Make error emails** (alan@originutah) → archive immediately
5. **Amazon confirmations** (all) → archive immediately
6. **Social notifications** (all) → archive immediately
7. **Newsletters** (all) → extract AI-relevant items → save digest → archive
8. **Needs reply** (all) → draft response → hold for approval
9. **Everything else** → flag + notify Alan via Telegram

## Key Rules
- **NEVER delete emails** — always archive (remove INBOX label)
- **NEVER send replies** — only draft, hold for approval
- Maton gateway at gateway.maton.ai handles OAuth automatically
