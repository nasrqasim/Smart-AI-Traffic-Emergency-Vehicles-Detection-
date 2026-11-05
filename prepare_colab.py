"""Package only portable source/network files; exclude the Windows venv and private files."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
FILES = ["train.py", "requirements.txt"]
FOLDERS = ["rl_env", "sumo_net", "eval", "tests"]
if __name__ == "__main__":
    destination = ROOT / "notebooks" / "traffic_training.zip"
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, name)
        for folder in FOLDERS:
            for source in (ROOT / folder).rglob("*"):
                if source.is_file() and source.suffix in (".py", ".xml", ".sumocfg"):
                    archive.write(source, source.relative_to(ROOT))
    print(destination)
