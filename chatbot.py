import streamlit as st
import json
from datetime import datetime
import os
import hashlib
from pathlib import Path
import requests  # Using requests for better error handling
from typing import Dict, List, Optional, Tuple, Generator
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import re
from PyPDF2 import PdfReader
import docx
import time  # Added this import to fix the NameError
import http.client  # Added this import for HTTP connections

# ---------------- CONFIGURATION ----------------
# Page configuration
st.set_page_config(
    page_title="AI Career Mentor",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
USER_FILE = "users.json"
DEFAULT_MODEL = "nemotron-3-nano:30b-cloud"
OLLAMA_HOST = "localhost"
OLLAMA_PORT = 11434
OLLAMA_TIMEOUT = 30  # Increased timeout

# ---------------- AUTHENTICATION FUNCTIONS ----------------

def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_password: str, provided_password: str) -> bool:
    """Verify a password against its hash."""
    return stored_password == hash_password(provided_password)

def create_user_file() -> Path:
    """Create users.json file if it doesn't exist."""
    user_file = Path(USER_FILE)
    if not user_file.exists():
        with open(user_file, "w") as f:
            json.dump({}, f)
    return user_file

def load_users() -> Dict[str, str]:
    """Load user data from JSON file."""
    user_file = create_user_file()
    try:
        with open(user_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_users(users: Dict[str, str]) -> None:
    """Save user data to JSON file."""
    user_file = create_user_file()
    with open(user_file, "w") as f:
        json.dump(users, f)

def authenticate_user(username: str, password: str) -> bool:
    """Authenticate a user with username and password."""
    users = load_users()
    return username in users and verify_password(users[username], password)

def register_user(username: str, password: str) -> bool:
    """Register a new user."""
    users = load_users()
    if username in users:
        return False
    users[username] = hash_password(password)
    save_users(users)
    return True

# ---------------- AUTHENTICATION UI ----------------

def show_login_page() -> None:
    """Display login/signup page."""
    st.title("🔐 Login to AI Career Mentor")
    
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login"):
            if authenticate_user(username, password):
                initialize_session_state(username)
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid username or password")
    
    with tab2:
        new_username = st.text_input("Username", key="signup_username")
        new_password = st.text_input("Password", type="password", key="signup_password")
        confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password")
        
        if st.button("Sign Up"):
            if new_password != confirm_password:
                st.error("Passwords do not match")
            elif not new_username or not new_password:
                st.error("Please enter both username and password")
            elif register_user(new_username, new_password):
                st.success("Account created successfully! Please login.")
            else:
                st.error("Username already exists")

def logout() -> None:
    """Log out current user and reset session state."""
    for key in st.session_state.keys():
        del st.session_state[key]
    st.rerun()

def check_authentication() -> bool:
    """Check if user is authenticated, show login page if not."""
    if "authenticated" not in st.session_state or not st.session_state.authenticated:
        show_login_page()
        return False
    return True

def initialize_session_state(username: str) -> None:
    """Initialize session state variables after successful login."""
    st.session_state.authenticated = True
    st.session_state.username = username
    st.session_state.messages = []
    st.session_state.chat_history = {}
    st.session_state.archived_chats = {}
    st.session_state.editing_message_index = None
    st.session_state.current_chat_name = None
    st.session_state.assessment_results = None
    st.session_state.show_assessment = False
    st.session_state.resume_analysis = None
    st.session_state.show_resume_analysis = False

# ---------------- CHAT MANAGEMENT FUNCTIONS ----------------

def save_current_chat() -> Optional[str]:
    """Save current chat to history."""
    if st.session_state.messages:
        timestamp = datetime.now().strftime('%H-%M-%S')
        name = f"Career_Chat_{timestamp}"
        st.session_state.chat_history[name] = st.session_state.messages.copy()
        st.session_state.current_chat_name = name
        return name
    return None

def load_chat(chat_name: str) -> None:
    """Load a specific chat from history."""
    st.session_state.messages = st.session_state.chat_history.get(chat_name, []).copy()
    st.session_state.current_chat_name = chat_name

def rename_chat(old_name: str, new_name: str) -> bool:
    """Rename a chat in history."""
    if old_name in st.session_state.chat_history and new_name not in st.session_state.chat_history:
        st.session_state.chat_history[new_name] = st.session_state.chat_history[old_name]
        del st.session_state.chat_history[old_name]
        if st.session_state.current_chat_name == old_name:
            st.session_state.current_chat_name = new_name
        return True
    return False

def archive_chat(chat_name: str) -> bool:
    """Archive a chat from active history."""
    if chat_name in st.session_state.chat_history:
        st.session_state.archived_chats[chat_name] = st.session_state.chat_history[chat_name]
        del st.session_state.chat_history[chat_name]
        if st.session_state.current_chat_name == chat_name:
            st.session_state.current_chat_name = None
        return True
    return False

def restore_chat(chat_name: str) -> bool:
    """Restore a chat from archived history."""
    if chat_name in st.session_state.archived_chats:
        st.session_state.chat_history[chat_name] = st.session_state.archived_chats[chat_name]
        del st.session_state.archived_chats[chat_name]
        return True
    return False

def delete_chat(chat_name: str, archived: bool = False) -> bool:
    """Delete a chat from history."""
    chat_dict = st.session_state.archived_chats if archived else st.session_state.chat_history
    if chat_name in chat_dict:
        del chat_dict[chat_name]
        if st.session_state.current_chat_name == chat_name:
            st.session_state.current_chat_name = None
        return True
    return False

# ---------------- RESUME ANALYSIS FUNCTIONS ----------------

def extract_text_from_pdf(pdf_file) -> str:
    """Extract text from a PDF file."""
    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_file.read()))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {str(e)}")
        return ""

def extract_text_from_docx(docx_file) -> str:
    """Extract text from a DOCX file."""
    try:
        doc = docx.Document(io.BytesIO(docx_file.read()))
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    except Exception as e:
        st.error(f"Error reading DOCX: {str(e)}")
        return ""

def extract_text_from_txt(txt_file) -> str:
    """Extract text from a TXT file."""
    try:
        return txt_file.read().decode("utf-8")
    except Exception as e:
        st.error(f"Error reading TXT: {str(e)}")
        return ""

def extract_resume_text(uploaded_file) -> str:
    """Extract text from an uploaded resume file."""
    file_type = uploaded_file.type
    
    if file_type == "application/pdf":
        return extract_text_from_pdf(uploaded_file)
    elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_text_from_docx(uploaded_file)
    elif file_type == "text/plain":
        return extract_text_from_txt(uploaded_file)
    else:
        st.error("Unsupported file type. Please upload a PDF, DOCX, or TXT file.")
        return ""

def analyze_resume(resume_text: str, model: str) -> Dict:
    """Analyze resume text using AI model."""
    # Create a comprehensive prompt for resume analysis
    analysis_prompt = f"""
    Analyze the following resume and provide a detailed assessment in JSON format with the following structure:
    
    {{
        "overall_score": <number between 0-100>,
        "strengths": [<list of 3-5 key strengths>],
        "improvements": [<list of 3-5 areas for improvement>],
        "skills": {{
            "technical": [<list of technical skills identified>],
            "soft": [<list of soft skills identified>]
        }},
        "experience_level": "<entry-level/mid-level/senior-level/executive>",
        "career_suggestions": [<list of 3-5 potential career paths>],
        "keywords_to_add": [<list of 5-10 keywords that should be added>],
        "formatting_feedback": "<brief feedback on formatting and structure>"
    }}
    
    Resume text:
    {resume_text}
    """
    
    try:
        # Get response from Ollama
        conn = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=OLLAMA_TIMEOUT)
        headers = {"Content-type": "application/json"}
        payload = json.dumps(
            {"model": model, "prompt": analysis_prompt, "stream": False}
        )
        conn.request("POST", "/api/generate", payload, headers)
        res = conn.getresponse()
        data = res.read()
        result = json.loads(data.decode("utf-8"))
        response_text = result.get("response", "")
        
        # Try to extract JSON from the response
        try:
            # Look for JSON pattern in the response
            json_match = re.search(r'```json(.*?)```', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(1).strip()
            else:
                # If no code block, try to find JSON directly
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                if start_idx != -1 and end_idx != -1:
                    json_text = response_text[start_idx:end_idx]
                else:
                    raise ValueError("No JSON found in response")
            
            analysis = json.loads(json_text)
            return analysis
        except (json.JSONDecodeError, ValueError) as e:
            st.error(f"Error parsing analysis results: {str(e)}")
            st.error("Raw response from AI:")
            st.text(response_text)
            return {
                "overall_score": 50,
                "strengths": ["Unable to analyze strengths"],
                "improvements": ["Unable to analyze improvements"],
                "skills": {"technical": [], "soft": []},
                "experience_level": "Unknown",
                "career_suggestions": ["Unable to suggest careers"],
                "keywords_to_add": [],
                "formatting_feedback": "Unable to analyze formatting"
            }
    except Exception as e:
        st.error(f"Error analyzing resume: {str(e)}")
        return {
            "overall_score": 50,
            "strengths": ["Unable to analyze strengths"],
            "improvements": ["Unable to analyze improvements"],
            "skills": {"technical": [], "soft": []},
            "experience_level": "Unknown",
            "career_suggestions": ["Unable to suggest careers"],
            "keywords_to_add": [],
            "formatting_feedback": "Unable to analyze formatting"
        }

def show_resume_analysis() -> None:
    """Display the resume analysis interface."""
    st.title("📄 Resume Analysis")
    st.markdown("Upload your resume to get AI-powered insights and recommendations.")
    
    # Check if we already have analysis results to display
    if st.session_state.resume_analysis:
        show_resume_analysis_results()
        return
    
    # File upload
    uploaded_file = st.file_uploader(
        "Upload your resume (PDF, DOCX, or TXT)",
        type=["pdf", "docx", "txt"]
    )
    
    if uploaded_file is not None:
        # Extract text from the resume
        with st.spinner("Extracting text from your resume..."):
            resume_text = extract_resume_text(uploaded_file)
        
        if resume_text:
            st.success("Resume text extracted successfully!")
            
            # Show a preview of the extracted text
            with st.expander("Preview of extracted text"):
                st.text_area("", resume_text, height=200)
            
            # Analyze button
            if st.button("Analyze Resume"):
                with st.spinner("Analyzing your resume..."):
                    # Use the default model
                    selected_model = DEFAULT_MODEL
                    
                    # Analyze the resume
                    analysis = analyze_resume(resume_text, selected_model)
                    
                    # Store results in session state
                    st.session_state.resume_analysis = {
                        "text": resume_text,
                        "analysis": analysis,
                        "filename": uploaded_file.name,
                        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    # Rerun to show results
                    st.rerun()

def show_resume_analysis_results() -> None:
    """Display the resume analysis results."""
    if not st.session_state.resume_analysis:
        return
    
    analysis_data = st.session_state.resume_analysis
    analysis = analysis_data["analysis"]
    
    st.success(f"Analysis completed on {analysis_data['timestamp']} for {analysis_data['filename']}")
    
    # Overall score with visual gauge
    st.subheader("Overall Resume Score")
    score = analysis.get("overall_score", 50)
    
    # Create a gauge chart for the score
    fig = go.Figure(go.Indicator(
        mode = "gauge+number+delta",
        value = score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Resume Score"},
        delta = {'reference': 70},
        gauge = {
            'axis': {'range': [None, 100]},
            'bar': {'color': "darkblue"},
            'steps': [
                {'range': [0, 50], 'color': "lightgray"},
                {'range': [50, 80], 'color': "gray"}],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 90}}))
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Strengths and Improvements
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🟢 Strengths")
        for strength in analysis.get("strengths", []):
            st.markdown(f"- {strength}")
    
    with col2:
        st.subheader("🔴 Areas for Improvement")
        for improvement in analysis.get("improvements", []):
            st.markdown(f"- {improvement}")
    
    # Skills Analysis
    st.subheader("🛠️ Skills Analysis")
    skills = analysis.get("skills", {})
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Technical Skills:**")
        for skill in skills.get("technical", []):
            st.markdown(f"- {skill}")
    
    with col2:
        st.markdown("**Soft Skills:**")
        for skill in skills.get("soft", []):
            st.markdown(f"- {skill}")
    
    # Experience Level
    st.subheader("📊 Experience Level")
    st.markdown(f"**Identified Level:** {analysis.get('experience_level', 'Unknown')}")
    
    # Career Suggestions
    st.subheader("🎯 Career Suggestions")
    for i, career in enumerate(analysis.get("career_suggestions", [])):
        st.markdown(f"{i+1}. {career}")
    
    # Keywords to Add
    st.subheader("🔑 Recommended Keywords to Add")
    keywords = analysis.get("keywords_to_add", [])
    if keywords:
        # Create a word cloud visualization of keywords
        keyword_df = pd.DataFrame({"keyword": keywords, "count": [1] * len(keywords)})
        fig = px.treemap(keyword_df, path=[px.Constant("Keywords"), "keyword"], values="count")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No specific keywords recommended")
    
    # Formatting Feedback
    st.subheader("📝 Formatting Feedback")
    st.markdown(analysis.get("formatting_feedback", "No feedback available"))
    
    # Action buttons
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("💬 Discuss Resume in Chat"):
            # Create a prompt about the resume analysis
            question = f"I just had my resume analyzed and got a score of {score}%. My strengths are: {', '.join(analysis.get('strengths', []))}. What should I focus on improving first?"
            
            # Add the question to the chat
            st.session_state.messages.append(
                {"role": "user", "content": question, "avatar": "👤"}
            )
            
            # Switch to chat view
            st.session_state.show_resume_analysis = False
            st.rerun()
    
    with col2:
        if st.button("🔄 Re-analyze Resume"):
            st.session_state.resume_analysis = None
            st.rerun()
    
    with col3:
        if st.button("💾 Save Analysis"):
            # Create a filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"resume_analysis_{st.session_state.username}_{timestamp}.json"
            
            # Save the results to a file
            with open(filename, "w") as f:
                json.dump(analysis_data, f)
            
            st.success(f"Analysis results saved to {filename}")

# ---------------- CAREER ASSESSMENT FUNCTIONS ----------------

def show_career_assessment() -> None:
    """Display the career assessment questionnaire."""
    st.title("📊 Career Assessment")
    st.markdown("Answer the following questions to get personalized career recommendations based on your interests, skills, and preferences.")
    
    # Check if we already have assessment results to display
    if st.session_state.assessment_results:
        show_assessment_results()
        return
    
    # Initialize assessment form state
    if "assessment_form" not in st.session_state:
        st.session_state.assessment_form = {}
    
    with st.form("career_assessment_form"):
        st.subheader("Interests")
        interests = st.multiselect(
            "Select your areas of interest:",
            options=["Technology", "Healthcare", "Education", "Business", "Arts & Design", "Science", "Engineering", "Finance", "Marketing", "Social Work"],
            key="interests"
        )
        
        st.subheader("Skills")
        technical_skills = st.multiselect(
            "Select your technical skills:",
            options=["Programming", "Data Analysis", "Project Management", "Design", "Writing", "Public Speaking", "Research", "Sales", "Customer Service", "Leadership"],
            key="technical_skills"
        )
        
        st.subheader("Work Environment Preferences")
        work_style = st.select_slider(
            "Preferred work style:",
            options=["Fully Remote", "Mostly Remote", "Hybrid", "Mostly In-Office", "Fully In-Office"],
            key="work_style"
        )
        
        team_size = st.select_slider(
            "Preferred team size:",
            options=["Solo Work", "Small Team (2-5)", "Medium Team (6-15)", "Large Team (16-50)", "Very Large Team (50+)"],
            key="team_size"
        )
        
        st.subheader("Career Goals")
        career_focus = st.select_slider(
            "What's most important to you in your career?",
            options=["Work-Life Balance", "Job Security", "High Income", "Creativity", "Making an Impact", "Continuous Learning", "Leadership Opportunities"],
            key="career_focus"
        )
        
        risk_tolerance = st.select_slider(
            "How comfortable are you with career risks?",
            options=["Very Risk-Averse", "Somewhat Risk-Averse", "Neutral", "Somewhat Risk-Tolerant", "Very Risk-Tolerant"],
            key="risk_tolerance"
        )
        
        submitted = st.form_submit_button("Get Career Recommendations")
        
        if submitted:
            # Process the assessment
            assessment_data = {
                "interests": interests,
                "technical_skills": technical_skills,
                "work_style": work_style,
                "team_size": team_size,
                "career_focus": career_focus,
                "risk_tolerance": risk_tolerance
            }
            
            # Generate recommendations
            recommendations = generate_career_recommendations(assessment_data)
            
            # Store results in session state
            st.session_state.assessment_results = {
                "data": assessment_data,
                "recommendations": recommendations,
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Rerun to show results
            st.rerun()

def generate_career_recommendations(assessment_data: Dict) -> List[Dict]:
    """Generate career recommendations based on assessment data."""
    # This is a simplified recommendation engine
    # In a real application, this would be more sophisticated
    
    recommendations = []
    
    # Map interests to career paths
    interest_career_map = {
        "Technology": ["Software Developer", "IT Manager", "Data Scientist", "Cybersecurity Analyst"],
        "Healthcare": ["Registered Nurse", "Healthcare Administrator", "Medical Technician", "Physical Therapist"],
        "Education": ["Teacher", "Education Administrator", "Curriculum Developer", "Corporate Trainer"],
        "Business": ["Business Analyst", "Management Consultant", "Product Manager", "Operations Manager"],
        "Arts & Design": ["Graphic Designer", "UX/UI Designer", "Art Director", "Content Creator"],
        "Science": ["Research Scientist", "Lab Technician", "Environmental Scientist", "Biomedical Engineer"],
        "Engineering": ["Mechanical Engineer", "Civil Engineer", "Electrical Engineer", "Software Engineer"],
        "Finance": ["Financial Analyst", "Accountant", "Investment Banker", "Financial Advisor"],
        "Marketing": ["Marketing Manager", "Content Strategist", "Social Media Manager", "Brand Manager"],
        "Social Work": ["Social Worker", "Counselor", "Community Organizer", "Non-profit Manager"]
    }
    
    # Map skills to career paths
    skill_career_map = {
        "Programming": ["Software Developer", "Data Scientist", "Software Engineer", "Web Developer"],
        "Data Analysis": ["Data Scientist", "Business Analyst", "Market Research Analyst", "Financial Analyst"],
        "Project Management": ["Project Manager", "Product Manager", "Operations Manager", "Management Consultant"],
        "Design": ["Graphic Designer", "UX/UI Designer", "Art Director", "Product Designer"],
        "Writing": ["Content Creator", "Technical Writer", "Copywriter", "Editor"],
        "Public Speaking": ["Corporate Trainer", "Sales Manager", "Public Relations Specialist", "Motivational Speaker"],
        "Research": ["Research Scientist", "Market Research Analyst", "Academic Researcher", "UX Researcher"],
        "Sales": ["Sales Manager", "Account Executive", "Business Development Manager", "Sales Representative"],
        "Customer Service": ["Customer Success Manager", "Customer Experience Manager", "Support Specialist", "Client Relations Manager"],
        "Leadership": ["Team Lead", "Department Manager", "Director", "Executive"]
    }
    
    # Get all potential careers from interests and skills
    potential_careers = set()
    
    for interest in assessment_data.get("interests", []):
        if interest in interest_career_map:
            potential_careers.update(interest_career_map[interest])
    
    for skill in assessment_data.get("technical_skills", []):
        if skill in skill_career_map:
            potential_careers.update(skill_career_map[skill])
    
    # If no interests or skills selected, provide general recommendations
    if not potential_careers:
        potential_careers = ["Project Manager", "Business Analyst", "Marketing Specialist", "Operations Manager"]
    
    # Score and rank careers based on work style and preferences
    career_scores = {}
    
    for career in potential_careers:
        score = 50  # Base score
        
        # Adjust score based on work style preference
        work_style = assessment_data.get("work_style", "Hybrid")
        if work_style == "Fully Remote" and career in ["Software Developer", "Data Scientist", "UX/UI Designer", "Content Creator"]:
            score += 20
        elif work_style == "Fully In-Office" and career in ["Healthcare Administrator", "Teacher", "Mechanical Engineer", "Registered Nurse"]:
            score += 20
        
        # Adjust score based on team size preference
        team_size = assessment_data.get("team_size", "Medium Team (6-15)")
        if team_size == "Solo Work" and career in ["Writer", "Research Scientist", "Graphic Designer"]:
            score += 15
        elif team_size == "Large Team (16-50)" and career in ["Project Manager", "Operations Manager", "Product Manager"]:
            score += 15
        
        # Adjust score based on career focus
        career_focus = assessment_data.get("career_focus", "Work-Life Balance")
        if career_focus == "High Income" and career in ["Investment Banker", "Software Engineer", "Management Consultant"]:
            score += 25
        elif career_focus == "Work-Life Balance" and career in ["Technical Writer", "UX/UI Designer", "Data Analyst"]:
            score += 25
        elif career_focus == "Making an Impact" and career in ["Social Worker", "Non-profit Manager", "Environmental Scientist"]:
            score += 25
        
        # Adjust score based on risk tolerance
        risk_tolerance = assessment_data.get("risk_tolerance", "Neutral")
        if risk_tolerance == "Very Risk-Tolerant" and career in ["Entrepreneur", "Investment Banker", "Management Consultant"]:
            score += 20
        elif risk_tolerance == "Very Risk-Averse" and career in ["Accountant", "Government Administrator", "Teacher"]:
            score += 20
        
        career_scores[career] = score
    
    # Sort careers by score and get top recommendations
    sorted_careers = sorted(career_scores.items(), key=lambda x: x[1], reverse=True)
    
    # Generate detailed recommendations
    for career, score in sorted_careers[:5]:  # Top 5 recommendations
        match_percentage = min(95, score)  # Cap at 95%
        
        # Generate a brief description for each career
        descriptions = {
            "Software Developer": "Design, develop, and test software applications and systems.",
            "Data Scientist": "Analyze complex data to help organizations make better decisions.",
            "UX/UI Designer": "Create user-friendly interfaces and experiences for digital products.",
            "Project Manager": "Plan, execute, and close projects, ensuring they meet deadlines and budgets.",
            "Product Manager": "Guide the development of products from conception to launch.",
            "Business Analyst": "Analyze business needs and find solutions to business problems.",
            "Marketing Manager": "Develop and implement marketing strategies to promote products or services.",
            "Financial Analyst": "Evaluate financial data to help businesses make investment decisions.",
            "Graphic Designer": "Create visual concepts to communicate ideas through designs.",
            "Technical Writer": "Create documentation that explains technical information in a clear way.",
            "Operations Manager": "Oversee the production of goods and services in an organization.",
            "Healthcare Administrator": "Manage healthcare facilities and ensure quality patient care.",
            "Teacher": "Educate students and help them develop knowledge and skills.",
            "Social Worker": "Help people cope with problems in their everyday lives.",
            "Accountant": "Prepare and examine financial records and ensure taxes are paid properly.",
            "Mechanical Engineer": "Design and develop mechanical devices and systems.",
            "Research Scientist": "Conduct research to advance knowledge in their field.",
            "Investment Banker": "Help companies raise capital and provide financial advisory services.",
            "Management Consultant": "Advise organizations on how to improve performance and efficiency.",
            "Environmental Scientist": "Study the environment and develop solutions to environmental problems.",
            "Registered Nurse": "Provide patient care and educate patients about health conditions.",
            "Content Creator": "Produce engaging content for various platforms and audiences.",
            "Cybersecurity Analyst": "Protect computer systems and networks from cyber threats.",
            "IT Manager": "Oversee the technology infrastructure of an organization.",
            "Education Administrator": "Manage educational institutions and programs.",
            "Art Director": "Oversee the visual style and images in publications, product packaging, and more.",
            "Civil Engineer": "Design and supervise the construction of infrastructure projects.",
            "Electrical Engineer": "Design, develop, and test electrical equipment and systems.",
            "Financial Advisor": "Provide financial guidance to individuals and businesses.",
            "Sales Manager": "Lead a team of sales representatives and set sales goals.",
            "Customer Success Manager": "Ensure customers get the most value from a product or service.",
            "Lab Technician": "Perform tests and procedures in a laboratory setting.",
            "Physical Therapist": "Help patients recover from injuries and illnesses.",
            "Biomedical Engineer": "Design and develop medical devices and equipment.",
            "Curriculum Developer": "Create educational materials and learning experiences.",
            "Corporate Trainer": "Teach employees skills and knowledge relevant to their jobs.",
            "Operations Manager": "Oversee the production of goods and services in an organization.",
            "Content Strategist": "Plan, develop, and manage content to meet business goals.",
            "Social Media Manager": "Manage social media accounts and create engaging content.",
            "Brand Manager": "Develop and maintain the public image of a company or product.",
            "Counselor": "Help individuals deal with mental health and emotional issues.",
            "Community Organizer": "Work with community members to address local issues.",
            "Non-profit Manager": "Oversee the operations of a non-profit organization.",
            "Public Relations Specialist": "Manage the public image of an organization or individual.",
            "Market Research Analyst": "Study market conditions to examine potential sales of products or services.",
            "Academic Researcher": "Conduct research in an academic setting to advance knowledge.",
            "UX Researcher": "Study user behavior to inform product design and development.",
            "Account Executive": "Manage client relationships and drive sales.",
            "Business Development Manager": "Identify new business opportunities and build relationships.",
            "Sales Representative": "Sell products or services to customers.",
            "Customer Experience Manager": "Oversee and improve the overall customer experience.",
            "Client Relations Manager": "Maintain and develop relationships with clients.",
            "Support Specialist": "Provide technical support to customers.",
            "Team Lead": "Lead a team of employees and oversee their work.",
            "Department Manager": "Manage a specific department within an organization.",
            "Director": "Oversee a major function or division of an organization.",
            "Executive": "Make high-level decisions that affect the entire organization.",
            "Copywriter": "Write compelling text for marketing and advertising purposes.",
            "Editor": "Review and revise content for publication.",
            "Motivational Speaker": "Deliver speeches to inspire and motivate audiences.",
            "Web Developer": "Build and maintain websites and web applications.",
            "Product Designer": "Design products that are both functional and aesthetically pleasing."
        }
        
        description = descriptions.get(career, "A professional role in your field of interest.")
        
        recommendations.append({
            "career": career,
            "match_percentage": match_percentage,
            "description": description,
            "key_skills": get_key_skills_for_career(career),
            "salary_range": get_salary_range_for_career(career),
            "growth_outlook": get_growth_outlook_for_career(career)
        })
    
    return recommendations

def get_key_skills_for_career(career: str) -> List[str]:
    """Get key skills required for a specific career."""
    skills_map = {
        "Software Developer": ["Programming", "Problem Solving", "Attention to Detail", "Teamwork"],
        "Data Scientist": ["Data Analysis", "Statistics", "Machine Learning", "Communication"],
        "UX/UI Designer": ["Design Principles", "User Research", "Prototyping", "Communication"],
        "Project Manager": ["Planning", "Risk Management", "Communication", "Leadership"],
        "Product Manager": ["Market Research", "Strategic Thinking", "Communication", "Leadership"],
        "Business Analyst": ["Critical Thinking", "Data Analysis", "Communication", "Problem Solving"],
        "Marketing Manager": ["Market Research", "Strategic Planning", "Communication", "Creativity"],
        "Financial Analyst": ["Financial Modeling", "Attention to Detail", "Analytical Thinking", "Communication"],
        "Graphic Designer": ["Design Software", "Creativity", "Typography", "Time Management"],
        "Technical Writer": ["Writing Skills", "Technical Knowledge", "Attention to Detail", "Communication"],
        "Operations Manager": ["Process Optimization", "Leadership", "Problem Solving", "Communication"],
        "Healthcare Administrator": ["Healthcare Knowledge", "Management", "Budgeting", "Communication"],
        "Teacher": ["Subject Knowledge", "Communication", "Patience", "Classroom Management"],
        "Social Worker": ["Empathy", "Communication", "Problem Solving", "Resourcefulness"],
        "Accountant": ["Accounting Principles", "Attention to Detail", "Analytical Skills", "Ethics"],
        "Mechanical Engineer": ["Engineering Principles", "Problem Solving", "Technical Skills", "Teamwork"],
        "Research Scientist": ["Research Methods", "Critical Thinking", "Data Analysis", "Patience"],
        "Investment Banker": ["Financial Analysis", "Strategic Thinking", "Communication", "Resilience"],
        "Management Consultant": ["Problem Solving", "Analytical Skills", "Communication", "Strategic Thinking"],
        "Environmental Scientist": ["Scientific Knowledge", "Data Analysis", "Field Research", "Communication"],
        "Registered Nurse": ["Medical Knowledge", "Patient Care", "Communication", "Empathy"],
        "Content Creator": ["Creativity", "Content Strategy", "Social Media Knowledge", "Communication"],
        "Cybersecurity Analyst": ["Network Security", "Problem Solving", "Attention to Detail", "Communication"],
        "IT Manager": ["IT Knowledge", "Management", "Strategic Planning", "Communication"],
        "Education Administrator": ["Educational Knowledge", "Management", "Budgeting", "Communication"],
        "Art Director": ["Design Principles", "Leadership", "Creativity", "Communication"],
        "Civil Engineer": ["Engineering Principles", "Project Management", "Problem Solving", "Attention to Detail"],
        "Electrical Engineer": ["Engineering Principles", "Technical Skills", "Problem Solving", "Teamwork"],
        "Financial Advisor": ["Financial Knowledge", "Communication", "Sales Skills", "Trustworthiness"],
        "Sales Manager": ["Sales Skills", "Leadership", "Communication", "Strategic Thinking"],
        "Customer Success Manager": ["Customer Service", "Communication", "Problem Solving", "Relationship Building"],
        "Lab Technician": ["Lab Procedures", "Attention to Detail", "Technical Skills", "Documentation"],
        "Physical Therapist": ["Medical Knowledge", "Patient Care", "Communication", "Patience"],
        "Biomedical Engineer": ["Engineering Principles", "Medical Knowledge", "Problem Solving", "Technical Skills"],
        "Curriculum Developer": ["Educational Knowledge", "Content Development", "Research Skills", "Communication"],
        "Corporate Trainer": ["Subject Knowledge", "Presentation Skills", "Communication", "Patience"],
        "Content Strategist": ["Content Planning", "SEO Knowledge", "Analytics", "Communication"],
        "Social Media Manager": ["Social Media Knowledge", "Content Creation", "Analytics", "Communication"],
        "Brand Manager": ["Marketing Knowledge", "Strategic Thinking", "Creativity", "Communication"],
        "Counselor": ["Psychology Knowledge", "Empathy", "Communication", "Active Listening"],
        "Community Organizer": ["Communication", "Leadership", "Problem Solving", "Resourcefulness"],
        "Non-profit Manager": ["Management", "Fundraising", "Communication", "Strategic Planning"],
        "Public Relations Specialist": ["Communication", "Writing Skills", "Media Relations", "Strategic Thinking"],
        "Market Research Analyst": ["Data Analysis", "Research Methods", "Critical Thinking", "Communication"],
        "Academic Researcher": ["Research Methods", "Subject Knowledge", "Critical Thinking", "Writing Skills"],
        "UX Researcher": ["Research Methods", "User Psychology", "Data Analysis", "Communication"],
        "Account Executive": ["Sales Skills", "Communication", "Relationship Building", "Product Knowledge"],
        "Business Development Manager": ["Sales Skills", "Strategic Thinking", "Communication", "Networking"],
        "Sales Representative": ["Sales Skills", "Communication", "Product Knowledge", "Persistence"],
        "Customer Experience Manager": ["Customer Service", "Communication", "Problem Solving", "Analytics"],
        "Client Relations Manager": ["Communication", "Relationship Building", "Problem Solving", "Customer Service"],
        "Support Specialist": ["Technical Knowledge", "Problem Solving", "Communication", "Patience"],
        "Team Lead": ["Leadership", "Communication", "Technical Skills", "Time Management"],
        "Department Manager": ["Management", "Strategic Planning", "Communication", "Budgeting"],
        "Director": ["Strategic Thinking", "Leadership", "Communication", "Decision Making"],
        "Executive": ["Strategic Vision", "Leadership", "Decision Making", "Communication"],
        "Copywriter": ["Writing Skills", "Creativity", "Marketing Knowledge", "Attention to Detail"],
        "Editor": ["Writing Skills", "Attention to Detail", "Communication", "Time Management"],
        "Motivational Speaker": ["Public Speaking", "Communication", "Inspiration", "Storytelling"],
        "Web Developer": ["Programming", "Web Technologies", "Problem Solving", "Attention to Detail"],
        "Product Designer": ["Design Principles", "User Research", "Prototyping", "Communication"]
    }
    
    return skills_map.get(career, ["Communication", "Problem Solving", "Teamwork", "Technical Skills"])

def get_salary_range_for_career(career: str) -> str:
    """Get estimated salary range for a specific career."""
    salary_map = {
        "Software Developer": "$70,000 - $150,000",
        "Data Scientist": "$85,000 - $170,000",
        "UX/UI Designer": "$65,000 - $130,000",
        "Project Manager": "$75,000 - $140,000",
        "Product Manager": "$85,000 - $160,000",
        "Business Analyst": "$65,000 - $120,000",
        "Marketing Manager": "$70,000 - $140,000",
        "Financial Analyst": "$65,000 - $120,000",
        "Graphic Designer": "$45,000 - $85,000",
        "Technical Writer": "$55,000 - $100,000",
        "Operations Manager": "$70,000 - $130,000",
        "Healthcare Administrator": "$75,000 - $140,000",
        "Teacher": "$40,000 - $75,000",
        "Social Worker": "$45,000 - $75,000",
        "Accountant": "$55,000 - $100,000",
        "Mechanical Engineer": "$70,000 - $130,000",
        "Research Scientist": "$75,000 - $140,000",
        "Investment Banker": "$100,000 - $250,000+",
        "Management Consultant": "$85,000 - $180,000",
        "Environmental Scientist": "$60,000 - $110,000",
        "Registered Nurse": "$60,000 - $90,000",
        "Content Creator": "$40,000 - $100,000+",
        "Cybersecurity Analyst": "$75,000 - $140,000",
        "IT Manager": "$85,000 - $150,000",
        "Education Administrator": "$70,000 - $130,000",
        "Art Director": "$65,000 - $130,000",
        "Civil Engineer": "$70,000 - $130,000",
        "Electrical Engineer": "$75,000 - $140,000",
        "Financial Advisor": "$60,000 - $150,000+",
        "Sales Manager": "$75,000 - $150,000+",
        "Customer Success Manager": "$65,000 - $120,000",
        "Lab Technician": "$40,000 - $70,000",
        "Physical Therapist": "$70,000 - $100,000",
        "Biomedical Engineer": "$70,000 - $130,000",
        "Curriculum Developer": "$60,000 - $100,000",
        "Corporate Trainer": "$60,000 - $110,000",
        "Content Strategist": "$60,000 - $110,000",
        "Social Media Manager": "$50,000 - $90,000",
        "Brand Manager": "$75,000 - $140,000",
        "Counselor": "$45,000 - $75,000",
        "Community Organizer": "$40,000 - $70,000",
        "Non-profit Manager": "$60,000 - $100,000",
        "Public Relations Specialist": "$50,000 - $90,000",
        "Market Research Analyst": "$60,000 - $110,000",
        "Academic Researcher": "$60,000 - $120,000",
        "UX Researcher": "$70,000 - $130,000",
        "Account Executive": "$60,000 - $130,000+",
        "Business Development Manager": "$70,000 - $140,000+",
        "Sales Representative": "$40,000 - $100,000+",
        "Customer Experience Manager": "$70,000 - $120,000",
        "Client Relations Manager": "$60,000 - $110,000",
        "Support Specialist": "$45,000 - $80,000",
        "Team Lead": "$70,000 - $120,000",
        "Department Manager": "$80,000 - $150,000",
        "Director": "$120,000 - $200,000+",
        "Executive": "$150,000 - $300,000+",
        "Copywriter": "$50,000 - $90,000",
        "Editor": "$55,000 - $95,000",
        "Motivational Speaker": "$50,000 - $200,000+",
        "Web Developer": "$60,000 - $120,000",
        "Product Designer": "$70,000 - $130,000"
    }
    
    return salary_map.get(career, "$50,000 - $100,000")

def get_growth_outlook_for_career(career: str) -> str:
    """Get growth outlook for a specific career."""
    outlook_map = {
        "Software Developer": "Excellent (22% growth expected through 2030)",
        "Data Scientist": "Excellent (31% growth expected through 2030)",
        "UX/UI Designer": "Excellent (13% growth expected through 2030)",
        "Project Manager": "Good (7% growth expected through 2030)",
        "Product Manager": "Excellent (10% growth expected through 2030)",
        "Business Analyst": "Good (7% growth expected through 2030)",
        "Marketing Manager": "Good (10% growth expected through 2030)",
        "Financial Analyst": "Good (6% growth expected through 2030)",
        "Graphic Designer": "Slow (3% growth expected through 2030)",
        "Technical Writer": "Good (7% growth expected through 2030)",
        "Operations Manager": "Good (7% growth expected through 2030)",
        "Healthcare Administrator": "Excellent (32% growth expected through 2030)",
        "Teacher": "Average (4% growth expected through 2030)",
        "Social Worker": "Excellent (13% growth expected through 2030)",
        "Accountant": "Average (4% growth expected through 2030)",
        "Mechanical Engineer": "Average (4% growth expected through 2030)",
        "Research Scientist": "Good (8% growth expected through 2030)",
        "Investment Banker": "Good (6% growth expected through 2030)",
        "Management Consultant": "Excellent (14% growth expected through 2030)",
        "Environmental Scientist": "Excellent (8% growth expected through 2030)",
        "Registered Nurse": "Excellent (9% growth expected through 2030)",
        "Content Creator": "Excellent (14% growth expected through 2030)",
        "Cybersecurity Analyst": "Excellent (33% growth expected through 2030)",
        "IT Manager": "Excellent (11% growth expected through 2030)",
        "Education Administrator": "Good (8% growth expected through 2030)",
        "Art Director": "Slow (4% growth expected through 2030)",
        "Civil Engineer": "Good (8% growth expected through 2030)",
        "Electrical Engineer": "Average (3% growth expected through 2030)",
        "Financial Advisor": "Excellent (5% growth expected through 2030)",
        "Sales Manager": "Good (5% growth expected through 2030)",
        "Customer Success Manager": "Excellent (15% growth expected through 2030)",
        "Lab Technician": "Average (7% growth expected through 2030)",
        "Physical Therapist": "Excellent (21% growth expected through 2030)",
        "Biomedical Engineer": "Excellent (6% growth expected through 2030)",
        "Curriculum Developer": "Good (7% growth expected through 2030)",
        "Corporate Trainer": "Good (9% growth expected through 2030)",
        "Content Strategist": "Excellent (10% growth expected through 2030)",
        "Social Media Manager": "Excellent (10% growth expected through 2030)",
        "Brand Manager": "Good (6% growth expected through 2030)",
        "Counselor": "Excellent (23% growth expected through 2030)",
        "Community Organizer": "Good (9% growth expected through 2030)",
        "Non-profit Manager": "Good (8% growth expected through 2030)",
        "Public Relations Specialist": "Good (11% growth expected through 2030)",
        "Market Research Analyst": "Excellent (18% growth expected through 2030)",
        "Academic Researcher": "Average (5% growth expected through 2030)",
        "UX Researcher": "Excellent (14% growth expected through 2030)",
        "Account Executive": "Good (6% growth expected through 2030)",
        "Business Development Manager": "Good (7% growth expected through 2030)",
        "Sales Representative": "Average (2% growth expected through 2030)",
        "Customer Experience Manager": "Excellent (15% growth expected through 2030)",
        "Client Relations Manager": "Good (6% growth expected through 2030)",
        "Support Specialist": "Average (6% growth expected through 2030)",
        "Team Lead": "Good (7% growth expected through 2030)",
        "Department Manager": "Good (7% growth expected through 2030)",
        "Director": "Good (8% growth expected through 2030)",
        "Executive": "Good (6% growth expected through 2030)",
        "Copywriter": "Slow (2% growth expected through 2030)",
        "Editor": "Slow (2% growth expected through 2030)",
        "Motivational Speaker": "Good (7% growth expected through 2030)",
        "Web Developer": "Excellent (13% growth expected through 2030)",
        "Product Designer": "Excellent (13% growth expected through 2030)"
    }
    
    return outlook_map.get(career, "Average (5% growth expected through 2030)")

def show_assessment_results() -> None:
    """Display the career assessment results."""
    if not st.session_state.assessment_results:
        return
    
    results = st.session_state.assessment_results
    recommendations = results["recommendations"]
    
    st.success(f"Assessment completed on {results['timestamp']}")
    
    # Create a visualization of the top recommendations
    st.subheader("Your Top Career Recommendations")
    
    # Create a dataframe for visualization
    df = pd.DataFrame([
        {"Career": rec["career"], "Match %": rec["match_percentage"]} 
        for rec in recommendations
    ])
    
    # Create a bar chart
    fig = px.bar(
        df, 
        x="Match %", 
        y="Career", 
        orientation='h',
        color="Match %",
        color_continuous_scale="viridis",
        title="Career Match Percentage"
    )
    fig.update_layout(yaxis={'categoryorder':'total ascending'})
    st.plotly_chart(fig, use_container_width=True)
    
    # Display detailed information for each recommendation
    for i, rec in enumerate(recommendations):
        with st.expander(f"{i+1}. {rec['career']} - {rec['match_percentage']}% Match"):
            st.markdown(f"**Description:** {rec['description']}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Key Skills Required:**")
                for skill in rec["key_skills"]:
                    st.markdown(f"- {skill}")
            
            with col2:
                st.markdown(f"**Salary Range:** {rec['salary_range']}")
                st.markdown(f"**Growth Outlook:** {rec['growth_outlook']}")
            
            # Add a button to discuss this career in the chat
            # Store the career in session state to be used in the chat
            if st.button(f"Discuss {rec['career']} in Chat", key=f"discuss_{i}"):
                st.session_state.selected_career = rec['career']
                st.session_state.show_assessment = False
                st.rerun()
    
    # Add buttons for retaking assessment and saving results
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Retake Assessment"):
            st.session_state.assessment_results = None
            st.rerun()
    
    with col2:
        if st.button("Save Assessment Results"):
            # Create a filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"career_assessment_{st.session_state.username}_{timestamp}.json"
            
            # Save the results to a file
            with open(filename, "w") as f:
                json.dump(results, f)
            
            st.success(f"Assessment results saved to {filename}")

# ---------------- OLLAMA INTEGRATION ----------------

def test_ollama_connection() -> bool:
    """Test if Ollama is running and accessible."""
    try:
        response = requests.get(f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags", timeout=5)
        if response.status_code == 200:
            return True
        else:
            return False
    except Exception:
        return False

def get_ollama_models() -> List[str]:
    """Get available models from Ollama."""
    try:
        response = requests.get(f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags", timeout=5)
        if response.status_code == 200:
            result = response.json()
            models = [model["name"] for model in result.get("models", [])]
            # Always include nemotron-3-nano:30b-cloud
            if DEFAULT_MODEL not in models:
                models.append(DEFAULT_MODEL)
            return models
        else:
            return [DEFAULT_MODEL]
    except Exception:
        return [DEFAULT_MODEL]

@st.cache_resource
def load_models() -> List[str]:
    """Load and cache available Ollama models."""
    return get_ollama_models()

def is_career_related_question(prompt: str) -> bool:
    """Check if the user's question is career-related."""
    career_keywords = [
        "career", "job", "work", "employment", "profession", "occupation", "vocation",
        "resume", "cv", "interview", "hiring", "recruitment", "salary", "pay", "wage",
        "skills", "qualification", "education", "training", "development", "promotion",
        "industry", "field", "sector", "company", "organization", "business", "enterprise",
        "networking", "professional", "expertise", "experience", "background", "path",
        "advancement", "growth", "opportunity", "position", "role", "title", "function",
        "department", "team", "management", "leadership", "supervisor", "boss", "colleague",
        "workplace", "environment", "culture", "benefits", "perks", "flexibility", "remote",
        "freelance", "contract", "full-time", "part-time", "internship", "apprenticeship",
        "entrepreneur", "startup", "business owner", "self-employed", "consultant",
        "coach", "mentor", "advisor", "guidance", "counseling", "planning", "strategy",
        "goal", "objective", "ambition", "aspiration", "dream", "passion", "interest",
        "strength", "weakness", "challenge", "obstacle", "solution", "advice", "recommendation",
        "suggestion", "tip", "hint", "best practice", "technique", "method", "approach",
        "tool", "resource", "platform", "website", "course", "certification", "degree",
        "diploma", "certificate", "license", "accreditation", "recognition", "award"
    ]
    
    prompt_lower = prompt.lower()
    return any(keyword in prompt_lower for keyword in career_keywords)

def get_ollama_response_stream(prompt: str, model: str) -> Generator[str, None, None]:
    """Get a streaming response from Ollama."""
    # Check if the question is career-related
    if not is_career_related_question(prompt):
        yield "I'm designed to help with career-related questions only. Please ask about careers, job searching, skills development, resume writing, interviews, or other professional topics."
        return
    
    # Build context with all message history
    messages = st.session_state.messages
    
    # System prompt for career guidance with strict focus
    system_prompt = """You are an AI Career Mentor, an expert in career guidance, job market trends, skill development, and professional growth. 
    Your role is to provide personalized career advice ONLY on career-related topics.
    
    STRICTLY FOCUS ON CAREER-RELATED QUESTIONS. If a user asks about non-career topics, politely redirect them to ask career-related questions.
    
    Provide thoughtful, detailed, and actionable career advice.
    Focus on practical steps, skill development opportunities, career paths, and industry insights.
    Be encouraging but realistic about career prospects and requirements."""
    
    # Build the full prompt with context
    full_prompt = f"{system_prompt}\n\n"
    for msg in messages:
        if msg["role"] == "user":
            full_prompt += f"User: {msg['content']}\n"
        elif msg["role"] == "assistant":
            full_prompt += f"Career Mentor: {msg['content']}\n"
    
    # Add the new prompt
    full_prompt += f"User: {prompt}\nCareer Mentor:"
    
    try:
        # Use http.client for better compatibility with Ollama
        conn = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=OLLAMA_TIMEOUT)
        headers = {"Content-type": "application/json"}
        payload = json.dumps(
            {"model": model, "prompt": full_prompt, "stream": True}
        )
        conn.request("POST", "/api/generate", payload, headers)
        res = conn.getresponse()
        
        if res.status == 200:
            # Read the response line by line
            while True:
                line = res.readline()
                if not line:
                    break
                
                try:
                    # Decode and parse the JSON response
                    data = json.loads(line.decode("utf-8"))
                    chunk = data.get("response", "")
                    if chunk:
                        yield chunk
                except json.JSONDecodeError:
                    # Skip lines that can't be parsed as JSON
                    continue
        else:
            yield f"⚠️ Error: Received status code {res.status} from Ollama"
        
        conn.close()
    except Exception as e:
        yield f"⚠️ Could not connect to Ollama. Make sure it is running. Error: {str(e)}"

# ---------------- UI COMPONENTS ----------------

def display_sidebar() -> str:
    """Display the sidebar with settings and controls."""
    with st.sidebar:
        st.title("⚙️ Settings")
        
        # Debug information
        with st.expander("🔍 System Status", expanded=False):
            # Test Ollama connection
            ollama_status = test_ollama_connection()
            if ollama_status:
                st.success("✅ Ollama is running and accessible")
            else:
                st.error("❌ Ollama is not running or not accessible")
                st.markdown("**Troubleshooting:**")
                st.markdown("1. Make sure Ollama is installed: `ollama --version`")
                st.markdown("2. Start Ollama: `ollama serve`")
                st.markdown("3. Check if port 11434 is available")
            
            # Show available models
            models = get_ollama_models()
            st.markdown(f"**Available Models:** {models}")
            
            # Model status
            if DEFAULT_MODEL in models:
                st.success(f"✅ {DEFAULT_MODEL} is available")
            else:
                st.warning(f"⚠️ {DEFAULT_MODEL} not found in Ollama")
        
        st.markdown("---")
        
        # User info and logout
        st.markdown(f"**Logged in as:** {st.session_state.get('username', 'Not logged in')}")
        if st.button("Logout"):
            logout()
        
        st.markdown("---")
        
        # Navigation
        st.subheader("Navigation")
        if st.button("💬 Chat with AI Mentor"):
            st.session_state.show_assessment = False
            st.session_state.show_resume_analysis = False
            st.rerun()
        
        if st.button("📊 Career Assessment"):
            st.session_state.show_assessment = True
            st.session_state.show_resume_analysis = False
            st.rerun()
            
        if st.button("📄 Resume Analysis"):
            st.session_state.show_assessment = False
            st.session_state.show_resume_analysis = True
            st.rerun()
        
        st.markdown("---")
        
        # Model selection - using only nemotron-3-nano:30b-cloud
        selected_model = DEFAULT_MODEL
        st.markdown(f"**Model:** {selected_model}")
        
        st.markdown("---")
        st.subheader("Chat Actions")
        
        # New chat button
        if st.button("New Chat"):
            save_current_chat()
            st.session_state.messages = []
            st.session_state.current_chat_name = None
            st.rerun()
        
        # Download chat button
        if st.session_state.messages:
            chat_text = "\n\n".join(
                [f"{m['role'].title()}: {m['content']}" for m in st.session_state.messages]
            )
            st.download_button(
                "Download Chat",
                data=chat_text,
                file_name=f"career_chat_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt",
                mime="text/plain",
            )
        
        st.markdown("---")
        
        # Chat history tabs
        active_tab, archived_tab = st.tabs(["Active Chats", "Archived Chats"])
        
        with active_tab:
            st.subheader("📚 Chat History")
            
            if st.session_state.chat_history:
                for chat_name in list(st.session_state.chat_history.keys()):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        if st.button(chat_name, key=f"load_{chat_name}", 
                                    help="Load this chat"):
                            load_chat(chat_name)
                            st.session_state.show_assessment = False
                            st.session_state.show_resume_analysis = False
                            st.rerun()
                    with col2:
                        if st.button("✏️", key=f"rename_{chat_name}", 
                                    help="Rename chat"):
                            st.session_state.renaming_chat = chat_name
                            st.rerun()
                    with col3:
                        if st.button("📦", key=f"archive_{chat_name}", 
                                    help="Archive chat"):
                            if archive_chat(chat_name):
                                st.rerun()
            else:
                st.caption("No active chats yet.")
        
        with archived_tab:
            st.subheader("📦 Archived Chats")
            
            if st.session_state.archived_chats:
                for chat_name in list(st.session_state.archived_chats.keys()):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        if st.button(chat_name, key=f"restore_{chat_name}", 
                                    help="Restore this chat"):
                            if restore_chat(chat_name):
                                st.rerun()
                    with col2:
                        if st.button("🗑️", key=f"delete_{chat_name}", 
                                    help="Delete chat"):
                            if delete_chat(chat_name, archived=True):
                                st.rerun()
            else:
                st.caption("No archived chats yet.")
    
    return selected_model

def display_rename_dialog() -> None:
    """Display the rename chat dialog if needed."""
    if st.session_state.get("renaming_chat"):
        chat_name = st.session_state.renaming_chat
        with st.sidebar:
            with st.expander("Rename Chat", expanded=True):
                new_name = st.text_input("New name:", value=chat_name, key=f"new_name_{chat_name}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Save", key=f"save_rename_{chat_name}"):
                        if rename_chat(chat_name, new_name):
                            st.success("Chat renamed!")
                        else:
                            st.error("Name already exists or invalid!")
                        st.session_state.renaming_chat = None
                        st.rerun()
                with col2:
                    if st.button("Cancel", key=f"cancel_rename_{chat_name}"):
                        st.session_state.renaming_chat = None
                        st.rerun()

def display_chat_interface(selected_model: str) -> None:
    """Display the main chat interface."""
    st.title("💬 AI Career Mentor Chatbot")
    st.markdown("⚠️ **Note:** This AI assistant only answers career-related questions. Please ask about careers, jobs, skills, or professional development.")
    
    # Check if we have a selected career from the assessment
    if "selected_career" in st.session_state and st.session_state.selected_career:
        career = st.session_state.selected_career
        # Create a prompt about this career
        question = f"Tell me more about being a {career}. What does a typical day look like, and what are the main challenges and rewards of this career path?"
        
        # Add the question to the chat
        st.session_state.messages.append(
            {"role": "user", "content": question, "avatar": "👤"}
        )
        
        # Clear the selected career from session state
        del st.session_state.selected_career
        
        # Rerun to display the question and get a response
        st.rerun()
    
    # Add some career guidance quick actions
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔍 Explore Careers"):
            st.session_state.messages.append(
                {"role": "user", "content": "I'd like to explore different career paths.", "avatar": "👤"}
            )
            st.rerun()
    
    with col2:
        if st.button("📈 Skill Development"):
            st.session_state.messages.append(
                {"role": "user", "content": "What skills should I develop to advance in my career?", "avatar": "👤"}
            )
            st.rerun()
    
    with col3:
        if st.button("🎯 Career Goals"):
            st.session_state.messages.append(
                {"role": "user", "content": "Help me set realistic career goals and create a plan to achieve them.", "avatar": "👤"}
            )
            st.rerun()
    
    # Display current chat name if available
    if st.session_state.current_chat_name:
        st.caption(f"Current chat: {st.session_state.current_chat_name}")
    
    # Custom CSS for chat interface
    st.markdown(
        """
    <style>
    .message-wrapper {
        position: relative;
        padding-right: 50px;
    }
    .copy-btn {
        position: absolute;
        top: 0;
        right: 0;
        background: transparent;
        border: none;
        cursor: pointer;
        opacity: 0.7;
        transition: opacity 0.2s;
        font-size: 14px;
    }
    .copy-btn:hover {
        opacity: 1;
    }
    .stChatMessage {
        padding-right: 60px !important;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )
    
    # Display messages
    for i, msg in enumerate(st.session_state.messages):
        # Check if this message is being edited
        if st.session_state.editing_message_index == i and msg["role"] == "user":
            with st.chat_message(msg["role"], avatar=msg.get("avatar")):
                edited_content = st.text_area("Edit your message:", value=msg["content"], key=f"edit_{i}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Save", key=f"save_{i}"):
                        st.session_state.messages[i]["content"] = edited_content
                        st.session_state.editing_message_index = None
                        st.rerun()
                with col2:
                    if st.button("Cancel", key=f"cancel_{i}"):
                        st.session_state.editing_message_index = None
                        st.rerun()
        else:
            with st.chat_message(msg["role"], avatar=msg.get("avatar")):
                col1, col2, col3 = st.columns([8, 1, 1])
                
                with col1:
                    st.markdown(msg["content"])
                    
                    # Display response time for assistant messages
                    if msg["role"] == "assistant" and "response_time" in msg:
                        st.caption(f"Response time: {msg['response_time']:.2f} seconds")
                
                with col2:
                    # Add edit button only for user messages
                    if msg["role"] == "user":
                        edit_key = f"edit_btn_{i}"
                        if st.button("✏️", key=edit_key, help="Edit message"):
                            st.session_state.editing_message_index = i
                            st.rerun()
                
                with col3:
                    copy_key = f"copy_{i}_{msg['role']}"
                    if st.button("📋", key=copy_key, help="Copy message"):
                        st.code(msg["content"], language="")
                        st.toast("Message copied to clipboard!", icon="✅")
    
    # Custom CSS for chat input
    st.markdown(
        """
    <style>
    .stChatInput textarea {
        border-radius: 40px !important;
        padding: 18px 25px !important;
        font-size: 18px !important;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )
    
    # Chat input
    prompt = st.chat_input("Ask about career paths, skills, job market trends...")
    
    if prompt:
        # Add user message to session state
        st.session_state.messages.append(
            {"role": "user", "content": prompt, "avatar": "👤"}
        )
        
        # Display user message
        with st.chat_message("user", avatar="👤"):
            col1, col2 = st.columns([10, 1])
            
            with col1:
                st.markdown(prompt)
            
            with col2:
                copy_key = f"copy_user_{len(st.session_state.messages)}"
                if st.button("📋", key=copy_key, help="Copy message"):
                    st.code(prompt, language="")
                    st.toast("Message copied to clipboard!", icon="✅")
        
        # Get and display assistant response
        with st.chat_message("assistant", avatar="🤖"):
            placeholder = st.empty()
            output = ""
            
            # Record start time for response tracking
            start_time = time.time()
            
            # Get response from Ollama
            response = ""
            try:
                # Build context with all message history
                messages = st.session_state.messages
                
                # System prompt for career guidance with strict focus
                system_prompt = """You are an AI Career Mentor, an expert in career guidance, job market trends, skill development, and professional growth. 
                Your role is to provide personalized career advice ONLY on career-related topics.
                
                STRICTLY FOCUS ON CAREER-RELATED QUESTIONS. If a user asks about non-career topics, politely redirect them to ask career-related questions.
                
                Provide thoughtful, detailed, and actionable career advice.
                Focus on practical steps, skill development opportunities, career paths, and industry insights.
                Be encouraging but realistic about career prospects and requirements."""
                
                # Build the full prompt with context
                full_prompt = f"{system_prompt}\n\n"
                for msg in messages:
                    if msg["role"] == "user":
                        full_prompt += f"User: {msg['content']}\n"
                    elif msg["role"] == "assistant":
                        full_prompt += f"Career Mentor: {msg['content']}\n"
                
                # Add the new prompt
                full_prompt += f"User: {prompt}\nCareer Mentor:"
                
                # Make the API call to Ollama
                conn = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=OLLAMA_TIMEOUT)
                headers = {"Content-type": "application/json"}
                payload = json.dumps(
                    {"model": selected_model, "prompt": full_prompt, "stream": True}
                )
                conn.request("POST", "/api/generate", payload, headers)
                res = conn.getresponse()
                
                if res.status == 200:
                    # Read the response line by line
                    while True:
                        line = res.readline()
                        if not line:
                            break
                        
                        try:
                            # Decode and parse the JSON response
                            data = json.loads(line.decode("utf-8"))
                            chunk = data.get("response", "")
                            if chunk:
                                output += chunk
                                placeholder.markdown(output + "▌")
                        except json.JSONDecodeError:
                            # Skip lines that can't be parsed as JSON
                            continue
                else:
                    output = f"⚠️ Error: Received status code {res.status} from Ollama"
                    placeholder.markdown(output)
                
                conn.close()
            except Exception as e:
                output = f"⚠️ Could not connect to Ollama. Make sure it is running. Error: {str(e)}"
                placeholder.markdown(output)
            
            # Calculate response time
            response_time = time.time() - start_time
            
            # Remove the cursor
            placeholder.markdown(output)
            st.caption(f"Response time: {response_time:.2f} seconds")
        
        # Add assistant message to session state
        st.session_state.messages.append(
            {"role": "assistant", "content": output, "avatar": "🤖", "response_time": response_time}
        )

# ---------------- MAIN APP ----------------

def main() -> None:
    """Main application function."""
    # Check authentication
    if not check_authentication():
        st.stop()
    
    # Initialize session state if needed
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = {}
    
    if "archived_chats" not in st.session_state:
        st.session_state.archived_chats = {}
    
    if "editing_message_index" not in st.session_state:
        st.session_state.editing_message_index = None
    
    if "current_chat_name" not in st.session_state:
        st.session_state.current_chat_name = None
    
    if "assessment_results" not in st.session_state:
        st.session_state.assessment_results = None
    
    if "show_assessment" not in st.session_state:
        st.session_state.show_assessment = False
    
    if "resume_analysis" not in st.session_state:
        st.session_state.resume_analysis = None
    
    if "show_resume_analysis" not in st.session_state:
        st.session_state.show_resume_analysis = False
    
    # Display sidebar and get selected model
    selected_model = display_sidebar()
    
    # Display rename dialog if needed
    display_rename_dialog()
    
    # Display the appropriate interface based on the current view
    if st.session_state.show_assessment:
        show_career_assessment()
    elif st.session_state.show_resume_analysis:
        show_resume_analysis()
    else:
        display_chat_interface(selected_model)

# Run the app
if __name__ == "__main__":
    main()