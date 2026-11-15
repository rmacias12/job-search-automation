"""
Semantic/Embedding-Based Job Matcher
Uses OpenAI embeddings or local sentence-transformers for meaning-based matching
"""

import os
from credentials import get_credential, has_credential
import json
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from functools import lru_cache


@dataclass 
class SemanticMatchResult:
    """Container for semantic matching results."""
    job_id: int
    resume_id: int
    semantic_score: float  # 0-100 based on embedding similarity
    combined_score: float  # Combined keyword + semantic
    
    # Component comparisons
    resume_summary_embedding: List[float]
    job_description_embedding: List[float]
    similarity: float  # Raw cosine similarity


class EmbeddingMatcher:
    """
    Semantic job matching using AI embeddings.
    Finds jobs with similar meaning even when keywords differ.
    """
    
    def __init__(self, openai_api_key: str = None, use_local: bool = False):
        """
        Initialize embedding matcher.
        
        Args:
            openai_api_key: OpenAI API key or op:// reference (falls back to credentials.json, then env)
            use_local: If True, use sentence-transformers instead of OpenAI
        """
        self.openai_api_key = (None if use_local else get_credential("OPENAI_API_KEY", openai_api_key))
        self.use_local = use_local
        
        # Cache for embeddings to reduce API calls
        self._embedding_cache = {}
        
        if use_local:
            self._init_local_model()
    
    def _init_local_model(self):
        """Initialize local sentence-transformers model."""
        try:
            from sentence_transformers import SentenceTransformer
            # Use a good general-purpose model
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            print("✅ Loaded local embedding model: all-MiniLM-L6-v2")
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
    
    def _get_embedding(self, text: str, cache_key: str = None) -> List[float]:
        """
        Get embedding vector for text.
        Caches results to reduce API calls.
        """
        # Check cache first
        if cache_key and cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]
        
        if self.use_local:
            embedding = self._get_local_embedding(text)
        else:
            embedding = self._get_openai_embedding(text)
        
        # Cache the result
        if cache_key:
            self._embedding_cache[cache_key] = embedding
        
        return embedding
    
    def _get_local_embedding(self, text: str) -> List[float]:
        """Get embedding using local sentence-transformers model."""
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    
    def _get_openai_embedding(self, text: str) -> List[float]:
        """Get embedding using OpenAI API."""
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "text-embedding-3-small",
            "input": text[:8000]  # Limit text length
        }
        
        response = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        return result['data'][0]['embedding']
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        
        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def create_resume_summary(self, resume_data: Dict) -> str:
        """
        Create a rich text summary of the resume for embedding.
        """
        parts = []
        
        # Professional profile
        if resume_data.get('summary'):
            parts.append(f"Professional Summary: {resume_data['summary']}")
        
        # Skills
        skills = resume_data.get('skills', [])
        if skills:
            parts.append(f"Technical Skills: {', '.join(skills)}")
        
        # Experience
        exp_years = resume_data.get('experience_years', 0)
        if exp_years:
            parts.append(f"Experience Level: {exp_years} years")
        
        # Job titles
        titles = resume_data.get('titles', [])
        if titles:
            parts.append(f"Job Titles: {', '.join(titles)}")
        
        # Work experience
        work_exp = resume_data.get('work_experience', [])
        if work_exp:
            parts.append("Work Experience:")
            for exp in work_exp[:3]:  # Last 3 roles
                company = exp.get('company', '')
                title = exp.get('title', '')
                desc = exp.get('description', '')
                parts.append(f"  - {title} at {company}: {desc}")
        
        return "\n".join(parts)
    
    def match_job(self, job: Dict, resume_data: Dict, 
                  keyword_score: float = None) -> SemanticMatchResult:
        """
        Calculate semantic similarity between job and resume.
        
        Args:
            job: Job dictionary with description
            resume_data: Resume data dict
            keyword_score: Optional keyword match score (0-100) for combined scoring
            
        Returns:
            SemanticMatchResult with scores
        """
        # Create rich summaries for both
        resume_text = self.create_resume_summary(resume_data)
        job_text = f"{job.get('title', '')}\n{job.get('description', '')}"
        
        # Get embeddings
        resume_embedding = self._get_embedding(
            resume_text, 
            cache_key=f"resume_{resume_data.get('resume_id', 'unknown')}"
        )
        job_embedding = self._get_embedding(job_text)
        
        # Calculate similarity
        similarity = self._cosine_similarity(resume_embedding, job_embedding)
        
        # Convert to 0-100 scale
        # Cosine similarity ranges from -1 to 1, typically 0 to 1 for these models
        semantic_score = ((similarity + 1) / 2) * 100  # Map -1:1 to 0:100
        
        # Combined score: blend keyword and semantic
        if keyword_score is not None:
            # 60% keyword (hard requirements) + 40% semantic (quality fit)
            combined = (keyword_score * 0.6) + (semantic_score * 0.4)
        else:
            combined = semantic_score
        
        return SemanticMatchResult(
            job_id=job.get('id', 0),
            resume_id=resume_data.get('id', 0),
            semantic_score=round(semantic_score, 2),
            combined_score=round(combined, 2),
            resume_summary_embedding=resume_embedding,
            job_description_embedding=job_embedding,
            similarity=round(similarity, 4)
        )
    
    def rerank_jobs(self, jobs: List[Dict], resume_data: Dict,
                    keyword_results: Dict[int, float] = None) -> List[SemanticMatchResult]:
        """
        Rerank jobs by semantic similarity.
        
        Args:
            jobs: List of job dictionaries
            resume_data: Resume dictionary
            keyword_results: Optional dict of {job_id: keyword_score}
            
        Returns:
            List of SemanticMatchResult sorted by combined score
        """
        print(f"🧠 Computing semantic similarity for {len(jobs)} jobs...")
        
        results = []
        for i, job in enumerate(jobs, 1):
            keyword_score = keyword_results.get(job.get('id'), None) if keyword_results else None
            result = self.match_job(job, resume_data, keyword_score)
            results.append(result)
            
            if i % 10 == 0:
                print(f"   Processed {i}/{len(jobs)} jobs...")
        
        # Sort by combined score descending
        results.sort(key=lambda x: x.combined_score, reverse=True)
        
        print(f"✅ Semantic ranking complete")
        return results
    
    def find_similar_jobs(self, reference_job_id: int, all_jobs: List[Dict], 
                          top_n: int = 5) -> List[Tuple[Dict, float]]:
        """
        Find jobs similar to a reference job.
        Uses semantic similarity between job descriptions.
        """
        # Find reference job
        ref_job = next((j for j in all_jobs if j.get('id') == reference_job_id), None)
        if not ref_job:
            return []
        
        ref_text = f"{ref_job.get('title', '')}\n{ref_job.get('description', '')}"
        ref_embedding = self._get_embedding(ref_text)
        
        similar = []
        for job in all_jobs:
            if job.get('id') == reference_job_id:
                continue
            
            job_text = f"{job.get('title', '')}\n{job.get('description', '')}"
            job_embedding = self._get_embedding(job_text)
            
            sim = self._cosine_similarity(ref_embedding, job_embedding)
            similar.append((job, sim))
        
        # Sort and return top N
        similar.sort(key=lambda x: x[1], reverse=True)
        return similar[:top_n]


class HybridMatcher:
    """
    Combines keyword matching (gatekeeper) with semantic matching (quality).
    Recommended production approach.
    """
    
    def __init__(self, resume_data: Dict, openai_key: str = None, use_local: bool = False):
        """
        Initialize hybrid matcher.
        
        Args:
            resume_data: Parsed resume dictionary
            openai_key: OpenAI API key
            use_local: Use local embeddings instead of API
        """
        from matcher import KeywordMatcher
        
        self.resume = resume_data
        self.keyword_matcher = KeywordMatcher(resume_data)
        
        # Only initialize embedding matcher if we have API key or local flag
        if openai_key or use_local or has_credential("OPENAI_API_KEY"):
            self.semantic_matcher = EmbeddingMatcher(
                openai_api_key=openai_key,
                use_local=use_local
            )
            self.use_semantic = True
        else:
            self.semantic_matcher = None
            self.use_semantic = False
    
    def match_jobs(self, jobs: List[Dict], min_keyword_score: float = 30.0,
                   min_semantic_score: float = 40.0) -> List[Dict]:
        """
        Full hybrid matching pipeline.
        
        1. Keyword filter (gatekeeper)
        2. Semantic scoring (quality)
        3. Combined ranking
        
        Args:
            jobs: List of job dictionaries
            min_keyword_score: Minimum keyword score to pass
            min_semantic_score: Minimum semantic score to include
            
        Returns:
            List of enriched job dicts with all scores
        """
        # Step 1: Keyword filtering
        print("🔍 Phase 1: Keyword filtering...")
        keyword_results = self.keyword_matcher.match_jobs(
            jobs, 
            min_score=min_keyword_score
        )
        
        if not keyword_results:
            print("No jobs passed keyword filters")
            return []
        
        keyword_passed_jobs = []
        keyword_scores = {}
        for result in keyword_results:
            job = next((j for j in jobs if j.get('id') == result.job_id), None)
            if job:
                keyword_passed_jobs.append(job)
                keyword_scores[result.job_id] = result.overall_score
        
        print(f"✅ {len(keyword_passed_jobs)} jobs passed keyword filter")
        
        # Step 2: Semantic scoring (if available)
        if self.use_semantic:
            print("🧠 Phase 2: Semantic scoring...")
            semantic_results = self.semantic_matcher.rerank_jobs(
                keyword_passed_jobs,
                self.resume,
                keyword_scores
            )
            
            # Filter by semantic score
            semantic_results = [
                r for r in semantic_results 
                if r.semantic_score >= min_semantic_score
            ]
            
            # Combine results
            enriched_results = []
            for sem_result in semantic_results:
                job = next((j for j in jobs if j.get('id') == sem_result.job_id), None)
                if job:
                    job_copy = job.copy()
                    job_copy['keyword_score'] = keyword_scores.get(sem_result.job_id, 0)
                    job_copy['semantic_score'] = sem_result.semantic_score
                    job_copy['combined_score'] = sem_result.combined_score
                    enriched_results.append(job_copy)
            
            # Sort by combined score
            enriched_results.sort(key=lambda x: x['combined_score'], reverse=True)
            
            return enriched_results
        else:
            # Keyword only
            print("ℹ️  Semantic scoring disabled (no API key)")
            enriched = []
            for result in keyword_results:
                job = next((j for j in jobs if j.get('id') == result.job_id), None)
                if job:
                    job_copy = job.copy()
                    job_copy['keyword_score'] = result.overall_score
                    job_copy['semantic_score'] = None
                    job_copy['combined_score'] = result.overall_score
                    enriched.append(job_copy)
            return enriched


# Example usage
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    from job_searcher import MockJobSearcher
    from matcher import create_test_resume
    
    print("Testing Embedding Matcher...")
    print("=" * 60)
    
    # Get test data
    searcher = MockJobSearcher()
    jobs = searcher.search_jobs("software engineer")
    resume = create_test_resume()
    
    # Check for API key
    if has_credential("OPENAI_API_KEY"):
        print("\nUsing OpenAI embeddings")
        matcher = EmbeddingMatcher()
        
        # Test semantic matching
        results = matcher.rerank_jobs(jobs, resume)
        
        print(f"\nTop matches by semantic similarity:")
        for i, result in enumerate(results[:3], 1):
            job = next((j for j in jobs if j.get('id') == result.job_id), None)
            if job:
                print(f"\n{i}. {job['title']} at {job['company']}")
                print(f"   Semantic Score: {result.semantic_score:.1f}%")
                print(f"   Similarity: {result.similarity:.4f}")
    else:
        print("\n⚠️  OPENAI_API_KEY not set")
        print("   Set it to test semantic matching")
        print("   Or use --local flag with sentence-transformers installed")
    
    # Test hybrid matcher
    print("\n" + "=" * 60)
    print("Testing Hybrid Matcher (keyword + semantic)...")
    
    hybrid = HybridMatcher(resume, use_local=False)
    results = hybrid.match_jobs(jobs)
    
    print(f"\nTop hybrid matches:")
    for i, job in enumerate(results[:3], 1):
        print(f"\n{i}. {job['title']} at {job['company']}")
        print(f"   Combined: {job['combined_score']:.1f}%")
        print(f"   Keyword: {job['keyword_score']:.1f}%")
        if job['semantic_score']:
            print(f"   Semantic: {job['semantic_score']:.1f}%")