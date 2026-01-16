# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FS-ABAQUS is an Abaqus job monitoring script that monitors simulation job status and sends notifications to Feishu (Lark). It tracks jobs by monitoring `.lck` files, parses `.sta` files for progress, and logs results to Feishu Bitable (multi-dimensional spreadsheet).

## Commands

```bash
# Install dependencies
uv sync

# Run the monitor
uv run python -m src.main

# Run with activated venv (Windows)
.venv\Scripts\activate
python -m src.main

# Run tests
uv run pytest
```

## Architecture

### Core Flow
1. `AbaqusMonitor` (src/main.py) runs the main polling loop
2. `JobDetector` (src/core/job_detector.py) scans directories for `.lck` files using set operations to detect new/ended jobs
3. `StaParser` (src/core/progress_parser.py) parses Abaqus `.sta` files for progress (step, increment, total time)
4. Notifications sent via `WebhookClient` (src/feishu/webhook_client.py)
5. Records logged to `BitableClient` (src/feishu/bitable_client.py)

### Key Detection Logic (job_detector.py)
- **New jobs**: `effective_lck - previous_jobs`
- **Ended jobs**: `previous_jobs - current_lck`
- **Active jobs**: `previous_jobs & effective_lck`
- **Orphan detection**: Jobs where Abaqus process stopped but `.lck` file remains (after grace period)

### Data Model
`JobInfo` (src/models/job.py) tracks:
- Job name, work directory, computer name
- Start/end time, status (RUNNING/SUCCESS/FAILED/ABORTED)
- Progress from .sta: step, increment, total_time, step_time, inc_time
- ODB file size, Feishu record_id

### Configuration
All settings loaded from environment variables via `Settings` class (src/config/settings.py):
- `FEISHU_APP_ID`, `FEISHU_APP_SECRET` - Feishu app credentials
- `FEISHU_WEBHOOK_URL` - Webhook endpoint for notifications
- `FEISHU_BITABLE_APP_TOKEN`, `FEISHU_TABLE_ID` - Bitable configuration
- `WATCH_DIRS` - Comma-separated list of directories to monitor
- `POLL_INTERVAL` - Scan interval in seconds (default: 5)
- `PROGRESS_NOTIFY_INTERVAL` - Progress notification interval in seconds (default: 3600)
- `LCK_GRACE_PERIOD` - Grace period before marking orphan jobs (default: 60)

## Abaqus File Formats

### .sta file structure
```
Abaqus/Standard 2024   DATE 14-1月-2026 TIME 05:51:43
STEP  INC ATT SEVERE EQUIL TOTAL  TOTAL      STEP       INC OF
              DISCON ITERS ITERS  TIME/    TIME/LPF    TIME/LPF
              ITERS               FREQ
   1     1   1     6     0     6  0.100      0.100      0.1000
...
THE ANALYSIS HAS COMPLETED SUCCESSFULLY
```

### Status detection from .sta last line
- `THE ANALYSIS HAS COMPLETED SUCCESSFULLY` -> SUCCESS
- `THE ANALYSIS HAS NOT BEEN COMPLETED` -> FAILED
- `THE ANALYSIS HAS BEEN TERMINATED DUE TO AN ERROR` -> FAILED
