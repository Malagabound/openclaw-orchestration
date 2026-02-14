#!/usr/bin/env python3
"""
OpenClaw Conversation Flow Integration
Hooks into OpenClaw to automatically store important conversations
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from memory_manager import MemoryManager
from auto_memory import AutoMemory
import json
import re
from datetime import datetime
from typing import Dict, Optional

class OpenClawMemoryIntegration:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.auto_memory = AutoMemory() if enabled else None
        self.memory_manager = MemoryManager() if enabled else None
        
        # Track session info
        self.current_session_id = self._get_session_id()
        self.conversation_count = 0
        
        if self.enabled:
            print("🔗 OpenClaw Memory Integration active")
        else:
            print("💤 OpenClaw Memory Integration disabled")
    
    def _get_session_id(self) -> str:
        """Generate session ID from current context."""
        
        # Try to get session info from environment or context
        channel = os.getenv('OPENCLAW_CHANNEL', 'unknown')
        user = os.getenv('OPENCLAW_USER', 'user')
        date_str = datetime.now().strftime("%Y_%m_%d")
        
        # Special handling for known channels
        if channel == 'telegram':
            return f"telegram_{user}_{date_str}"
        elif channel == 'cli':
            return f"cli_{date_str}"
        else:
            return f"{channel}_{date_str}"
    
    def process_conversation_exchange(self, user_message: str, assistant_response: str, 
                                    metadata: Optional[Dict] = None) -> bool:
        """Process a conversation exchange and store if important."""
        
        if not self.enabled:
            return False
        
        self.conversation_count += 1
        
        # Add metadata
        if metadata is None:
            metadata = {}
        
        metadata.update({
            'session_count': self.conversation_count,
            'processed_at': datetime.now().isoformat(),
            'integration_version': '1.0'
        })
        
        try:
            # Use AutoMemory to determine if we should store
            stored = self.auto_memory.store_if_important(user_message, assistant_response)
            
            if stored:
                # Add metadata to the stored conversation
                self._add_metadata_to_last_conversations(metadata)
                
            return stored
            
        except Exception as e:
            print(f"⚠️ Memory integration error: {e}")
            return False
    
    def _add_metadata_to_last_conversations(self, metadata: Dict):
        """Add metadata to the most recent conversations."""
        try:
            import sqlite3
            with sqlite3.connect(self.memory_manager.db_path) as conn:
                # Update the last two conversations (user + assistant)
                # Use JSON functions if available, otherwise just replace
                try:
                    conn.execute("""
                        UPDATE conversations 
                        SET metadata = json_patch(COALESCE(metadata, '{}'), ?)
                        WHERE id IN (
                            SELECT id FROM conversations 
                            ORDER BY id DESC 
                            LIMIT 2
                        )
                    """, (json.dumps(metadata),))
                except:
                    # Fallback if JSON functions not available
                    conn.execute("""
                        UPDATE conversations 
                        SET metadata = ?
                        WHERE id IN (
                            SELECT id FROM conversations 
                            ORDER BY id DESC 
                            LIMIT 2
                        )
                    """, (json.dumps(metadata),))
        except Exception as e:
            print(f"⚠️ Could not add metadata: {e}")
    
    def inject_context_if_needed(self, user_query: str, max_context_chars: int = 1000) -> str:
        """Inject relevant context if the query would benefit from it."""
        
        if not self.enabled:
            return ""
        
        # Keywords that suggest context would be helpful
        context_keywords = [
            'remember', 'recall', 'previous', 'before', 'earlier', 'last time',
            'we discussed', 'you said', 'mentioned', 'talked about'
        ]
        
        # Question patterns that benefit from context
        question_patterns = [
            r'\bwhat did\b', r'\bhow did\b', r'\bwhen did\b',
            r'\bwhere did\b', r'\bwhy did\b', r'\bwho did\b'
        ]
        
        user_lower = user_query.lower()
        
        # Check if context injection is needed
        needs_context = (
            any(keyword in user_lower for keyword in context_keywords) or
            any(re.search(pattern, user_lower) for pattern in question_patterns) or
            len(user_query.split()) > 10  # Complex queries benefit from context
        )
        
        if not needs_context:
            return ""
        
        try:
            # Get relevant context
            context = self.auto_memory.inject_relevant_context(user_query, max_context=3)
            
            # Truncate if too long
            if len(context) > max_context_chars:
                context = context[:max_context_chars] + "...\n"
            
            return context
            
        except Exception as e:
            print(f"⚠️ Context injection error: {e}")
            return ""
    
    def get_conversation_stats(self) -> Dict:
        """Get statistics for current session."""
        
        if not self.enabled:
            return {"enabled": False}
        
        stats = self.memory_manager.get_stats()
        stats.update({
            "enabled": True,
            "current_session": self.current_session_id,
            "session_conversation_count": self.conversation_count,
            "integration_active": True
        })
        
        return stats
    
    def force_store_conversation(self, user_message: str, assistant_response: str, 
                                importance: int = 5, category: str = "manual") -> bool:
        """Manually force storage of a conversation (for important exchanges)."""
        
        if not self.enabled:
            return False
        
        try:
            user_id, assistant_id = self.memory_manager.store_current_conversation(
                user_message, assistant_response, self.current_session_id
            )
            
            print(f"🧠 Manually stored conversation: user_id={user_id}, assistant_id={assistant_id}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to manually store conversation: {e}")
            return False

# Global integration instance
_memory_integration = None

def get_memory_integration(enabled: bool = True) -> OpenClawMemoryIntegration:
    """Get global memory integration instance."""
    global _memory_integration
    
    if _memory_integration is None:
        _memory_integration = OpenClawMemoryIntegration(enabled=enabled)
    
    return _memory_integration

def process_conversation(user_message: str, assistant_response: str, metadata: Dict = None) -> bool:
    """Convenience function to process a conversation."""
    integration = get_memory_integration()
    return integration.process_conversation_exchange(user_message, assistant_response, metadata)

def get_context_for_query(user_query: str) -> str:
    """Convenience function to get context for a query."""
    integration = get_memory_integration()
    return integration.inject_context_if_needed(user_query)

def get_memory_stats() -> Dict:
    """Convenience function to get memory stats."""
    integration = get_memory_integration()
    return integration.get_conversation_stats()

# Test the integration
if __name__ == "__main__":
    print("🧪 Testing OpenClaw Memory Integration")
    print("=" * 50)
    
    integration = OpenClawMemoryIntegration()
    
    # Test conversation processing
    user_msg = "Can you help me implement a better memory system?"
    assistant_msg = "I'll create a comprehensive memory database with vector search capabilities..."
    
    stored = integration.process_conversation_exchange(user_msg, assistant_msg)
    print(f"✅ Conversation {'stored' if stored else 'not stored'}")
    
    # Test context injection
    context_query = "What did we discuss about memory systems?"
    context = integration.inject_context_if_needed(context_query)
    print(f"🔍 Context injection: {len(context)} characters")
    
    # Test stats
    stats = integration.get_conversation_stats()
    print(f"📊 Stats: {stats}")
    
    print("\n✅ Integration test complete!")