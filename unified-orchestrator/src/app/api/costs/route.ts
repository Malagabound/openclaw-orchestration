import { NextResponse } from 'next/server';
import { UnifiedDatabase } from '@/lib/database';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const days = parseInt(searchParams.get('days') || '7');

  try {
    const db = new UnifiedDatabase();
    const stats = db.getAPIUsageStats(days);
    db.close();

    return NextResponse.json(stats);
  } catch (error) {
    console.error('Failed to fetch cost stats:', error);
    return NextResponse.json(
      { error: 'Failed to fetch cost stats' },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const db = new UnifiedDatabase();
    db.logAPIUsage(body);
    db.close();

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Failed to log API usage:', error);
    return NextResponse.json(
      { error: 'Failed to log API usage' },
      { status: 500 }
    );
  }
}