"""
Resume Parser Module
Extracts structured data from PDF/DOCX resumes using pdfplumber + OpenAI
"""

import os
from credentials import get_credential, has_credential
import re
import json
from pathlib import Path
from typing import Dict, Optional
import pdfplumber


class ResumeParser:
    """
    Parse PDF resumes and extract structured data.
    Uses pdfplumber for text extraction, OpenAI for intelligent parsing.
    """
    
    def __init__(self, openai_api_key: str = None):
        """
        Initialize parser.
        
        Args:
            openai_api_key: OpenAI API key. Uses credentials.json, then OPENAI_API_KEY env var.
        """
        self.openai_api_key = get_credential("OPENAI_API_KEY", openai_api_key)
        
    def parse_pdf(self, pdf_path: str) -> Dict:
        """
        Parse a PDF resume file and return structured data.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dictionary with extracted resume data
        """
        # Extract raw text from PDF
        raw_text = self._extract_text_from_pdf(pdf_path)
        
        if not raw_text.strip():
            raise ValueError(f"Could not extract text from {pdf_path}")
        
        print(f"📄 Extracted {len(raw_text)} characters from PDF")
        
        # Parse with OpenAI if available, otherwise use regex fallback
        if self.openai_api_key:
            try:
                structured_data = self._parse_with_openai(raw_text)
                structured_data['raw_text'] = raw_text
                structured_data['parse_method'] = 'openai'
                return structured_data
            except Exception as e:
                print(f"⚠️  OpenAI parsing failed: {e}")
                print("   Falling back to regex parsing...")
        
        # Fallback: Regex-based parsing
        structured_data = self._parse_with_regex(raw_text)
        structured_data['raw_text'] = raw_text
        structured_data['parse_method'] = 'regex'
        return structured_data
    
    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract all text from PDF using pdfplumber."""
        text_parts = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        
        return "\n\n".join(text_parts)
    
    def _parse_with_openai(self, text: str) -> Dict:
        """
        Use OpenAI API to intelligently parse resume text.
        Returns structured JSON with all relevant fields.
        """
        import requests
        
        system_prompt = """You are a resume parsing assistant. Extract structured information from the provided resume text and return it as a JSON object with the following fields:

{
    "name": "Full name of the candidate",
    "email": "Email address",
    "phone": "Phone number",
    "location": "City, State or location",
    "titles": ["List of job titles held", "e.g. Software Engineer", "Senior Developer"],
    "skills": ["List of technical skills", "e.g. Python", "AWS", "React"],
    "experience_years": number,
    "summary": "Brief professional summary",
    "education": [
        {"degree": "Bachelor of Science", "field": "Computer Science", "school": "University Name", "year": "2020"}
    ],
    "work_experience": [
        {"company": "Company Name", "title": "Job Title", "duration": "2020-2022", "description": "Key responsibilities and achievements"}
    ],
    "certifications": ["Optional list of certifications"],
    "languages": ["Optional list of languages"],
    "links": {"linkedin": "url", "github": "url", "portfolio": "url"}
}

Return ONLY the JSON object, no other text. Use empty arrays or null for missing fields. Be thorough and extract as much detail as possible."""

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4o-mini",  # Use mini for cost efficiency
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:8000]}  # Limit to first 8000 chars
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1  # Low temperature for consistency
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        
        result = response.json()
        parsed_content = json.loads(result['choices'][0]['message']['content'])
        
        # Normalize fields to match our schema
        return self._normalize_parsed_data(parsed_content)
    
    def _parse_with_regex(self, text: str) -> Dict:
        """
        Fallback parsing using regex patterns.
        Less accurate but works without API calls.
        """
        data = {
            'name': self._extract_name(text),
            'email': self._extract_email(text),
            'phone': self._extract_phone(text),
            'location': self._extract_location(text),
            'skills': self._extract_skills_regex(text),
            'titles': self._extract_titles_regex(text),
            'experience_years': self._estimate_experience(text),
            'summary': None,
            'education': [],
            'work_experience': []
        }
        
        return data
    
    def _normalize_parsed_data(self, data: Dict) -> Dict:
        """Normalize OpenAI output to match our internal schema."""
        normalized = {
            'name': data.get('name'),
            'email': data.get('email'),
            'phone': data.get('phone'),
            'location': data.get('location'),
            'skills': data.get('skills', []),
            'titles': data.get('titles', []),
            'experience_years': data.get('experience_years', 0),
            'summary': data.get('summary'),
            'education': data.get('education', []),
            'work_experience': data.get('work_experience', [])
        }
        
        # Convert experience_years to int if string
        if isinstance(normalized['experience_years'], str):
            numbers = re.findall(r'\d+', normalized['experience_years'])
            if numbers:
                normalized['experience_years'] = int(numbers[0])
            else:
                normalized['experience_years'] = 0
        
        return normalized
    
    def _extract_name(self, text: str) -> Optional[str]:
        """Extract name from resume text (usually at the top)."""
        lines = text.strip().split('\n')[:5]  # Check first 5 lines
        for line in lines:
            line = line.strip()
            # Look for 2-3 word names (exclude single words or emails)
            if 2 <= len(line.split()) <= 3 and '@' not in line and len(line) > 5:
                if all(c.isalpha() or c.isspace() or c in '.-' for c in line):
                    return line
        return None
    
    def _extract_email(self, text: str) -> Optional[str]:
        """Extract email address."""
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(pattern, text)
        return match.group(0) if match else None
    
    def _extract_phone(self, text: str) -> Optional[str]:
        """Extract phone number."""
        # Various phone formats
        patterns = [
            r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # (555) 123-4567
            r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'  # +1 (555) 123-4567
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None
    
    def _extract_location(self, text: str) -> Optional[str]:
        """Extract location (city, state pattern)."""
        # Common US city/state patterns
        pattern = r'([A-Za-z\s]+,\s*[A-Z]{2})'
        matches = re.findall(pattern, text)
        # Return first match that looks like a location
        for match in matches:
            if len(match) > 5 and not any(x in match.lower() for x in ['@', 'http', 'www']):
                return match.strip()
        return None
    
    def _extract_skills_regex(self, text: str) -> list:
        """Extract common tech skills using regex."""
        common_skills = [
            'python', 'javascript', 'typescript', 'java', 'go', 'rust', 'c++', 'c#',
            'react', 'vue', 'angular', 'svelte', 'next.js', 'node.js',
            'sql', 'postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch',
            'aws', 'gcp', 'azure', 'docker', 'kubernetes', 'terraform',
            'git', 'github', 'gitlab', 'ci/cd', 'jenkins', 'github actions',
            'linux', 'bash', 'nginx', 'apache', 'rest api', 'graphql',
            'machine learning', 'tensorflow', 'pytorch', 'pandas', 'numpy',
            'django', 'flask', 'fastapi', 'express', 'spring boot',
            'html', 'css', 'sass', 'tailwind', 'bootstrap'
        ]
        
        found_skills = []
        text_lower = text.lower()
        
        for skill in common_skills:
            # Look for skill as whole word
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, text_lower):
                found_skills.append(skill)
        
        return found_skills
    
    def _extract_titles_regex(self, text: str) -> list:
        """Extract job titles using regex."""
        common_titles = [
            'software engineer', 'senior software engineer', 'staff engineer',
            'backend developer', 'frontend developer', 'full stack developer',
            'devops engineer', 'site reliability engineer', 'sre',
            'data engineer', 'data scientist', 'machine learning engineer',
            'tech lead', 'engineering manager', 'cto', 'vp of engineering',
            'product manager', 'project manager', 'scrum master',
            'qa engineer', 'test engineer', 'automation engineer'
        ]
        
        found_titles = []
        text_lower = text.lower()
        
        for title in common_titles:
            if title in text_lower:
                found_titles.append(title)
        
        return found_titles
    
    def _estimate_experience(self, text: str) -> int:
        """Estimate years of experience from work history."""
        # Look for "X years" or "X+ years" patterns
        patterns = [
            r'(\d+)\+?\s*years?\s+(?:of\s+)?experience',
            r'(\d+)\+?\s*years?\s+in\s+',
            r'(\d+)\+?\s*yrs?\s+experience'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text.lower())
            if matches:
                # Return the largest number found
                return max(int(m) for m in matches)
        
        # If no explicit mention, count year ranges in experience section
        year_pattern = r'(20\d{2})\s*[-–]\s*(20\d{2}|present|current|now)'
        matches = re.findall(year_pattern, text, re.IGNORECASE)
        
        total_years = 0
        for start, end in matches:
            start_year = int(start)
            if end.lower() in ['present', 'current', 'now']:
                end_year = 2024
            else:
                end_year = int(end)
            total_years += (end_year - start_year)
        
        return max(total_years, 0)


def create_resume_config_from_pdf(pdf_path: str, output_path: str = None, openai_key: str = None) -> Dict:
    """
    Parse a PDF resume and create a resume config file.
    
    Args:
        pdf_path: Path to PDF resume
        output_path: Where to save the config JSON (optional)
        openai_key: OpenAI API key (optional)
        
    Returns:
        The parsed resume data dict
    """
    parser = ResumeParser(openai_api_key=openai_key)
    data = parser.parse_pdf(pdf_path)
    
    # Add default preferences that aren't in the resume
    resume_config = {
        'resume_id': f"parsed_{Path(pdf_path).stem}",
        **data,
        'required_skills': [],  # User must specify
        'excluded_keywords': [],  # User must specify
        'preferred_locations': [],  # User must specify
        'preferred_job_types': ['remote', 'hybrid'],
        'target_salary_min': None,
        'target_salary_max': None
    }
    
    # Save if output path provided
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(resume_config, f, indent=2)
        print(f"✅ Saved resume config to: {output_path}")
    
    return resume_config


# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python resume_parser.py <path_to_pdf_resume>")
        print("\nEnvironment variable:")
        print("  OPENAI_API_KEY - Optional, enables better parsing")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        sys.exit(1)
    
    print(f"📄 Parsing resume: {pdf_path}")
    print("-" * 60)
    
    try:
        parser = ResumeParser()
        result = parser.parse_pdf(pdf_path)
        
        print(f"\n✅ Parsed using: {result.get('parse_method', 'unknown')}")
        print(f"\nName: {result.get('name', 'Not found')}")
        print(f"Email: {result.get('email', 'Not found')}")
        print(f"Phone: {result.get('phone', 'Not found')}")
        print(f"Location: {result.get('location', 'Not found')}")
        print(f"Experience: {result.get('experience_years', 0)} years")
        print(f"\nSkills ({len(result.get('skills', []))}):")
        for skill in result.get('skills', [])[:10]:
            print(f"  - {skill}")
        if len(result.get('skills', [])) > 10:
            print(f"  ... and {len(result.get('skills', [])) - 10} more")
        
        print(f"\nTitles ({len(result.get('titles', []))}):")
        for title in result.get('titles', [])[:5]:
            print(f"  - {title}")
        
        # Save config
        output = os.path.expanduser("~/job-search-automation/parsed_resume_config.json")
        create_resume_config_from_pdf(pdf_path, output)
        
    except Exception as e:
        print(f"❌ Error parsing resume: {e}")
        import traceback
        traceback.print_exc()