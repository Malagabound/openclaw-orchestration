import { NextResponse } from 'next/server';
import { UnifiedDatabase } from '@/lib/database';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const filter = searchParams.get('filter');

  try {
    const db = new UnifiedDatabase();
    const opportunities = db.getResearchOpportunities(filter || undefined);
    db.close();

    return NextResponse.json(opportunities);
  } catch (error) {
    console.error('Failed to fetch research opportunities:', error);
    return NextResponse.json(
      { error: 'Failed to fetch research opportunities' },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const db = new UnifiedDatabase();
    const opportunity = db.addResearchOpportunity(body);
    db.close();

    return NextResponse.json(opportunity);
  } catch (error) {
    console.error('Failed to create research opportunity:', error);
    return NextResponse.json(
      { error: 'Failed to create research opportunity' },
      { status: 500 }
    );
  }
}