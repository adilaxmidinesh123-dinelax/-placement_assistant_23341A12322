import re

class ResumeParser:
    @staticmethod
    def extract_skills(text):
        skill_keywords = ['python', 'java', 'javascript', 'sql', 'c++', 'html', 'css', 'react', 'node.js', 
                         'django', 'flask', 'mongodb', 'mysql', 'postgresql', 'aws', 'docker', 'git', 
                         'machine learning', 'data analysis', 'excel', 'tableau', 'communication', 
                         'teamwork', 'problem solving', 'leadership', 'time management']
        found = []
        text_lower = text.lower()
        for s in skill_keywords:
            if s in text_lower:
                found.append(s)
        return found
    
    @staticmethod
    def extract_projects(text):
        projects = []
        lines = text.split('\n')
        for line in lines:
            if 'project' in line.lower():
                if len(line.strip()) > 5 and len(line.strip()) < 200:
                    projects.append(line.strip())
        return projects[:5]
    
    @staticmethod
    def extract_education(text):
        patterns = [r'B\.?Tech', r'M\.?Tech', r'B\.?E', r'M\.?E', r'BCA', r'MCA', 
                   r'B\.?Sc', r'M\.?Sc', r'MBA', r'Ph\.?D', r'Bachelor', r'Master']
        for pat in patterns:
            if re.search(pat.lower(), text.lower()):
                match = re.search(r'.{0,30}' + pat + r'.{0,30}', text, re.IGNORECASE)
                if match:
                    return match.group().strip()
        return "Not specified"
    
    @staticmethod
    def analyze_strengths(skills, job_role):
        strengths = []
        role_keywords = {
            'software engineer': ['python', 'java', 'javascript', 'sql', 'data structures', 'algorithms'],
            'data analyst': ['python', 'sql', 'excel', 'data analysis', 'statistics', 'tableau'],
            'web developer': ['html', 'css', 'javascript', 'react', 'node.js'],
            'data scientist': ['python', 'machine learning', 'statistics', 'sql']
        }
        role_lower = job_role.lower()
        relevant = []
        for role, kw in role_keywords.items():
            if role in role_lower:
                relevant = kw
                break
        if not relevant:
            relevant = ['python', 'sql', 'communication', 'problem solving']
        for s in skills:
            if s in relevant:
                strengths.append(f"Strong {s} skill for {job_role}")
        if not strengths:
            strengths.append("Good foundational knowledge")
        return strengths[:4]
    
    @staticmethod
    def identify_weak_areas(skills, job_role):
        weak = []
        required = {
            'software engineer': ['data structures', 'algorithms', 'python/java', 'sql', 'system design'],
            'data analyst': ['sql', 'excel', 'python', 'statistics', 'data visualization'],
            'web developer': ['html/css', 'javascript', 'react/angular', 'node.js', 'git'],
            'data scientist': ['python', 'machine learning', 'statistics', 'sql']
        }
        role_lower = job_role.lower()
        req_list = []
        for r, lst in required.items():
            if r in role_lower:
                req_list = lst
                break
        if not req_list:
            req_list = ['technical skills', 'problem solving', 'communication']
        for req in req_list:
            found = any(req.lower() in s.lower() or s.lower() in req.lower() for s in skills)
            if not found:
                weak.append(f"Missing {req}")
        return weak
    
    @staticmethod
    def get_missing_skills(skills, job_role):
        target_skills = {
            'tcs': ['java', 'sql', 'communication', 'aptitude', 'logical reasoning'],
            'infosys': ['python', 'java', 'sql', 'system design', 'agile'],
            'google': ['data structures', 'algorithms', 'system design', 'python/java', 'problem solving'],
            'amazon': ['data structures', 'algorithms', 'leadership principles', 'scalability', 'oop'],
            'microsoft': ['c#', 'azure', 'system design', 'problem solving', 'team collaboration'],
        }
        company_lower = job_role.lower()
        target = target_skills.get(company_lower, ['technical skills', 'problem solving', 'communication', 'teamwork'])
        missing = []
        for t in target:
            if not any(t.lower() in s.lower() or s.lower() in t.lower() for s in skills):
                missing.append(t)
        return missing[:5]