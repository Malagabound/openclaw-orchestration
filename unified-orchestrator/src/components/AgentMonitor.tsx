'use client';

import { useState, useEffect } from 'react';
import { Users, Activity, Clock, CheckCircle, AlertCircle, PlayCircle } from 'lucide-react';

interface AgentActivity {
  id: number;
  agent_name: string;
  activity_type: string;
  task_description: string;
  status: 'open' | 'in_progress' | 'completed';
  priority: number;
  created_at: string;
  completed_at?: string;
}

interface AgentStats {
  name: string;
  role: string;
  status: 'active' | 'idle' | 'busy';
  tasks_completed_today: number;
  current_tasks: number;
  last_activity: string;
  specialization: string[];
}

export default function AgentMonitor() {
  const [activities, setActivities] = useState<AgentActivity[]>([]);
  const [agentStats, setAgentStats] = useState<AgentStats[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAgentData();
    // Set up polling for real-time updates
    const interval = setInterval(loadAgentData, 30000); // 30 seconds
    return () => clearInterval(interval);
  }, []);

  const loadAgentData = async () => {
    try {
      // In real implementation, these would be API calls
      // For now, using mock data that represents our actual agent system
      
      setAgentStats([
        {
          name: 'rex',
          role: 'Research & Market Analysis',
          status: 'active',
          tasks_completed_today: 3,
          current_tasks: 2,
          last_activity: '5 minutes ago',
          specialization: ['Market Research', 'Competitive Analysis', 'Trend Monitoring']
        },
        {
          name: 'pixel',
          role: 'Digital Products',
          status: 'busy',
          tasks_completed_today: 1,
          current_tasks: 3,
          last_activity: '2 minutes ago',
          specialization: ['Product Validation', 'Template Creation', 'Marketplace Strategy']
        },
        {
          name: 'scout',
          role: 'Quality & Validation',
          status: 'active',
          tasks_completed_today: 2,
          current_tasks: 1,
          last_activity: '12 minutes ago',
          specialization: ['Phase 2 Validation', 'Quality Control', 'Fact Checking']
        },
        {
          name: 'haven',
          role: 'Real Estate & Investments',
          status: 'idle',
          tasks_completed_today: 0,
          current_tasks: 0,
          last_activity: '2 hours ago',
          specialization: ['Property Analysis', 'Investment Research', 'Market Trends']
        },
        {
          name: 'vault',
          role: 'Business Acquisition',
          status: 'idle',
          tasks_completed_today: 0,
          current_tasks: 0,
          last_activity: '4 hours ago',
          specialization: ['Deal Analysis', 'Due Diligence', 'ROI Assessment']
        },
        {
          name: 'nora',
          role: 'Operations & Day Job',
          status: 'active',
          tasks_completed_today: 4,
          current_tasks: 1,
          last_activity: '8 minutes ago',
          specialization: ['QuickBooks', 'Email Processing', 'Operations']
        },
        {
          name: 'keeper',
          role: 'Maintenance & Automation',
          status: 'active',
          tasks_completed_today: 5,
          current_tasks: 0,
          last_activity: '15 minutes ago',
          specialization: ['System Health', 'Backups', 'Cron Jobs']
        }
      ]);

      setActivities([
        {
          id: 1,
          agent_name: 'rex',
          activity_type: 'research',
          task_description: 'Validating OpenClaw template marketplace demand',
          status: 'in_progress',
          priority: 5,
          created_at: new Date(Date.now() - 1000 * 60 * 15).toISOString(), // 15 min ago
        },
        {
          id: 2,
          agent_name: 'pixel',
          activity_type: 'validation',
          task_description: 'Creating digital product pricing analysis',
          status: 'in_progress',
          priority: 4,
          created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(), // 30 min ago
        },
        {
          id: 3,
          agent_name: 'scout',
          activity_type: 'quality_check',
          task_description: 'Phase 2 validation for automation templates opportunity',
          status: 'in_progress',
          priority: 5,
          created_at: new Date(Date.now() - 1000 * 60 * 45).toISOString(), // 45 min ago
        },
        {
          id: 4,
          agent_name: 'nora',
          activity_type: 'processing',
          task_description: 'Processing utility bills and updating spreadsheet',
          status: 'completed',
          priority: 3,
          created_at: new Date(Date.now() - 1000 * 60 * 60).toISOString(), // 1 hour ago
          completed_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(), // 30 min ago
        },
        {
          id: 5,
          agent_name: 'keeper',
          activity_type: 'maintenance',
          task_description: 'Daily backup and system health check',
          status: 'completed',
          priority: 2,
          created_at: new Date(Date.now() - 1000 * 60 * 90).toISOString(), // 1.5 hours ago
          completed_at: new Date(Date.now() - 1000 * 60 * 75).toISOString(), // 1.25 hours ago
        }
      ]);

    } catch (error) {
      console.error('Failed to load agent data:', error);
    }
    setLoading(false);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500/20 text-green-400 border-green-500/30';
      case 'busy': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      case 'idle': return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
      default: return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
    }
  };

  const getActivityStatusIcon = (status: string) => {
    switch (status) {
      case 'in_progress': return <PlayCircle className="h-4 w-4 text-blue-400" />;
      case 'completed': return <CheckCircle className="h-4 w-4 text-green-400" />;
      default: return <AlertCircle className="h-4 w-4 text-slate-400" />;
    }
  };

  const getPriorityColor = (priority: number) => {
    if (priority >= 5) return 'text-red-400';
    if (priority >= 4) return 'text-yellow-400';
    if (priority >= 3) return 'text-blue-400';
    return 'text-slate-400';
  };

  const filteredActivities = selectedAgent === 'all' 
    ? activities 
    : activities.filter(activity => activity.agent_name === selectedAgent);

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-slate-800 rounded mb-6"></div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="h-32 bg-slate-800 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100 mb-2">Agent Coordination</h2>
          <p className="text-slate-400">Real-time multi-agent system monitoring</p>
        </div>
      </div>

      {/* Agent Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agentStats.map((agent) => (
          <div key={agent.name} className="bg-slate-800 rounded-lg border border-slate-700 p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-3">
                <div className="w-3 h-3 rounded-full bg-gradient-to-r from-blue-400 to-purple-400"></div>
                <h3 className="font-semibold text-slate-200 capitalize">{agent.name}</h3>
              </div>
              <span className={`px-2 py-1 text-xs font-medium rounded border ${getStatusColor(agent.status)} capitalize`}>
                {agent.status}
              </span>
            </div>
            
            <p className="text-sm text-slate-400 mb-3">{agent.role}</p>
            
            <div className="grid grid-cols-2 gap-3 text-sm mb-3">
              <div>
                <span className="text-slate-500">Today:</span>
                <span className="text-slate-200 ml-1 font-medium">{agent.tasks_completed_today}</span>
              </div>
              <div>
                <span className="text-slate-500">Active:</span>
                <span className="text-slate-200 ml-1 font-medium">{agent.current_tasks}</span>
              </div>
            </div>
            
            <div className="flex items-center text-xs text-slate-500">
              <Clock className="h-3 w-3 mr-1" />
              Last activity: {agent.last_activity}
            </div>
          </div>
        ))}
      </div>

      {/* Activity Feed */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="p-4 border-b border-slate-700">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-slate-200 flex items-center">
              <Activity className="h-5 w-5 mr-2" />
              Recent Activity
            </h3>
            
            <select
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              className="bg-slate-700 border border-slate-600 rounded-md px-3 py-1.5 text-sm text-slate-200"
            >
              <option value="all">All Agents</option>
              {agentStats.map(agent => (
                <option key={agent.name} value={agent.name} className="capitalize">
                  {agent.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        
        <div className="divide-y divide-slate-700">
          {filteredActivities.length === 0 ? (
            <div className="p-8 text-center">
              <Users className="h-12 w-12 text-slate-600 mx-auto mb-4" />
              <p className="text-slate-400">No recent activity</p>
            </div>
          ) : (
            filteredActivities.map((activity) => (
              <div key={activity.id} className="p-4 hover:bg-slate-800/50 transition-colors">
                <div className="flex items-start space-x-3">
                  <div className="mt-1">
                    {getActivityStatusIcon(activity.status)}
                  </div>
                  
                  <div className="flex-1">
                    <div className="flex items-center space-x-2 mb-1">
                      <span className="font-medium text-slate-200 capitalize">{activity.agent_name}</span>
                      <span className="text-slate-500">•</span>
                      <span className="text-sm text-slate-400 capitalize">{activity.activity_type.replace('_', ' ')}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${getPriorityColor(activity.priority)}`}>
                        P{activity.priority}
                      </span>
                    </div>
                    
                    <p className="text-sm text-slate-300 mb-2">{activity.task_description}</p>
                    
                    <div className="flex items-center text-xs text-slate-500 space-x-4">
                      <span>Started {new Date(activity.created_at).toLocaleTimeString()}</span>
                      {activity.completed_at && (
                        <span>Completed {new Date(activity.completed_at).toLocaleTimeString()}</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}