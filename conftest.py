"""Put the package's parent dir on sys.path so `import knowledge_engine` works
when pytest is invoked from inside the knowledge_engine/ directory."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
