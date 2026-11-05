"""Build concise guides and a portable, verified source-project archive."""
from pathlib import Path
import hashlib
import json
import re
import zipfile
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "guides"
PDFS = ROOT / "output" / "pdf"
DIST = ROOT / "dist"

REPORT = r"""# Project report
## AI Smart Traffic Signal Control
This final-year project simulates an intelligent four-way traffic intersection. A trained AI controller selects which road receives green and for how long. A browser dashboard displays actual simulated vehicles, signal states, queues, waiting time and completed trips. It runs locally without cameras, traffic hardware or a GPU.

## Techniques used
- Traffic simulation: SUMO models roads, lane changes, turns and vehicle movement. TraCI connects Python to the simulator; libsumo accelerates offline training.
- Reinforcement learning: a Deep Q-Network (DQN), implemented with Stable-Baselines3 and PyTorch, learns from a negative time-averaged queue reward. Its network has two 64-unit hidden layers, experience replay, a target network and epsilon-greedy exploration. VecNormalize scales training rewards.
- State and actions: 18 inputs describe eight lane densities, the active approach, elapsed green, emergency presence and four red ages. The 16 actions combine four approaches with 10, 20, 30 or 45 seconds of green.
- Signal safeguards: one approach is green at a time. Changes use 3 seconds of yellow and 2 seconds of all red. Waiting approaches receive priority through fairness rules. Emergency vehicles within 200 m receive priority while clearance is preserved.
- Web monitoring: Flask and Socket.IO expose live state and queued controls. The current browser UI polls the state API and draws interpolated vehicle positions on an HTML canvas, with Midnight/Daylight and fullscreen views.
- Optional computer vision: a separate YOLOv8n/OpenCV demo detects vehicles in video. It uses pretrained weights and is not the sensor source for the SUMO controller.

## What has been measured
Training completed 12,000 decisions with randomized route demand. Validation selected the 10,000-decision checkpoint. Final testing used five separate, matched 900-second scenarios per controller.

| Controller | Mean queue (vehicles) | Completed-trip wait (s) | Completed trips |
|---|---:|---:|---:|
| Fixed cycle | 87.52 | 125.70 | 341.0 |
| Density adaptive | 83.89 | 114.26 | 363.8 |
| Trained DQN | 86.80 | 117.12 | 345.2 |

DQN reduced completed-trip wait by 6.8% against fixed timing, but the density-adaptive baseline performed better overall. All three controllers recorded zero collision vehicle events and zero teleports in these tests. Completed-trip wait excludes unfinished trips; these results are simulation evidence, not real-world accuracy or safety guarantees. Ten real-SUMO integration tests cover signal clearance, exclusivity, emergency priority, fairness and reset behavior.

## Current scope
The dashboard defaults to trained DQN and automatic traffic. Existing checkpoints can run immediately; retraining is optional. The Colab notebook supports longer experiments. Real-camera accuracy requires labeled test data and further detector evaluation. Hardware deployment is outside this simulation build.
"""

SETUP = r"""# Setup and run guide
## 1. Extract and open the project
Extract the ZIP completely. Open the inner AI_Smart_Traffic_Signal_FYP folder containing requirements.txt, dashboard and models. Do not run from inside the ZIP.

Use Windows 10/11 with 64-bit Python 3.12, a browser and an internet connection for the initial package installation. VS Code is optional. A GPU, camera and separate SUMO installer are not required.

## 2. Create a Python environment
Open PowerShell in the project root:
```powershell
py -3.12 --version
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```
If py is unavailable, check python --version and use python -m venv venv with a Python 3.12 installation, or use its full executable path. Avoid the Microsoft Store alias if it does not launch Python. On the original PC, an existing working venv can be used; a copied ZIP needs its own environment. Packages are not bundled in the ZIP. Automatic SUMO discovery removes the need to set SUMO_HOME manually.

## 3. Start the simulation
From the same project root:
```powershell
.\venv\Scripts\python.exe dashboard/app.py --port 5000
```
Open http://127.0.0.1:5000. Keep PowerShell open; press Ctrl+C there to stop the server. The default controller is trained DQN, using models/dqn_approach_best.zip when available. The supplied checkpoint requires no retraining.

Alternatively run .\run_simulation.ps1. The direct Python command above works if PowerShell blocks scripts. If port 5000 is occupied, add --port 5001 and open http://127.0.0.1:5001.

## 4. Use the dashboard
- Choose AI / trained DQN, density adaptive or fixed cycle from Controller.
- Pause/resume playback, change its speed, or reset the episode.
- Choose a road and vehicle type, then add a vehicle. Scheduled automatic traffic continues independently.
- Inject an ambulance or fire engine to observe emergency priority.
- Change Midnight/Daylight, junction/full-network view, or expand to fullscreen.
- Read queue, completed-trip wait, throughput and the saved benchmark table. Refresh with Ctrl+Shift+R after UI updates.

## 5. Check the installation
```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```
Ten integration tests start real SUMO instances. Run them in a separate terminal from the dashboard. Optional JavaScript syntax check, if Node.js is installed: node --check dashboard/static/app.js. Node.js is not needed to run the simulation.

## 6. Optional training and evaluation
Use a separate PowerShell terminal. Keep supplied model files backed up before retraining: these commands write new model outputs.
```powershell
$env:TRAFFIC_USE_LIBSUMO = '1'
.\venv\Scripts\python.exe train.py --timesteps 100000 `
  --episode-seconds 1800 --randomize-routes `
  --out models/dqn_approach_v3.zip
.\venv\Scripts\python.exe eval/select_model.py --episodes 3 --episode-seconds 1800 --seed 9000
.\venv\Scripts\python.exe eval/evaluate.py `
  --model models/dqn_approach_best.zip --episodes 5 `
  --episode-seconds 1800 --seed 20000 --randomize-routes `
  --out eval/new_results.json
```
Validation chooses a checkpoint; evaluation compares it against both baselines. Seeds 10000-10004 were used for the supplied test results; use fresh seeds for new final tests. Restart the dashboard to load changed weights. To return that terminal to the default TraCI backend, run Remove-Item Env:TRAFFIC_USE_LIBSUMO, or open a fresh terminal.

## 7. Optional Colab and vision
Run .\venv\Scripts\python.exe prepare_colab.py. Open notebooks/Traffic_Training_Colab.ipynb with the VS Code Colab extension or in Colab. Connect a runtime, run cells in order, and upload notebooks/traffic_training.zip when prompted. Google runtime/Drive authorization uses your own account. Copy exported model artifacts into models, then restart the dashboard.

For the separate supplied-video detector demo:
```powershell
Set-Location vision
..\venv\Scripts\python.exe detect_density.py `
  --source traffic_sample.mp4 --weights yolov8n.pt `
  --frame 60 --out demo_frame.jpg
```
The detector is optional and does not control the live SUMO simulation. Fine-tuning and mAP measurement require a labeled dataset.

## Quick troubleshooting
- Missing modules: install requirements.txt using the exact venv Python command above, not a different system Python.
- SUMO missing: reinstall eclipse-sumo==1.27.1 in the same venv. Manual SUMO_HOME setup is normally unnecessary.
- Model incompatible: use the supplied four-approach best/v3 checkpoint. Legacy dqn_traffic models use a different state/action layout.
- Connection refused: keep the server terminal running, inspect its error, and use the same port in the browser.
- Old UI: perform a hard refresh. Stop and restart Flask after template changes.
- Congested traffic: compare adaptive control, reset, or inspect the original scenario generator. This does not mean the renderer is frozen.
"""

UNDERSTANDING = r"""# Understanding the project
## The control loop
1. SUMO advances vehicle movement and exposes traffic state through TraCI.
2. TrafficSignalEnv builds an 18-value observation from lane demand, current green, elapsed green, emergency presence and red ages.
3. The selected DQN or baseline proposes an approach and green duration.
4. The environment applies fairness/emergency safeguards and yellow/all-red clearance.
5. SUMO advances, the environment records performance, and the dashboard displays actual vehicle positions and signal states.

The safety wrapper is shared by the evaluated controllers. Therefore, a DQN proposal may be overridden. In simulation, state comes from SUMO ground truth, not camera detections.

## Where to look
| Folder or file | Purpose |
|---|---|
| dashboard/app.py | Local web server, simulation worker and state/control APIs |
| dashboard/templates, dashboard/static | HTML, styling and live city renderer |
| rl_env/traffic_env.py | Gymnasium environment, observations, actions, reward and signal safeguards |
| sumo_net | Intersection geometry, routes, scenario configuration and demand generator |
| train.py | DQN learning, reward normalization and checkpoints |
| eval/baselines.py | Fixed-cycle, density-adaptive and DQN policy interfaces |
| eval/select_model.py | Checkpoint selection on validation scenarios |
| eval/evaluate.py | Matched-scenario comparison of the three controllers |
| models/dqn_approach_best.zip | Selected four-approach checkpoint loaded by the dashboard |
| models/dqn_approach_best.json | Selection metadata and validation scores |
| eval/held_out_results_v3.json | Detailed measured results for the supplied model |
| notebooks/Traffic_Training_Colab.ipynb | Portable training, selection and evaluation workflow |
| vision | Separate pretrained YOLO vehicle detection demonstration |
| tests/test_simulation.py | Real-SUMO integration tests |

## How to interpret performance
Lower queue and waiting time are desirable; higher completed throughput is desirable. Always inspect unfinished/pending vehicles, collisions and teleports too. A controller that serves only easy trips can report low completed-trip wait while leaving a large backlog. Traffic control has no single classification-style accuracy percentage.

The current DQN uses a queue-based reward; do not describe it as a fully implemented PressLight controller. Density adaptive control is a rule-based baseline, not the trained neural model. The older two-axis checkpoints and README_legacy.md describe historical experiments, not the current four-approach controller. Progress_Report.docx is the original project document; use Project_Report.pdf for the current implementation summary.

## What is in the delivery
Source code, intersection/route files, selected and historical model artifacts, sample vision assets, tests, training notebook, measured results and guides are included. Machine-specific venv, caches, logs and temporary build files are excluded. Dependencies install from requirements.txt; the ZIP is a portable source distribution, not a standalone executable.
"""

START = """# Start here

1. Read guides/Project_Report.pdf for a short project and techniques summary.
2. Follow guides/Setup_Guide.pdf to install dependencies and run the dashboard.
3. Read guides/Understanding_Guide.pdf for the control loop and repository map.

Each guide also has an editable Markdown copy in guides.

Quick start after installing 64-bit Python 3.12, from this folder:

```powershell
py -3.12 -m venv venv
.\\venv\\Scripts\\python.exe -m pip install -r requirements.txt
.\\venv\\Scripts\\python.exe dashboard/app.py --port 5000
```

Open http://127.0.0.1:5000. The supplied trained model is ready to run.
The virtual environment and installed dependencies are intentionally not bundled.
README.md contains additional implementation details. README_legacy.md,
WINDOWS_SETUP_GUIDE.md and Progress_Report.docx retain earlier project notes;
the guides above describe the current packaged version.
"""


def make_pdf(markdown, destination):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted, PageBreak
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="GuideTitle", fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=colors.HexColor("#143c3c"), spaceAfter=13))
    styles.add(ParagraphStyle(name="GuideSection", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=colors.HexColor("#17765d"), spaceBefore=12, spaceAfter=5))
    styles.add(ParagraphStyle(name="GuideBody", fontName="Helvetica", fontSize=9, leading=12.5, spaceAfter=6))
    styles.add(ParagraphStyle(name="GuideCell", fontName="Helvetica", fontSize=8, leading=10.5))
    styles.add(ParagraphStyle(name="GuideCode", fontName="Courier", fontSize=8, leading=11, backColor=colors.HexColor("#eef4f2"), borderPadding=8, spaceBefore=5, spaceAfter=9))
    story = []
    lines = markdown.strip().splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            code = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                # Keep shell tokens intact; long commands wrap at whitespace.
                import textwrap
                code += textwrap.wrap(lines[index], width=99, subsequent_indent="  ", break_long_words=False, break_on_hyphens=False) or [""]
                index += 1
            story.append(Preformatted("\n".join(code), styles["GuideCode"]))
        elif line.startswith("| "):
            rows = []
            while index < len(lines) and lines[index].startswith("|"):
                cells = [x.strip() for x in lines[index].strip("|").split("|")]
                if not all(re.fullmatch(r"[-:]+", cell) for cell in cells):
                    rows.append([Paragraph(escape(cell), styles["GuideCell"]) for cell in cells])
                index += 1
            index -= 1
            width = A4[0] - 92
            widths = [width * .36, width * .64] if len(rows[0]) == 2 else [width*.31, width*.23, width*.25, width*.21]
            table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e4efeb")),("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),.6,colors.HexColor("#7cae9c")),("LINEBELOW",(0,1),(-1,-1),.3,colors.HexColor("#d6e1dd")),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
            if len(rows[0]) == 2:
                table.setStyle(TableStyle([("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
            story += [table, Spacer(1,8)]
        elif line.startswith("# "):
            story.append(Paragraph(escape(line[2:]), styles["GuideTitle"]))
        elif line.startswith("## "):
            if destination.stem == "Setup_Guide" and line.startswith("## 6."):
                story.append(PageBreak())
            story.append(Paragraph(escape(line[3:]), styles["GuideSection"]))
        elif line.strip():
            story.append(Paragraph(escape(line), styles["GuideBody"]))
        index += 1
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#bdd3ca"))
        canvas.line(46,36,A4[0]-46,36)
        canvas.setFont("Helvetica",7)
        canvas.setFillColor(colors.HexColor("#60766f"))
        canvas.drawString(46,24,"AI SMART TRAFFIC SIGNAL FYP | Simulation edition | 22 October 2026")
        canvas.drawRightString(A4[0]-46,24,str(doc.page))
        canvas.restoreState()
    SimpleDocTemplate(str(destination), pagesize=A4, rightMargin=46,leftMargin=46,topMargin=38,bottomMargin=48,title=markdown.splitlines()[0][2:],author="AI Smart Traffic Signal FYP").build(story,onFirstPage=footer,onLaterPages=footer)


def build_archive():
    directories = ["dashboard", "eval", "models", "notebooks", "rl_env", "sumo_net", "tests", "vision", "guides", "tools"]
    files = ["START_HERE.md", "README.md", "README_legacy.md", "WINDOWS_SETUP_GUIDE.md", "requirements.txt", "train.py", "run_simulation.ps1", "run_training.ps1", "prepare_colab.py", "Progress_Report.docx", "dashboard-preview.png", "dashboard-mobile.png"]
    entries = {}
    for name in files:
        path = ROOT / name
        if path.is_file():
            entries[name] = path
    for directory in directories:
        for path in (ROOT / directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".log"):
                entries[path.relative_to(ROOT).as_posix()] = path
    for pdf in PDFS.glob("*.pdf"):
        entries["guides/" + pdf.name] = pdf
    manifest = {name: dict(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for name, path in sorted(entries.items())}
    archive_path = DIST / "AI_Smart_Traffic_Signal_FYP_Complete.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, path in sorted(entries.items()):
            archive.write(path, "AI_Smart_Traffic_Signal_FYP/" + name)
        archive.writestr("AI_Smart_Traffic_Signal_FYP/PACKAGE_MANIFEST.json", json.dumps(manifest, indent=2))
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive integrity check failed")
    print(json.dumps(dict(zip=str(archive_path), files=len(entries)+1, bytes=archive_path.stat().st_size), indent=2))


if __name__ == "__main__":
    for directory in (GUIDES, PDFS, DIST):
        directory.mkdir(parents=True, exist_ok=True)
    for name, text in [("Project_Report", REPORT), ("Setup_Guide", SETUP), ("Understanding_Guide", UNDERSTANDING)]:
        (GUIDES / (name + ".md")).write_text(text, encoding="utf-8")
        make_pdf(text, PDFS / (name + ".pdf"))
    (ROOT / "START_HERE.md").write_text(START, encoding="utf-8")
    build_archive()
