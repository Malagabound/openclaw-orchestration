import { NextResponse } from 'next/server';
import { UnifiedDatabase } from '@/lib/database';

export async function GET() {
  try {
    const db = new UnifiedDatabase();
    const activities = db.getAgentActivities(50);
    db.close();

    return NextResponse.json(activities);
  } catch (error) {
    console.error('Failed to fetch agent activities:', error);
    return NextResponse.json(
      { error: 'Failed to fetch agent activities' },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const db = new UnifiedDatabase();
    const activity = db.addAgentActivity(body);
    db.close();

    return NextResponse.json(activity);
  } catch (error) {
    console.error('Failed to create agent activity:', error);
    return NextResponse.json(
      { error: 'Failed to create agent activity' },
      { status: 500 }
    );
  }
}