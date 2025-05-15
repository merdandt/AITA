
# --- Constants ---
import re


OUTPUT_FOLDER_NAME = "student_submissions_output"
# If GOOGLE_API_KEY is needed by the authenticator agent
# if not os.getenv('GOOGLE_API_KEY'):
#     raise ValueError('GOOGLE_API_KEY is not set. Please add it to your environment variables if your Agent uses it.')
# model = ChatGoogleGenerativeAI(model='gemini-pro') # Or your preferred model for the agent

# --- Helper: Sanitize Filename ---
def sanitize_filename(name: str) -> str:
    name = re.sub(r'[^\w\s-]', '', name) # Remove invalid chars
    name = re.sub(r'\s+', '_', name).strip('_') # Replace spaces with underscores
    return name 