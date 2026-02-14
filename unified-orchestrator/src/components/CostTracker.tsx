'use client';

import { useState, useEffect } from 'react';
import { BarChart3, TrendingDown, DollarSign, Zap, AlertTriangle, Target } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

interface ModelUsage {
  model: string;
  total_calls: number;
  total_tokens: number;
  total_cost: number;
  task_type: string;
}

interface DailyUsage {
  date: string;
  calls: number;
  cost: number;
  tokens: number;
}

interface CostOptimization {
  category: string;
  current_model: string;
  suggested_model: string;
  potential_savings: number;
  task_count: number;
  description: string;
}

export default function CostTracker() {
  const [modelUsage, setModelUsage] = useState<ModelUsage[]>([]);
  const [dailyUsage, setDailyUsage] = useState<DailyUsage[]>([]);
  const [optimizations, setOptimizations] = useState<CostOptimization[]>([]);
  const [totalCost, setTotalCost] = useState(0);
  const [savingsTarget, setSavingsTarget] = useState(70); // 70% savings goal
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCostData();
  }, []);

  const loadCostData = async () => {
    try {
      // In real implementation, this would call our API
      // Mock data representing our actual cost tracking needs
      
      const mockModelUsage: ModelUsage[] = [
        {
          model: 'claude-sonnet-4-20250514',
          total_calls: 156,
          total_tokens: 450000,
          total_cost: 18.75,
          task_type: 'research'
        },
        {
          model: 'claude-sonnet-4-20250514',
          total_calls: 89,
          total_tokens: 280000,
          total_cost: 11.65,
          task_type: 'validation'
        },
        {
          model: 'claude-opus-4-6',
          total_calls: 12,
          total_tokens: 95000,
          total_cost: 8.95,
          task_type: 'strategy'
        },
        {
          model: 'claude-haiku-3-20240307',
          total_calls: 234,
          total_tokens: 180000,
          total_cost: 1.44,
          task_type: 'operations'
        },
        {
          model: 'gpt-4-turbo',
          total_calls: 45,
          total_tokens: 120000,
          total_cost: 4.50,
          task_type: 'analysis'
        }
      ];

      const mockDailyUsage: DailyUsage[] = [
        { date: 'Feb 7', calls: 45, cost: 5.23, tokens: 125000 },
        { date: 'Feb 8', calls: 67, cost: 7.89, tokens: 189000 },
        { date: 'Feb 9', calls: 52, cost: 6.12, tokens: 145000 },
        { date: 'Feb 10', calls: 71, cost: 8.45, tokens: 201000 },
        { date: 'Feb 11', calls: 38, cost: 4.67, tokens: 98000 },
        { date: 'Feb 12', calls: 84, cost: 9.87, tokens: 235000 },
        { date: 'Feb 13', calls: 91, cost: 11.23, tokens: 267000 }
      ];

      const mockOptimizations: CostOptimization[] = [
        {
          category: 'Research Tasks',
          current_model: 'claude-sonnet-4',
          suggested_model: 'claude-haiku-3',
          potential_savings: 12.50,
          task_count: 156,
          description: 'Simple data extraction and formatting tasks can use cheaper model'
        },
        {
          category: 'Email Processing',
          current_model: 'claude-sonnet-4',
          suggested_model: 'claude-haiku-3',
          potential_savings: 8.30,
          task_count: 89,
          description: 'Email categorization and basic parsing doesn\'t require premium model'
        },
        {
          category: 'Validation Checks',
          current_model: 'gpt-4-turbo',
          suggested_model: 'claude-sonnet-4',
          potential_savings: 2.25,
          task_count: 45,
          description: 'Switch to more cost-effective model with similar capabilities'
        }
      ];

      setModelUsage(mockModelUsage);
      setDailyUsage(mockDailyUsage);
      setOptimizations(mockOptimizations);
      setTotalCost(mockModelUsage.reduce((sum, usage) => sum + usage.total_cost, 0));

    } catch (error) {
      console.error('Failed to load cost data:', error);
    }
    setLoading(false);
  };

  const modelColors = {
    'claude-sonnet-4-20250514': '#3b82f6',
    'claude-opus-4-6': '#8b5cf6', 
    'claude-haiku-3-20240307': '#10b981',
    'gpt-4-turbo': '#f59e0b',
  };

  const potentialSavings = optimizations.reduce((sum, opt) => sum + opt.potential_savings, 0);
  const currentSavingsPercent = Math.round((potentialSavings / totalCost) * 100);

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-slate-800 rounded mb-6"></div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-24 bg-slate-800 rounded"></div>
          ))}
        </div>
        <div className="h-64 bg-slate-800 rounded"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100 mb-2">AI Cost Optimization</h2>
          <p className="text-slate-400">Track usage and optimize model routing for maximum efficiency</p>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
          <div className="flex items-center justify-between mb-2">
            <DollarSign className="h-8 w-8 text-green-400" />
            <span className="text-2xl font-bold text-slate-100">${totalCost.toFixed(2)}</span>
          </div>
          <p className="text-slate-400 text-sm">Total Cost (7 days)</p>
          <p className="text-green-400 text-xs mt-1">-15% vs last week</p>
        </div>

        <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
          <div className="flex items-center justify-between mb-2">
            <Target className="h-8 w-8 text-blue-400" />
            <span className="text-2xl font-bold text-slate-100">{currentSavingsPercent}%</span>
          </div>
          <p className="text-slate-400 text-sm">Potential Savings</p>
          <p className="text-slate-500 text-xs mt-1">Target: {savingsTarget}%</p>
        </div>

        <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
          <div className="flex items-center justify-between mb-2">
            <Zap className="h-8 w-8 text-yellow-400" />
            <span className="text-2xl font-bold text-slate-100">
              {modelUsage.reduce((sum, usage) => sum + usage.total_calls, 0)}
            </span>
          </div>
          <p className="text-slate-400 text-sm">Total API Calls</p>
          <p className="text-yellow-400 text-xs mt-1">+23% efficiency</p>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Daily Usage Trend */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
          <h3 className="text-lg font-semibold text-slate-200 mb-4 flex items-center">
            <BarChart3 className="h-5 w-5 mr-2" />
            Daily Usage Trend
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={dailyUsage}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" stroke="#9ca3af" fontSize={12} />
              <YAxis stroke="#9ca3af" fontSize={12} />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1e293b', 
                  border: '1px solid #374151',
                  borderRadius: '6px'
                }}
              />
              <Bar dataKey="cost" fill="#3b82f6" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Model Usage Distribution */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
          <h3 className="text-lg font-semibold text-slate-200 mb-4">Model Usage by Cost</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={modelUsage}
                cx="50%"
                cy="50%"
                outerRadius={80}
                dataKey="total_cost"
                label={({ model, total_cost }) => `$${total_cost.toFixed(2)}`}
              >
                {modelUsage.map((entry, index) => (
                  <Cell 
                    key={`cell-${index}`} 
                    fill={modelColors[entry.model as keyof typeof modelColors] || '#64748b'} 
                  />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1e293b', 
                  border: '1px solid #374151',
                  borderRadius: '6px'
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Optimization Recommendations */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="p-6 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-slate-200 flex items-center">
            <TrendingDown className="h-5 w-5 mr-2 text-green-400" />
            Cost Optimization Opportunities
          </h3>
          <p className="text-slate-400 text-sm mt-1">
            Potential savings: <span className="text-green-400 font-medium">${potentialSavings.toFixed(2)}/week</span>
          </p>
        </div>
        
        <div className="divide-y divide-slate-700">
          {optimizations.map((opt, index) => (
            <div key={index} className="p-6 hover:bg-slate-800/50 transition-colors">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h4 className="font-medium text-slate-200 mb-1">{opt.category}</h4>
                  <p className="text-sm text-slate-400">{opt.description}</p>
                </div>
                <div className="text-right">
                  <div className="text-lg font-semibold text-green-400">
                    ${opt.potential_savings.toFixed(2)}
                  </div>
                  <div className="text-xs text-slate-500">savings/week</div>
                </div>
              </div>
              
              <div className="flex items-center space-x-4 text-sm">
                <div className="flex items-center space-x-2">
                  <span className="text-slate-500">Current:</span>
                  <span className="px-2 py-1 bg-red-500/20 text-red-400 rounded border border-red-500/30">
                    {opt.current_model}
                  </span>
                </div>
                <div className="text-slate-400">→</div>
                <div className="flex items-center space-x-2">
                  <span className="text-slate-500">Suggested:</span>
                  <span className="px-2 py-1 bg-green-500/20 text-green-400 rounded border border-green-500/30">
                    {opt.suggested_model}
                  </span>
                </div>
                <div className="text-slate-500 ml-auto">
                  {opt.task_count} tasks affected
                </div>
              </div>
              
              <div className="mt-4">
                <button className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-md transition-colors">
                  Apply Optimization
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Detailed Usage Table */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="p-6 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-slate-200">Detailed Usage by Model & Task</h3>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-700/50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Model
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Task Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Calls
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Tokens
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Cost
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {modelUsage.map((usage, index) => (
                <tr key={index} className="hover:bg-slate-700/25">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-200">
                    {usage.model}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-300 capitalize">
                    {usage.task_type}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-300">
                    {usage.total_calls.toLocaleString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-300">
                    {usage.total_tokens.toLocaleString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-green-400">
                    ${usage.total_cost.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}