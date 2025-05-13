import json
import traceback
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, Browser, BrowserConfig
from dotenv import load_dotenv
import asyncio
import os
import sys
from pydantic import BaseModel, Field
from typing import List, Optional

# Importing colorama for cross-platform colored terminal output
from colorama import init, Fore, Back, Style
init(autoreset=True)

# Assuming these are your imports from browser_use
from browser_use.browser.context import BrowserContext
from browser_use import ActionResult, Agent, Controller
from browser_use.browser.browser import Browser, BrowserConfig

load_dotenv()

# Define colored logging functions
def log_info(message):
    print(f"{Fore.CYAN}[INFO] {message}{Style.RESET_ALL}")

def log_success(message):
    print(f"{Fore.GREEN}[SUCCESS] {message}{Style.RESET_ALL}")

def log_warning(message):
    print(f"{Fore.YELLOW}[WARNING] {message}{Style.RESET_ALL}")

def log_error(message):
    print(f"{Fore.RED}[ERROR] {message}{Style.RESET_ALL}")

def log_debug(message):
    print(f"{Fore.MAGENTA}[DEBUG] {message}{Style.RESET_ALL}")

def log_step(step_num, message):
    print(f"{Fore.BLUE}[STEP {step_num}] {message}{Style.RESET_ALL}")

# Define a Pydantic model for student submissions
class DiscussionEntry(BaseModel):
    student_id: Optional[str] = Field(default="ID not found")
    author: Optional[str] = Field(default="Author not found")
    post_date: Optional[str] = Field(default="Date not found")
    content: Optional[str] = Field(default="Content not found")

# --- Your Controller Setup ---
# Load environment variables
load_dotenv()
# Add checks for necessary API keys (Google in this case)
if not os.getenv('GOOGLE_API_KEY'):
     raise ValueError('GOOGLE_API_KEY is not set. Please add it to your environment variables.')

controller = Controller() # Instantiate your controller

# --- Custom Action Definition ---
# Decorator to register the action
@controller.registry.action('SpeedGrader: Extract student discussion submissions')
async def extract_student_submissions(browser: BrowserContext) -> ActionResult:
    """
    Extracts discussion submissions for the student currently displayed in SpeedGrader.
    Focuses on the submission_description div inside the main content area.
    """
    log_info("Executing action: extract_student_submissions")
    page = await browser.get_current_page()
    submissions: List[DiscussionEntry] = []

    try:
        # Get the current student ID from the URL or page element
        url = page.url
        student_id = None
        # Extract student_id from URL pattern like "student_id=1812493"
        import re
        student_id_match = re.search(r'student_id=(\d+)', url)
        if student_id_match:
            student_id = student_id_match.group(1)
            log_success(f"Current student ID: {student_id}")
        else:
            # Fallback: try to get student ID from the page
            try:
                # This selector might need adjustment based on the actual page structure
                student_selector = "#speedgrader_selected_student_label"
                student_element = await page.locator(student_selector).first
                if await student_element.count() > 0:
                    student_text = await student_element.text_content()
                    # Extract just numbers if text contains ID
                    id_match = re.search(r'(\d+)', student_text)
                    student_id = id_match.group(1) if id_match else "unknown"
            except Exception as e:
                log_warning(f"Could not extract student ID from page: {e}")
                student_id = "unknown"
        
        # Wait for the content to load
        log_debug("Waiting for discussion entries to load...")
        await page.wait_for_selector('div#content.ic-Layout-contentMain', timeout=5000)
        
        # Navigate to the submission description within the main content
        main_content = await page.locator('div#content.ic-Layout-contentMain').first
        submission_desc = await main_content.locator('div.submission_description').first
        
        if await submission_desc.count() == 0:
            log_warning("Submission description div not found.")
            return ActionResult(
                extracted_content=json.dumps([]),
                include_in_memory=True,
                result_summary="Submission description not found for this student."
            )
        
        # Find all discussion entries within submission description
        # Using the exact class you specified: "discussion_entry communication_message can_be_marked_as_read read"
        entry_selector = 'div.discussion_entry.communication_message'
        discussion_entries = await submission_desc.locator(entry_selector).all()
        
        if not discussion_entries:
            log_warning("No discussion entries found for this student.")
            return ActionResult(
                extracted_content=json.dumps([{"student_id": student_id, "entries": []}]),
                include_in_memory=True,
                result_summary=f"No discussion entries found for student {student_id}."
            )
        
        log_success(f"Found {len(discussion_entries)} discussion entries.")
        
        for i, entry in enumerate(discussion_entries):
            entry_data = {"student_id": student_id}
            log_step(i+1, f"Processing entry {i+1}/{len(discussion_entries)}")
            
            # Extract Author - adjust selectors based on the actual HTML structure
            author_selector = '.discussion-header-content .author'
            author_loc = entry.locator(author_selector).first
            if await author_loc.count() > 0:
                entry_data['author'] = await author_loc.text_content()
                log_debug(f"Entry {i+1}: Author found: {entry_data['author']}")
            else:
                # Fallback selectors if the first one doesn't work
                fallback_selectors = [
                    '.comment_header .user_name',
                    '.user_name',
                    '.author_name',
                    '.message_author'
                ]
                for selector in fallback_selectors:
                    alt_loc = entry.locator(selector).first
                    if await alt_loc.count() > 0:
                        entry_data['author'] = await alt_loc.text_content()
                        log_debug(f"Entry {i+1}: Author found with fallback: {entry_data['author']}")
                        break
                if 'author' not in entry_data:
                    log_warning(f"Entry {i+1}: Author element not found")
            
            # Extract Date
            date_selector = '.discussion-header-content time'
            date_loc = entry.locator(date_selector).first
            if await date_loc.count() > 0:
                # Try to get the datetime attribute first, fallback to visible text
                date_attr = await date_loc.get_attribute('datetime') 
                if date_attr:
                    entry_data['post_date'] = date_attr
                else:
                    entry_data['post_date'] = await date_loc.text_content()
                log_debug(f"Entry {i+1}: Date found: {entry_data['post_date']}")
            else:
                # Fallback date selectors
                fallback_selectors = [
                    '.posted_at time',
                    '.comment_posted_at time',
                    '.posted_date',
                    'time'
                ]
                for selector in fallback_selectors:
                    alt_loc = entry.locator(selector).first
                    if await alt_loc.count() > 0:
                        date_attr = await alt_loc.get_attribute('datetime')
                        if date_attr:
                            entry_data['post_date'] = date_attr
                        else:
                            entry_data['post_date'] = await alt_loc.text_content()
                        log_debug(f"Entry {i+1}: Date found with fallback: {entry_data['post_date']}")
                        break
                if 'post_date' not in entry_data:
                    log_warning(f"Entry {i+1}: Date element not found")
            
            # Extract Content
            content_selector = '.message_body'
            content_loc = entry.locator(content_selector).first
            if await content_loc.count() > 0:
                content_text = await content_loc.text_content()
                entry_data['content'] = content_text.strip() if content_text else "No content"
                log_debug(f"Entry {i+1}: Content found (length: {len(entry_data['content'])} chars)")
            else:
                # Fallback content selectors
                fallback_selectors = [
                    '.comment_body',
                    '.discussion_entry_content',
                    '.message-content',
                    '.entry_content'
                ]
                for selector in fallback_selectors:
                    alt_loc = entry.locator(selector).first
                    if await alt_loc.count() > 0:
                        content_text = await alt_loc.text_content()
                        entry_data['content'] = content_text.strip() if content_text else "No content"
                        log_debug(f"Entry {i+1}: Content found with fallback (length: {len(entry_data['content'])} chars)")
                        break
                if 'content' not in entry_data:
                    log_warning(f"Entry {i+1}: Content element not found")
            
            # Create Pydantic object
            submission_entry = DiscussionEntry(**entry_data)
            submissions.append(submission_entry)
            log_success(f"Extracted entry {i+1}: Author={submission_entry.author}, Date={submission_entry.post_date}")
        
        # Convert to list of dicts for JSON serialization
        submission_dicts = [item.model_dump() for item in submissions]
        
        # Create a structured response with student ID as the key
        result = {
            "student_id": student_id,
            "entries": submission_dicts
        }
        
        json_output = json.dumps(result)
        log_success(f"Successfully extracted {len(submissions)} entries for student {student_id}.")
        
        # Save to a temp file - using student ID in filename for clarity
        with open(f"student_{student_id}_submissions.json", "w") as temp_file:
            temp_file.write(json_output)
        
        return ActionResult(
            extracted_content=json_output,
            include_in_memory=True,
            result_summary=f"Successfully extracted {len(submissions)} discussion entries for student {student_id}."
        )
    
    except Exception as e:
        log_error(f"Error during submission extraction: {str(e)}")
        # Include traceback for debugging
        import traceback
        traceback.print_exc()
        return ActionResult(
            error=f"Failed to extract submissions: {e}",
            extracted_content=json.dumps({"error": str(e), "student_id": student_id if 'student_id' in locals() else "unknown"}),
            include_in_memory=True
        )


browser = Browser()

model = ChatGoogleGenerativeAI(model='gemini-2.0-flash-lite')

sensitive_data = {
    "ms_email": "A02458093@aggies.usu.edu",
    "ms_password": "4Future$100%!",
}

async def main():
    async with await browser.new_context() as context:
        authenticator = Agent(
            task="""
            - Open the URL: https://usu.instructure.com/courses/780705/gradebook/speed_grader?assignment_id=4809230&student_id=1812493
            - Authenticate using the following credentials:
            - Enter email: ms_email
            - Enter password: ms_password
            - Click the "Log In" button.
            - Wait for the page to load.
            """,
            llm=model,
            message_context="You are a browser automation agent. Your task is to automate the login process for a web application.",
            browser_context=context,
            sensitive_data=sensitive_data,
        )
        await authenticator.run()
        log_success("Authentication and Navigation Complete. Running Grader Agent...")

        grader = Agent(
            task="""
            You are on the SpeedGrader page of a Canvas course. Your task is to:
            
            1. Extract the discussion submissions for the current student using the action "SpeedGrader: Extract student discussion submissions"
            2. After extracting data, click the "next student" button (id="next-student-button")
            3. Wait for the page to load completely
            4. Repeat steps 1-3 until you've processed all students (when the next button is disabled)
            5. Compile all the extracted data into a comprehensive report
            """,
            llm=model,
            message_context="Your goal is to extract discussion submissions for each student in the SpeedGrader interface.",
            browser_context=context,
            controller=controller,
        )
        log_success("Grader Agent Started.")
        result_json_string = await grader.run()
        log_success("Grader Agent Finished. Processing results...")

        # Process the result
        if result_json_string:
            try:
                # Parse the JSON string returned by the agent
                all_student_data = json.loads(result_json_string)
                print("\n--- Extracted Student Submissions ---")
                # Pretty print the results
                print(json.dumps(all_student_data, indent=2))
                
                # Save the complete dataset to a file
                with open("all_student_submissions.json", "w") as outfile:
                    json.dump(all_student_data, outfile, indent=2)
                log_success(f"Saved complete dataset to all_student_submissions.json")
                
                # Optional: Generate summary stats
                total_students = len(all_student_data) if isinstance(all_student_data, list) else 1
                print(f"\nProcessed {total_students} student(s)")
                
            except json.JSONDecodeError:
                log_error("Error: Agent did not return valid JSON.")
                print("Raw Output:", result_json_string)
            except Exception as e:
                log_error(f"An error occurred processing the results: {e}")
                print("Raw Output:", result_json_string)
        else:
            log_error("Grader agent did not return any result.")

    await browser.close() # Ensure browser is closed

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        log_error(f"An error occurred during execution: {e}")
        traceback.print_exc()  # Print full traceback for debugging
        