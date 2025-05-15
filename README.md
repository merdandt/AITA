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

Run the application using the Python script:

```bash
python app.py
```

The script will:
1. Authenticate to Canvas using your credentials
2. Navigate through student submissions in SpeedGrader
3. Extract discussion entries for each student
4. Save data to JSON files in the `student_submissions_output` folder
5. Generate AI summaries and create a CSV file with the results

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

To modify the application for different Canvas courses or assignments:

1. Update the URL in the `main()` function in `app.py` or in the notebook:
   ```python
   url="https://usu.instructure.com/courses/YOUR_COURSE_ID/gradebook/speed_grader?assignment_id=YOUR_ASSIGNMENT_ID&student_id=STARTING_STUDENT_ID"
   ```

2. Adjust the `max_entries` parameter in the `SubmissionAnalyzer` class if you need to extract more than 4 entries per student.

## Troubleshooting

- **Authentication Issues**: Ensure your Canvas credentials are correct in the `.env` file
- **Browser Automation**: If browser automation fails, try increasing timeouts in the `extract_data_for_current_student` function
- **AI Summarization**: Check that your Google API key is valid and has access to the Gemini model

## License

[Specify License]