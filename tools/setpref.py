import json, sys, os, subprocess, time, glob

pref = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Preferences")
val = sys.argv[1].lower() == "true"

subprocess.run(["taskkill", "/F", "/IM", "msedge.exe", "/T"], capture_output=True)
time.sleep(2)

with open(pref, "r", encoding="utf-8") as f:
    p = json.load(f)
p.setdefault("browser", {})
old = p["browser"].get("custom_chrome_frame")
p["browser"]["custom_chrome_frame"] = val
with open(pref, "w", encoding="utf-8") as f:
    json.dump(p, f, separators=(",", ":"), ensure_ascii=False)
print("custom_chrome_frame:", old, "->", val, flush=True)

exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
subprocess.Popen([exe, "about:blank"])
time.sleep(9)
print("launched", flush=True)
