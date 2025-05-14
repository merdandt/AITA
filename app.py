import json
import traceback
from langchain_google_genai import ChatGoogleGenerativeAI
from playwright.async_api import Page
from dotenv import load_dotenv
import asyncio
import os
import sys
import re
from pydantic import BaseModel, Field
from typing import List, Optional, Dict

from colorama import init, Fore, Style
init(autoreset=True)

# Assuming these are your imports from browser_use for the authenticator
from browser_use import Agent, Controller 
from browser_use.browser.browser import Browser, BrowserConfig
# from langchain_google_genai import ChatGoogleGenerativeAI # If your Agent uses it

load_dotenv()

# --- Define colored logging functions ---
def log_info(message): print(f"{Fore.CYAN}[INFO] {message}{Style.RESET_ALL}")
def log_success(message): print(f"{Fore.GREEN}[SUCCESS] {message}{Style.RESET_ALL}")
def log_warning(message): print(f"{Fore.YELLOW}[WARNING] {message}{Style.RESET_ALL}")
def log_error(message): print(f"{Fore.RED}[ERROR] {message}{Style.RESET_ALL}")
def log_debug(message): print(f"{Fore.MAGENTA}[DEBUG] {message}{Style.RESET_ALL}")
def log_step(step_num, message): print(f"{Fore.BLUE}[STEP {step_num}] {message}{Style.RESET_ALL}")

# --- Pydantic Models ---
class DiscussionEntry(BaseModel):
    author: Optional[str] = Field(default="Author not found")
    post_date: Optional[str] = Field(default="Date not found")
    content: Optional[str] = Field(default="Content not found")

class StudentSubmissionData(BaseModel):
    student_id: Optional[str] = Field(default="ID not found")
    student_name: Optional[str] = Field(default="Name not found")
    entries: List[DiscussionEntry] = []
    status: Optional[str] = None
    error: Optional[str] = None

# --- Constants ---
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

# --- Core Extraction Function ---
async def extract_data_for_current_student(page: Page) -> StudentSubmissionData:
    log_info("Attempting to extract data for the current student...")
    current_student_id = "ID not found"
    current_student_name = "Name not found"

    try:
        # 1. Extract Student ID from URL (most reliable)
        url = page.url
        student_id_match = re.search(r'student_id=(\d+)', url)
        if student_id_match:
            current_student_id = student_id_match.group(1)
            log_success(f"Student ID from URL: {current_student_id}")
        else: # Fallback: Try to get student ID from a common dropdown element if URL fails
            try:
                dropdown_selector = "select#user_id option[selected]"
                if await page.locator(dropdown_selector).count() > 0:
                    current_student_id = await page.locator(dropdown_selector).first.get_attribute("value") or "ID not found"
                    log_success(f"Student ID from dropdown: {current_student_id}")
                else:
                    log_warning("Student ID not in URL and dropdown selector not found.")
            except Exception as e_id_page:
                log_warning(f"Could not get student ID from page elements: {e_id_page}")

        # 2. Extract Student Name
        # Prioritized selector based on your provided HTML for student name.
        name_selectors = [
            "span.ui-selectmenu-status span.ui-selectmenu-item-header", # New primary based on provided HTML
            "#speedgrader_selected_student_label",
            "span.user_name",
            "div.userName",
            "h2.sg-header-primary > span",
            "button[aria-label^='User view'] > span:not([class*='screenreader'])",
            "span[data-testid='current-student-name']"
        ]
        for selector in name_selectors:
            try:
                name_element = page.locator(selector).first
                await name_element.wait_for(state="visible", timeout=1000) # Slightly longer timeout for primary
                if await name_element.count() > 0:
                    raw_name = await name_element.text_content()
                    if raw_name:
                        current_student_name = re.split(r'\(ID:|\sAttempt\s\d|,\s*\d+\s*of', raw_name)[0].strip()
                        log_success(f"Student Name: '{current_student_name}' (using selector: {selector})")
                        break
            except Exception:
                log_debug(f"Student name selector '{selector}' not found/visible or timed out.")
        if current_student_name == "Name not found":
            log_warning("Student name could not be extracted.")

        # 3. Determine the correct frame/container for submissions
        submission_container_scope = page
        iframe_selectors = [
            'iframe[id^="discussion_topic_iframe"]',
            'iframe[title="Rich Text Area"]',
            'iframe.discussion-embed',
            'iframe#speedgrader_iframe',
            'iframe#tool_content'
        ]
        found_iframe = False
        for iframe_selector in iframe_selectors:
            iframe_loc = page.locator(iframe_selector).first
            if await iframe_loc.count() > 0 and await iframe_loc.is_visible():
                log_info(f"Detected iframe ('{iframe_selector}'). Switching scope to iframe content.")
                try:
                    frame = iframe_loc.frame_locator(':scope')
                    await frame.page().wait_for_load_state('domcontentloaded', timeout=10000)
                    await frame.locator('body').wait_for(state="visible", timeout=5000)
                    submission_container_scope = frame
                    found_iframe = True
                    log_success("Successfully focused on iframe for submissions.")
                    break
                except Exception as e_iframe:
                    log_warning(f"Could not properly access content within iframe '{iframe_selector}': {e_iframe}. Will try main page.")
                    submission_container_scope = page
                    found_iframe = False
        
        if not found_iframe:
            log_info("No specific discussion iframe detected or accessed. Assuming content is on main page or a general content iframe.")

        # 4. Locate the main content area for discussion posts
        main_content_area_locator = submission_container_scope.locator('div#content.ic-Layout-contentMain').first
        # Specific container for submissions as per your HTML
        submission_desc_locator = main_content_area_locator.locator('div.submission_description').first

        search_root_locator = submission_container_scope 

        if await submission_desc_locator.count() > 0 and await submission_desc_locator.is_visible(timeout=3000):
            log_debug("Found 'div.submission_description'. Searching for entries within it.")
            search_root_locator = submission_desc_locator
        elif await main_content_area_locator.count() > 0 and await main_content_area_locator.is_visible(timeout=3000):
            log_debug("Found 'div#content.ic-Layout-contentMain'. 'submission_description' not found or not visible. Searching for entries within main content.")
            search_root_locator = main_content_area_locator
        else:
            log_warning("'div#content.ic-Layout-contentMain' and 'div.submission_description' not found/visible. Searching directly in current scope.")

        # 5. Find all discussion entries
        # Primary selector for entries based on your HTML
        entry_selector = 'div.discussion_entry.communication_message'
        entry_selector_fallback = 'article.discussion-entry, div.comment_holder > div.comment'

        discussion_entry_locators = await search_root_locator.locator(entry_selector).all()
        if not discussion_entry_locators:
            log_debug(f"No entries with '{entry_selector}'. Trying fallback: '{entry_selector_fallback}'")
            discussion_entry_locators = await search_root_locator.locator(entry_selector_fallback).all()

        if not discussion_entry_locators:
            log_warning(f"No discussion entries found for student {current_student_id} ({current_student_name}).")
            return StudentSubmissionData(student_id=current_student_id, student_name=current_student_name, status="No discussion entries found in specified containers.")

        log_success(f"Found {len(discussion_entry_locators)} potential discussion entry elements.")
        extracted_entries: List[DiscussionEntry] = []

        for i, entry_loc in enumerate(discussion_entry_locators):
            log_step(i + 1, f"Processing entry {i + 1}/{len(discussion_entry_locators)}")
            
            # Author is the student whose page is being viewed
            author = current_student_name if current_student_name != "Name not found" else "Student name not resolved"
            if author != "Student name not resolved":
                log_debug(f"Entry {i+1}: Author='{author}' (current student)")
            else:
                log_warning(f"Entry {i+1}: Author set to default as student name was not resolved for the page.")

            post_date, content = "Date not found", "Content not found"

            # Extract Date - Prioritizing based on your HTML structure
            # Primary target: div.post_date.time_ago_date (within div.header.clearfix)
            # Fallbacks for more general cases are kept.
            date_sels = [
                'div.header div.post_date.time_ago_date', # Specific to your HTML
                '.discussion-header-content time', 
                '.posted_at time', 
                '.comment_posted_at time', 
                '.post_date', # General class
                'time' # General tag
            ]
            for sel_idx, sel in enumerate(date_sels):
                loc = entry_loc.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible(timeout=500):
                    date_val = "Date not found"
                    if sel_idx == 0: # Specific selector: div.post_date.time_ago_date
                        timestamp = await loc.get_attribute('data-timestamp')
                        title_attr = await loc.get_attribute('title')
                        text_content = await loc.text_content()
                        if timestamp: date_val = timestamp.strip()
                        elif title_attr: date_val = title_attr.strip()
                        elif text_content: date_val = text_content.strip()
                    else: # Generic time selectors
                        datetime_attr = await loc.get_attribute('datetime')
                        title_attr = await loc.get_attribute('title') # Common for time tags
                        text_content = await loc.text_content()
                        if datetime_attr: date_val = datetime_attr.strip()
                        elif title_attr: date_val = title_attr.strip()
                        elif text_content: date_val = text_content.strip()
                    
                    if date_val != "Date not found":
                        post_date = date_val
                        break
            if post_date == "Date not found": log_debug(f"Entry {i+1}: Date not found.")
            else: log_debug(f"Entry {i+1}: Date='{post_date}'")

            # Extract Content - Prioritizing based on your HTML structure
            # Primary target: div.message.user_content.enhanced (within div.content)
            content_sels = [
                'div.content div.message.user_content.enhanced', # Specific to your HTML
                '.message_body', 
                '.comment_body', 
                '.discussion_entry_content', 
                '.message-content', 
                '.entry_content',
                '.user_content' 
            ]
            for sel in content_sels:
                loc = entry_loc.locator(sel).first
                if await loc.count() > 0: 
                    content_text = await loc.text_content()
                    if content_text: 
                        content = content_text.strip()
                        break
            if content == "Content not found": log_debug(f"Entry {i+1}: Content not found.")
            else: log_debug(f"Entry {i+1}: Content length={len(content)}")
            
            # Only add entry if it has some data beyond a potentially unresolved author
            if not (author == "Student name not resolved" and post_date == "Date not found" and content == "Content not found"):
                 if content != "Content not found" or post_date != "Date not found": # Ensure at least content or date is found
                    extracted_entries.append(DiscussionEntry(author=author, post_date=post_date, content=content))
                 else:
                    log_debug(f"Entry {i+1} had no content or date, skipping.")
            else:
                log_debug(f"Entry {i+1} had no data at all (including unresolved author), skipping.")


        if not extracted_entries:
            status_msg = "Found entry elements, but no meaningful data (date/content) extracted from them."
            log_warning(status_msg)
            return StudentSubmissionData(student_id=current_student_id, student_name=current_student_name, status=status_msg)

        return StudentSubmissionData(
            student_id=current_student_id,
            student_name=current_student_name,
            entries=extracted_entries,
            status=f"Successfully extracted {len(extracted_entries)} entries."
        )
    
    except Exception as e:
        error_msg = f"CRITICAL Error during extraction for student {current_student_id} ({current_student_name}): {str(e)}"
        log_error(error_msg)
        traceback.print_exc()
        return StudentSubmissionData(
            student_id=current_student_id,
            student_name=current_student_name,
            status="Extraction failed with critical error.",
            error=str(e)
        )
        
# --- Main Execution Logic ---
browser_manager = Browser()
# controller = Controller() # Only if authenticator agent needs to register actions not defined elsewhere

sensitive_data = {
    "ms_email": os.getenv("MS_EMAIL", "A02458093@aggies.usu.edu"), # Example: get from env or default
    "ms_password": os.getenv("MS_PASSWORD", "4Future$100%!"),
}

model = ChatGoogleGenerativeAI(model='gemini-2.0-flash-lite') # Keep for authenticator

async def main():
    all_students_data: List[StudentSubmissionData] = []
    
    if not os.path.exists(OUTPUT_FOLDER_NAME):
        os.makedirs(OUTPUT_FOLDER_NAME)
        log_info(f"Created output folder: ./{OUTPUT_FOLDER_NAME}/")

    async with await browser_manager.new_context(
        # viewport={"width": 1920, "height": 1080}, # Example: set viewport
        # user_agent="Mozilla/5.0 ...", # Example: set user agent
    ) as context: # This is browser_use.BrowserContext
        
        authenticator_agent = Agent(
            task="""
            - Open the URL: https://usu.instructure.com/courses/780705/gradebook/speed_grader?assignment_id=4809230&student_id=1812493
            - Authenticate using the following credentials:
            - Enter email: ms_email
            - Enter password: ms_password
            - Wait for User to approve login on Authenticator app. Do not proceed until approved.
            - Ensure you land on the SpeedGrader page for the first student.
            """,
            llm=model, # If your agent uses an LLM
            message_context="You are a browser automation agent for login.",
            browser_context=context,
            sensitive_data=sensitive_data,
            # controller=controller, # If agent uses registered actions
        )
        try:
            await authenticator_agent.run()
            log_success("Authentication and navigation to SpeedGrader complete.")
        except Exception as auth_err:
            log_error(f"Authenticator agent failed: {auth_err}")
            traceback.print_exc()
            await browser_manager.close()
            return

        page = await context.get_current_page()
        if not page:
            log_error("Failed to get current page from browser_context after authentication.")
            await browser_manager.close()
            return

        log_info("Starting Playwright data extraction loop...")
        next_button_selector = "button#next-student-button, button[aria-label='Next Student'], button[data-testid='next-student-button']"
        # prev_button_selector = "button#prev-student-button, button[aria-label='Previous Student']" # For reference
        
        processed_student_ids_this_run = set()
        # MAX_STUDENTS = 3 # For testing, uncomment and set a small number
        # students_done_count = 0

        while True: # students_done_count < MAX_STUDENTS:
            current_url_for_check = page.url # For checking if URL changes after click
            
            log_info(f"Processing page: {current_url_for_check}")

            # Wait for page to stabilize (next button usable, network idle)
            try:
                next_button_loc_check = page.locator(next_button_selector).first
                await next_button_loc_check.wait_for(state="visible", timeout=15000)
                log_debug("Next button visible. Waiting for network idle...")
                await page.wait_for_load_state('networkidle', timeout=30000) # Increased timeout
                log_debug("Page network idle.")
            except Exception as e_wait_stable:
                log_error(f"Page did not stabilize for student at {current_url_for_check}: {e_wait_stable}")
                # Decide: break or try to extract? For now, try to extract.
                log_warning("Attempting extraction despite potential page instability.")

            student_data = await extract_data_for_current_student(page)
            
            # Check for loop conditions or inability to get ID
            if student_data.student_id == "ID not found":
                log_error("Student ID could not be determined. Breaking loop to prevent processing unknown student.")
                all_students_data.append(student_data) # Save what we have
                break
            if student_data.student_id in processed_student_ids_this_run:
                log_warning(f"Student ID {student_data.student_id} re-encountered. This could mean the page didn't advance. Breaking loop.")
                all_students_data.append(student_data) # Save what we have before breaking
                break
            
            processed_student_ids_this_run.add(student_data.student_id)
            all_students_data.append(student_data)
            # students_done_count += 1

            # Save individual student data
            s_id = sanitize_filename(student_data.student_id)
            s_name = sanitize_filename(student_data.student_name if student_data.student_name != "Name not found" else "UnknownName")
            individual_filename = os.path.join(OUTPUT_FOLDER_NAME, f"student_{s_id}_{s_name}.json")
            try:
                with open(individual_filename, "w", encoding='utf-8') as f_out:
                    json.dump(student_data.model_dump(), f_out, indent=2, ensure_ascii=False)
                log_success(f"Saved data for {s_name} ({s_id}) to {individual_filename}")
            except Exception as e_save_ind:
                log_error(f"Failed to save individual file {individual_filename}: {e_save_ind}")

            # Navigate to the next student
            next_button_locator = page.locator(next_button_selector).first
            if not await next_button_locator.is_visible(timeout=5000) or not await next_button_locator.is_enabled(timeout=5000):
                log_info("Next student button is not visible or enabled. Assuming end of student list.")
                break
            
            log_info("Clicking 'Next Student' button...")
            try:
                await next_button_locator.click(timeout=10000)
                # Wait for URL to change AND network to be idle (more robust)
                log_debug(f"Waiting for URL to change from {current_url_for_check} and network to settle...")
                await page.wait_for_function(
                    f"() => window.location.href !== '{current_url_for_check}' && window.location.href.includes('student_id=')",
                    timeout=20000 # Wait for URL to change
                )
                log_success(f"URL changed to: {page.url}")
                await page.wait_for_load_state('networkidle', timeout=30000) # Then wait for content
                log_success("Network idle after advancing to next student.")
            except Exception as e_nav:
                log_error(f"Error clicking 'Next Student' or waiting for new page: {e_nav}")
                if page.url == current_url_for_check:
                     log_error("URL did not change. Potential stuck page. Breaking loop.")
                traceback.print_exc()
                break
        
        log_success(f"Finished iterating. Processed {len(all_students_data)} student records.")

        # Save compiled report
        if all_students_data:
            compiled_report_path = os.path.join(OUTPUT_FOLDER_NAME, "ALL_students_compiled_report.json")
            try:
                data_to_save = [s.model_dump() for s in all_students_data]
                with open(compiled_report_path, "w", encoding='utf-8') as f_all:
                    json.dump(data_to_save, f_all, indent=2, ensure_ascii=False)
                log_success(f"Saved compiled report to: {compiled_report_path}")
            except Exception as e_save_all:
                log_error(f"Failed to save compiled report {compiled_report_path}: {e_save_all}")
        else:
            log_warning("No student data was collected to compile a report.")

        await browser_manager.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e_main_run:
        log_error(f"Critical error in main execution: {e_main_run}")
        traceback.print_exc()