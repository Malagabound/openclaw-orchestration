#!/usr/bin/env node
// Hacker News scraper for micro-SaaS idea discovery
// Usage: node hackernews_scraper.js [hours_back]

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
  /ask hn.*tool/i,
  /ask hn.*app/i,
  /ask hn.*service/i,
];

function matchesPatterns(text) {
  if (!text) return null;
  for (const pattern of SEARCH_PATTERNS) {
    if (pattern.test(text)) return pattern.source;
  }
  return null;
}

async function main() {
  const hoursBack = parseInt(process.argv[2]) || 24;
  const since = Math.floor(Date.now() / 1000) - (hoursBack * 3600);
  
  try {
    // Search Ask HN posts
    const url = `https://hn.algolia.com/api/v1/search_by_date?tags=ask_hn&hitsPerPage=100&numericFilters=created_at_i>${since}`;
    const response = await fetch(url);
    
    if (!response.ok) throw new Error(`HN API error: ${response.status}`);
    
    const data = await response.json();
    const hits = data?.hits || [];
    
    const matches = [];
    for (const hit of hits) {
      const titleMatch = matchesPatterns(hit.title);
      const storyMatch = matchesPatterns(hit.story_text);
      const matched = titleMatch || storyMatch;
      
      if (matched) {
        matches.push({
          id: `hn_${hit.objectID}`,
          source: 'hackernews',
          title: hit.title,
          selftext: (hit.story_text || '').slice(0, 1000),
          url: `https://news.ycombinator.com/item?id=${hit.objectID}`,
          score: hit.points || 0,
          num_comments: hit.num_comments || 0,
          created_utc: hit.created_at_i,
          pattern_matched: matched,
        });
      }
    }
    
    console.log(JSON.stringify(matches, null, 2));
  } catch (err) {
    console.error(`Error scraping HN: ${err.message}`);
    console.log('[]');
  }
}

main();
