# Start here

1. Read guides/Project_Report.pdf for a short project and techniques summary.
2. Follow guides/Setup_Guide.pdf to install dependencies and run the dashboard.
3. Read guides/Understanding_Guide.pdf for the control loop and repository map.

Each guide also has an editable Markdown copy in guides.

Quick start after installing 64-bit Python 3.12, from this folder:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe dashboard/app.py --port 5000
```

Open http://127.0.0.1:5000. The supplied trained model is ready to run.
The virtual environment and installed dependencies are intentionally not bundled.
README.md contains additional implementation details. README_legacy.md,
WINDOWS_SETUP_GUIDE.md and Progress_Report.docx retain earlier project notes;
the guides above describe the current packaged version.
