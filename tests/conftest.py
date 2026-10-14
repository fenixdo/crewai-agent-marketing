import os

os.environ.setdefault("AMS_HITL", "auto")  # chosen when main.py is imported: the scripted reviewer
os.environ["FAKE_LLM_DELAY"] = "0"
os.environ.pop("MODEL", None)
