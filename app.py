import json
import traceback
from langchain_google_genai import ChatGoogleGenerativeAI
from playwright.async_api import Page
from dotenv import load_dotenv
import asyncio
import os
import re
from typing import List, Union

from logger import *
from models import DiscussionEntry, StudentSubmissionData
from prompts import AUTH_TASK
# Assuming these are your imports from browser_use for the authenticator
from browser_use import Agent, Controller 
from browser_use.browser.browser import Browser, BrowserConfig
from playwright.async_api import Page, FrameLocator, Locator

from submission_analizer import run_submission_analysis
from utils import OUTPUT_FOLDER_NAME, sanitize_filename

# from langchain_google_genai import ChatGoogleGenerativeAI # If your Agent uses it
load_dotenv()


# --- Core Extraction Function ---
async def extract_data_for_current_student(page: Page) -> StudentSubmissionData:
    log_info(f"Attempting to extract data for student at URL: {page.url}")
    current_student_id = "ID not found"
    current_student_name = "Name not found"

    try:
        # Steps 1 & 2: Student ID and Name extraction (Using the slightly improved logic from the last iteration for robustness)
        url = page.url
        student_id_match = re.search(r'student_id=(\d+)', url)
        if student_id_match: current_student_id = student_id_match.group(1)
        
        if current_student_id != "ID not found": log_success(f"Student ID: {current_student_id}")
        else: log_warning("Student ID not found in URL.")

        name_selectors = ["span.ui-selectmenu-status span.ui-selectmenu-item-header", "#speedgrader_selected_student_label"]
        for selector in name_selectors:
            name_element_locator = page.locator(selector).first
            if await name_element_locator.count() > 0:
                try:
                    # Using is_visible with a timeout from the old robust version, but on name_element_locator directly
                    if await name_element_locator.is_visible(timeout=1000): # Short timeout for name
                        raw_name = await name_element_locator.text_content()
                        if raw_name:
                            current_student_name = re.split(r'\(ID:|\sAttempt\s\d', raw_name)[0].strip()
                            break
                    else:
                        log_debug(f"Name element for selector '{selector}' not visible quickly.")
                except Exception as e_name_vis:
                    log_debug(f"Error checking visibility for name selector '{selector}': {e_name_vis}")
            
        if current_student_name != "Name not found": log_success(f"Student Name: {current_student_name}")
        else: log_warning(f"Student Name not found for ID {current_student_id}.")

        # --- "No Submission" Check (from the last reliable iteration) ---
        no_submission_indicator_sel = "div#this_student_does_not_have_a_submission"
        no_submission_indicator = page.locator(no_submission_indicator_sel)
        
        try:
            await no_submission_indicator.wait_for(state="visible", timeout=2000)
            log_info(f"Student {current_student_id} ({current_student_name}): Confirmed no submission via indicator '{no_submission_indicator_sel}'.")
            return StudentSubmissionData(
                student_id=current_student_id,
                student_name=current_student_name,
                entries=[],
                status="This student does not have a submission for this assignment (explicit indicator)."
            )
        except Exception: 
            log_info(f"Indicator '{no_submission_indicator_sel}' not visible. Assuming a submission exists for {current_student_id} ({current_student_name}).")
        # --- End "No Submission" Check ---

        # 3. IFRAME DETECTION AND SCOPE SWITCHING (from the last reliable iteration, slightly adjusted for clarity)
        submission_scope: Union[Page, FrameLocator] = page # Default to main page
        iframe_focused = False
        log_info(f"Initial submission_scope is main page ({page.url}).")
        
        iframe_holder_locator = page.locator('div#iframe_holder')
        iframe_sel_to_check = 'iframe#speedgrader_iframe'
        
        try:
            await iframe_holder_locator.wait_for(state="visible", timeout=5000) # Check if iframe container is visible
            log_debug(f"iframe_holder 'div#iframe_holder' is visible for {current_student_id}.")
            
            iframe_locator_on_page = page.locator(iframe_sel_to_check) # Now locate the iframe
            if await iframe_locator_on_page.count() > 0:
                log_info(f"Iframe element(s) FOUND for selector '{iframe_sel_to_check}'. Using first.")
                iframe_element = iframe_locator_on_page.first
                try:
                    await iframe_element.wait_for(state="visible", timeout=5000) # Wait for iframe itself to be visible
                    current_frame_scope = iframe_element.frame_locator(':scope')
                    # Wait for body inside iframe to ensure content is loaded and visible
                    await current_frame_scope.locator('body').wait_for(state="visible", timeout=10000) 
                    
                    log_success(f"Successfully focused on iframe '{iframe_sel_to_check}'. New submission_scope is this FrameLocator.")
                    submission_scope = current_frame_scope # Switch scope to the iframe
                    iframe_focused = True
                except Exception as e_iframe_focus:
                    log_warning(f"Error focusing/interacting with iframe '{iframe_sel_to_check}': {e_iframe_focus}.")
            else:
                log_warning(f"iframe_holder was visible, but iframe '{iframe_sel_to_check}' count was 0.")
        except Exception as e_iframe_holder:
            log_warning(f"iframe_holder 'div#iframe_holder' was NOT visible or error: {e_iframe_holder}. Assuming content (if any) is on main page.")
        
        if not iframe_focused:
            log_warning(f"No specific iframe focused for {current_student_id}. Content search will be on main page.")
        
        # --- SECTION 4: LOCATE THE MAIN CONTENT AREA (FROM OLD ROBUST FUNCTION) ---
        log_info(f"Current submission_scope for content search: {type(submission_scope)}")
        main_content_container_sel = 'div#content.ic-Layout-contentMain'
        submission_description_sel = 'div.submission_description'
        search_root_locator: Union[Page, FrameLocator, Locator] = submission_scope # Default
        
        # Note: .first is a property, not a method call
        main_content_loc = submission_scope.locator(main_content_container_sel).first 
        
        # Using the old robust logic: count > 0 and is_visible(timeout=...)
        if await main_content_loc.count() > 0 and await main_content_loc.is_visible(timeout=7000):
            log_success(f"'{main_content_container_sel}' is VISIBLE in current scope.")
            submission_desc_loc = main_content_loc.locator(submission_description_sel).first
            if await submission_desc_loc.count() > 0 and await submission_desc_loc.is_visible(timeout=5000):
                log_success(f"'{submission_description_sel}' is VISIBLE. Using it as search_root_locator.")
                search_root_locator = submission_desc_loc
            else:
                log_warning(f"'{submission_description_sel}' not found/visible within '{main_content_container_sel}'. Using parent '{main_content_container_sel}' as search_root.")
                search_root_locator = main_content_loc
        else:
            log_warning(f"'{main_content_container_sel}' NOT FOUND or NOT VISIBLE in current scope ({type(submission_scope)}). Search root will be the full submission_scope.")
            # search_root_locator remains submission_scope if main_content_loc is not found/visible

        log_info(f"Final search_root_locator type: {type(search_root_locator)}")

        # --- SECTION 5: FIND ALL DISCUSSION ENTRIES (FROM OLD ROBUST FUNCTION) ---
        entry_selector = 'div.discussion_entry.communication_message'
        entry_selector_fallback = 'article.discussion-entry, div.comment_holder > div.comment'
        
        # search_root_locator can be Page, FrameLocator, or Locator. All have .locator()
        discussion_entry_locators = await search_root_locator.locator(entry_selector).all()
        if not discussion_entry_locators:
            log_debug(f"No entries found with primary selector '{entry_selector}'. Trying fallback...")
            discussion_entry_locators = await search_root_locator.locator(entry_selector_fallback).all()

        if not discussion_entry_locators:
            status_msg = f"No discussion entry elements found in the determined content area ({type(search_root_locator)}) for student {current_student_id}."
            if iframe_focused: # Add specificity if iframe was the target
                 status_msg = f"Submission iframe was focused, but no discussion entries found within it (search root: {type(search_root_locator)}) for student {current_student_id}."
            log_warning(status_msg)
            return StudentSubmissionData(student_id=current_student_id, student_name=current_student_name, entries=[], status=status_msg)

        log_success(f"Found {len(discussion_entry_locators)} potential discussion entry elements. Starting parsing loop...")
        extracted_entries: List[DiscussionEntry] = []

        # --- DETAILED PARSING LOOP (FROM OLD ROBUST FUNCTION) ---
        for i, entry_loc_item in enumerate(discussion_entry_locators): 
            log_step(i + 1, f"Processing entry element {i + 1}/{len(discussion_entry_locators)}")
            try:
                # Ensure element is attached before trying to get HTML. Short timeout.
                await entry_loc_item.wait_for(state="attached", timeout=2000) 
                entry_html_snippet_handle = await entry_loc_item.evaluate_handle('(element) => element.outerHTML.slice(0, 1200)')
                log_debug(f"Entry {i+1} HTML SNIPPET:\n{await entry_html_snippet_handle.json_value()}")
            except Exception as e_entry_html: 
                log_warning(f"Could not get HTML snippet for entry {i+1}: {e_entry_html}")

            author_entry = current_student_name if current_student_name != "Name not found" else "Student name not resolved"
            log_debug(f"Entry {i+1}: Author determined as '{author_entry}'")

            post_date_entry = "Date not found"
            content_entry = "Content not found"

            # Date Extraction (Old Robust Logic)
            date_sels_map = {
                'div.header div.post_date.time_ago_date': ['data-timestamp', 'title', 'text'],
                '.discussion-header-content time': ['datetime', 'title', 'text'],
                '.posted_at time': ['datetime', 'title', 'text'],
            }
            date_found_for_this_entry = False
            for date_sel_str_item, attr_priority_item in date_sels_map.items():
                if date_found_for_this_entry: break
                log_debug(f"Entry {i+1}: Trying date selector '{date_sel_str_item}'")
                date_element_loc = entry_loc_item.locator(date_sel_str_item).first # .first is a property
                
                if await date_element_loc.count() > 0: 
                    log_debug(f"Entry {i+1}:   FOUND element for date selector '{date_sel_str_item}'.")
                    try:
                        # No explicit wait_for here, as per old robust logic (relying on count > 0)
                        for attr_type in attr_priority_item:
                            val = None
                            if attr_type == 'text':
                                val = await date_element_loc.text_content()
                                log_debug(f"Entry {i+1}:     '{date_sel_str_item}' -> text_content(): '{val}'")
                            else:
                                val = await date_element_loc.get_attribute(attr_type)
                                log_debug(f"Entry {i+1}:     '{date_sel_str_item}' -> get_attribute('{attr_type}'): '{val}'")
                            
                            if val and val.strip():
                                post_date_entry = val.strip()
                                log_success(f"Entry {i+1}:   DATE extracted as '{post_date_entry}' using selector '{date_sel_str_item}' (from '{attr_type}').")
                                date_found_for_this_entry = True; break 
                        if date_found_for_this_entry: break 
                    except Exception as e_date_extract:
                        log_warning(f"Entry {i+1}:     Error processing date element for '{date_sel_str_item}': {e_date_extract}")
                else:
                    log_debug(f"Entry {i+1}:   NO element found for date selector '{date_sel_str_item}'.")
            if not date_found_for_this_entry: log_warning(f"Entry {i+1}: DATE extraction FAILED.")

            # Content Extraction (Old Robust Logic - using text_content())
            content_sels_list = [
                'div.content div.message.user_content.enhanced', '.message_body', '.entry_content'
            ]
            content_found_for_this_entry = False
            for content_sel_str_item in content_sels_list:
                if content_found_for_this_entry: break
                log_debug(f"Entry {i+1}: Trying content selector '{content_sel_str_item}'")
                content_element_loc = entry_loc_item.locator(content_sel_str_item).first # .first is a property

                if await content_element_loc.count() > 0:
                    log_debug(f"Entry {i+1}:   FOUND element for content selector '{content_sel_str_item}'.")
                    try:
                        # Using text_content() as per old robust logic
                        extracted_text = await content_element_loc.text_content() 
                        log_debug(f"Entry {i+1}:     Raw text (len {len(extracted_text or '')}): '{(extracted_text or '')[:200]}...'")
                        if extracted_text and extracted_text.strip():
                            content_entry = extracted_text.strip()
                            log_success(f"Entry {i+1}:   CONTENT extracted (len {len(content_entry)}) using '{content_sel_str_item}'.")
                            content_found_for_this_entry = True; break
                        else: log_debug(f"Entry {i+1}:     Content element found but text is empty/whitespace.")
                    except Exception as e_content_extract:
                        log_warning(f"Entry {i+1}:     Error processing content element for '{content_sel_str_item}': {e_content_extract}")
                else:
                    log_debug(f"Entry {i+1}:   NO element found for content selector '{content_sel_str_item}'.")
            if not content_found_for_this_entry: log_warning(f"Entry {i+1}: CONTENT extraction FAILED.")
            
            if post_date_entry != "Date not found" or content_entry != "Content not found":
                extracted_entries.append(DiscussionEntry(author=author_entry, post_date=post_date_entry, content=content_entry))
                log_success(f"Entry {i+1}: ADDED to extracted_entries list.")
            else:
                log_error(f"Entry {i+1}: SKIPPED. No valid date OR content found for student {current_student_id}.")
        # --- END OF DETAILED PARSING LOOP ---

        # Final status reporting (using old robust logic's style for this path)
        if not extracted_entries and discussion_entry_locators: 
            status_msg = f"Found {len(discussion_entry_locators)} entry elements for student {current_student_id}, but NO meaningful data could be extracted."
            log_error(status_msg)
            return StudentSubmissionData(student_id=current_student_id, student_name=current_student_name, entries=[], status=status_msg)
        
        final_status_message = f"Successfully extracted {len(extracted_entries)} entries for student {current_student_id}."
        if iframe_focused:
            final_status_message += " (from iframe)"
        else:
            final_status_message += " (from main page content)" # Simplified if not iframe

        log_success(final_status_message)
        return StudentSubmissionData(
            student_id=current_student_id, 
            student_name=current_student_name, 
            entries=extracted_entries, 
            status=final_status_message
        )

    except Exception as e:
        error_msg = f"CRITICAL Error during extraction for student {current_student_id} ({current_student_name}): {str(e)}"
        log_error(error_msg)
        traceback.print_exc()
        return StudentSubmissionData(student_id=current_student_id, student_name=current_student_name, status="Extraction failed with critical error.", error=str(e))

                
# --- Main Execution Logic ---
browser_manager = Browser()
# controller = Controller() # Only if authenticator agent needs to register actions not defined elsewhere

sensitive_data = {
    "ms_email": os.getenv("MS_EMAIL", "A02458093@aggies.usu.edu"), # Example: get from env or default
    "ms_password": os.getenv("MS_PASSWORD", "4Future$100%!"),
}

model = ChatGoogleGenerativeAI(model='gemini-2.0-flash-lite') # Keep for authenticator
model_analyzer = ChatGoogleGenerativeAI(model='gemma-3-27b-it')


async def main():
    all_students_data: List[StudentSubmissionData] = []
    
    if not os.path.exists(OUTPUT_FOLDER_NAME):
        os.makedirs(OUTPUT_FOLDER_NAME)
        log_info(f"Created output folder: ./{OUTPUT_FOLDER_NAME}/")

    async with await browser_manager.new_context(
        # viewport={"width": 1920, "height": 1080}, # Example: set viewport
        # user_agent="Mozilla/5.0 ...", # Example: set user agent
    ) as context: # This is browser_use.BrowserContext
        # 1. Authentication and Navigation
        authenticator_agent = Agent(
            task=AUTH_TASK.format(
                url="https://usu.instructure.com/courses/780705/gradebook/speed_grader?assignment_id=4809230&student_id=1812493",
                ms_email="ms_email",
                ms_password="ms_password",
            ),
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
        
        # 2. Student Data Extraction Loop 
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

        # 3. Save compiled report
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
        log_info("--- Finished Part 1: Data Extraction. Browser closed. ---")

        # Part 2: Analysis and CSV Generation
        # This part runs after the browser is closed and the JSON report is (presumably) generated.
        log_info("--- Starting Part 2: Submission Analysis and CSV Generation ---")
      
        # 4. Analyze and generate CSV
        run_submission_analysis(llm_instance=model_analyzer)
        log_info("--- Finished Part 2: Submission Analysis and CSV Generation ---")
    

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e_main_run:
        log_error(f"Critical error in main execution: {e_main_run}")
        traceback.print_exc()