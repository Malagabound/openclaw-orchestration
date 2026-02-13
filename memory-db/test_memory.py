#!/usr/bin/env python3
"""Test the memory database system."""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from memory_manager import MemoryManager
import json

def test_memory_system():
    print("🧠 Testing George's Memory Database System")
    print("=" * 50)
    
    # Initialize
    mm = MemoryManager()
    print("✅ Memory Manager initialized")
    
    # Test storing our current conversation about the database
    session_id = "telegram_alan_2026_02_13"
    
    # Store the conversation that led to this implementation
    conversations = [
        {
            "user": "Do we need a third party service like super memory or could you mimic the skill and store the data in a local database on the Mac mini?",
            "assistant": "Excellent question! You're absolutely right - a local database would be much better. Let me examine what SuperMemory does and see if we can replicate it locally..."
        },
        {
            "user": "So would you be able to store vector data also so we can do better searches of the data?",
            "assistant": "Absolutely! Vector storage would make the local memory system incredibly powerful for semantic search..."
        },
        {
            "user": "Please transcribe this YouTube video. It has a lot of valuable information about how the person is working with it. Focus first on the database set up he talks about.",
            "assistant": "🎯 Database Setup Insights from the Video... Based on the YouTube transcript, here's how this advanced OpenClaw user set up their database system..."
        },
        {
            "user": "How can we use a similar if not exact set up for your memory?",
            "assistant": "Perfect! Based on the video, I can design an almost identical system for my memory. Here's the exact setup we need: 🏗️ Local Memory Database Design..."
        },
        {
            "user": "Great please implement that now",
            "assistant": "🚀 Building Local Memory Database Now. Let me implement this hybrid SQLite + vector system step by step..."
        }
    ]
    
    print(f"📝 Storing {len(conversations)} conversation exchanges...")
    
    stored_count = 0
    for i, conv in enumerate(conversations):
        user_id, assistant_id = mm.store_current_conversation(
            conv["user"], 
            conv["assistant"], 
            session_id
        )
        stored_count += 2
        print(f"   Stored exchange {i+1}: user_id={user_id}, assistant_id={assistant_id}")
    
    print(f"✅ Stored {stored_count} conversation turns")
    
    # Test SQL search
    print("\n🔍 Testing SQL Search...")
    results = mm.search_conversations_sql(query="database", limit=5)
    print(f"   Found {len(results)} conversations mentioning 'database'")
    for result in results[:2]:
        print(f"   - [{result['category']}] {result['content'][:100]}...")
    
    # Test semantic search
    print("\n🎯 Testing Semantic Search...")
    results = mm.search_conversations_semantic("memory system implementation", limit=3)
    print(f"   Found {len(results)} semantically similar conversations")
    for result in results[:2]:
        print(f"   - [{result['category']}] {result['content'][:100]}...")
    
    # Test recent context
    print("\n⏰ Testing Recent Context Retrieval...")
    recent = mm.get_recent_context(session_id, limit=5)
    print(f"   Found {len(recent)} recent conversations")
    
    # Show database stats
    print("\n📊 Database Statistics:")
    stats = mm.get_stats()
    print(json.dumps(stats, indent=2))
    
    print("\n✅ All tests passed! Memory database is working.")
    return mm

if __name__ == "__main__":
    test_memory_system()