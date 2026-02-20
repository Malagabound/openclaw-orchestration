#!/usr/bin/env node
/**
 * Email Agent — Automated email triage for Alan's Gmail accounts.
 * Usage: node check-email.js [--dry-run] [--account <email>] [--max <n>]
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

// ── Config ──────────────────────────────────────────────────────────────────
const MATON_GATEWAY = 'https://gateway.maton.ai/google-mail';

// Read Maton API key from credential file (never hardcode)
const matonCredPath = path.join(process.env.HOME, '.openclaw', 'credentials', 'maton');
let MATON_KEY;
try {
  const raw = fs.readFileSync(matonCredPath, 'utf8').trim();
  MATON_KEY = raw.includes('=') ? raw.split('=').slice(1).join('=').trim() : raw;
} catch (e) {
  console.error(`Fatal: Cannot read Maton credential at ${matonCredPath}: ${e.message}`);
  process.exit(1);
}

const ACCOUNTS = [
  { email: 'george@originutah.com', connId: '26429363-7040-4bdc-b7b2-26a040d06a96' },
  { email: 'alan@originutah.com',   connId: '84a9a500-ccea-4a27-9bd8-38cb811904ad' },
  { email: 'alan@roccoriley.com',   connId: '5fbd0b9d-1f06-4b12-a791-657279ae14b2' },
];

const WINHAW_LABEL = 'Label_106';
const SPREADSHEET_ID = '11HXbgyvNV2GRsslRxeA9kyxx91Vhv1Lx7LY_8siR0xQ';

// ── Args ────────────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const DRY_RUN = args.includes('--dry-run');
const accountFilter = args.includes('--account') ? args[args.indexOf('--account') + 1] : null;
const maxEmails = args.includes('--max') ? parseInt(args[args.indexOf('--max') + 1]) : 50;

// ── HTTP helpers ────────────────────────────────────────────────────────────
function request(url, opts = {}) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, {
      method: opts.method || 'GET',
      headers: opts.headers || {},
    }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        if (res.statusCode >= 400) {
          let hint = '';
          if (res.statusCode === 400) hint = ' (check Maton connection status at ctrl.maton.ai)';
          if (res.statusCode === 401) hint = ' (invalid Maton API key)';
          if (res.statusCode === 429) hint = ' (rate limited — 10 req/sec)';
          reject(new Error(`HTTP ${res.statusCode}${hint}: ${data.slice(0, 300)}`));
        } else {
          try { resolve(JSON.parse(data)); } catch { resolve(data); }
        }
      });
    });
    req.on('error', reject);
    if (opts.body) req.write(typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body));
    req.end();
  });
}

// ── Gmail API helpers (via Maton gateway) ───────────────────────────────────
const GMAIL = `${MATON_GATEWAY}/gmail/v1/users/me`;

async function gmailGet(apiPath, connId) {
  return request(`${GMAIL}${apiPath}`, {
    headers: {
      Authorization: `Bearer ${MATON_KEY}`,
      'Maton-Connection': connId,
    },
  });
}

async function gmailPost(apiPath, connId, body) {
  return request(`${GMAIL}${apiPath}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${MATON_KEY}`,
      'Maton-Connection': connId,
      'Content-Type': 'application/json',
    },
    body,
  });
}

async function listUnread(connId, max) {
  const resp = await gmailGet(`/messages?q=in:inbox+is:unread&maxResults=${max}`, connId);
  return resp.messages || [];
}

async function getMessage(connId, msgId) {
  return gmailGet(`/messages/${msgId}?format=full`, connId);
}

function getHeader(msg, name) {
  const h = (msg.payload?.headers || []).find(h => h.name.toLowerCase() === name.toLowerCase());
  return h?.value || '';
}

function getSnippet(msg) {
  return msg.snippet || '';
}

// ── Classification ──────────────────────────────────────────────────────────
function classify(msg, accountEmail) {
  const from = getHeader(msg, 'From').toLowerCase();
  const subject = getHeader(msg, 'Subject').toLowerCase();
  const snippet = getSnippet(msg).toLowerCase();
  const isAlanOrigin = accountEmail === 'alan@originutah.com';

  // 1. Utility bills (alan@originutah only)
  if (isAlanOrigin && (
    from.includes('xpressbillpay') ||
    from.includes('dominion energy') || subject.includes('dominion energy') ||
    from.includes('enbridge') || subject.includes('enbridge gas')
  )) {
    return { action: 'utility', label: 'Utility Bill', archive: true, addLabel: WINHAW_LABEL };
  }

  // 2. PM rent breakdowns (alan@originutah only)
  if (isAlanOrigin && (
    from.includes('propertymanag') || from.includes('rent manager') ||
    subject.includes('rent breakdown') || subject.includes('owner statement') ||
    subject.includes('property management')
  )) {
    return { action: 'pm-rent', label: 'PM Rent Breakdown', archive: true };
  }

  // 3. Jotform Pinnacle Chiro
  if (isAlanOrigin && from.includes('jotform') && (
    subject.includes('pinnacle chiropractic') || snippet.includes('pinnacle chiropractic')
  )) {
    return { action: 'archive', label: 'Jotform Pinnacle Chiro' };
  }

  // 4. Make error emails - improved pattern matching
  if (isAlanOrigin && from.includes('make') && (
    subject.includes('encountered error') || subject.includes('error in 3')
  )) {
    return { action: 'archive', label: 'Make Error Email' };
  }

  // 5-pre. WordPress (any) — auto-archive per TOOLS.md
  if (isAlanOrigin && from.includes('wordpress@')) {
    return { action: 'archive', label: 'WordPress Notification' };
  }

  // 5-pre2. Left Main Academy — auto-archive per TOOLS.md
  if (from.includes('left main academy') || (from.includes('thinkific.com') && subject.includes('left main academy'))) {
    return { action: 'archive', label: 'Left Main Academy' };
  }

  // 5-pre3. Mercury — transaction declined — auto-archive per TOOLS.md
  if (from.includes('mercury.com') && subject.includes('transaction declined')) {
    return { action: 'archive', label: 'Mercury Declined' };
  }

  // 5-pre4. Mercury — card charged — auto-archive per TOOLS.md
  if (from.includes('mercury.com') && subject.includes('card has been charged')) {
    return { action: 'archive', label: 'Mercury Charge' };
  }

  // 5-pre5. Optimize OS — all notifications — auto-archive per TOOLS.md
  if (from.includes('optimizeos.ai') || from.includes('noreply@optimizeos.ai')) {
    return { action: 'archive', label: 'Optimize OS Notification' };
  }

  // 5a. Google Docs/Sheets/Drive share notifications — auto-archive
  if (from.includes('drive-shares-dm-noreply@') || from.includes('drive-shares-noreply@') ||
      (from.includes('@google.com') && (subject.includes('document shared with you') ||
       subject.includes('spreadsheet shared with you') || subject.includes('shared a file')))) {
    return { action: 'archive', label: 'Google Drive Share' };
  }

  // 5b. Verification codes / OTP — auto-archive (ephemeral)
  if (subject.includes('verification code') || subject.includes('security code') ||
      subject.includes('login code') || subject.includes('one-time') ||
      subject.includes('otp') || subject.includes('confirm your email') ||
      subject.includes('activate your account')) {
    return { action: 'archive', label: 'Verification/OTP' };
  }

  // 5c. Google Workspace / Gmail onboarding — auto-archive
  if ((from.includes('workspace-noreply@google') || from.includes('mail-noreply@google')) &&
      (subject.includes('welcome') || subject.includes('tips') || subject.includes('get the'))) {
    return { action: 'archive', label: 'Google Onboarding' };
  }

  // 5d. Status page incidents (Claude, etc.) — auto-archive
  if (from.includes('statuspage.io') || from.includes('status@')) {
    return { action: 'archive', label: 'Status Page Notification' };
  }

  // 5e. Delivery / shipping notifications (non-Amazon)
  if ((from.includes('uniuni') || from.includes('ups.com') || from.includes('fedex') ||
       from.includes('usps')) && (subject.includes('deliver') || subject.includes('shipment') ||
       subject.includes('tracking'))) {
    return { action: 'archive', label: 'Delivery Notification' };
  }

  // 5f. iTunes / Apple media notifications
  if (from.includes('apple.com') && (subject.includes('new episode') ||
      subject.includes('available for download') || subject.includes('receipt'))) {
    return { action: 'archive', label: 'Apple Media Notification' };
  }

  // 5g. Discord notifications — auto-archive
  if (from.includes('discord.com') && (subject.includes('missed messages') ||
      subject.includes('mentioned') || subject.includes('new messages'))) {
    return { action: 'archive', label: 'Discord Notification' };
  }

  // 5h. HP / printer notifications — auto-archive
  if (from.includes('hp.com') || from.includes('hpsmart.com')) {
    return { action: 'archive', label: 'Printer Notification' };
  }

  // 5i. Mail delivery failures — auto-archive
  if (from.includes('mailer-daemon') || from.includes('postmaster')) {
    return { action: 'archive', label: 'Mail Delivery Failure' };
  }

  // 5. Amazon confirmations
  if ((from.includes('amazon') || from.includes('amazon.com')) && (
    subject.includes('order') || subject.includes('shipping') ||
    subject.includes('delivered') || subject.includes('delivery') ||
    subject.includes('your amazon') || subject.includes('shipment') ||
    subject.includes('shipped') || subject.includes('arriving') ||
    subject.includes('out for delivery')
  )) {
    return { action: 'archive', label: 'Amazon Confirmation' };
  }

  // 6. Social notifications
  const socialDomains = ['facebook', 'facebookmail', 'linkedin', 'twitter', 'instagram', 'noreply@'];
  if (socialDomains.some(d => from.includes(d)) && (
    subject.includes('notification') || subject.includes('mentioned') ||
    subject.includes('liked') || subject.includes('commented') ||
    subject.includes('posted') || subject.includes('invitation') ||
    subject.includes('new follower') || subject.includes('connection') ||
    from.includes('facebookmail') || from.includes('@linkedin.com') ||
    from.includes('@twitter.com') || from.includes('@x.com') ||
    from.includes('@instagram.com')
  )) {
    return { action: 'archive', label: 'Social Notification' };
  }

  // 7. Newsletters
  const newsletterSignals = [
    'unsubscribe', 'newsletter', 'digest', 'weekly update', 'list-unsubscribe'
  ];
  const hasUnsubscribe = (msg.payload?.headers || []).some(
    h => h.name.toLowerCase() === 'list-unsubscribe'
  );
  if (hasUnsubscribe || newsletterSignals.some(s => subject.includes(s) || snippet.includes(s))) {
    return { action: 'newsletter', label: 'Newsletter' };
  }

  // 7b. Satisfaction surveys / rating requests — auto-archive
  const surveySignals = ['how would you rate', 'rate the support', 'satisfaction survey',
    'rate your experience', 'how did we do', 'take our survey', 'leave a review',
    'feedback survey', 'customer satisfaction', 'nps survey', 'rate us'];
  if (surveySignals.some(s => subject.includes(s) || snippet.includes(s))) {
    return { action: 'archive', label: 'Survey/Rating Request' };
  }

  // 8. Needs reply heuristic — direct personal email with question
  const questionSignals = ['?', 'please let me know', 'can you', 'could you', 'would you',
    'are you available', 'when can', 'rsvp', 'respond', 'get back to me'];
  const looksPersonal = !from.includes('noreply') && !from.includes('no-reply') &&
    !from.includes('notifications') && !from.includes('mailer-daemon');
  if (looksPersonal && questionSignals.some(q => subject.includes(q) || snippet.includes(q))) {
    return { action: 'needs-reply', label: 'Needs Reply' };
  }

  // 9. Everything else
  return { action: 'unknown', label: 'Needs Attention' };
}

// ── Actions ─────────────────────────────────────────────────────────────────
async function archiveMessage(connId, msgId) {
  if (DRY_RUN) return;
  await gmailPost(`/messages/${msgId}/modify`, connId, { removeLabelIds: ['INBOX'] });
}

async function addLabelAndArchive(connId, msgId, labelId) {
  if (DRY_RUN) return;
  await gmailPost(`/messages/${msgId}/modify`, connId, {
    addLabelIds: [labelId],
    removeLabelIds: ['INBOX'],
  });
}

// ── Main ────────────────────────────────────────────────────────────────────
async function processAccount(account) {
  const { email, connId } = account;
  console.log(`\n${'═'.repeat(60)}`);
  console.log(`📧 Processing: ${email}`);
  console.log('═'.repeat(60));

  let messages;
  try {
    messages = await listUnread(connId, maxEmails);
  } catch (e) {
    console.error(`  ❌ Failed to list messages: ${e.message}`);
    return { email, error: e.message, results: [] };
  }

  console.log(`  Found ${messages.length} unread messages`);
  const results = [];

  for (const { id } of messages) {
    let msg;
    try {
      msg = await getMessage(connId, id);
    } catch (e) {
      console.error(`  ❌ Failed to get message ${id}: ${e.message}`);
      continue;
    }

    const from = getHeader(msg, 'From');
    const subject = getHeader(msg, 'Subject');
    const classification = classify(msg, email);

    const entry = {
      id,
      from: from.slice(0, 60),
      subject: subject.slice(0, 80),
      classification: classification.label,
      action: classification.action,
    };
    results.push(entry);

    const prefix = DRY_RUN ? '  🔍 [DRY RUN]' : '  ✅';
    console.log(`${prefix} ${classification.label}`);
    console.log(`     From: ${from.slice(0, 60)}`);
    console.log(`     Subject: ${subject.slice(0, 80)}`);

    // Execute action
    try {
      switch (classification.action) {
        case 'utility':
          console.log(`     → Would update spreadsheet ${SPREADSHEET_ID} + add label ${WINHAW_LABEL} + archive`);
          await addLabelAndArchive(connId, id, WINHAW_LABEL);
          break;
        case 'pm-rent':
          console.log(`     → Would update cash flow sheet + archive`);
          await archiveMessage(connId, id);
          break;
        case 'archive':
          console.log(`     → Archive`);
          await archiveMessage(connId, id);
          break;
        case 'newsletter':
          console.log(`     → Would extract AI-relevant items + save digest + archive`);
          await archiveMessage(connId, id);
          break;
        case 'needs-reply':
          console.log(`     → Would draft reply + hold for approval`);
          // Don't archive — keep in inbox for visibility
          break;
        case 'unknown':
        default:
          console.log(`     → Flag as needs-attention + notify Alan`);
          break;
      }
    } catch (e) {
      console.error(`     ❌ Action failed: ${e.message}`);
    }
  }

  return { email, results };
}

async function main() {
  console.log(`\n🤖 Email Agent — ${DRY_RUN ? 'DRY RUN' : 'LIVE'} mode`);
  console.log(`   Max emails per account: ${maxEmails}`);
  console.log(`   Time: ${new Date().toISOString()}\n`);

  const accounts = accountFilter
    ? ACCOUNTS.filter(a => a.email.includes(accountFilter))
    : ACCOUNTS;

  if (accounts.length === 0) {
    console.error('No matching accounts found');
    process.exit(1);
  }

  const allResults = [];
  for (const account of accounts) {
    const result = await processAccount(account);
    allResults.push(result);
  }

  // Summary
  console.log(`\n${'═'.repeat(60)}`);
  console.log('📊 SUMMARY');
  console.log('═'.repeat(60));

  const actionCounts = {};
  let total = 0;
  for (const { email, results, error } of allResults) {
    if (error) {
      console.log(`  ${email}: ERROR — ${error}`);
      continue;
    }
    console.log(`  ${email}: ${results.length} emails processed`);
    for (const r of results) {
      actionCounts[r.classification] = (actionCounts[r.classification] || 0) + 1;
      total++;
    }
  }

  console.log(`\n  Total: ${total} emails`);
  for (const [label, count] of Object.entries(actionCounts).sort((a, b) => b[1] - a[1])) {
    console.log(`    ${label}: ${count}`);
  }

  // Save log
  const logDir = path.join(__dirname, '..', 'logs');
  if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
  const logFile = path.join(logDir, `${new Date().toISOString().slice(0, 10)}.json`);
  const logEntry = { timestamp: new Date().toISOString(), dryRun: DRY_RUN, results: allResults };

  let existing = [];
  if (fs.existsSync(logFile)) {
    try { existing = JSON.parse(fs.readFileSync(logFile, 'utf8')); } catch {}
  }
  existing.push(logEntry);
  fs.writeFileSync(logFile, JSON.stringify(existing, null, 2));
  console.log(`\n  Log saved: ${logFile}`);
}

main().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
