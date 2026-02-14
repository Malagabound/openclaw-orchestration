import { NextResponse } from 'next/server';
import { UnifiedDatabase } from '@/lib/database';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get('q');
  const limit = parseInt(searchParams.get('limit') || '20');

  if (!query || query.length < 2) {
    return NextResponse.json({ results: [] });
  }

  try {
    const db = new UnifiedDatabase();
    const results = db.searchAll(query, limit);
    db.close();

    // Transform results for the frontend
    const transformedResults = results.map(result => {
      if (result.type === 'research') {
        return {
          type: 'research',
          title: result.title,
          description: `${result.domain} opportunity • Score: ${result.market_demand_score}/30`,
          metadata: `Phase ${result.phase_status.replace('phase_', '')} • ${result.domain.replace('_', ' ')} • ${new Date(result.created_at).toLocaleDateString()}`,
          url: result.template_url || undefined
        };
      } else if (result.type === 'conversation') {
        return {
          type: 'conversation',
          title: result.user_message?.substring(0, 80) + '...' || 'Conversation',
          description: result.assistant_message?.substring(0, 120) + '...' || '',
          metadata: `${new Date(result.timestamp).toLocaleDateString()} • ${result.category} • Conversation`
        };
      }
      return result;
    });

    return NextResponse.json({ results: transformedResults });
  } catch (error) {
    console.error('Search failed:', error);
    return NextResponse.json(
      { error: 'Search failed' },
      { status: 500 }
    );
  }
}