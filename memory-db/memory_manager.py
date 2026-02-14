#!/usr/bin/env python3
"""
George's Local Memory Database Manager
Hybrid SQLite + Vector system for conversation memory
"""

import sqlite3
import json
import numpy as np
import os
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import re

# Import OpenAI embeddings
try:
    from openai_embeddings import OpenAIEmbeddings
except ImportError:
    print("⚠️ OpenAI embeddings not available - using hash fallback")
    OpenAIEmbeddings = None

class MemoryManager:
    def __init__(self, db_path: str = "memory-db/conversations.db"):
        self.db_path = db_path
        self.ensure_db_directory()
        self.init_database()
        
        # Initialize OpenAI embeddings if available
        self.embedder = OpenAIEmbeddings() if OpenAIEmbeddings else None
        if self.embedder:
            print("🧠 Memory Manager initialized with OpenAI embeddings")
        else:
            print("🧠 Memory Manager initialized with hash-based embeddings")
        
    def ensure_db_directory(self):
        """Create memory-db directory if it doesn't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def init_database(self):
        """Initialize the database with schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Read and execute schema
            schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
            if os.path.exists(schema_path):
                with open(schema_path, 'r') as f:
                    conn.executescript(f.read())
            else:
                print(f"Warning: Schema file not found at {schema_path}")
    
    def store_conversation(self, 
                          session_id: str,
                          role: str, 
                          content: str,
                          importance_score: int = 3,
                          category: str = "general",
                          metadata: Dict = None,
                          generate_embedding: bool = True) -> int:
        """Store a conversation turn in the database."""
        
        if metadata is None:
            metadata = {}
            
        # Add automatic metadata
        metadata.update({
            "content_length": len(content),
            "word_count": len(content.split()),
            "timestamp": datetime.now().isoformat()
        })
        
        with sqlite3.connect(self.db_path) as conn:
            # Insert conversation
            cursor = conn.execute(
                """INSERT INTO conversations 
                   (session_id, role, content, importance_score, category, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, role, content, importance_score, category, json.dumps(metadata))
            )
            conversation_id = cursor.lastrowid
            
            # Generate and store embedding if requested
            if generate_embedding:
                self._store_embedding(conn, conversation_id, content)
            
            # Update session tracking
            self._update_session(conn, session_id)
            
            return conversation_id
    
    def _store_embedding(self, conn: sqlite3.Connection, conversation_id: int, content: str):
        """Generate and store embedding for content."""
        try:
            if self.embedder:
                # Use real OpenAI embeddings
                embedding = self.embedder.generate_embedding(content)
                model_name = self.embedder.model
            else:
                # Fallback to hash-based
                embedding = self._create_simple_embedding(content)
                model_name = "hash-based-fallback"
            
            if embedding is not None:
                embedding_blob = embedding.tobytes()
                
                conn.execute(
                    """INSERT INTO conversation_embeddings 
                       (conversation_id, embedding, embedding_model) VALUES (?, ?, ?)""",
                    (conversation_id, embedding_blob, model_name)
                )
        except Exception as e:
            print(f"Warning: Could not store embedding: {e}")
    
    def _create_simple_embedding(self, text: str, dimension: int = 384) -> np.ndarray:
        """Create a simple hash-based embedding (placeholder for real embeddings)."""
        # Convert text to consistent hash
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        
        # Create deterministic "embedding" from hash
        embedding = np.array([
            int(text_hash[i:i+2], 16) / 255.0 - 0.5 
            for i in range(0, min(len(text_hash), dimension * 2), 2)
        ])
        
        # Pad or truncate to desired dimension
        if len(embedding) < dimension:
            embedding = np.pad(embedding, (0, dimension - len(embedding)))
        else:
            embedding = embedding[:dimension]
            
        return embedding
    
    def _update_session(self, conn: sqlite3.Connection, session_id: str):
        """Update session tracking."""
        conn.execute(
            """INSERT OR REPLACE INTO memory_sessions 
               (session_id, last_activity, total_turns)
               VALUES (?, ?, COALESCE((SELECT total_turns FROM memory_sessions WHERE session_id = ?) + 1, 1))""",
            (session_id, datetime.now().isoformat(), session_id)
        )
    
    def search_conversations_sql(self, 
                                query: str = None,
                                category: str = None,
                                importance_min: int = None,
                                days_back: int = None,
                                limit: int = 20) -> List[Dict]:
        """Search conversations using SQL queries."""
        
        conditions = []
        params = []
        
        if query:
            conditions.append("content LIKE ?")
            params.append(f"%{query}%")
            
        if category:
            conditions.append("category = ?")
            params.append(category)
            
        if importance_min:
            conditions.append("importance_score >= ?")
            params.append(importance_min)
            
        if days_back:
            cutoff = datetime.now() - timedelta(days=days_back)
            conditions.append("timestamp >= ?")
            params.append(cutoff.isoformat())
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query_sql = f"""
            SELECT id, session_id, timestamp, role, content, importance_score, category, metadata
            FROM conversations 
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            results = conn.execute(query_sql, params).fetchall()
            
            return [dict(row) for row in results]
    
    def search_conversations_semantic(self, query: str, limit: int = 10) -> List[Dict]:
        """Search conversations using semantic similarity."""
        query_embedding = self._create_simple_embedding(query)
        
        # Get all conversations with embeddings
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            results = conn.execute("""
                SELECT c.id, c.session_id, c.timestamp, c.role, c.content, 
                       c.importance_score, c.category, c.metadata, e.embedding
                FROM conversations c
                JOIN conversation_embeddings e ON c.id = e.conversation_id
                ORDER BY c.timestamp DESC
            """).fetchall()
        
        # Calculate similarities
        similarities = []
        for row in results:
            stored_embedding = np.frombuffer(row['embedding'], dtype=np.float64)
            similarity = self._cosine_similarity(query_embedding, stored_embedding)
            
            similarities.append({
                'similarity': similarity,
                'conversation': dict(row)
            })
        
        # Sort by similarity and return top results
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        return [item['conversation'] for item in similarities[:limit]]
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        try:
            dot_product = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
                
            return dot_product / (norm_a * norm_b)
        except:
            return 0.0
    
    def get_recent_context(self, session_id: str, limit: int = 10) -> List[Dict]:
        """Get recent conversation context for a session."""
        return self.search_conversations_sql(
            query=None,
            days_back=7,
            limit=limit
        )
    
    def categorize_content(self, content: str) -> Tuple[str, int]:
        """Auto-categorize content and assign importance score."""
        content_lower = content.lower()
        
        # High importance keywords
        high_importance_keywords = [
            'error', 'mistake', 'wrong', 'fix', 'critical', 'urgent', 
            'important', 'security', 'vulnerability', 'breach'
        ]
        
        # Category detection
        if any(word in content_lower for word in ['security', 'vulnerability', 'audit', 'breach']):
            category = 'security'
            importance = 5
        elif any(word in content_lower for word in ['database', 'memory', 'storage', 'sqlite']):
            category = 'technical'
            importance = 4
        elif any(word in content_lower for word in ['business', 'revenue', 'product', 'market']):
            category = 'business'
            importance = 4
        elif any(word in content_lower for word in ['build', 'create', 'implement', 'develop']):
            category = 'development'
            importance = 3
        elif any(word in content_lower for word in ['research', 'analyze', 'investigate']):
            category = 'research'
            importance = 3
        elif any(word in content_lower for word in high_importance_keywords):
            category = 'critical'
            importance = 5
        else:
            category = 'general'
            importance = 2
            
        # Boost importance for questions
        if content.strip().endswith('?'):
            importance = min(importance + 1, 5)
            
        return category, importance
    
    def store_current_conversation(self, user_message: str, assistant_response: str, session_id: str):
        """Store both sides of a conversation exchange."""
        
        # Categorize and score user message
        user_category, user_importance = self.categorize_content(user_message)
        
        # Categorize and score assistant response
        assistant_category, assistant_importance = self.categorize_content(assistant_response)
        
        # Store user message
        user_id = self.store_conversation(
            session_id=session_id,
            role="user",
            content=user_message,
            importance_score=user_importance,
            category=user_category
        )
        
        # Store assistant response
        assistant_id = self.store_conversation(
            session_id=session_id,
            role="assistant", 
            content=assistant_response,
            importance_score=assistant_importance,
            category=assistant_category
        )
        
        return user_id, assistant_id
    
    def get_stats(self) -> Dict:
        """Get database statistics."""
        with sqlite3.connect(self.db_path) as conn:
            stats = {}
            
            # Total conversations
            stats['total_conversations'] = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            
            # By category
            categories = conn.execute("""
                SELECT category, COUNT(*) as count 
                FROM conversations 
                GROUP BY category 
                ORDER BY count DESC
            """).fetchall()
            stats['by_category'] = dict(categories)
            
            # By importance
            importance = conn.execute("""
                SELECT importance_score, COUNT(*) as count 
                FROM conversations 
                GROUP BY importance_score 
                ORDER BY importance_score DESC
            """).fetchall()
            stats['by_importance'] = dict(importance)
            
            # Recent activity (last 7 days)
            cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            stats['recent_conversations'] = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE timestamp >= ?", 
                (cutoff,)
            ).fetchone()[0]
            
            # Sessions
            stats['total_sessions'] = conn.execute("SELECT COUNT(*) FROM memory_sessions").fetchone()[0]
            
            return stats

if __name__ == "__main__":
    # Test the memory manager
    mm = MemoryManager()
    print("Memory Manager initialized successfully!")
    
    # Test storage
    test_session = "test_session_001"
    
    user_msg = "Can you implement a local memory database system?"
    assistant_msg = "Yes! I'll create a hybrid SQLite + vector system for conversation memory..."
    
    user_id, assistant_id = mm.store_current_conversation(user_msg, assistant_msg, test_session)
    print(f"Stored conversation: user_id={user_id}, assistant_id={assistant_id}")
    
    # Test search
    results = mm.search_conversations_sql(query="memory database", limit=5)
    print(f"Found {len(results)} matching conversations")
    
    # Show stats
    stats = mm.get_stats()
    print("Database stats:", json.dumps(stats, indent=2))