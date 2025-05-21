# AITA: Automated Instructure Teaching Assistant

A tool for extracting and analyzing student discussion entries from Canvas using browser automation and AI-powered summarization.

## Features

- Automates login to Canvas using browser automation
- Extracts student discussion entries from SpeedGrader
- Saves data for each student in individual JSON files
- Creates a compiled report of all student data
- Generates AI summaries of student entries using Google's Gemini model
- Outputs an organized CSV with student information, entries, and summaries

## Requirements

- Python 3.9+
- Google API key (for Gemini AI)
- Canvas account credentials

## Installation Instructions

### Common Steps (All Platforms)

1. Clone this repository:
   ```bash
   git clone <repository-url>
   cd AITA
   ```

2. Create a `.env` file in the project root with the following variables:
   ```
   GOOGLE_API_KEY=your_google_api_key
   MS_EMAIL=your_canvas_email
   MS_PASSWORD=your_canvas_password
   ```

### Platform-Specific Installation

#### macOS

1. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Playwright browsers:
   ```bash
   playwright install
   ```

#### Windows

1. Create and activate a virtual environment:
   ```cmd
   python -m venv venv
   venv\Scripts\activate
   ```

2. Install dependencies:
   ```cmd
   pip install -r requirements.txt
   ```

3. Install Playwright browsers:
   ```cmd
   playwright install
   ```

#### Linux

1. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Playwright browsers:
   ```bash
   playwright install
   ```

4. Install additional dependencies required by Playwright:
   ```bash
   sudo apt update
   sudo apt install -y libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libdbus-1-3 libxcb1 libxkbcommon0 libatspi2.0-0 libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2
   ```

## Running the Application

### Script Mode

The application is run using the `app.py` script and supports command-line arguments for configuration.

**Command-Line Arguments:**

*   `--url "YOUR_CANVAS_SPEEDGRADER_URL"`
    *   **Type:** String
    *   **Required:** Yes
    *   **Description:** The full URL to the specific Canvas SpeedGrader page for the assignment you want to process. This URL typically includes a course ID, assignment ID, and may include an initial student ID.
    *   Example: `"https://usu.instructure.com/courses/123456/gradebook/speed_grader?assignment_id=789012&student_id=345678"`

*   `--email "your_email@example.com"`
    *   **Type:** String
    *   **Required:** No
    *   **Description:** Your Microsoft email address for Canvas authentication.
    *   **Fallback:** If not provided, the script will attempt to use the `MS_EMAIL` environment variable defined in your `.env` file.

*   `--password "your_password"`
    *   **Type:** String
    *   **Required:** No
    *   **Description:** Your Microsoft password for Canvas authentication.
    *   **Security Note:** Providing your password directly on the command line can be insecure as it may be stored in your shell history. For better security, consider relying on the `MS_PASSWORD` environment variable in your `.env` file.
    *   **Fallback:** If not provided, the script will attempt to use the `MS_PASSWORD` environment variable defined in your `.env` file.

**Execution Example:**

```bash
python app.py --url "https://usu.instructure.com/courses/XXXXXX/gradebook/speed_grader?assignment_id=YYYYYYY" --email "your_email@example.com" --password "your_password"
```

**Argument Precedence:**

*   For email and password, command-line arguments take precedence.
*   If `--email` is provided, it will be used regardless of the `MS_EMAIL` environment variable.
*   If `--password` is provided, it will be used regardless of the `MS_PASSWORD` environment variable.
*   If `--email` is *not* provided, the `MS_EMAIL` environment variable will be used.
*   If `--password` is *not* provided, the `MS_PASSWORD` environment variable will be used.

**Script Actions:**

The script will:
1. Authenticate to Canvas using the provided or environment variable credentials.
2. Navigate to the SpeedGrader URL specified by the `--url` argument.
3. Iterate through student submissions.
4. Extract discussion entries for each student.
5. Save data to JSON files in the `student_submissions_output` folder.
6. Generate AI summaries and create a CSV file with the results.

### Jupyter Notebook Mode

1. Start Jupyter Lab or Jupyter Notebook:
   ```bash
   jupyter lab
   # or
   jupyter notebook
   ```

2. Open the `AITA_Notebook.ipynb` file

3. Run the cells sequentially to execute the application

## Output Files

The application generates the following output files in the `student_submissions_output` folder:

- `student_[ID]_[NAME].json`: Individual JSON files for each student
- `ALL_students_compiled_report.json`: Compiled report of all student data
- `analyzed_student_submissions.csv`: CSV file with student information, entries, and AI-generated summaries

## Customization

**Target URL:**

*   The primary way to specify the target Canvas course and assignment is by using the `--url` command-line argument when running `app.py`. See the "Running the Application" section for details.
*   If using the Jupyter Notebook (`AITA_Notebook.ipynb`), you will need to update the URL directly in the relevant cell within the notebook.

**Number of Entries:**

*   To adjust the `max_entries` parameter (if you need to extract more or fewer than the default of 4 entries per student), you will need to modify it in the `SubmissionAnalyzer` class within the `submission_analyzer.py` file.

## Troubleshooting

- **Authentication Issues**: Ensure your Canvas credentials are correct in the `.env` file
- **Browser Automation**: If browser automation fails, try increasing timeouts in the `extract_data_for_current_student` function
- **AI Summarization**: Check that your Google API key is valid and has access to the Gemini model

## License

[Specify License]