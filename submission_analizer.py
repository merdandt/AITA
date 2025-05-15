import asyncio
import json
import os
import traceback
from langchain_google_genai import ChatGoogleGenerativeAI
import pandas as pd # For CSV creation
from langchain_core.messages import HumanMessage

from logger import *
from models import StudentSubmissionData
from utils import OUTPUT_FOLDER_NAME


class SubmissionAnalyzer:
    def __init__(self, llm_instance: ChatGoogleGenerativeAI, max_entries: int = 4):
        self.llm = llm_instance
        self.max_entries = max_entries
        log_info(f"SubmissionAnalyzer initialized with LLM: {llm_instance.model} and max_entries: {max_entries}")

    async def _get_summary(self, content: str) -> str:
        if not content or content == "Content not found":
            return "No content to summarize"
        try:
            prompt = f"Please summarize the following student discussion entry in one or two sentences:\n\n---\n{content}\n---\n\nSummary:"
            log_debug(f"Attempting to summarize content (first 100 chars): {content[:100]}...")
            # Assuming your LLM has an `ainvoke` method for async calls
            # and accepts a string or a list of messages
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            summary = response.content.strip()
            log_success(f"Summary generated (first 50 chars): {summary[:50]}...")
            return summary
        except Exception as e:
            log_error(f"Error generating summary: {e}")
            traceback.print_exc()
            return "Error generating summary"

    async def process_json_report(self, json_file_path: str, output_csv_path: str):
        log_info(f"Starting processing of JSON report: {json_file_path}")
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                all_students_data_raw = json.load(f)
            log_success(f"Successfully loaded data for {len(all_students_data_raw)} students from {json_file_path}")
        except FileNotFoundError:
            log_error(f"JSON report file not found: {json_file_path}")
            return
        except json.JSONDecodeError:
            log_error(f"Error decoding JSON from file: {json_file_path}")
            return
        except Exception as e:
            log_error(f"An unexpected error occurred loading JSON file: {e}")
            return

        # Validate data structure (optional, but good practice)
        if not isinstance(all_students_data_raw, list):
            log_error("JSON data is not a list as expected.")
            return

        all_students_data = [StudentSubmissionData(**data) for data in all_students_data_raw]

        processed_rows = []
        summary_tasks = [] # For collecting summarization tasks to run concurrently

        # First pass: Prepare data and create summarization tasks
        for i, student_data in enumerate(all_students_data): # student_data is a StudentSubmissionData instance
            log_step(i + 1, f"Processing student: {student_data.student_name} (ID: {student_data.student_id})")
            # ADD THIS:
            log_debug(f"Student {student_data.student_id} has {len(student_data.entries)} entries (according to Pydantic).")
            if not student_data.entries:
                log_debug(f"  No entries found for student {student_data.student_id} in the parsed data.")

            row = { # This initialization is fine
                "student_id": student_data.student_id,
                "student_name": student_data.student_name,
            }
            for entry_num in range(1, self.max_entries + 1):
                row[f"entry_{entry_num}_date"] = None
                row[f"entry_{entry_num}_content"] = None
                row[f"entry_{entry_num}_summary"] = None

            for j, entry in enumerate(student_data.entries): # entry is a DiscussionEntry instance
                if j < self.max_entries:
                    entry_idx = j + 1
                    # ADD/MODIFY THIS DEBUG LINE:
                    log_debug(f"  Student {student_data.student_id}, Parsed Entry {entry_idx}/{len(student_data.entries)}: "
                              f"post_date='{entry.post_date}' (Type: {type(entry.post_date)}), "
                              f"content_preview='{(entry.content or '')[:100]}...' (Type: {type(entry.content)})")

                    row[f"entry_{entry_idx}_date"] = entry.post_date
                    row[f"entry_{entry_idx}_content"] = entry.content

                    if entry.content and entry.content != "Content not found":
                        log_debug(f"    Content for entry {entry_idx} IS valid for summarization.")
                        summary_tasks.append(
                            (self._get_summary(entry.content), row, f"entry_{entry_idx}_summary")
                        )
                    else:
                        # ADD/MODIFY THIS WARNING:
                        log_warning(f"    Student {student_data.student_id}, Entry {entry_idx}: Content NOT valid for summarization. "
                                    f"Actual content value: '{entry.content}' (Type: {type(entry.content)}). "
                                    f"Is None: {entry.content is None}, Is empty string: {entry.content == ''}, Is 'Content not found': {entry.content == 'Content not found'}")
                        # Ensure a placeholder summary if no summary is generated
                        row[f"entry_{entry_idx}_summary"] = "Content unsuitable for summary" # Or leave as None
                else:
                    log_warning(f"Student {student_data.student_id} has more than {self.max_entries} entries. Skipping extras for CSV.")
                    break
            processed_rows.append(row)

        # Second pass: Execute all summarization tasks concurrently
        log_info(f"Starting generation of {len(summary_tasks)} summaries...")
        summary_results_with_refs = await asyncio.gather(*(task for task, _, _ in summary_tasks))
        log_success(f"Completed {len(summary_results_with_refs)} summary generations.")

        # Third pass: Populate summaries back into the rows
        for i, (task_tuple) in enumerate(summary_tasks):
            _, row_ref, summary_key_ref = task_tuple
            row_ref[summary_key_ref] = summary_results_with_refs[i]

        # Create DataFrame and save to CSV
        if not processed_rows:
            log_warning("No data processed to write to CSV.")
            return

        try:
            df = pd.DataFrame(processed_rows)
            # Define column order explicitly
            columns = ["student_id", "student_name"]
            for i in range(1, self.max_entries + 1):
                columns.extend([f"entry_{i}_date", f"entry_{i}_content", f"entry_{i}_summary"])
            
            # Ensure all expected columns exist, adding them if they were missed (e.g. if no student had 4 entries)
            for col in columns:
                if col not in df.columns:
                    df[col] = None # Or pd.NA or ""

            df = df[columns] # Reorder/select columns

            df.to_csv(output_csv_path, index=False, encoding='utf-8')
            log_success(f"Successfully wrote processed data to CSV: {output_csv_path}")
        except Exception as e:
            log_error(f"Error writing data to CSV: {e}")
            traceback.print_exc()
            
            
async def run_submission_analysis(llm_instance: ChatGoogleGenerativeAI):
    """
    Function to run the submission analysis part.
    """
    log_info("Starting submission analysis process...")
    analyzer = SubmissionAnalyzer(llm_instance=llm_instance, max_entries=4)

    json_report_path = os.path.join(OUTPUT_FOLDER_NAME, "ALL_students_compiled_report.json")
    csv_output_path = os.path.join(OUTPUT_FOLDER_NAME, "analyzed_student_submissions.csv")

    if not os.path.exists(json_report_path):
        log_error(f"Cannot perform analysis: Compiled JSON report '{json_report_path}' not found.")
        log_warning("Please ensure the main data extraction script (main function) runs successfully first.")
        return

    await analyzer.process_json_report(json_file_path=json_report_path, output_csv_path=csv_output_path)
    log_info("Submission analysis process finished.")
