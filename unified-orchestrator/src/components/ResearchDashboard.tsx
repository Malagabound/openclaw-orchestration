'use client';

import { useState, useEffect } from 'react';
import { TrendingUp, ExternalLink, Calendar, Star, Filter } from 'lucide-react';

interface ResearchOpportunity {
  id: number;
  title: string;
  domain: 'digital_products' | 'saas';
  market_demand_score: number;
  phase_status: 'phase_2' | 'phase_3' | 'approved' | 'building';
  discovery_date: string;
  validation_date?: string;
  presented_date?: string;
  case_studies?: string;
  differentiation_thesis?: string;
  revenue_projection?: string;
  template_url?: string;
}

export default function ResearchDashboard() {
  const [opportunities, setOpportunities] = useState<ResearchOpportunity[]>([]);
  const [filter, setFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadOpportunities();
  }, [filter]);

  const loadOpportunities = async () => {
    try {
      const response = await fetch(`/api/research?filter=${filter}`);
      const data = await response.json();
      setOpportunities(data);
    } catch (error) {
      console.error('Failed to load research opportunities:', error);
      // Mock data for development
      setOpportunities([
        {
          id: 1,
          title: "OpenClaw Automation Templates",
          domain: "digital_products",
          market_demand_score: 28,
          phase_status: "phase_2",
          discovery_date: "2026-02-10",
          validation_date: "2026-02-13",
          case_studies: "Analyzed 15 competing template packs on Gumroad. Top sellers: $2-5k/month. Clear market demand for OpenClaw-specific automation templates.",
          differentiation_thesis: "First-to-market with comprehensive OpenClaw agent templates. Existing solutions are generic AI templates.",
          revenue_projection: "$1,500-3,000/month within 90 days",
          template_url: "https://docs.google.com/document/d/1abc123/edit"
        },
        {
          id: 2,
          title: "Multi-Agent Orchestration SaaS",
          domain: "saas",
          market_demand_score: 26,
          phase_status: "phase_3",
          discovery_date: "2026-02-08",
          validation_date: "2026-02-12",
          presented_date: "2026-02-13",
          case_studies: "Surveyed 50 OpenClaw users. 78% struggle with agent coordination. No existing solutions address this specific need.",
          differentiation_thesis: "Only solution built specifically for OpenClaw multi-agent systems. Competitors focus on generic AI automation.",
          revenue_projection: "$5,000-12,000/month at scale"
        }
      ]);
    }
    setLoading(false);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'phase_2': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      case 'phase_3': return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      case 'approved': return 'bg-green-500/20 text-green-400 border-green-500/30';
      case 'building': return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
      default: return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'phase_2': return 'Deep Validation';
      case 'phase_3': return 'Awaiting Approval';
      case 'approved': return 'Approved for Phase 3';
      case 'building': return 'In Development';
      default: return status;
    }
  };

  const getDomainLabel = (domain: string) => {
    return domain === 'digital_products' ? 'Digital Products' : 'SaaS';
  };

  const getDomainColor = (domain: string) => {
    return domain === 'digital_products' 
      ? 'bg-orange-500/20 text-orange-400' 
      : 'bg-cyan-500/20 text-cyan-400';
  };

  if (loading) {
    return (
      <div className="animate-pulse">
        <div className="h-8 bg-slate-800 rounded mb-6"></div>
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
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
          <h2 className="text-2xl font-bold text-slate-100 mb-2">Research Opportunities</h2>
          <p className="text-slate-400">Phase 2+ validated opportunities ranked by market demand</p>
        </div>
        
        <div className="flex items-center space-x-3">
          <Filter className="h-4 w-4 text-slate-400" />
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-200"
          >
            <option value="all">All Phases</option>
            <option value="phase_2">Deep Validation</option>
            <option value="phase_3">Awaiting Approval</option>
            <option value="approved">Approved</option>
            <option value="building">Building</option>
          </select>
        </div>
      </div>

      {/* Opportunities List */}
      {opportunities.length === 0 ? (
        <div className="text-center py-12 bg-slate-800/50 rounded-lg border border-slate-700">
          <TrendingUp className="h-12 w-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-400 mb-2">No opportunities yet</h3>
          <p className="text-slate-500">Research opportunities will appear here as agents discover them</p>
        </div>
      ) : (
        <div className="space-y-4">
          {opportunities.map((opportunity) => (
            <div key={opportunity.id} className="bg-slate-800 rounded-lg border border-slate-700 p-6 hover:border-slate-600 transition-colors">
              {/* Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <h3 className="text-xl font-semibold text-slate-100">{opportunity.title}</h3>
                    <span className={`px-2 py-1 text-xs font-medium rounded border ${getDomainColor(opportunity.domain)}`}>
                      {getDomainLabel(opportunity.domain)}
                    </span>
                  </div>
                  
                  <div className="flex items-center space-x-4 text-sm text-slate-400">
                    <span className={`px-2 py-1 text-xs font-medium rounded border ${getStatusColor(opportunity.phase_status)}`}>
                      {getStatusLabel(opportunity.phase_status)}
                    </span>
                    <div className="flex items-center space-x-1">
                      <Star className="h-4 w-4 text-yellow-400" />
                      <span className="font-medium text-yellow-400">{opportunity.market_demand_score}/30</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Calendar className="h-4 w-4" />
                      <span>Discovered {new Date(opportunity.discovery_date).toLocaleDateString()}</span>
                    </div>
                  </div>
                </div>
                
                {opportunity.template_url && (
                  <a
                    href={opportunity.template_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center space-x-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-md transition-colors"
                  >
                    <span>View Details</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>

              {/* Content */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {opportunity.case_studies && (
                  <div>
                    <h4 className="text-sm font-medium text-slate-300 mb-2">Market Validation</h4>
                    <p className="text-slate-400 text-sm leading-relaxed">{opportunity.case_studies}</p>
                  </div>
                )}
                
                {opportunity.differentiation_thesis && (
                  <div>
                    <h4 className="text-sm font-medium text-slate-300 mb-2">Differentiation</h4>
                    <p className="text-slate-400 text-sm leading-relaxed">{opportunity.differentiation_thesis}</p>
                  </div>
                )}
                
                {opportunity.revenue_projection && (
                  <div className="md:col-span-2">
                    <h4 className="text-sm font-medium text-slate-300 mb-2">Revenue Projection</h4>
                    <p className="text-green-400 text-sm font-medium">{opportunity.revenue_projection}</p>
                  </div>
                )}
              </div>

              {/* Actions */}
              {opportunity.phase_status === 'phase_3' && (
                <div className="mt-6 pt-4 border-t border-slate-700 flex space-x-3">
                  <button className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white text-sm rounded-md transition-colors">
                    Approve for Phase 3
                  </button>
                  <button className="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded-md transition-colors">
                    Request Changes
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}