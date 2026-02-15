#!/usr/bin/env python3
"""
Multi-Agent Orchestrator Dashboard
Based on SiteGPT's 14-agent coordination system

Provides task coordination, agent communication, and progress tracking
for George's specialist agent ecosystem.
"""

import json
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import hashlib

class OrchestratorDashboard:
    def __init__(self, db_path: str = "orchestrator-dashboard/coordination.db"):
        self.db_path = db_path
        self.ensure_directory()
        self.init_database()
        
    def ensure_directory(self):
        """Create dashboard directory if it doesn't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def init_database(self):
        """Initialize the coordination database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript("""
                -- Tasks table - central task coordination
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT DEFAULT 'open' CHECK(status IN ('open', 'in_progress', 'review', 'completed', 'blocked')),
                    priority INTEGER DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
                    domain TEXT NOT NULL, -- 'research', 'digital_products' [DEACTIVATED: 'real_estate', 'business_acquisition', 'operations']
                    assigned_agent TEXT, -- 'research', 'product', 'meta', 'ops', 'comms', 'haven', 'vault', 'george'
                    created_by TEXT DEFAULT 'george',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    due_date DATETIME,
                    deliverable_type TEXT, -- 'report', 'analysis', 'recommendation', 'implementation'
                    deliverable_url TEXT,
                    estimated_effort INTEGER, -- 1-10 scale
                    business_impact INTEGER DEFAULT 3 CHECK(business_impact BETWEEN 1 AND 5)
                );
                
                -- Agent activity tracking
                CREATE TABLE IF NOT EXISTS agent_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    task_id INTEGER,
                    activity_type TEXT NOT NULL, -- 'checkin', 'contribution', 'completion', 'question'
                    message TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
                );
                
                -- Agent contributions to tasks
                CREATE TABLE IF NOT EXISTS task_contributions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    agent_name TEXT NOT NULL,
                    contribution_type TEXT NOT NULL, -- 'insight', 'analysis', 'question', 'deliverable'
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                
                -- Alan mentions and notifications
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    message TEXT NOT NULL,
                    urgency TEXT DEFAULT 'normal' CHECK(urgency IN ('low', 'normal', 'high', 'urgent')),
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'acknowledged', 'resolved')),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sent_at DATETIME,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
                );
                
                -- Squad chat for agent insights
                CREATE TABLE IF NOT EXISTS squad_chat (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    related_task_id INTEGER,
                    FOREIGN KEY (related_task_id) REFERENCES tasks(id) ON DELETE SET NULL
                );
                
                -- Agent check-in tracking (15-minute system)
                CREATE TABLE IF NOT EXISTS agent_checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    tasks_reviewed INTEGER DEFAULT 0,
                    contributions_made INTEGER DEFAULT 0
                );
                
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_tasks_domain ON tasks(domain);
                CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC);
                CREATE INDEX IF NOT EXISTS idx_activity_agent ON agent_activity(agent_name);
                CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON agent_activity(timestamp DESC);
            """)
    
    def create_task(self, 
                   title: str,
                   description: str, 
                   domain: str,
                   priority: int = 3,
                   assigned_agent: Optional[str] = None,
                   deliverable_type: str = "report",
                   estimated_effort: int = 5,
                   business_impact: int = 3) -> int:
        """Create a new task in the coordination system."""
        
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            cursor = conn.execute("""
                INSERT INTO tasks 
                (title, description, domain, priority, assigned_agent, deliverable_type, estimated_effort, business_impact)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, description, domain, priority, assigned_agent, deliverable_type, estimated_effort, business_impact))
            
            task_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Log task creation (separate connection)
            self.log_agent_activity("george", task_id, "creation", f"Created task: {title}")
            
            return task_id
        except sqlite3.Error as e:
            conn.close()
            raise e
    
    def get_tasks_for_agent_checkin(self, agent_name: str, minutes_ago: int = 15) -> List[Dict]:
        """Get new tasks created since agent's last check-in."""
        
        cutoff_time = datetime.now() - timedelta(minutes=minutes_ago)
        
        # Domain mapping for agents
        agent_domains = {
            'research': ['research', 'market_analysis', 'software_subscriptions'],
            'product': ['digital_products', 'product_validation'],
            'meta': ['validation', 'quality_control'],
            'ops': ['maintenance', 'email', 'automation']
        }
        
        domains = agent_domains.get(agent_name, [])
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            placeholders = ','.join(['?' for _ in domains])
            query = f"""
                SELECT * FROM tasks 
                WHERE created_at >= ? 
                AND (domain IN ({placeholders}) OR assigned_agent = ? OR assigned_agent IS NULL)
                AND status IN ('open', 'in_progress')
                ORDER BY priority DESC, created_at DESC
            """
            
            results = conn.execute(query, [cutoff_time.isoformat()] + domains + [agent_name]).fetchall()
            return [dict(row) for row in results]
    
    def agent_checkin(self, agent_name: str) -> Dict:
        """Process agent check-in and return relevant tasks."""
        
        # Get tasks for review
        tasks = self.get_tasks_for_agent_checkin(agent_name)
        
        # Log the check-in
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO agent_checkins (agent_name, tasks_reviewed)
                VALUES (?, ?)
            """, (agent_name, len(tasks)))
        
        self.log_agent_activity(agent_name, None, "checkin", f"Reviewed {len(tasks)} tasks during 15-min checkin")
        
        return {
            "agent": agent_name,
            "timestamp": datetime.now().isoformat(),
            "tasks_to_review": tasks,
            "tasks_count": len(tasks)
        }
    
    def add_task_contribution(self, task_id: int, agent_name: str, contribution_type: str, content: str) -> bool:
        """Agent adds contribution to a task."""
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO task_contributions (task_id, agent_name, contribution_type, content)
                VALUES (?, ?, ?, ?)
            """, (task_id, agent_name, contribution_type, content))
            
            # Update task status to in_progress if it was open
            conn.execute("""
                UPDATE tasks SET 
                    status = CASE WHEN status = 'open' THEN 'in_progress' ELSE status END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (task_id,))
        
        self.log_agent_activity(agent_name, task_id, "contribution", f"{contribution_type}: {content[:100]}")
        return True
    
    def complete_task(self, task_id: int, agent_name: str, deliverable_url: Optional[str] = None) -> bool:
        """Mark task as completed with deliverable."""
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE tasks SET 
                    status = 'completed',
                    deliverable_url = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (deliverable_url, task_id))
        
        self.log_agent_activity(agent_name, task_id, "completion", f"Task completed. Deliverable: {deliverable_url or 'None'}")
        
        # Create notification for George/Alan
        self.create_notification(task_id, f"Task completed by {agent_name}", "normal")
        
        return True
    
    def log_agent_activity(self, agent_name: str, task_id: Optional[int], activity_type: str, message: str):
        """Log agent activity for tracking."""
        
        # Use a separate connection for activity logging to avoid locks
        try:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.execute("""
                INSERT INTO agent_activity (agent_name, task_id, activity_type, message)
                VALUES (?, ?, ?, ?)
            """, (agent_name, task_id, activity_type, message))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            print(f"⚠️ Could not log activity: {e}")
    
    def create_notification(self, task_id: Optional[int], message: str, urgency: str = "normal"):
        """Create notification for Alan/George."""
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO notifications (task_id, message, urgency)
                VALUES (?, ?, ?)
            """, (task_id, message, urgency))
    
    def get_dashboard_summary(self) -> Dict:
        """Get overview for dashboard display."""
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Task status summary
            task_stats = conn.execute("""
                SELECT status, COUNT(*) as count, AVG(priority) as avg_priority
                FROM tasks 
                WHERE created_at >= date('now', '-7 days')
                GROUP BY status
            """).fetchall()
            
            # Agent activity summary
            agent_stats = conn.execute("""
                SELECT agent_name, COUNT(*) as activities
                FROM agent_activity 
                WHERE timestamp >= datetime('now', '-1 day')
                GROUP BY agent_name
                ORDER BY activities DESC
            """).fetchall()
            
            # Pending notifications
            notifications = conn.execute("""
                SELECT COUNT(*) as pending_count
                FROM notifications 
                WHERE status = 'pending'
            """).fetchone()
            
            # Recent contributions
            recent_contributions = conn.execute("""
                SELECT t.title, tc.agent_name, tc.contribution_type, tc.content, tc.timestamp
                FROM task_contributions tc
                JOIN tasks t ON tc.task_id = t.id
                WHERE tc.timestamp >= datetime('now', '-4 hours')
                ORDER BY tc.timestamp DESC
                LIMIT 10
            """).fetchall()
            
            return {
                "task_stats": [dict(row) for row in task_stats],
                "agent_activity": [dict(row) for row in agent_stats],
                "pending_notifications": notifications["pending_count"],
                "recent_contributions": [dict(row) for row in recent_contributions],
                "timestamp": datetime.now().isoformat()
            }
    
    def broadcast_task(self, title: str, description: str, target_agents: List[str]) -> int:
        """Broadcast task to multiple specialist agents."""
        
        # Create the main task
        task_id = self.create_task(
            title=title,
            description=description, 
            domain="multi_agent",
            priority=4,  # High priority for broadcast tasks
            deliverable_type="collaborative_report"
        )
        
        # Notify all target agents
        for agent in target_agents:
            self.log_agent_activity(agent, task_id, "broadcast", f"Task broadcast to {agent}")
            
        self.create_notification(task_id, f"Task broadcast to {', '.join(target_agents)}", "normal")
        
        return task_id
    
    def squad_chat_post(self, agent_name: str, message: str, related_task_id: Optional[int] = None):
        """Post to squad chat for agent insights."""
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO squad_chat (agent_name, message, related_task_id)
                VALUES (?, ?, ?)
            """, (agent_name, message, related_task_id))
    
    def get_squad_chat_recent(self, hours_back: int = 24) -> List[Dict]:
        """Get recent squad chat messages."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            results = conn.execute("""
                SELECT sc.*, t.title as related_task_title
                FROM squad_chat sc
                LEFT JOIN tasks t ON sc.related_task_id = t.id
                WHERE sc.timestamp >= ?
                ORDER BY sc.timestamp DESC
            """, (cutoff_time.isoformat(),)).fetchall()
            
            return [dict(row) for row in results]

def test_dashboard():
    """Test the orchestrator dashboard system."""
    
    print("🎯 Testing Orchestrator Dashboard System")
    print("=" * 50)
    
    dashboard = OrchestratorDashboard()
    
    # Test task creation
    task_id = dashboard.create_task(
        title="Analyze podcast opportunities for SiteGPT growth",
        description="Research podcasts in the AI/SaaS space that would be good for founder interviews. Focus on growth potential and audience alignment.",
        domain="research",
        priority=4,
        assigned_agent="research",
        deliverable_type="analysis",
        business_impact=4
    )
    print(f"Created task with ID: {task_id}")

    # Test agent check-in
    checkin_result = dashboard.agent_checkin("research")
    print(f"Research checked in and found {checkin_result['tasks_count']} tasks")

    # Test contribution
    dashboard.add_task_contribution(
        task_id=task_id,
        agent_name="research",
        contribution_type="insight",
        content="Found 15 AI podcasts with 10k+ listeners. Identified top 5 based on host engagement and audience overlap."
    )
    print("Research added contribution to podcast research task")

    # Test squad chat
    dashboard.squad_chat_post(
        agent_name="product",
        message="Noticed podcast research happening. Digital product creators often get good traction on developer-focused shows. Happy to analyze which shows convert best for product launches.",
        related_task_id=task_id
    )
    print("Product added insight to squad chat")
    
    # Test dashboard summary
    summary = dashboard.get_dashboard_summary()
    print("✅ Generated dashboard summary")
    print(f"   Task stats: {summary['task_stats']}")
    print(f"   Agent activity: {summary['agent_activity']}")
    print(f"   Recent contributions: {len(summary['recent_contributions'])}")
    
    print("\n🎉 Orchestrator Dashboard is working!")
    return dashboard

if __name__ == "__main__":
    test_dashboard()