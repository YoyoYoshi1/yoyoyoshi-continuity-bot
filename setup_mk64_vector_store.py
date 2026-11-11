import os
import sys
from pathlib import Path
from openai import OpenAI

if len(sys.argv) != 2:
    raise SystemExit("Usage: python setup_mk64_vector_store.py path/to/mk64_guide.txt")

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(f"File not found: {path}")

if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Set OPENAI_API_KEY first.")

client = OpenAI()
store = client.vector_stores.create(name="MK64 Switch — YoyoYoshi Guide")

with path.open("rb") as guide_file:
    batch = client.vector_stores.file_batches.upload_and_poll(
        vector_store_id=store.id,
        files=[guide_file],
    )

print("Vector store status:", batch.status)
print("OPENAI_MK64_VECTOR_STORE_ID=" + store.id)
