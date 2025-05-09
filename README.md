# HackerNews Browser Agent - User Guide

This Docker application scrapes Hacker News (or other websites) and outputs the results in various tabular formats.

## Quick Start

```bash
# Basic usage with API key - get 5 posts from Show HN
docker run -e OPENAI_API_KEY=sk-your-key-here \
  -v /path/on/your/machine:/app/output \
  hn-browser-agent
```

## Input Parameters

### Required Parameters:
- **OPENAI_API_KEY**: Your OpenAI API key

### Optional Parameters:
- **NUM_POSTS**: Number of posts to retrieve (default: 5)
- **OUTPUT_FORMAT**: Format for saving results (default: markdown)
- **TASK**: Custom task description
- **URL**: Specific URL to scrape (for future use)
- **USERNAME**: Login username (for future use)
- **PASSWORD**: Login password (for future use)

## Output Formats

The application supports multiple output formats:

- **markdown**: Tabular Markdown format (default)
- **excel**: Microsoft Excel spreadsheet
- **csv**: Comma-separated values
- **json**: JSON format
- **txt**: Plain text

## Usage Examples

### 1. Get 10 posts in Excel format:

```bash
docker run \
  -e OPENAI_API_KEY=sk-your-key-here \
  -e NUM_POSTS=10 \
  -e OUTPUT_FORMAT=excel \
  -v /path/on/your/machine:/app/output \
  hn-browser-agent
```

### 2. Custom task with different output format:

```bash
docker run \
  -e OPENAI_API_KEY=sk-your-key-here \
  -e TASK="Go to hackernews and find posts about AI" \
  -e OUTPUT_FORMAT=csv \
  -v /path/on/your/machine:/app/output \
  hn-browser-agent
```

### 3. Using configuration file:

Create a `config.json` file:

```json
{
  "task": "Go to hackernews show hn and give me posts",
  "api_key": "your-openai-api-key-here",
  "output_format": "markdown",
  "num_posts": 10,
  "url": "https://news.ycombinator.com",
  "username": "",
  "password": ""
}
```

Run with the config file:

```bash
docker run \
  -v /path/to/folder/with/config.json:/app/input \
  -v /path/on/your/machine:/app/output \
  hn-browser-agent
```

## Output Files

The application will generate files with timestamps in your output directory:

- `results_20250509_123045.md`: Markdown table
- `results_20250509_123045.xlsx`: Excel spreadsheet
- `results_20250509_123045.json`: JSON data
- `results_20250509_123045.csv`: CSV file
- `results_20250509_123045.txt`: Text file

## Sample Output (Markdown)

| Title | URL | Comments | Hours Since Post |
|-------|-----|----------|----------------|
| Show HN: Aberdeen – An elegant approach to reactive UIs | https://aberdeenjs.org | 56 | 3 |
| Show HN: A backend agnostic Ruby framework for building reactive desktop apps | https://codeberg.org | 3 | 1 |
| Show HN: Oliphaunt – A Native Mastodon Client for macOS | https://testflight.apple.com | 3 | 0 |
| Show HN: BlenderQ – A TUI for managing multiple Blender renders | https://github.com/kyletryon | 0 | 0 |
| Show HN: Hyvector – A fast and modern SVG editor | https://hyvector.com | 38 | 5 |

## Building the Docker Image

```bash
# Clone the repository
git clone https://github.com/yourusername/hn-browser-agent.git
cd hn-browser-agent

# Build the Docker image
docker build -t hn-browser-agent .
```

## Scheduling Automated Runs

### On Linux with Cron:

```bash
# Run daily at 8 AM and get 10 posts in Excel format
0 8 * * * docker run -e OPENAI_API_KEY=$(cat /secure/path/api_key.txt) -e NUM_POSTS=10 -e OUTPUT_FORMAT=excel -v /data/output:/app/output hn-browser-agent
```

### On Windows with Task Scheduler:

Create a batch file `run_hn_agent.bat`:
```batch
docker run -e OPENAI_API_KEY=sk-your-key-here -e NUM_POSTS=10 -e OUTPUT_FORMAT=excel -v C:\Data\Output:/app/output hn-browser-agent
```

Then add this batch file as a scheduled task.