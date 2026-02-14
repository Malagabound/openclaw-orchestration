# Email Agent

Automated email triage for Alan's 3 Gmail accounts via Nango OAuth.

## Accounts
| Email | Nango Connection ID |
|-------|-------------------|
| george@originutah.com | e98c0c58-19d5-405c-8b7e-da378c55d49d |
| alan@originutah.com | 3361470f-2fc4-4291-8ab8-d929ae60e4b6 |
| alan@roccoriley.com | 1ecf42ca-9d74-40e2-9d2e-4515da3a9797 |

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
- Nango at localhost:3003 provides fresh OAuth tokens
