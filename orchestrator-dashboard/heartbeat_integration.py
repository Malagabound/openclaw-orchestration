#!/usr/bin/env python3
"""
Heartbeat Integration for Multi-Agent Coordination
Integrates 15-minute agent check-ins with OpenClaw heartbeat system
"""

import sys
import os
import json
sys.path.append(os.path.dirname(__file__))

from agent_coordinator import AgentCoordinator
from datetime import datetime

def agent_heartbeat_checkin(agent_name: str) -> str:
    """
    Process agent heartbeat check-in for 15-minute coordination system.
    Called by individual agent heartbeats.
    """
    
    coordinator = AgentCoordinator()
    
    try:
        # Process the check-in
        result = coordinator.process_agent_checkin(agent_name)
        
        if result['status'] == 'no_action':
            return f"COORDINATION_OK - {agent_name} checked in, no new tasks"
        
        # Format tasks for agent attention
        tasks = result['tasks']
        if not tasks:
            return f"COORDINATION_OK - {agent_name} checked in, no actionable tasks"
        
        # Build response for agent
        response_parts = [
            f"🎯 {agent_name.upper()} COORDINATION UPDATE",
            f"Found {len(tasks)} tasks requiring attention:"
        ]
        
        for task in tasks:
            priority_emoji = "🔥" if task['priority'] >= 4 else "⚡" if task['priority'] == 3 else "📝"
            status_emoji = "🔄" if task['status'] == 'in_progress' else "🆕"
            
            response_parts.append(
                f"\n{priority_emoji} {status_emoji} **Task #{task['id']}**: {task['title']}"
            )
            
            if task['can_contribute']:
                response_parts.append(f"   💡 **Action**: You can contribute {task['domain']} expertise")
            else:
                response_parts.append(f"   👀 **Info**: Monitor for cross-domain insights")
        
        response_parts.append(f"\n⏰ Next check-in: 15 minutes")
        response_parts.append(f"📊 Use dashboard to add contributions or insights")
        
        return "\n".join(response_parts)
        
    except Exception as e:
        return f"⚠️ Coordination error for {agent_name}: {e}"

def george_coordination_summary() -> str:
    """
    Generate coordination summary for George's heartbeat.
    Shows overall system status and any items requiring attention.
    """
    
    coordinator = AgentCoordinator()
    
    try:
        status = coordinator.get_coordination_status()
        
        if status['system_status'] == 'idle':
            return "COORDINATION_OK - Multi-agent system idle, no active tasks"
        
        response_parts = [
            "🎯 MULTI-AGENT COORDINATION STATUS"
        ]
        
        # System overview
        response_parts.append(f"📊 **System**: {status['total_tasks']} tasks, {status['active_agents']} active agents")
        
        # Task breakdown
        if status['task_breakdown']:
            task_summary = []
            for stat in status['task_breakdown']:
                task_summary.append(f"{stat['count']} {stat['status']}")
            response_parts.append(f"📋 **Tasks**: {', '.join(task_summary)}")
        
        # Agent activity
        if status['agent_activity']:
            active_agents = []
            for agent in status['agent_activity']:
                active_agents.append(f"{agent['agent_name']} ({agent['activities']})")
            response_parts.append(f"🤖 **Active**: {', '.join(active_agents[:3])}")
        
        # Notifications
        if status['pending_notifications'] > 0:
            response_parts.append(f"🔔 **Alert**: {status['pending_notifications']} notifications pending")
        
        # System health
        if status['recent_activity_count'] > 10:
            response_parts.append("✅ **Health**: High activity - system operating well")
        elif status['recent_activity_count'] > 0:
            response_parts.append("🔶 **Health**: Moderate activity")
        else:
            response_parts.append("⚠️ **Health**: Low activity - agents may need attention")
        
        return "\n".join(response_parts)
        
    except Exception as e:
        return f"⚠️ Coordination system error: {e}"

def process_alan_task_request(request: str) -> str:
    """
    Process task request from Alan and route to appropriate agents.
    Called when Alan makes requests through George.
    """
    
    coordinator = AgentCoordinator()
    
    try:
        # Create broadcast task
        task_id = coordinator.broadcast_task_to_agents(
            title=f"Alan Request: {request[:50]}...",
            description=request,
            priority=4  # High priority for Alan's direct requests
        )
        
        # Determine which agents will be involved
        relevant_agents = coordinator._determine_relevant_agents(request)
        
        response_parts = [
            f"🎯 TASK BROADCAST INITIATED",
            f"**Task ID**: {task_id}",
            f"**Request**: {request[:100]}...",
            f"**Routing to**: {', '.join(relevant_agents) if relevant_agents else 'All available agents'}",
            f"**Priority**: High (Alan direct request)",
            "",
            "⏰ Agents will review within 15 minutes and begin work",
            "📊 Progress tracking via coordination dashboard",
            "🔔 I'll notify you when deliverables are ready"
        ]
        
        return "\n".join(response_parts)
        
    except Exception as e:
        return f"❌ Task routing failed: {e}"

# CLI interface for testing and manual operations
def main():
    """Command line interface for coordination system."""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Multi-Agent Coordination System")
    parser.add_argument('action', choices=['checkin', 'status', 'broadcast'], help='Action to perform')
    parser.add_argument('--agent', help='Agent name for checkin')
    parser.add_argument('--task', help='Task description for broadcast')
    
    args = parser.parse_args()
    
    if args.action == 'checkin':
        if not args.agent:
            print("Error: --agent required for checkin")
            return
        result = agent_heartbeat_checkin(args.agent)
        print(result)
        
    elif args.action == 'status':
        result = george_coordination_summary()
        print(result)
        
    elif args.action == 'broadcast':
        if not args.task:
            print("Error: --task required for broadcast") 
            return
        result = process_alan_task_request(args.task)
        print(result)

if __name__ == "__main__":
    main()