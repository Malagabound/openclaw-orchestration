#!/usr/bin/env node
// Reddit scraper for micro-SaaS idea discovery
// Usage: node reddit_scraper.js <subreddit> [limit]

const SEARCH_PATTERNS = [
  /i wish there was/i,
  /why isn'?t there/i,
  /would pay for/i,
  /someone should build/i,
  /looking for a tool/i,
  /need a simple/i,
  /frustrated with/i,
  /paying too much/i,
  /is there a tool/i,
  /any tool that/i,
  /alternative to/i,
  /looking for.*app/i,
  /looking for.*service/i,
  /does anyone know.*tool/i,
];

async function fetchSubreddit(subreddit, limit = 100) {
  const url = `https://www.reddit.com/r/${subreddit}/new.json?limit=${limit}`;
  const response = await fetch(url, {
    headers: { 'User-Agent': 'OpenClaw-SaaS-Discovery/1.0 (idea monitoring bot)' }
  });
  
  if (response.status === 429) {
    console.error(`Rate limited on r/${subreddit}, waiting 60s...`);
    await new Promise(r => setTimeout(r, 60000));
    const retry = await fetch(url, {
      headers: { 'User-Agent': 'OpenClaw-SaaS-Discovery/1.0 (idea monitoring bot)' }
    });
    if (!retry.ok) throw new Error(`Reddit API error: ${retry.status}`);
    return retry.json();
  }
  
  if (!response.ok) throw new Error(`Reddit API error: ${response.status}`);
  return response.json();
}

function matchesPatterns(text) {
  if (!text) return null;
  for (const pattern of SEARCH_PATTERNS) {
    if (pattern.test(text)) return pattern.source;
  }
  return null;
}

async function main() {
  const subreddit = process.argv[2];
  const limit = parseInt(process.argv[3]) || 100;
  
  if (!subreddit) {
    console.error('Usage: node reddit_scraper.js <subreddit> [limit]');
    process.exit(1);
  }
  
  try {
    const data = await fetchSubreddit(subreddit, limit);
    const posts = data?.data?.children || [];
    
    const matches = [];
    for (const post of posts) {
      const d = post.data;
      const titleMatch = matchesPatterns(d.title);
      const bodyMatch = matchesPatterns(d.selftext);
      const matched = titleMatch || bodyMatch;
      
      if (matched) {
        matches.push({
          id: `reddit_${d.id}`,
          source: 'reddit',
          subreddit: subreddit,
          title: d.title,
          selftext: (d.selftext || '').slice(0, 1000),
          url: `https://reddit.com${d.permalink}`,
          score: d.score,
          num_comments: d.num_comments,
          created_utc: d.created_utc,
          pattern_matched: matched,
        });
      }
    }
    
    console.log(JSON.stringify(matches, null, 2));
  } catch (err) {
    console.error(`Error scraping r/${subreddit}: ${err.message}`);
    console.log('[]');
  }
}

main();
