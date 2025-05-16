import json
import os
import traceback
import time # Import for time.sleep()

from langchain_google_genai import ChatGoogleGenerativeAI
import pandas as pd
from langchain_core.messages import HumanMessage
import google.api_core.exceptions # For specific exception handling

# Assuming these are your custom imports
from logger import log_info, log_success, log_warning, log_error, log_debug, log_step
from models import StudentSubmissionData # Assuming DiscussionEntry is part of models or handled by StudentSubmissionData
from prompts import ANALIZE_TEXT # Assuming this is your prompt string
from utils import OUTPUT_FOLDER_NAME


class SubmissionAnalyzer:
    def __init__(self, llm_instance: ChatGoogleGenerativeAI, max_entries: int = 4):
        self.llm = llm_instance
        self.max_entries = max_entries
        # Safely get model name, LangChain objects might have different attribute names
        model_name = getattr(self.llm, 'model', getattr(self.llm, 'model_name', 'Unknown Model'))
        log_info(f"SubmissionAnalyzer initialized with LLM: {model_name} and max_entries: {self.max_entries}")

    def _get_summary(self, content: str) -> str:
        if not content or content == "Content not found":
            log_debug("No content provided or default content found, skipping summary.")
            return "No content to summarize"
        try:
            prompt = ANALIZE_TEXT.format(text=content)
            log_debug(f"Attempting to summarize content (first 100 chars): {content[:100]}...")

            # Use synchronous invoke
            response = self.llm.invoke([HumanMessage(content=prompt)])
            summary = response.content.strip()
            log_success(f"Summary generated (first 50 chars): {summary[:50]}...")
            return summary
        except google.api_core.exceptions.ResourceExhausted as e:
            model_name = getattr(self.llm, 'model', getattr(self.llm, 'model_name', 'Unknown Model'))
            log_error(f"RATE LIMIT HIT for model '{model_name}'. Details: {e}")
            # Extract retry delay if possible, otherwise use a default
            retry_after = 30 # Default retry delay
            if hasattr(e, 'retry') and e.retry and hasattr(e.retry, 'delay') and e.retry.delay:
                retry_after = e.retry.delay.total_seconds() if hasattr(e.retry.delay, 'total_seconds') else e.retry.delay
                log_warning(f"API suggests retry after {retry_after} seconds.")
            else: # Try to parse from message if not directly available in exception structure
                match = re.search(r'retry_delay {\s*seconds: (\d+)\s*}', str(e))
                if match:
                    retry_after = int(match.group(1))
                    log_warning(f"Parsed retry_delay from error message: {retry_after} seconds.")

            return f"Error: Rate limit hit. Suggested retry after {retry_after}s."
        except Exception as e:
            log_error(f"Error generating summary: {e}")
            # traceback.print_exc() # Optionally keep for full debugging
            return "Error: Failed to generate summary"

    def process_json_report(self, json_file_path: str, output_csv_path: str):
        log_info(f"Starting processing of JSON report: {json_file_path}")
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                all_students_data_raw = json.load(f)
            log_success(f"Successfully loaded data for {len(all_students_data_raw)} students from {json_file_path}")
        except FileNotFoundError:
            log_error(f"JSON report file not found: {json_file_path}")
            return
        except json.JSONDecodeError as e:
            log_error(f"Error decoding JSON from file {json_file_path}: {e}")
            return
        except Exception as e:
            log_error(f"An unexpected error occurred loading JSON file {json_file_path}: {e}")
            return

        if not isinstance(all_students_data_raw, list):
            log_error("JSON data is not a list as expected.")
            return

        # Determine delay based on common free tier limits (conservative)
        llm_model_name = getattr(self.llm, 'model', getattr(self.llm, 'model_name', '')).lower()
        # Default to 30 RPM (2.1 sec/request)
        # Use 60 RPM (1.1 sec/request) if gemini model detected (and not gemma)
        # Gemma models on free tier via Gemini API might be 15-30 RPM
        delay_seconds = 2.1
        if 'gemini' in llm_model_name and 'gemma' not in llm_model_name:
            delay_seconds = 1.1
        elif 'gemma' in llm_model_name: # Potentially more restrictive
            delay_seconds = 4.1 # ~15 RPM
        log_info(f"Using base summarization delay of {delay_seconds:.1f} seconds between API calls (model: {llm_model_name}).")

        processed_rows = []
        total_summaries_eligible = 0
        summaries_attempted_count = 0
        summaries_successful_count = 0

        for student_data_dict in all_students_data_raw:
            total_summaries_eligible += sum(
                1 for entry in student_data_dict.get("entries", [])[:self.max_entries]
                if entry.get("content") and entry.get("content") != "Content not found"
            )

        log_info(f"Found {total_summaries_eligible} entries eligible for summarization across all students.")

        for i, student_data_dict in enumerate(all_students_data_raw):
            # Parse with Pydantic for easier access and validation if needed
            student_data = StudentSubmissionData(**student_data_dict)
            log_step(i + 1, f"Processing student: {student_data.student_name} (ID: {student_data.student_id})")
            log_debug(f"Student {student_data.student_id} has {len(student_data.entries)} entries (according to Pydantic).")
            if not student_data.entries:
                log_debug(f"  No entries found for student {student_data.student_id} in the parsed data.")

            row = {
                "student_id": student_data.student_id,
                "student_name": student_data.student_name,
            }
            # Initialize all possible entry columns to None
            for entry_col_num in range(1, self.max_entries + 1):
                row[f"entry_{entry_col_num}_date"] = None
                row[f"entry_{entry_col_num}_content"] = None
                row[f"entry_{entry_col_num}_summary"] = None

            for j, entry in enumerate(student_data.entries):
                if j < self.max_entries:
                    entry_csv_col_idx = j + 1
                    log_debug(f"  Student {student_data.student_id}, Parsed Entry {entry_csv_col_idx}/{len(student_data.entries)}: "
                              f"post_date='{entry.post_date}', content_preview='{(entry.content or '')[:50]}...'")

                    row[f"entry_{entry_csv_col_idx}_date"] = entry.post_date
                    row[f"entry_{entry_csv_col_idx}_content"] = entry.content

                    if entry.content and entry.content != "Content not found":
                        summaries_attempted_count += 1
                        log_info(f"  Attempting summary {summaries_attempted_count}/{total_summaries_eligible} for student {student_data.student_id}, entry {entry_csv_col_idx}...")
                        summary = self._get_summary(entry.content)
                        row[f"entry_{entry_csv_col_idx}_summary"] = summary

                        if summary and not summary.startswith("Error:"):
                            summaries_successful_count +=1
                        
                        # Handle rate limit sleeps
                        current_sleep = delay_seconds
                        if "Rate limit hit" in summary:
                            # Try to parse suggested retry_after from the summary string itself
                            match = re.search(r'Suggested retry after (\d+\.?\d*)s', summary)
                            if match:
                                current_sleep = float(match.group(1)) + 0.5 # Add a small buffer
                                log_warning(f"Rate limit hit. Will sleep for parsed {current_sleep:.1f} seconds.")
                            else:
                                current_sleep = 30 # Default longer sleep if parsing fails
                                log_warning(f"Rate limit hit. Will sleep for default {current_sleep} seconds.")
                        
                        if summaries_attempted_count < total_summaries_eligible: # Don't sleep after the very last summary attempt
                            log_debug(f"  Sleeping for {current_sleep:.1f} seconds before next API call...")
                            time.sleep(current_sleep)
                    else:
                        log_warning(f"  Student {student_data.student_id}, Entry {entry_csv_col_idx}: Content NOT valid for summarization. "
                                    f"Content: '{entry.content}'")
                        row[f"entry_{entry_csv_col_idx}_summary"] = "Content unsuitable for summary"
                else: # Should not be strictly necessary if slice [:self.max_entries] is used above, but good for clarity
                    log_warning(f"Student {student_data.student_id} has more than {self.max_entries} entries. Only processing first {self.max_entries}.")
                    break
            processed_rows.append(row)

        log_success(f"Finished all summary attempts. Total eligible: {total_summaries_eligible}, Attempted: {summaries_attempted_count}, Successful: {summaries_successful_count}.")

        if not processed_rows:
            log_warning("No data processed to write to CSV.")
            return

        try:
            df = pd.DataFrame(processed_rows)
            columns = ["student_id", "student_name"]
            for k_idx in range(1, self.max_entries + 1):
                columns.extend([f"entry_{k_idx}_date", f"entry_{k_idx}_content", f"entry_{k_idx}_summary"])

            for col in columns:
                if col not in df.columns:
                    df[col] = None  # Or use "N/A" if you prefer

            df = df[columns]
            df.to_csv(output_csv_path, index=False, encoding='utf-8')
            log_success(f"Successfully wrote processed data to CSV: {output_csv_path}")
        except Exception as e:
            log_error(f"Error writing data to CSV: {e}")
            traceback.print_exc()


def run_submission_analysis(llm_instance: ChatGoogleGenerativeAI):
    """
    Function to run the submission analysis part synchronously.
    """
    log_info("Starting submission analysis process...")
    analyzer = SubmissionAnalyzer(llm_instance=llm_instance, max_entries=4)

    json_report_path = os.path.join(OUTPUT_FOLDER_NAME, "ALL_students_compiled_report.json")
    csv_output_path = os.path.join(OUTPUT_FOLDER_NAME, "analyzed_student_submissions.csv")

    if not os.path.exists(json_report_path):
        log_error(f"Cannot perform analysis: Compiled JSON report '{json_report_path}' not found.")
        log_warning("Please ensure the main data extraction script (main function) runs successfully first.")
        return

    analyzer.process_json_report(json_file_path=json_report_path, output_csv_path=csv_output_path)
    log_info("Submission analysis process finished.")
