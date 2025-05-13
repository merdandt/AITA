import streamlit as st
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, Browser, BrowserConfig
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Set page config
st.set_page_config(page_title="Canvas SpeedGrader Assistant", page_icon="🎓", layout="wide")

# Initialize the model outside of the function
@st.cache_resource
def get_model():
    return ChatGoogleGenerativeAI(model='gemini-2.5-flash-preview-04-17')

model = get_model()

# Initialize the browser outside of the function
@st.cache_resource
def get_browser():
    return Browser(
        config=BrowserConfig(
            browser_binary_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        ),
    )

browser = get_browser()

st.title("Canvas SpeedGrader Assistant")

# Sidebar for configuration
with st.sidebar:
    st.header("Configuration")
    email = st.text_input("Canvas Email", value="A02458093@aggies.usu.edu")
    password = st.text_input("Canvas Password", value="4Future$100%!", type="password")
    course_url = st.text_input("Course URL", value="https://usu.instructure.com/courses/780705/assignments")
    speedgrader_url = st.text_input("SpeedGrader URL", value="https://usu.instructure.com/courses/780705/gradebook/speed_grader?assignment_id=4809230&student_id=1812493")

# Main application
tab1, tab2, tab3 = st.tabs(["Login", "Navigate", "Count Students"])

# Status container
status_container = st.empty()
result_container = st.empty()

# Session state to track process
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "navigated" not in st.session_state:
    st.session_state.navigated = False
if "student_count" not in st.session_state:
    st.session_state.student_count = None
if "context" not in st.session_state:
    st.session_state.context = None

async def authenticate(email, password, url):
    try:
        if not st.session_state.context:
            context = await browser.new_context()
            st.session_state.context = context
        else:
            context = st.session_state.context
            
        authenticator = Agent(
            task=f"""
            - Open the URL: {url}
            - Authenticate using the following credentials:
            - Enter email: "{email}"
            - Enter password: "{password}"
            - Click the "Log In" button.
            """,
            llm=model,
            browser_context=context
        )
        result = await authenticator.run()
        st.session_state.authenticated = True
        return result
    except Exception as e:
        return f"Error during authentication: {str(e)}"

async def navigate(url):
    try:
        context = st.session_state.context
        navigator = Agent(
            task=f"""
            - Open the URL: {url}
            - Find the elemen with the class="css-d9mlzv-view--inlineBlock-baseButton" (menu button)
            - Click the menu button (in the menu dialog number of items will appear).
            - Find and click "Open in SpeedGrader" item on class="discussion-thread-menuitem-speedGrader"
            - Proceed to the SpeedGrader page.
            """,
            llm=model,
            browser_context=context
        )
        result = await navigator.run()
        st.session_state.navigated = True
        return result
    except Exception as e:
        return f"Error during navigation: {str(e)}"

async def count_students():
    try:
        context = st.session_state.context
        grader = Agent(
            task="""
            - Open the dropdown with class "ui-selectmenu ui-widget ui-state-default ui-corner-all ui-selectmenu-dropdown not_graded ui-selectmenu-hasIcon".
            - Count the items (which represent students).
            """,
            llm=model,
            browser_context=context
        )
        result = await grader.run()
        return result
    except Exception as e:
        return f"Error counting students: {str(e)}"

# Login Tab
with tab1:
    st.header("Step 1: Login to Canvas")
    st.write("Click the button below to login with your Canvas credentials.")
    
    if st.button("Login to Canvas"):
        with status_container:
            with st.spinner("Logging in..."):
                auth_result = asyncio.run(authenticate(email, password, course_url))
                
        with result_container:
            if st.session_state.authenticated:
                st.success("Successfully logged in!")
                st.write(auth_result)
            else:
                st.error("Login failed")
                st.write(auth_result)
    
    if st.session_state.authenticated:
        st.success("You are logged in.")

# Navigate Tab
with tab2:
    st.header("Step 2: Navigate to SpeedGrader")
    st.write("Navigate to the SpeedGrader interface.")
    
    if not st.session_state.authenticated:
        st.warning("Please login first in the Login tab.")
    else:
        if st.button("Open SpeedGrader"):
            with status_container:
                with st.spinner("Navigating to SpeedGrader..."):
                    nav_result = asyncio.run(navigate(speedgrader_url))
                    
            with result_container:
                if st.session_state.navigated:
                    st.success("Successfully navigated to SpeedGrader!")
                    st.write(nav_result)
                else:
                    st.error("Navigation failed")
                    st.write(nav_result)
        
        if st.session_state.navigated:
            st.success("You are in SpeedGrader.")

# Count Students Tab
with tab3:
    st.header("Step 3: Count Students")
    st.write("Count the number of students in the SpeedGrader dropdown.")
    
    if not st.session_state.navigated:
        st.warning("Please navigate to SpeedGrader first in the Navigate tab.")
    else:
        if st.button("Count Students"):
            with status_container:
                with st.spinner("Counting students..."):
                    count_result = asyncio.run(count_students())
                    
            with result_container:
                st.success("Successfully counted students!")
                st.write(count_result)
                
                # Try to extract the count from the result
                import re
                try:
                    count_match = re.search(r'(\d+)\s+students', count_result)
                    if count_match:
                        st.session_state.student_count = int(count_match.group(1))
                        st.metric("Number of Students", st.session_state.student_count)
                except:
                    st.write("Could not automatically extract student count from response.")

# Footer
st.markdown("---")
st.caption("Canvas SpeedGrader Assistant powered by Gemini AI")
