# Search API Integration Plan

**Date:** 2026-02-08
**Status:** Waiting for API keys from Alan tomorrow

## Current Problem
- Agents doing research WITHOUT proper web search capabilities
- Built-in web_search (Brave) missing API key
- Firecrawl missing API key  
- Research quality compromised

## Integration Plan (When Keys Available)

### 1. Brave Search API (Primary)
**Setup:** `openclaw configure --section web` 
**Use for:** Market research, competitive analysis, demand validation
**All agents:** Primary search tool for Phase 1 discovery

### 2. Firecrawl API (Secondary)  
**Setup:** Add FIRECRAWL_API_KEY to environment
**Use for:** Marketplace scraping, competitor site analysis
**Specific applications:**
- Rex: Scrape app stores, SaaS directories
- Pixel: Scrape Gumroad, Etsy, Creative Market  
- Vault: Scrape acquisition marketplaces

## Agent-Specific Search Strategies

### Rex (SaaS) 💰
- **Brave:** "SaaS for [niche]", competitor research, market sizing
- **Firecrawl:** Scrape Apify Store, Discord bot directories, Shopify App Store

### Pixel (Digital Products) 🎨  
- **Brave:** Template trends, design demand, market validation
- **Firecrawl:** Scrape Gumroad categories, Etsy bestsellers, Creative Market

### Vault (Acquisitions) 🏦
- **Brave:** Industry research, company background checks, market trends  
- **Firecrawl:** Scrape Acquire.com, Flippa listings, business valuations

## Implementation Checklist (Tomorrow)
- [ ] Set up Brave API key via `openclaw configure --section web`
- [ ] Add FIRECRAWL_API_KEY to credentials 
- [ ] Update agent systemPrompts to reference search tools
- [ ] Test search capabilities with all agents
- [ ] Update research skills to include search methodologies

## Expected Impact
- Dramatically improved research quality
- Faster discovery and validation  
- Better competitive analysis
- More accurate market sizing