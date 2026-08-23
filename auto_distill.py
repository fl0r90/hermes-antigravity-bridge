#!/usr/bin/env python3
import sys
import os
import time
import json
import sqlite3
import subprocess

STATE_DB = "/opt/stacks/hermes/data/state.db"
CHECKPOINT_FILE = "/root/.auto_distill_checkpoint"
MEMPALACE_HELPER = "/opt/stacks/hermes/data/mempalace_helper.py"

def get_last_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                return float(f.read().strip())
        except Exception:
            pass
    return time.time() - 3600 # default last 1h

def save_checkpoint(ts):
    with open(CHECKPOINT_FILE, "w") as f:
        f.write(str(ts))

def run_distillation():
    if not os.path.exists(STATE_DB):
        return
        
    last_ts = get_last_checkpoint()
    con = sqlite3.connect(STATE_DB)
    cur = con.cursor()
    cur.execute("SELECT s.source, m.role, m.content, m.timestamp FROM messages m JOIN sessions s ON m.session_id = s.id WHERE m.timestamp > ? ORDER BY m.timestamp ASC LIMIT 40", (last_ts,))
    rows = cur.fetchall()
    con.close()
    
    if len(rows) < 2:
        print("[AUTO-DISTILL] No new conversation turns since last check.")
        return
        
    max_ts = max(r[3] for r in rows)
    chat_transcript = "\n".join([f"[{r[0].upper()} {r[1]}]: {str(r[2]).strip()}" for r in rows])
    
    prompt = f"""Analizeaza urmatoarea conversatie recenta si extrage STRICT faptele concrete, dispozitivele, configuratiile tehnice, regulile sau preferintele utilizatorului (Florin) care merita retinute pe termen lung.
Daca este doar conversatie uzuala sau intrebari simple de moment (ex: vreme, glume), raspunde DOAR cu cuvantul: NONE.

Daca gasesti fapte permanente, returneaza-le ca linii separate in formatul:
[WING: infra|devices|fixes|prefs|family]: Fapt concret rezumat scurt.

Conversatie:
{chat_transcript}"""

    process = subprocess.run(
        ["/usr/local/bin/agy", "--model", "Gemini 3.7 Flash (Low)", "--disable-slash-commands", "-p", prompt, "--output-format", "json", "--dangerously-skip-permissions"],
        capture_output=True,
        text=True
    )
    
    save_checkpoint(max_ts)
    
    if process.returncode != 0:
        return
        
    raw_out = process.stdout.strip()
    try:
        data = json.loads(raw_out)
        response_text = data.get("response", "").strip()
    except Exception:
        response_text = raw_out
        
    if "NONE" in response_text.upper() and len(response_text) < 30:
        print("[AUTO-DISTILL] No new permanent facts found.")
        return
        
    print(f"[AUTO-DISTILL] Extracted facts:\n{response_text}")
    for line in response_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("[WING:"):
            continue
        try:
            wing_part, content = line.split("]:", 1)
            wing = wing_part.replace("[WING:", "").strip().lower()
            content = content.strip()
            if content and wing:
                subprocess.run(["python3", MEMPALACE_HELPER, "save", "--wing", wing, content], capture_output=True)
                print(f"[AUTO-DISTILL] Stored in [{wing}]: {content}")
        except Exception as e:
            print(f"[AUTO-DISTILL] Parse error: {e}")

if __name__ == "__main__":
    run_distillation()
