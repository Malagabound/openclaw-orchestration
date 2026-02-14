'use client';

import { useState, useEffect } from 'react';
import { Search, BarChart3, Users, Brain, Settings, Zap } from 'lucide-react';
import CommandPalette from '../components/CommandPalette';
import ResearchDashboard from '../components/ResearchDashboard';
import AgentMonitor from '../components/AgentMonitor';
import CostTracker from '../components/CostTracker';

export default function UnifiedOrchestrator() {
  const [activeView, setActiveView] = useState('research');
  const [showCommandPalette, setShowCommandPalette] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setShowCommandPalette(true);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  const views = [
    { id: 'research', name: 'Research', icon: Brain, description: 'Market opportunities & validation' },
    { id: 'agents', name: 'Agents', icon: Users, description: 'Multi-agent coordination' },
    { id: 'costs', name: 'Optimization', icon: BarChart3, description: 'AI usage & cost tracking' },
    { id: 'memory', name: 'Memory', icon: Search, description: 'Knowledge & conversations' },
  ];

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      {/* Header */}
      <div className="border-b border-slate-800 bg-slate-900/95 backdrop-blur-sm sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <Zap className="h-8 w-8 text-blue-400" />
                <h1 className="text-xl font-bold text-slate-100">OpenClaw Orchestrator</h1>
              </div>
              
              <div className="hidden md:flex items-center space-x-1">
                {views.map((view) => (
                  <button
                    key={view.id}
                    onClick={() => setActiveView(view.id)}
                    className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                      activeView === view.id
                        ? 'bg-slate-800 text-blue-400'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                    }`}
                  >
                    <view.icon className="h-4 w-4 inline mr-2" />
                    {view.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center space-x-4">
              <button
                onClick={() => setShowCommandPalette(true)}
                className="px-3 py-1.5 text-sm bg-slate-800 hover:bg-slate-700 rounded-md border border-slate-700 transition-colors"
              >
                <Search className="h-4 w-4 inline mr-2" />
                Search... <span className="text-slate-500">⌘K</span>
              </button>
              
              <button className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition-colors">
                <Settings className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Navigation */}
      <div className="md:hidden border-b border-slate-800 bg-slate-900">
        <div className="px-4 py-3">
          <div className="grid grid-cols-4 gap-2">
            {views.map((view) => (
              <button
                key={view.id}
                onClick={() => setActiveView(view.id)}
                className={`p-3 rounded-lg text-center transition-colors ${
                  activeView === view.id
                    ? 'bg-slate-800 text-blue-400'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                }`}
              >
                <view.icon className="h-5 w-5 mx-auto mb-1" />
                <div className="text-xs font-medium">{view.name}</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeView === 'research' && <ResearchDashboard />}
        {activeView === 'agents' && <AgentMonitor />}
        {activeView === 'costs' && <CostTracker />}
        {activeView === 'memory' && (
          <div className="text-center py-12">
            <Brain className="h-12 w-12 text-slate-600 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-400 mb-2">Memory Search</h3>
            <p className="text-slate-500">Use ⌘K to search conversations and knowledge</p>
          </div>
        )}
      </div>

      {/* Command Palette */}
      {showCommandPalette && (
        <CommandPalette onClose={() => setShowCommandPalette(false)} />
      )}
    </div>
  );
}