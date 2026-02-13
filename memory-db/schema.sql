-- George's Local Memory Database Schema
-- Hybrid SQLite + Vector system for conversation memory

-- Main conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    importance_score INTEGER DEFAULT 3 CHECK(importance_score BETWEEN 1 AND 5),
    category TEXT DEFAULT 'general',
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Vector embeddings table (using BLOB for vector storage)
CREATE TABLE IF NOT EXISTS conversation_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    embedding BLOB NOT NULL, -- Store as binary data
    embedding_model TEXT DEFAULT 'text-embedding-ada-002',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- Memory file links (connect to existing memory/*.md system)
CREATE TABLE IF NOT EXISTS memory_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    linked_file TEXT NOT NULL, -- path to memory/YYYY-MM-DD.md
    link_type TEXT DEFAULT 'reference' CHECK(link_type IN ('reference', 'continuation', 'decision', 'task')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- Sessions tracking
CREATE TABLE IF NOT EXISTS memory_sessions (
    session_id TEXT PRIMARY KEY,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
    channel TEXT, -- 'telegram', 'cli', etc.
    context_summary TEXT,
    total_turns INTEGER DEFAULT 0
);

-- Search optimization indexes
CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_category ON conversations(category);
CREATE INDEX IF NOT EXISTS idx_conversations_importance ON conversations(importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_memory_links_file ON memory_links(linked_file);

-- Categories for better organization
INSERT OR IGNORE INTO conversations (id, session_id, role, content, category) VALUES 
(0, 'system', 'system', 'Memory database initialized', 'system');