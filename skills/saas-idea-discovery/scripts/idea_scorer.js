#!/usr/bin/env node
// Idea scorer for micro-SaaS discovery
// Usage: node idea_scorer.js '<json_post_data>'
// Input: JSON string with fields: title, selftext, score, num_comments

const COMPLEX_KEYWORDS = /(machine learning|ML|AI model|real.?time|blockchain|cryptocurrency|video processing|3D|VR|AR|multiplayer)/i;
const SIMPLE_KEYWORDS = /(convert|export|import|generate|track|monitor|notify|alert|schedule|bookmark|save|organize|format|validate|check)/i;
const COMPLAINT_KEYWORDS = /(frustrated|annoying|terrible|awful|hate|expensive|overpriced|bloated|complicated|overkill|slow|buggy|broken)/i;
const BUSINESS_KEYWORDS = /(business|company|team|client|customer|invoice|report|dashboard|analytics|CRM|project|freelanc|agency|startup)/i;
const MOAT_KEYWORDS = /(Google|Microsoft|Amazon|Apple|Meta|Salesforce|Stripe|Slack|Notion|Figma|Canva)/i;

function scoreIdea(post) {
  const text = `${post.title || ''} ${post.selftext || ''}`.toLowerCase();
  const upvotes = post.score || 0;
  const comments = post.num_comments || 0;
  
  // 1. Buildable in <1 week (0-20)
  let buildable = 10; // default middle
  if (SIMPLE_KEYWORDS.test(text)) buildable += 5;
  if (!COMPLEX_KEYWORDS.test(text)) buildable += 5;
  if (text.length < 500) buildable += 2; // simple problem = short description
  buildable = Math.min(buildable, 20);
  
  // 2. Clear single use case (0-20)
  let clearUseCase = 10;
  if (SIMPLE_KEYWORDS.test(text)) clearUseCase += 5;
  const sentences = text.split(/[.!?]+/).filter(s => s.trim().length > 10);
  if (sentences.length <= 5) clearUseCase += 3; // concise = focused
  if (/(just|simply|only|single)/i.test(text)) clearUseCase += 2;
  clearUseCase = Math.min(clearUseCase, 20);
  
  // 3. Existing solutions suck (0-15)
  let existingSuck = 5;
  if (COMPLAINT_KEYWORDS.test(text)) existingSuck += 7;
  if (/(alternative|replacement|instead of|better than)/i.test(text)) existingSuck += 3;
  existingSuck = Math.min(existingSuck, 15);
  
  // 4. People actively complaining (0-15)
  let complaints = 3;
  if (upvotes >= 50) complaints += 6;
  else if (upvotes >= 20) complaints += 4;
  else if (upvotes >= 10) complaints += 3;
  else if (upvotes >= 5) complaints += 2;
  if (comments >= 20) complaints += 6;
  else if (comments >= 10) complaints += 4;
  else if (comments >= 5) complaints += 2;
  complaints = Math.min(complaints, 15);
  
  // 5. Monetizable (0-15)
  let monetizable = 5;
  if (BUSINESS_KEYWORDS.test(text)) monetizable += 5;
  if (/(pay|subscription|pricing|plan|pro|premium)/i.test(text)) monetizable += 3;
  if (/(save.*time|automate|productivity|efficiency)/i.test(text)) monetizable += 2;
  monetizable = Math.min(monetizable, 15);
  
  // 6. No major competitor moat (0-15)
  let noMoat = 10;
  if (MOAT_KEYWORDS.test(text)) noMoat -= 5;
  if (/(no good|no decent|nothing|doesn.?t exist)/i.test(text)) noMoat += 5;
  noMoat = Math.max(0, Math.min(noMoat, 15));
  
  const total = buildable + clearUseCase + existingSuck + complaints + monetizable + noMoat;
  
  return {
    total,
    breakdown: {
      buildable,
      clear_use_case: clearUseCase,
      existing_suck: existingSuck,
      complaints,
      monetizable,
      no_moat: noMoat,
    }
  };
}

try {
  const input = JSON.parse(process.argv[2]);
  const result = scoreIdea(input);
  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(`Scoring error: ${err.message}`);
  console.log(JSON.stringify({ total: 0, breakdown: {}, error: err.message }));
}
