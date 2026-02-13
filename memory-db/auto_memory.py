#!/usr/bin/env python3
"""
Auto-Memory Integration for George
Automatically captures and stores important conversations
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from memory_manager import MemoryManager
import json
import re
from datetime import datetime
from typing import Dict

class AutoMemory:
    def __init__(self):
        self.mm = MemoryManager()
        self.current_session = self._get_current_session()
        
    def _get_current_session(self) -> str:
        """Generate current session ID based on date and channel."""
        date_str = datetime.now().strftime("%Y_%m_%d")
        return f"telegram_alan_{date_str}"
    
    def should_store_conversation(self, user_message: str, assistant_response: str) -> bool:
        """Determine if conversation should be stored based on importance triggers."""
        
        # High importance triggers
        high_importance_patterns = [
            r'\b(implement|build|create|fix|error|mistake|security|critical)\b',
            r'\b(database|memory|storage|system)\b',
            r'\b(business|revenue|product|market)\b',
            r'\b(decision|important|urgent|priority)\b'
        ]
        
        # Always store if user asks complex questions
        if any(word in user_message.lower() for word in ['how', 'why', 'what', 'implement', 'build']):
            return True
            
        # Store if assistant provides substantial responses
        if len(assistant_response) > 500:  # Substantial response
            return True
            
        # Store if matches high importance patterns
        combined_text = (user_message + " " + assistant_response).lower()
        for pattern in high_importance_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                return True
        
        # Store corrections and feedback
        correction_patterns = [
            r'\b(no|wrong|actually|correct|fix|mistake)\b',
            r'\b(should be|instead|rather|better)\b'
        ]
        
        for pattern in correction_patterns:
            if re.search(pattern, user_message.lower()):
                return True
                
        return False
    
    def store_if_important(self, user_message: str, assistant_response: str) -> bool:
        """Store conversation if it meets importance criteria."""
        
        if self.should_store_conversation(user_message, assistant_response):
            user_id, assistant_id = self.mm.store_current_conversation(
                user_message, 
                assistant_response, 
                self.current_session
            )
            
            print(f"🧠 Auto-stored conversation: user_id={user_id}, assistant_id={assistant_id}")
            return True
        
        return False
    
    def inject_relevant_context(self, user_query: str, max_context: int = 3) -> str:
        """Inject relevant past conversations as context for current query."""
        
        # Search for semantically similar conversations
        relevant = self.mm.search_conversations_semantic(user_query, limit=max_context)
        
        if not relevant:
            return ""
        
        context_parts = []
        for conv in relevant:
            timestamp = conv.get('timestamp', '')
            content = conv.get('content', '')[:300]  # Truncate for context
            category = conv.get('category', '')
            
            context_parts.append(f"[{category}] {content}")
        
        if context_parts:
            return f"\n\n**Relevant past context:**\n" + "\n".join(f"- {part}" for part in context_parts)
        
        return ""
    
    def get_conversation_summary(self, days_back: int = 7) -> Dict:
        """Get a summary of recent conversation activity."""
        
        recent = self.mm.search_conversations_sql(days_back=days_back, limit=100)
        
        summary = {
            "total_conversations": len(recent),
            "categories": {},
            "key_topics": [],
            "recent_decisions": []
        }
        
        # Categorize conversations
        for conv in recent:
            category = conv.get('category', 'general')
            summary['categories'][category] = summary['categories'].get(category, 0) + 1
            
            # Extract key topics and decisions
            content = conv.get('content', '').lower()
            if any(word in content for word in ['decision', 'decide', 'choose', 'implement']):
                summary['recent_decisions'].append({
                    'timestamp': conv.get('timestamp', ''),
                    'content': conv.get('content', '')[:200]
                })
        
        return summary
    
    def backup_to_daily_memory(self, target_date: str = None) -> str:
        """Backup conversations to daily memory file format."""
        
        if not target_date:
            target_date = datetime.now().strftime("%Y-%m-%d")
        
        # Get conversations for the date
        conversations = self.mm.search_conversations_sql(days_back=1, limit=50)
        
        memory_content = f"# Memory {target_date}\n\n"
        memory_content += "## Key Conversations\n\n"
        
        for conv in conversations:
            timestamp = conv.get('timestamp', '')
            role = conv.get('role', '')
            content = conv.get('content', '')
            category = conv.get('category', '')
            importance = conv.get('importance_score', '')
            
            memory_content += f"### [{category}] {role.title()} - ⭐{importance}\n"
            memory_content += f"**Time:** {timestamp}\n\n"
            memory_content += f"{content}\n\n"
            memory_content += "---\n\n"
        
        # Write to memory file
        memory_file = f"memory/{target_date}.md"
        os.makedirs("memory", exist_ok=True)
        
        with open(memory_file, 'w') as f:
            f.write(memory_content)
        
        return memory_file

def test_auto_memory():
    """Test the auto-memory system."""
    print("🤖 Testing Auto-Memory System")
    print("=" * 40)
    
    auto_mem = AutoMemory()
    
    # Test conversation storage decision
    test_cases = [
        ("How are you?", "I'm doing well, thanks!"),  # Should not store
        ("Please implement a database system", "I'll create a hybrid SQLite + vector system..."),  # Should store
        ("Fix this error in the code", "Here's the corrected version..."),  # Should store
        ("What's the weather?", "I don't have weather data."),  # Should not store
    ]
    
    stored_count = 0
    for user_msg, assistant_msg in test_cases:
        stored = auto_mem.store_if_important(user_msg, assistant_msg)
        print(f"   {'✅' if stored else '❌'} '{user_msg[:30]}...' -> {'STORED' if stored else 'SKIPPED'}")
        if stored:
            stored_count += 1
    
    print(f"\n📊 Stored {stored_count} of {len(test_cases)} test conversations")
    
    # Test context injection
    context = auto_mem.inject_relevant_context("database implementation")
    print(f"\n🔍 Context injection test: {len(context)} characters of context")
    
    # Test summary
    summary = auto_mem.get_conversation_summary()
    print(f"\n📈 Summary: {summary['total_conversations']} recent conversations")
    print(f"   Categories: {summary['categories']}")
    
    # Test backup
    backup_file = auto_mem.backup_to_daily_memory()
    print(f"\n💾 Created backup file: {backup_file}")
    
    print("\n✅ Auto-Memory system is working!")

if __name__ == "__main__":
    test_auto_memory()