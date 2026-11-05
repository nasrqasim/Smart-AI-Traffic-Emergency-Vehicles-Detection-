"""Regenerate the portable Colab notebook using only the Python standard library."""
import json
from pathlib import Path

cells = []
def markdown(text):
    cells.append(dict(cell_type="markdown", metadata={}, source=text.splitlines(True)))
def code(text):
    cells.append(dict(cell_type="code", metadata={}, execution_count=None, outputs=[], source=text.splitlines(True)))

markdown("""# Smart traffic signal: train, benchmark, export
Open this notebook using your VS Code Colab extension and connect to a Colab runtime, or use Colab in a browser.
Run `venv/Scripts/python.exe prepare_colab.py` locally first. The first cell requests that generated ZIP if the source is absent.
CPU is suitable for the small DQN MLP; GPU does not speed up the SUMO simulation automatically.
These experiments measure traffic control performance, not classification accuracy. The original checkpoints are legacy experiments.
""")
code("""from pathlib import Path
import os, zipfile, subprocess, sys
ROOT = Path('/content/traffic_fyp') if Path('/content').exists() else Path.cwd()
ROOT.mkdir(exist_ok=True)
if not (ROOT / 'train.py').exists():
    from google.colab import files
    uploaded = files.upload()  # choose notebooks/traffic_training.zip
    bundle = next(name for name in uploaded if name.endswith('.zip'))
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(ROOT)
os.chdir(ROOT)
print('Workspace:', ROOT)
""")
code("""subprocess.run([sys.executable, '-m', 'pip', 'install',
                'eclipse-sumo==1.27.1', 'libsumo==1.27.1', 'traci==1.27.1', 'sumolib==1.27.1',
                'gymnasium==1.3.0', 'stable-baselines3==2.9.0', 'torch', 'numpy'], check=True)
""")
markdown("""## Persist training artifacts
On Colab, this asks you to authorize Google Drive. Checkpoints survive runtime disconnects.
If you prefer no Drive access, set SAVE_TO_DRIVE=False and download the output before ending the session.
""")
code("""SAVE_TO_DRIVE = True
ARTIFACTS = ROOT / 'models'
if SAVE_TO_DRIVE and Path('/content').exists():
    from google.colab import drive
    drive.mount('/content/drive')
    ARTIFACTS = Path('/content/drive/MyDrive/traffic_fyp_models')
ARTIFACTS.mkdir(parents=True, exist_ok=True)
MODEL = ARTIFACTS / 'dqn_approach_v3.zip'
""")
code("""os.environ['TRAFFIC_USE_LIBSUMO'] = '1'
TIMESTEPS = 100_000  # additional decisions; increase after inspecting held-out performance
command = [sys.executable, '-u', 'train.py', '--timesteps', str(TIMESTEPS),
           '--episode-seconds', '1800', '--randomize-routes', '--seed', '0',
           '--out', str(MODEL), '--save-freq', '5000', '--device', 'cpu']
# To resume, use the checkpoint and normalization file from the SAME step:
# command += ['--resume-from', str(ARTIFACTS/'checkpoints/dqn_approach_v3_5000_steps.zip'),
#             '--resume-vecnormalize', str(ARTIFACTS/'checkpoints/dqn_approach_v3_vecnormalize_5000_steps.pkl')]
subprocess.run(command, check=True)
""")
markdown("""## Checkpoint selection using validation scenarios
This chooses the checkpoint with fewer collision/teleport events and lower queue, then higher throughput.
Final test seeds remain separate. Validation can take several minutes when there are many checkpoints.
""")
code("""subprocess.run([sys.executable, '-u', 'eval/select_model.py', '--model-dir', str(ARTIFACTS),
                '--episodes', '3', '--episode-seconds', '1800', '--seed', '9000'], check=True)
MODEL = ARTIFACTS / 'dqn_approach_best.zip'
""")
markdown("""## Held-out evaluation
Use the same scenario seeds and horizon for every controller. Seeds 10000+ are separate from training.
Review queues, completed throughput, unfinished/pending vehicles, collisions and teleports together.
A lower wait among completed trips alone can hide starvation. Keep additional untouched seeds for the final FYP report after selecting hyperparameters.
""")
code("""REPORT = ARTIFACTS / 'held_out_results_v3.json'
subprocess.run([sys.executable, '-u', 'eval/evaluate.py', '--model', str(MODEL),
                '--episodes', '10', '--episode-seconds', '1800', '--seed', '10000',
                '--randomize-routes', '--out', str(REPORT)], check=True)
import json
results = json.loads(REPORT.read_text())
for row in results:
    print({k:v for k,v in row.items() if k != 'episode_results'})
""")
code("""output = ARTIFACTS / 'traffic_model_export.zip'
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for file in ARTIFACTS.iterdir():
        if file.is_file() and file.suffix in ('.zip', '.pkl', '.json') and file != output:
            archive.write(file, file.name)
if Path('/content').exists():
    from google.colab import files
    files.download(str(output))
print('Copy the trained ZIP and metadata into your local models folder, then run run_simulation.ps1 -Controller dqn.')
""")
markdown("""## Optional: evaluate a separately labeled vision dataset
The SUMO simulation does not need YOLO or a camera. Detection mAP requires an annotated dataset with an independent test split.
This cell does not run until you supply its dataset YAML. Do not tune on the test split.
""")
code("""DATA_YAML = None  # e.g. '/content/drive/MyDrive/traffic_dataset/data.yaml'
if DATA_YAML:
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'ultralytics==8.4.157'], check=True)
    from ultralytics import YOLO
    detector = YOLO('yolov8n.pt')
    detector.train(data=DATA_YAML, epochs=100, imgsz=640, batch=16, project=str(ARTIFACTS/'vision'))
    best = YOLO(str(Path(detector.trainer.save_dir)/'weights/best.pt'))
    metrics = best.val(data=DATA_YAML, split='test')
    print(metrics.results_dict)
else:
    print('Vision training skipped: no labeled dataset supplied.')
""")

notebook = dict(cells=cells, metadata=dict(kernelspec=dict(display_name="Python 3", language="python", name="python3")), nbformat=4, nbformat_minor=5)
Path(__file__).with_name("Traffic_Training_Colab.ipynb").write_text(json.dumps(notebook, indent=2), encoding="utf-8")
