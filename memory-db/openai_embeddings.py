#!/usr/bin/env python3
"""
Real OpenAI Embeddings Integration for Memory Database
Replace hash-based embeddings with actual OpenAI API calls
"""

import os
import json
import numpy as np
from typing import List, Optional
import time

try:
    from openai import OpenAI
    openai_available = True
except ImportError:
    openai_available = False
    print("⚠️ OpenAI package not available")

class OpenAIEmbeddings:
    def __init__(self, api_key: Optional[str] = None, model: str = "text-embedding-ada-002"):
        self.model = model
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.client = None
        
        if not self.api_key:
            # Try to read from OpenClaw credentials
            cred_paths = [
                os.path.expanduser("~/.openclaw/credentials/openai"),
                ".env"
            ]
            
            for path in cred_paths:
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        content = f.read()
                        for line in content.split('\n'):
                            if line.startswith('OPENAI_API_KEY'):
                                self.api_key = line.split('=', 1)[1].strip().strip('"\'')
                                break
                    if self.api_key:
                        break
        
        if self.api_key and openai_available:
            try:
                self.client = OpenAI(api_key=self.api_key)
                print(f"✅ OpenAI API configured with model: {self.model}")
            except Exception as e:
                print(f"⚠️ OpenAI API setup failed: {e}")
                self.client = None
        else:
            print("⚠️ OpenAI API key not found or package unavailable - using hash-based fallback")
            
    def generate_embedding(self, text: str, max_retries: int = 3) -> Optional[np.ndarray]:
        """Generate embedding using OpenAI API with fallback."""
        
        if not self.client:
            return self._hash_fallback_embedding(text)
        
        # Clean text for API
        text = text.strip().replace('\n', ' ')[:8000]  # Limit length
        
        for attempt in range(max_retries):
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=text
                )
                
                embedding = np.array(response.data[0].embedding)
                return embedding
                
            except Exception as e:
                print(f"⚠️ OpenAI API attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    print("❌ OpenAI API failed, using hash fallback")
                    return self._hash_fallback_embedding(text)
        
        return None
    
    def _hash_fallback_embedding(self, text: str, dimension: int = 1536) -> np.ndarray:
        """Fallback hash-based embedding when API unavailable."""
        import hashlib
        
        # Same logic as before but with OpenAI dimensions
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        
        embedding = np.array([
            int(text_hash[i:i+2], 16) / 255.0 - 0.5 
            for i in range(0, min(len(text_hash), dimension * 2), 2)
        ])
        
        if len(embedding) < dimension:
            embedding = np.pad(embedding, (0, dimension - len(embedding)))
        else:
            embedding = embedding[:dimension]
            
        return embedding
    
    def batch_generate_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for multiple texts."""
        
        if not self.client:
            return [self._hash_fallback_embedding(text) for text in texts]
        
        embeddings = []
        
        # Process in batches to respect rate limits
        batch_size = 20
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = []
            
            for text in batch:
                embedding = self.generate_embedding(text)
                if embedding is not None:
                    batch_embeddings.append(embedding)
                else:
                    batch_embeddings.append(self._hash_fallback_embedding(text))
            
            embeddings.extend(batch_embeddings)
            
            # Rate limiting
            if i + batch_size < len(texts):
                time.sleep(1)
        
        return embeddings
    
    def similarity_search(self, query_text: str, embeddings: List[np.ndarray], texts: List[str], top_k: int = 5):
        """Find most similar texts using cosine similarity."""
        
        query_embedding = self.generate_embedding(query_text)
        if query_embedding is None:
            return []
        
        similarities = []
        for i, embedding in enumerate(embeddings):
            similarity = self._cosine_similarity(query_embedding, embedding)
            similarities.append((similarity, i, texts[i]))
        
        # Sort by similarity (highest first)
        similarities.sort(reverse=True)
        
        return similarities[:top_k]
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity."""
        try:
            dot_product = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
                
            return dot_product / (norm_a * norm_b)
        except:
            return 0.0

def test_embeddings():
    """Test the embedding system."""
    print("🧪 Testing OpenAI Embeddings Integration")
    print("=" * 50)
    
    embedder = OpenAIEmbeddings()
    
    # Test single embedding
    test_text = "I need to implement a database system with vector search capabilities"
    embedding = embedder.generate_embedding(test_text)
    
    if embedding is not None:
        print(f"✅ Generated embedding: shape {embedding.shape}")
        print(f"   First 5 dimensions: {embedding[:5]}")
    else:
        print("❌ Failed to generate embedding")
    
    # Test batch processing
    test_texts = [
        "Database implementation with SQLite",
        "Vector search and semantic similarity",
        "OpenAI API integration for embeddings",
        "Memory system for conversation storage"
    ]
    
    print(f"\n🔄 Batch processing {len(test_texts)} texts...")
    batch_embeddings = embedder.batch_generate_embeddings(test_texts)
    print(f"✅ Generated {len(batch_embeddings)} embeddings")
    
    # Test similarity search
    query = "database vector search"
    print(f"\n🔍 Similarity search for: '{query}'")
    results = embedder.similarity_search(query, batch_embeddings, test_texts, top_k=3)
    
    for i, (similarity, idx, text) in enumerate(results):
        print(f"   {i+1}. [{similarity:.3f}] {text}")
    
    print("\n✅ Embeddings system test complete!")

if __name__ == "__main__":
    test_embeddings()