#!/usr/bin/env python3
"""
Agent Coordination System
Integrates with OpenClaw heartbeat for 15-minute check-ins and task coordination
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from dashboard import OrchestratorDashboard
import json
from datetime import datetime
from typing import Dict, List

class AgentCoordinator:
    def __init__(self):
        self.dashboard = OrchestratorDashboard()
        
    def process_agent_checkin(self, agent_name: str) -> Dict:
        """Process 15-minute agent check-in and return action items."""
        
        # Get check-in results
        checkin_result = self.dashboard.agent_checkin(agent_name)
        tasks = checkin_result['tasks_to_review']
        
        if not tasks:
            return {
                "status": "no_action",
                "message": f"{agent_name} checked in - no new tasks requiring attention",
                "checkin_time": datetime.now().isoformat()
            }
        
        # Format tasks for agent review
        formatted_tasks = []
        for task in tasks:
            formatted_tasks.append({
                "id": task['id'],
                "title": task['title'],
                "description": task['description'],
                "priority": task['priority'],
                "status": task['status'],
                "domain": task['domain'],
                "can_contribute": self._can_agent_contribute(agent_name, task)
            })
        
        return {
            "status": "tasks_available",
            "agent": agent_name,
            "tasks": formatted_tasks,
            "tasks_count": len(tasks),
            "checkin_time": datetime.now().isoformat(),
            "next_checkin": "15 minutes"
        }
    
    def _can_agent_contribute(self, agent_name: str, task: Dict) -> bool:
        """Determine if agent can contribute to this task based on domain expertise."""
        
        # Agent expertise mapping
        agent_expertise = {
            'research': ['research', 'market_analysis', 'competitive_analysis', 'customer_research', 'software_subscriptions', 'saas_opportunities'],
            'product': ['digital_products', 'product_validation', 'marketplace_strategy', 'product_creation'],
            'meta': ['validation', 'quality_control', 'fact_checking', 'cross_domain_review'],
            'ops': ['maintenance', 'email_management', 'automation', 'system_health']
        }
        
        expertise = agent_expertise.get(agent_name, [])
        task_domain = task['domain']
        
        # Direct domain match
        if task_domain in expertise:
            return True
            
        # Cross-domain opportunities
        if agent_name == 'meta':  # Meta can validate everything
            return True
            
        if 'research' in task['title'].lower() and agent_name == 'research':
            return True

        if any(keyword in task['description'].lower() for keyword in ['product', 'market', 'customer']):
            if agent_name in ['research', 'product']:
                return True
        
        return False
    
    def agent_contribute_to_task(self, agent_name: str, task_id: int, contribution_type: str, content: str) -> bool:
        """Agent adds contribution to a task."""
        
        success = self.dashboard.add_task_contribution(task_id, agent_name, contribution_type, content)
        
        if success:
            # Check if this contribution triggers task completion
            if contribution_type == "deliverable":
                # Notify George that deliverable is ready for review
                self.dashboard.create_notification(
                    task_id, 
                    f"{agent_name} completed deliverable for task {task_id}",
                    "normal"
                )
        
        return success
    
    def broadcast_task_to_agents(self, title: str, description: str, priority: int = 3) -> int:
        """George broadcasts a task that needs multi-agent coordination."""
        
        # Determine relevant agents based on task content
        relevant_agents = self._determine_relevant_agents(title + " " + description)
        
        task_id = self.dashboard.broadcast_task(title, description, relevant_agents)
        
        return task_id
    
    def _determine_relevant_agents(self, task_content: str) -> List[str]:
        """Determine which agents should be involved in a task."""
        
        content_lower = task_content.lower()
        relevant_agents = []
        
        # Keyword-based agent selection
        if any(word in content_lower for word in ['research', 'analyze', 'market', 'competitive']):
            relevant_agents.append('research')

        if any(word in content_lower for word in ['product', 'digital', 'template', 'course', 'gumroad']):
            relevant_agents.append('product')

        if 'validation' in content_lower or 'validate' in content_lower:
            relevant_agents.append('meta')
        
        return list(set(relevant_agents))  # Remove duplicates
    
    def get_agent_task_summary(self, agent_name: str) -> Dict:
        """Get summary of tasks for a specific agent."""
        
        summary = self.dashboard.get_dashboard_summary()
        
        # Get agent-specific tasks
        checkin_result = self.dashboard.agent_checkin(agent_name)
        
        return {
            "agent": agent_name,
            "available_tasks": len(checkin_result['tasks_to_review']),
            "overall_activity": summary['agent_activity'],
            "recent_contributions": [c for c in summary['recent_contributions'] if c['agent_name'] == agent_name],
            "timestamp": datetime.now().isoformat()
        }
    
    def create_alan_notification(self, message: str, urgency: str = "normal", task_id: int = None) -> bool:
        """Create notification for Alan via Telegram."""
        
        self.dashboard.create_notification(task_id, message, urgency)
        
        # If high urgency, also create immediate Telegram message
        if urgency in ['high', 'urgent']:
            return True  # Trigger immediate notification
            
        return False  # Regular notification queue
    
    def get_coordination_status(self) -> Dict:
        """Get overall coordination system status."""
        
        summary = self.dashboard.get_dashboard_summary()
        
        # Calculate system health metrics
        total_tasks = sum(stat['count'] for stat in summary['task_stats'])
        active_agents = len(summary['agent_activity'])
        recent_activity = sum(stat['activities'] for stat in summary['agent_activity'])
        
        return {
            "system_status": "active" if active_agents > 0 else "idle",
            "total_tasks": total_tasks,
            "active_agents": active_agents,
            "recent_activity_count": recent_activity,
            "pending_notifications": summary['pending_notifications'],
            "last_updated": summary['timestamp'],
            "agent_activity": summary['agent_activity'],
            "task_breakdown": summary['task_stats']
        }

def test_coordination():
    """Test the agent coordination system."""
    
    print("🤖 Testing Agent Coordination System")
    print("=" * 50)
    
    coordinator = AgentCoordinator()
    
    # Test broadcast task
    print("1. Testing broadcast task creation...")
    task_id = coordinator.broadcast_task_to_agents(
        "Research and validate micro-SaaS opportunity in project management space",
        "We need to analyze the project management software market for micro-SaaS opportunities. This should include market research, competitor analysis, product validation approach, and business model recommendations."
    )
    print(f"   ✅ Created broadcast task {task_id}")
    
    # Test agent check-ins
    print("2. Testing agent check-ins...")
    agents = ['research', 'product', 'meta']
    
    for agent in agents:
        checkin = coordinator.process_agent_checkin(agent)
        print(f"   ✅ {agent} checked in: {checkin['status']} ({checkin.get('tasks_count', 0)} tasks)")
    
    # Test task contribution
    print("3. Testing task contributions...")
    coordinator.agent_contribute_to_task(
        agent_name="research",
        task_id=task_id,
        contribution_type="analysis",
        content="Initial market research shows 15+ established players (Asana, Monday.com, etc.) but identified 3 underserved niches: construction project management, event planning workflows, and creative agency resource allocation."
    )
    print("   Research added market analysis contribution")

    coordinator.agent_contribute_to_task(
        agent_name="product",
        task_id=task_id,
        contribution_type="insight",
        content="Construction PM niche has highest potential - analyzed 5 existing solutions, all are either too complex or missing key features like permit tracking and subcontractor coordination. Market size ~$500M with low digital adoption."
    )
    print("   Product added product validation insight")
    
    # Test coordination status
    print("4. Testing coordination status...")
    status = coordinator.get_coordination_status()
    print(f"   ✅ System status: {status['system_status']}")
    print(f"   ✅ Active agents: {status['active_agents']}")
    print(f"   ✅ Total tasks: {status['total_tasks']}")
    print(f"   ✅ Recent activity: {status['recent_activity_count']} actions")
    
    print("\n🎉 Agent Coordination System is working!")
    return coordinator

if __name__ == "__main__":
    test_coordination()