#!/usr/bin/env python3
"""
George's Memory CLI - Command line interface for memory database
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from memory_manager import MemoryManager
import json
import argparse
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description="George's Memory Database CLI")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Store command
    store_parser = subparsers.add_parser('store', help='Store a conversation')
    store_parser.add_argument('--session', required=True, help='Session ID')
    store_parser.add_argument('--role', choices=['user', 'assistant'], required=True, help='Speaker role')
    store_parser.add_argument('--content', required=True, help='Message content')
    store_parser.add_argument('--importance', type=int, default=3, help='Importance score (1-5)')
    store_parser.add_argument('--category', default='general', help='Category')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search conversations')
    search_parser.add_argument('--query', help='Search query')
    search_parser.add_argument('--category', help='Filter by category')
    search_parser.add_argument('--importance', type=int, help='Minimum importance score')
    search_parser.add_argument('--days', type=int, help='Days back to search')
    search_parser.add_argument('--limit', type=int, default=10, help='Max results')
    search_parser.add_argument('--semantic', action='store_true', help='Use semantic search')
    
    # Recent command
    recent_parser = subparsers.add_parser('recent', help='Get recent conversations')
    recent_parser.add_argument('--session', help='Session ID')
    recent_parser.add_argument('--limit', type=int, default=10, help='Max results')
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show database statistics')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import from memory files')
    import_parser.add_argument('--file', help='Memory file to import')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    mm = MemoryManager()
    
    if args.command == 'store':
        conversation_id = mm.store_conversation(
            session_id=args.session,
            role=args.role,
            content=args.content,
            importance_score=args.importance,
            category=args.category
        )
        print(f"✅ Stored conversation with ID: {conversation_id}")
    
    elif args.command == 'search':
        if args.semantic and args.query:
            results = mm.search_conversations_semantic(args.query, args.limit)
        else:
            results = mm.search_conversations_sql(
                query=args.query,
                category=args.category,
                importance_min=args.importance,
                days_back=args.days,
                limit=args.limit
            )
        
        print(f"🔍 Found {len(results)} conversations:")
        for result in results:
            timestamp = result.get('timestamp', '')
            category = result.get('category', '')
            importance = result.get('importance_score', '')
            content = result.get('content', '')[:200]
            
            print(f"\n[{timestamp}] [{category}] [⭐{importance}]")
            print(f"   {content}...")
    
    elif args.command == 'recent':
        results = mm.get_recent_context(args.session or 'all', args.limit)
        print(f"⏰ Recent {len(results)} conversations:")
        
        for result in results:
            timestamp = result.get('timestamp', '')
            role = result.get('role', '')
            content = result.get('content', '')[:150]
            
            print(f"\n[{timestamp}] {role}:")
            print(f"   {content}...")
    
    elif args.command == 'stats':
        stats = mm.get_stats()
        print("📊 Memory Database Statistics:")
        print(json.dumps(stats, indent=2))
    
    elif args.command == 'import':
        if args.file:
            print(f"📥 Importing from {args.file}")
            # TODO: Implement memory file import
            print("Import functionality coming soon...")
        else:
            print("❌ Please specify a file to import with --file")

if __name__ == "__main__":
    main()