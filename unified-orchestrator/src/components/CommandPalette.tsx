'use client';

import { useState, useEffect, useRef } from 'react';
import { Search, FileText, Brain, Users, X, ArrowRight } from 'lucide-react';

interface SearchResult {
  type: 'research' | 'conversation' | 'agent' | 'task';
  title: string;
  description: string;
  metadata?: string;
  url?: string;
  id?: string;
}

interface CommandPaletteProps {
  onClose: () => void;
}

export default function CommandPalette({ onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Focus input when component mounts
    inputRef.current?.focus();

    // Handle escape key
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  useEffect(() => {
    if (query.length > 2) {
      performSearch(query);
    } else {
      setResults([]);
    }
  }, [query]);

  const performSearch = async (searchQuery: string) => {
    setLoading(true);
    try {
      // In a real implementation, this would call our API
      // For now, simulating search results
      await new Promise(resolve => setTimeout(resolve, 200)); // Simulate API delay
      
      const mockResults: SearchResult[] = [
        {
          type: 'research',
          title: 'OpenClaw Automation Templates',
          description: 'Digital product opportunity with 28/30 market demand score',
          metadata: 'Phase 2 • Digital Products • Feb 13',
          url: 'https://docs.google.com/document/d/1abc123/edit'
        },
        {
          type: 'research',
          title: 'Multi-Agent Orchestration SaaS',
          description: 'SaaS opportunity targeting OpenClaw users needing agent coordination',
          metadata: 'Phase 3 • SaaS • Feb 12',
          url: 'https://docs.google.com/document/d/1def456/edit'
        },
        {
          type: 'conversation',
          title: 'Discussion about research workflow automation',
          description: 'Conversation covering Phase 1/2/3 validation process and agent coordination',
          metadata: 'Feb 13 • 45 messages • High importance',
        },
        {
          type: 'conversation',
          title: 'GitHub process and daily automation setup',
          description: 'Technical discussion about setting up daily git commits and cron jobs',
          metadata: 'Feb 13 • 23 messages • Technical',
        },
        {
          type: 'agent',
          title: 'Rex - Research Agent Activity',
          description: 'Currently validating 2 opportunities, completed 5 tasks this week',
          metadata: 'Research & Market Analysis • Active',
        },
        {
          type: 'agent',
          title: 'Scout - Validation Agent',
          description: 'Phase 2 validation in progress for OpenClaw templates opportunity',
          metadata: 'Quality & Validation • In Progress',
        }
      ].filter(result => 
        result.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        result.description.toLowerCase().includes(searchQuery.toLowerCase())
      );

      setResults(mockResults);
      setSelectedIndex(0);
    } catch (error) {
      console.error('Search failed:', error);
      setResults([]);
    }
    setLoading(false);
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => Math.min(prev + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter' && results[selectedIndex]) {
      e.preventDefault();
      handleSelect(results[selectedIndex]);
    }
  };

  const handleSelect = (result: SearchResult) => {
    if (result.url) {
      window.open(result.url, '_blank');
    }
    // Here we could also trigger navigation or other actions based on result type
    onClose();
  };

  const getResultIcon = (type: string) => {
    switch (type) {
      case 'research': return Brain;
      case 'conversation': return FileText;
      case 'agent': return Users;
      default: return Search;
    }
  };

  const getResultColor = (type: string) => {
    switch (type) {
      case 'research': return 'text-blue-400';
      case 'conversation': return 'text-green-400';
      case 'agent': return 'text-purple-400';
      default: return 'text-slate-400';
    }
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case 'research': return 'Research';
      case 'conversation': return 'Conversation';
      case 'agent': return 'Agent';
      default: return 'Unknown';
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      
      {/* Command Palette */}
      <div className="relative min-h-screen flex items-start justify-center p-4 pt-16">
        <div className="bg-slate-800 rounded-lg border border-slate-700 shadow-2xl w-full max-w-2xl">
          {/* Search Input */}
          <div className="flex items-center border-b border-slate-700 px-4">
            <Search className="h-5 w-5 text-slate-400 mr-3" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => handleKeyDown(e.nativeEvent)}
              placeholder="Search research, conversations, agents..."
              className="w-full py-4 bg-transparent text-slate-200 placeholder-slate-500 focus:outline-none"
            />
            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-slate-200 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Results */}
          <div className="max-h-96 overflow-y-auto">
            {loading && (
              <div className="px-4 py-8 text-center">
                <div className="animate-spin h-6 w-6 border-2 border-blue-400 border-t-transparent rounded-full mx-auto mb-2"></div>
                <p className="text-slate-400 text-sm">Searching...</p>
              </div>
            )}

            {!loading && query.length > 0 && results.length === 0 && (
              <div className="px-4 py-8 text-center">
                <p className="text-slate-400">No results found for "{query}"</p>
              </div>
            )}

            {!loading && query.length <= 2 && (
              <div className="px-4 py-8 text-center">
                <p className="text-slate-500 text-sm">Type to search across research, conversations, and agents</p>
              </div>
            )}

            {results.map((result, index) => {
              const Icon = getResultIcon(result.type);
              const isSelected = index === selectedIndex;
              
              return (
                <button
                  key={`${result.type}-${index}`}
                  onClick={() => handleSelect(result)}
                  className={`w-full px-4 py-3 flex items-center space-x-3 hover:bg-slate-700 transition-colors text-left ${
                    isSelected ? 'bg-slate-700' : ''
                  }`}
                >
                  <Icon className={`h-5 w-5 flex-shrink-0 ${getResultColor(result.type)}`} />
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-2 mb-1">
                      <h3 className="font-medium text-slate-200 truncate">{result.title}</h3>
                      <span className={`px-2 py-0.5 text-xs font-medium rounded ${getResultColor(result.type)} bg-current bg-opacity-20`}>
                        {getTypeLabel(result.type)}
                      </span>
                    </div>
                    <p className="text-sm text-slate-400 truncate">{result.description}</p>
                    {result.metadata && (
                      <p className="text-xs text-slate-500 mt-1">{result.metadata}</p>
                    )}
                  </div>

                  {result.url && (
                    <ArrowRight className="h-4 w-4 text-slate-500 flex-shrink-0" />
                  )}
                </button>
              );
            })}
          </div>

          {/* Footer */}
          {results.length > 0 && (
            <div className="border-t border-slate-700 px-4 py-2 text-xs text-slate-500 flex justify-between">
              <span>↑↓ to navigate</span>
              <span>↵ to select</span>
              <span>esc to close</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}