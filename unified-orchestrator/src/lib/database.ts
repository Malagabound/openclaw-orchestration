import Database from 'better-sqlite3';
import path from 'path';

const dbPath = path.join(process.cwd(), '../../memory-db/conversations.db');

export interface ResearchOpportunity {
  id: number;
  title: string;
  domain: 'digital_products' | 'saas';
  market_demand_score: number;
  phase_status: 'phase_1' | 'phase_2' | 'phase_3' | 'approved' | 'building' | 'rejected';
  discovery_date: string;
  validation_date?: string;
  presented_date?: string;
  phase_1_score?: number;
  phase_2_score?: number;
  case_studies?: string;
  differentiation_thesis?: string;
  revenue_projection?: string;
  template_url?: string;
}

export interface AgentActivity {
  id: number;
  agent_name: string;
  activity_type: string;
  task_description: string;
  status: 'open' | 'in_progress' | 'completed';
  priority: number;
  created_at: string;
  completed_at?: string;
}

export interface APIUsage {
  id: number;
  timestamp: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  task_type: string;
  description: string;
  cost_estimate: number;
  source: string;
}

export class UnifiedDatabase {
  private db: Database.Database;

  constructor() {
    this.db = new Database(dbPath);
    this.init();
  }

  private init() {
    // Create research opportunities table
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS research_opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        domain TEXT CHECK(domain IN ('digital_products', 'saas')) NOT NULL,
        market_demand_score INTEGER NOT NULL,
        phase_status TEXT CHECK(phase_status IN ('phase_1', 'phase_2', 'phase_3', 'approved', 'building', 'rejected')) NOT NULL,
        discovery_date TEXT NOT NULL,
        validation_date TEXT,
        presented_date TEXT,
        phase_1_score INTEGER,
        phase_2_score INTEGER,
        case_studies TEXT,
        differentiation_thesis TEXT,
        revenue_projection TEXT,
        template_url TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create agent activities table  
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS agent_activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_name TEXT NOT NULL,
        activity_type TEXT NOT NULL,
        task_description TEXT NOT NULL,
        status TEXT CHECK(status IN ('open', 'in_progress', 'completed')) NOT NULL,
        priority INTEGER DEFAULT 3,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME
      )
    `);

    // Create API usage tracking table
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS api_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        model TEXT NOT NULL,
        input_tokens INTEGER NOT NULL,
        output_tokens INTEGER NOT NULL,
        total_tokens INTEGER NOT NULL,
        task_type TEXT NOT NULL,
        description TEXT,
        cost_estimate REAL NOT NULL,
        source TEXT NOT NULL
      )
    `);

    // Create indexes for better performance
    this.db.exec(`
      CREATE INDEX IF NOT EXISTS idx_research_phase ON research_opportunities(phase_status);
      CREATE INDEX IF NOT EXISTS idx_research_domain ON research_opportunities(domain);
      CREATE INDEX IF NOT EXISTS idx_research_score ON research_opportunities(market_demand_score);
      CREATE INDEX IF NOT EXISTS idx_agent_status ON agent_activities(status);
      CREATE INDEX IF NOT EXISTS idx_api_timestamp ON api_usage(timestamp);
    `);
  }

  // Research Opportunities
  getResearchOpportunities(phaseFilter?: string): ResearchOpportunity[] {
    let query = `
      SELECT * FROM research_opportunities 
      WHERE phase_status NOT IN ('phase_1', 'rejected')
      ORDER BY market_demand_score DESC, created_at DESC
    `;
    
    if (phaseFilter) {
      query = `
        SELECT * FROM research_opportunities 
        WHERE phase_status = ? AND phase_status NOT IN ('phase_1', 'rejected')
        ORDER BY market_demand_score DESC, created_at DESC
      `;
      return this.db.prepare(query).all(phaseFilter) as ResearchOpportunity[];
    }
    
    return this.db.prepare(query).all() as ResearchOpportunity[];
  }

  addResearchOpportunity(opportunity: Omit<ResearchOpportunity, 'id'>): ResearchOpportunity {
    const stmt = this.db.prepare(`
      INSERT INTO research_opportunities 
      (title, domain, market_demand_score, phase_status, discovery_date, validation_date, 
       presented_date, phase_1_score, phase_2_score, case_studies, differentiation_thesis, 
       revenue_projection, template_url)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    
    const result = stmt.run(
      opportunity.title,
      opportunity.domain,
      opportunity.market_demand_score,
      opportunity.phase_status,
      opportunity.discovery_date,
      opportunity.validation_date,
      opportunity.presented_date,
      opportunity.phase_1_score,
      opportunity.phase_2_score,
      opportunity.case_studies,
      opportunity.differentiation_thesis,
      opportunity.revenue_projection,
      opportunity.template_url
    );

    return { ...opportunity, id: result.lastInsertRowid as number };
  }

  // Agent Activities
  getAgentActivities(limit: number = 20): AgentActivity[] {
    const stmt = this.db.prepare(`
      SELECT * FROM agent_activities 
      ORDER BY created_at DESC 
      LIMIT ?
    `);
    return stmt.all(limit) as AgentActivity[];
  }

  addAgentActivity(activity: Omit<AgentActivity, 'id' | 'created_at'>): AgentActivity {
    const stmt = this.db.prepare(`
      INSERT INTO agent_activities (agent_name, activity_type, task_description, status, priority)
      VALUES (?, ?, ?, ?, ?)
    `);
    
    const result = stmt.run(
      activity.agent_name,
      activity.activity_type,
      activity.task_description,
      activity.status,
      activity.priority
    );

    return { 
      ...activity, 
      id: result.lastInsertRowid as number,
      created_at: new Date().toISOString()
    };
  }

  updateAgentActivity(id: number, updates: Partial<AgentActivity>): void {
    const fields = Object.keys(updates).map(key => `${key} = ?`).join(', ');
    const values = Object.values(updates);
    
    const stmt = this.db.prepare(`
      UPDATE agent_activities 
      SET ${fields}
      WHERE id = ?
    `);
    
    stmt.run(...values, id);
  }

  // API Usage Tracking
  logAPIUsage(usage: Omit<APIUsage, 'id' | 'timestamp'>): void {
    const stmt = this.db.prepare(`
      INSERT INTO api_usage (model, input_tokens, output_tokens, total_tokens, task_type, description, cost_estimate, source)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    
    stmt.run(
      usage.model,
      usage.input_tokens,
      usage.output_tokens,
      usage.total_tokens,
      usage.task_type,
      usage.description,
      usage.cost_estimate,
      usage.source
    );
  }

  getAPIUsageStats(days: number = 7): any {
    const stmt = this.db.prepare(`
      SELECT 
        COUNT(*) as total_calls,
        SUM(total_tokens) as total_tokens,
        SUM(cost_estimate) as total_cost,
        model,
        task_type
      FROM api_usage 
      WHERE timestamp >= datetime('now', '-${days} days')
      GROUP BY model, task_type
      ORDER BY total_cost DESC
    `);
    
    return stmt.all();
  }

  // Search functionality
  searchAll(query: string, limit: number = 20): any[] {
    // Search research opportunities
    const researchStmt = this.db.prepare(`
      SELECT 'research' as type, title, domain, market_demand_score, phase_status, created_at
      FROM research_opportunities 
      WHERE (title LIKE ? OR case_studies LIKE ? OR differentiation_thesis LIKE ?)
      AND phase_status NOT IN ('phase_1', 'rejected')
      ORDER BY market_demand_score DESC
      LIMIT ?
    `);
    
    const searchTerm = `%${query}%`;
    const research = researchStmt.all(searchTerm, searchTerm, searchTerm, Math.floor(limit / 2));

    // Search conversations (from existing memory database)
    try {
      const conversationStmt = this.db.prepare(`
        SELECT 'conversation' as type, user_message, assistant_message, category, timestamp
        FROM conversations 
        WHERE user_message LIKE ? OR assistant_message LIKE ?
        ORDER BY timestamp DESC
        LIMIT ?
      `);
      
      const conversations = conversationStmt.all(searchTerm, searchTerm, Math.floor(limit / 2));
      
      return [...research, ...conversations];
    } catch (error) {
      // If conversations table doesn't exist, just return research results
      return research;
    }
  }

  close() {
    this.db.close();
  }
}