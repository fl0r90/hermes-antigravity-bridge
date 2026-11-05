import asyncio
import json
import time
import sys
import os
import re
import shutil
import subprocess
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn

app = FastAPI(title="Hermes Antigravity Bridge Proxy", version="2.5.0")

AGY_BIN = os.environ.get("AGY_BIN", shutil.which("agy") or "/usr/local/bin/agy")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "Gemini 3.8 Flash (Low)")
PRO_MODEL = os.environ.get("PRO_MODEL", "Gemini 4 Argon (Medium)")
BRAIN_DIR = "/root/.gemini/antigravity-cli/brain"

# Fast mock endpoints for instant connectivity & capability probes
@app.get("/v1/models")
@app.get("/api/v1/models")
@app.get("/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "antigravity-vibe-engine",
                "object": "model",
                "created": 1700000000,
                "owned_by": "custom",
                "context_length": 256000
            },
            {
                "id": "gemini-3.8-flash",
                "object": "model",
                "created": 1700000000,
                "owned_by": "custom",
                "context_length": 256000
            },
            {
                "id": "gemini-4-argon",
                "object": "model",
                "created": 1700000000,
                "owned_by": "custom",
                "context_length": 256000
            }
        ]
    }

@app.get("/v1/models/{model_name:path}")
async def get_model(model_name: str):
    return {
        "id": model_name,
        "object": "model",
        "created": 1700000000,
        "owned_by": "custom",
        "context_length": 256000
    }

@app.get("/version")
@app.get("/api/version")
async def version():
    return {"version": "2.5.0", "status": "running"}

@app.get("/props")
@app.get("/v1/props")
@app.post("/api/show")
async def mock_ok():
    return {"status": "ok", "version": "2.5.0", "context_length": 256000}

@app.get("/api/laptop/register")
@app.post("/api/laptop/register")
async def register_laptop_ip(ip: str = None, request: Request = None):
    client_ip = request.client.host if request and request.client else None
    effective_ip = (ip or client_ip or "").strip()
    if effective_ip:
        if effective_ip.startswith("::ffff:"):
            effective_ip = effective_ip.replace("::ffff:", "")
        try:
            with open("/opt/stacks/hermes/data/laptop_current_ip.txt", "w") as f:
                f.write(effective_ip)
            print(f"[LAPTOP-REGISTER] Laptop reported active IP: {effective_ip}")
            return {"status": "ok", "registered_ip": effective_ip}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "No IP detected"}

SUBAGENT_SYSTEM_PREFIX = os.environ.get("SUBAGENT_SYSTEM_PREFIX", """You are a focused, autonomous subagent executing a delegated task inside the Hermes container.
Always write your final report/summary in Romanian (limba română), clear, technical, and direct.

INFRASTRUCTURE CHEAT-SHEET (CRITICAL):
1. Proxmox Bare-Metal Host / NAS (Intel N150 CPU, lm-sensors, dynamic-fancontrol, ZFS/HDDs, VM 100 XPEnology):
   - IP: 192.168.0.18
   - Execute commands on Proxmox via: ssh -o BatchMode=yes root@192.168.0.18 "<command>" (e.g. ssh -o BatchMode=yes root@192.168.0.18 "sensors; uptime") or python3 /opt/data/proxmox_helper.py.
   - NEVER run sensors or systemctl status dynamic-fancontrol on 192.168.0.196 (192.168.0.196 is an LXC container; hardware sensors and fancontrol are on 192.168.0.18!).
2. Servicii Host (LXC 102 - 192.168.0.196, Docker stack: radarr, sonarr, prowlarr, jellyfin, jellyseerr, dockge, adguardhome):
   - You have direct access to the Docker socket inside this container (docker ps, docker logs, docker inspect) or via ssh -o BatchMode=yes root@192.168.0.196 "<command>".
   - Stack configs are on 192.168.0.196 in /opt/stacks/.
3. Jellyseerr helper: python3 /opt/data/jellyseerr_helper.py

TOOL CALL FORMAT:
To execute a tool, emit ONLY standard text tags in this exact format (outside of <think> tags):
<tool_call>{"name":"terminal","arguments":{"command":"your bash command here"}}</tool_call>
or for reading/writing files:
<tool_call>{"name":"read_file","arguments":{"path":"/path/to/file"}}</tool_call>
<tool_call>{"name":"write_file","arguments":{"path":"/path/to/file","content":"..."}}</tool_call>
<tool_call>{"name":"patch","arguments":{"path":"/path/to/file","old_string":"...","new_string":"..."}}</tool_call>

When you have completed the task and gathered all evidence, provide your final summary and conclusion directly in plain Romanian text without any tool calls.""")

STATIC_PREFIX = os.environ.get("STATIC_SYSTEM_PREFIX", """You are Hermes Agent, a sharp, witty Romanian SysAdmin & DevOps assistant (băiat de cartier tehnic, vorbind direct cu 'boss', amuzant, dar 100% riguros pe dovezi tehnice).
Parlează românește direct, natural și fără limbaj corporatrist.

CRITICAL RUNTIME DIRECTIVE (MANDATORY):
You are the main conversational interface on Telegram. Your #1 priority is to NEVER block the Telegram conversation!
To call a tool, output ONLY standard text tags (never inside <think> tags):
<tool_call>{"name":"tool_name","arguments":{"key":"value"}}</tool_call>

REGULĂ DE AUR — DELEGARE ÎN FUNDAL (SUBAGENT-FIRST ARCHITECTURE):
1. Pentru ORICE verificare tehnică, stress test, citire de senzori, analiză de loguri, investigație Docker/Proxmox, modificare de configurație sau sarcină care necesită execuție de comenzi (ex: "fă un stress test", "vezi ce are prowlarr", "verifică proxmox", "modifică fan curve"):
   ESTE STRICT INTERZIS să rulezi terminal direct în chat-ul principal!
   EȘTI OBLIGAT să trimiți un subagent în fundal apelând delegate_task:
   <tool_call>{"name":"delegate_task","arguments":{"tasks":[{"goal":"<obiectiv complet și detaliat în română>","context":"Proxmox/NAS (senzori, fancontrol, CPU N150): ssh root@192.168.0.18. Servicii/Docker (arrstack, jellyfin, prowlarr): docker local sau ssh root@192.168.0.196."}]}}</tool_call>
2. CÂND FLORIN ÎNTREABĂ CE FACE SUBAGENTUL ("ce face?", "cât mai are?", "status agent"):
   Verifică starea subagenților activi apelând:
   <tool_call>{"name":"delegate_task","arguments":{"action":"list"}}</tool_call>
3. CÂND UN SUBAGENT DIN FUNDAL TERMINĂ ([ASYNC DELEGATION ... COMPLETE ...]):
   Primești automat rezultatul lui complet în mesaj. Prezintă-i lui Florin raportul tehnic clar, structurat și prietenos în română, fără să mai apelezi alte unelte dacă treaba e gata!
4. PENTRU CONVERSAȚIE NORMALĂ / ÎNTREBĂRI TEORETICE (ex: "salut", "are pwm mufa cu 3 fire?", "ce mai faci?"):
   Răspunde direct în text, pe loc, fără să apelezi nicio unealtă!
5. COMUNICARE CU ANTIGRAVITY (LAPTOP DEV):
   Dacă Florin cere să-i transmiți ceva lui Antigravity sau legat de codul DocAI de pe laptop:
   <tool_call>{"name":"terminal","arguments":{"command":"python3 /opt/data/laptop_bridge.py run --async \"<mesajul lui Florin>\""}}</tool_call>""")


def _clean_str(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            loaded = json.loads(s)
            if isinstance(loaded, str):
                return loaded
        except Exception:
            return s[1:-1]
    return s


def translate_native_tool(name: str, args: dict) -> dict | None:
    """Translates any native Antigravity CLI (agy) tool call into a Hermes container tool call."""
    if not isinstance(args, dict):
        args = {}
    name_low = (name or "").strip().lower()

    if name_low == "run_command":
        cmd_line = _clean_str(args.get("CommandLine") or args.get("command") or "")
        if cmd_line:
            return {"name": "terminal", "arguments": {"command": cmd_line}}

    elif name_low == "invoke_subagent":
        goal = _clean_str(args.get("Prompt") or args.get("goal") or "")
        role = _clean_str(args.get("Role") or args.get("context") or "")
        if goal:
            return {"name": "delegate_task", "arguments": {"tasks": [{"goal": goal, "context": role}]}}

    elif name_low in ("view_file", "read_file"):
        path = _clean_str(args.get("AbsolutePath") or args.get("Path") or args.get("path") or "")
        if path:
            out_args = {"path": path}
            start_line = args.get("StartLine") or args.get("offset")
            end_line = args.get("EndLine")
            if start_line:
                try:
                    out_args["offset"] = int(start_line)
                    if end_line:
                        out_args["limit"] = max(1, int(end_line) - int(start_line) + 1)
                except Exception:
                    pass
            return {"name": "read_file", "arguments": out_args}

    elif name_low in ("write_to_file", "write_file"):
        path = _clean_str(args.get("TargetFile") or args.get("Path") or args.get("path") or "")
        content = _clean_str(args.get("CodeContent") or args.get("Content") or args.get("content") or "")
        if path:
            return {"name": "write_file", "arguments": {"path": path, "content": content}}

    elif name_low in ("replace_file_content", "edit_file", "multi_replace_file_content"):
        path = _clean_str(args.get("TargetFile") or args.get("Path") or args.get("path") or "")
        old_s = _clean_str(args.get("TargetContent") or args.get("Target") or args.get("old_string") or "")
        new_s = _clean_str(args.get("ReplacementContent") or args.get("Replacement") or args.get("new_string") or "")
        if path and old_s:
            return {"name": "patch", "arguments": {"path": path, "old_string": old_s, "new_string": new_s}}

    elif name_low == "list_dir":
        dpath = _clean_str(args.get("DirectoryPath") or args.get("path") or ".")
        return {"name": "terminal", "arguments": {"command": f"ls -la {dpath}"}}

    elif name_low == "grep_search":
        q = _clean_str(args.get("Query") or args.get("pattern") or "")
        spath = _clean_str(args.get("SearchPath") or args.get("path") or ".")
        if q:
            return {"name": "search_files", "arguments": {"pattern": q, "path": spath}}

    elif name_low == "find_by_name":
        pat = _clean_str(args.get("Pattern") or args.get("pattern") or "")
        sdir = _clean_str(args.get("SearchDirectory") or args.get("path") or ".")
        if pat:
            return {"name": "search_files", "arguments": {"pattern": pat, "target": "files", "path": sdir}}

    elif name_low == "search_web":
        q = _clean_str(args.get("query") or "")
        if q:
            return {"name": "web_search", "arguments": {"query": q}}

    elif name_low == "read_url_content":
        u = _clean_str(args.get("Url") or args.get("url") or "")
        if u:
            return {"name": "web_extract", "arguments": {"urls": [u]}}

    # If the model called a tool name that is ALREADY a Hermes tool (e.g. terminal, delegate_task, patch)
    elif name_low in ("terminal", "delegate_task", "patch", "search_files", "web_search", "web_extract", "memory"):
        return {"name": name_low, "arguments": args}

    return None


def _as_text(content) -> str:
    """Normalizes OpenAI message content (str | list of parts | None) to plain text.
    Multimodal parts (e.g. Telegram photos) arrive as lists; agy -p only accepts text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict):
                if p.get("type") == "text" or "text" in p:
                    parts.append(str(p.get("text") or ""))
                elif p.get("type") in ("image_url", "image", "input_image"):
                    parts.append("[Imagine atașată — bridge-ul nu poate transmite imagini către model]")
            elif isinstance(p, str):
                parts.append(p)
        return "\n".join(x for x in parts if x)
    return str(content)


def detect_is_subagent(messages: list) -> bool:
    """Accurately detects if the request comes from a Hermes child subagent vs the main conversation."""
    for m in messages:
        if m.get("role") == "system":
            c = (m.get("content") or "").lower()
            if "you are a focused subagent working on a specific delegated task" in c:
                return True
            if "you are a focused, autonomous subagent executing a delegated task" in c:
                return True
    return False


def build_cached_prompt(messages, tools=None, max_history_messages=36):
    prompt_parts = []

    sys_msgs = [m for m in messages if m.get("role") == "system"]
    non_sys = [m for m in messages if m.get("role") != "system"]

    is_subagent = detect_is_subagent(messages)

    custom_tools_desc = ""
    if tools and isinstance(tools, list):
        filtered_tools = []
        for t in tools:
            fn = t.get("function", {})
            t_name = fn.get("name", "")
            if any(bad in t_name.lower() for bad in ("feishu", "wechat", "lark", "dingtalk")):
                continue
            filtered_tools.append({
                "name": t_name,
                "description": fn.get("description", "")[:120],
                "parameters": fn.get("parameters", {})
            })
        if filtered_tools:
            custom_tools_desc = f"\nActive Tools available: {json.dumps(filtered_tools)}"

    if is_subagent:
        base_prefix = SUBAGENT_SYSTEM_PREFIX + custom_tools_desc
        # Subagent turn limit warnings:
        num_turns = len(non_sys)
        if num_turns >= 20:
            prompt_parts.append("""[SYSTEM DIRECTIVE - HARD WRAP-UP]:
Ai executat deja multiple iterații pentru această sarcină. Dacă ai obținut datele necesare sau dacă sunt erori, NU mai apela alte unelte! Formulează direct raportul final complet și sintetizat pentru a încheia execuția.""")
        if num_turns >= 30:
            prompt_parts.append("""[SYSTEM DIRECTIVE - STRICT STOP]:
LIMITĂ MAXIMĂ DE ITERAȚII ATINSĂ. NU MAI APELA NICIO UNEALTĂ (<tool_call> ESTE STRICT INTERZIS). Sintetizează IMEDIAT raportul final cu tot ce ai investigat sau descoperit până acum!""")
    else:
        base_prefix = STATIC_PREFIX + custom_tools_desc
    prompt_parts.append(base_prefix)

    for sm in sys_msgs:
        s_content = sm.get("content", "").strip()
        if s_content and s_content not in STATIC_PREFIX and s_content not in SUBAGENT_SYSTEM_PREFIX:
            prompt_parts.append(f"[system]:\n{s_content}")

    # Filter out poisoned historical syncope/interrupt messages so the model never imitates them
    cleaned_non_sys = []
    for m in non_sys:
        c = (m.get("content") or "").strip()
        if "Boss, m-am sincopat o secunda pe conexiune" in c:
            continue
        if c == "[interrupt: no assistant output for this turn]":
            continue
        cleaned_non_sys.append(m)

    if len(cleaned_non_sys) > max_history_messages:
        recent_chat = [cleaned_non_sys[0]] + cleaned_non_sys[-(max_history_messages - 1):]
    else:
        recent_chat = cleaned_non_sys

    last_user_msg = ""
    for m in reversed(recent_chat):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "") or ""
            break

    if not is_subagent and re.search(r"\bantigravity\b", re.sub(r"antigravity-vibe-engine", "", last_user_msg, flags=re.I), re.I):
        prompt_parts.append("""[SYSTEM DIRECTIVE - MANDATORY TOOL CALL]:
Utilizatorul i se adresează lui Antigravity (sau cere să-i transmiți ceva / să verifice ceva).
ESTE STRICT INTERZIS să inventezi dialoguri!
TREBUIE să generezi IMEDIAT apelul de unealtă terminal:
<tool_call>{"name":"terminal","arguments":{"command":"python3 /opt/data/laptop_bridge.py run --async \"<mesaj_utilizator>\""}}</tool_call>
După ce primești confirmarea lansării, îi răspunzi scurt lui Florin că sarcina a fost lansată pe laptop.""")

    if not is_subagent and "[ASYNC DELEGATION" in last_user_msg:
        prompt_parts.append("""[SYSTEM DIRECTIVE - SUBAGENT REPORT READY]:
Subagentul trimis de tine în fundal a terminat! Mai jos ai rezultatul complet al muncii lui.
Prezintă-i lui Florin raportul final în limba română, clar, prietenos și cu toate cifrele/detaliile tehnice obținute.
NU apela nicio unealtă suplimentară dacă sarcina s-a finalizat cu succes (status=completed)!""")

    for m in recent_chat:
        role = m.get("role", "user")
        content = m.get("content", "") or ""

        if role == "tool":
            tool_name = m.get("name", "tool")
            if len(content) > 2500:
                content = content[:1400] + f"\n...[Truncated {len(content)-2200} chars]...\n" + content[-800:]
            prompt_parts.append(f"[Tool Response for {tool_name}]:\n{content}")
        elif role == "assistant" and "tool_calls" in m:
            t_calls = m.get("tool_calls", [])
            calls_list = []
            for tc in t_calls:
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                try:
                    parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    parsed_args = {}
                call_dict = {"name": fn_name, "arguments": parsed_args}
                calls_list.append("<tool_call>" + json.dumps(call_dict, ensure_ascii=False) + "</tool_call>")
            calls_str = "\n".join(calls_list)
            prompt_parts.append(f"[assistant]:\n{content}\n{calls_str}")
        else:
            prompt_parts.append(f"[{role}]:\n{content}")

    return "\n\n".join(prompt_parts)


def select_model(prompt: str, client_requested_model: str = "") -> tuple[str, str]:
    return DEFAULT_MODEL, "2m"


def extract_reasoning(text: str) -> tuple[str, str]:
    reasoning_parts = []
    for m in re.finditer(r"<think>\s*(.*?)\s*</think>", text, re.DOTALL):
        r = m.group(1).strip()
        if r:
            reasoning_parts.append(r)
    cleaned = re.sub(r"<think>\s*.*?\s*</think>", "", text, flags=re.DOTALL).strip()
    return "\n".join(reasoning_parts), cleaned


def extract_tool_calls(text: str) -> tuple[list, str]:
    tool_calls = []
    seen = set()
    matches = list(re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL))
    for i, m in enumerate(matches):
        raw_json = m.group(1).strip()
        try:
            call_obj = json.loads(raw_json)
            name = (call_obj.get("name") or "").strip()
            args = call_obj.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            # Reject placeholder/dummy tool calls
            if not name or name in ("tool_name", "name"):
                continue
            if name == "terminal":
                cmd_val = (args.get("command") or "").strip()
                if not cmd_val or cmd_val in ("...", "<command>", "your bash command here"):
                    continue
            # Also translate if the model wrote a native agy tool name inside <tool_call>
            if name not in ("terminal", "delegate_task", "read_file", "write_file", "patch", "search_files", "web_search", "web_extract", "memory", "session_search", "clarify", "browser_exec", "execute_code", "skill_view", "skill_manage", "skills_list", "tool_search", "tool_describe"):
                translated = translate_native_tool(name, args)
                if translated:
                    name = translated["name"]
                    args = translated["arguments"]
                elif name == "patch_file":
                    name = "patch"
            args_str = json.dumps(args, ensure_ascii=False)
            key = (name, args_str)
            if key in seen:
                continue
            seen.add(key)
            tool_calls.append({
                "id": f"call_{int(time.time() * 1000)}_{i}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": args_str
                }
            })
        except Exception:
            pass

    cleaned_text = re.sub(r"<tool_call>\s*.*?\s*</tool_call>", "", text, flags=re.DOTALL).strip()
    return tool_calls, cleaned_text


def _read_first_turn_from_transcript(conv_id: str, fallback_step_tools: list) -> str:
    """Reads step_index 1 (PLANNER_RESPONSE) from transcript_full.jsonl and translates native tool calls."""
    parts = []
    translated_calls = []

    if conv_id:
        t_path = os.path.join(BRAIN_DIR, conv_id, ".system_generated", "logs", "transcript_full.jsonl")
        if not os.path.exists(t_path):
            t_path = os.path.join(BRAIN_DIR, conv_id, ".system_generated", "logs", "transcript.jsonl")
        if os.path.exists(t_path):
            try:
                with open(t_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        d = json.loads(line)
                        if d.get("step_index") == 1 and d.get("type") == "PLANNER_RESPONSE":
                            thinking = (d.get("thinking") or "").strip()
                            content = (d.get("content") or "").strip()
                            if thinking:
                                parts.append(f"<think>{thinking}</think>")
                            if content:
                                parts.append(content)
                            for tc in d.get("tool_calls") or []:
                                t_name = tc.get("name", "")
                                t_args = tc.get("args") or tc.get("arguments") or {}
                                tr = translate_native_tool(t_name, t_args)
                                if tr:
                                    translated_calls.append(tr)
                            break
            except Exception as e:
                print(f"[TRANSCRIPT-READ-ERR] {conv_id}: {e}")

    if not translated_calls and fallback_step_tools:
        for st in fallback_step_tools:
            tr = translate_native_tool(st.get("name", ""), st.get("parameters", {}))
            if tr:
                translated_calls.append(tr)

    for tr in translated_calls:
        parts.append("<tool_call>" + json.dumps(tr, ensure_ascii=False) + "</tool_call>")

    return "\n".join(parts).strip()


async def run_agy_prompt(prompt: str, model_name: str, timeout_str: str = "2m") -> tuple[str, bool]:
    """Runs a single LLM turn via agy WITHOUT --dangerously-skip-permissions.
    Never executes tools on the host; intercepts any native tool call in ~3.5s and translates it for Hermes."""
    # Prompt is fed via stdin (stream-json) instead of argv: Linux caps a single argv
    # string at 128KB (MAX_ARG_STRLEN), which caused "[Errno 7] Argument list too long".
    cmd = [
        AGY_BIN,
        f"--model={model_name}",
        f"--print-timeout={timeout_str}",
        "--disable-slash-commands",
        "--print=",
        "--input-format=stream-json",
        "--output-format=stream-json"
    ]
    os.makedirs("/tmp/agy_scratch", exist_ok=True)

    process = None
    conv_id = None
    captured_step_tools = []

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/tmp/agy_scratch",
            limit=16 * 1024 * 1024
        )
        payload = json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n"
        process.stdin.write(payload.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

        full_response = ""
        success = False
        loop_timeout = 45.0
        start_wait = time.time()

        while time.time() - start_wait < loop_timeout:
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=10.0)
            except asyncio.TimeoutError:
                if process.returncode is not None:
                    break
                continue

            if not line:
                break

            line_str = line.decode("utf-8", errors="replace").strip()
            if not line_str or not line_str.startswith("{"):
                continue

            try:
                data = json.loads(line_str)
                ev = data.get("event")
                if ev == "init":
                    conv_id = data.get("conversation_id")
                elif ev == "step_update":
                    su = data.get("step_update", {})
                    if not conv_id:
                        conv_id = su.get("conversation_id")
                    if su.get("step_type") == "tool" and su.get("state") == "ACTIVE":
                        t_info = su.get("tool_info") or {}
                        captured_step_tools.append({
                            "name": t_info.get("name") or su.get("tool_name") or "",
                            "parameters": t_info.get("parameters") or {}
                        })
                        # Wait 120ms for transcript flush and any parallel tool step_updates, then break immediately!
                        await asyncio.sleep(0.12)
                        break
                elif ev == "result":
                    res = data.get("result", {})
                    if not conv_id:
                        conv_id = res.get("conversation_id")
                    status = res.get("status", "")
                    if status == "SUCCESS":
                        full_response = (res.get("response") or "").strip()
                        success = bool(full_response)
                    break
            except Exception:
                pass

        if captured_step_tools or not full_response:
            recovered = _read_first_turn_from_transcript(conv_id, captured_step_tools)
            if recovered:
                full_response = recovered
                success = True
                print(f"[NATIVE-TOOL-INTERCEPT] Translated native tool call(s) from conv {conv_id} in {round(time.time() - start_wait, 2)}s")

        return full_response, success
    except Exception as e:
        print(f"[RUN-AGY-ERROR] {e}")
        return "", False
    finally:
        if process:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
        if conv_id:
            try:
                shutil.rmtree(os.path.join(BRAIN_DIR, conv_id), ignore_errors=True)
            except Exception:
                pass


def extract_async_delegation_fallback(text: str) -> str:
    """Extracts the subagent summary directly from an [ASYNC DELEGATION ...] notification if LLM fails."""
    m = re.search(r"--- [✓⚠✗] TASK .*?---\n(.*?)(?:\nFull live transcript:|\Z)", text, re.DOTALL)
    if m and m.group(1).strip():
        return f"📋 **Raport Subagent:**\n\n{m.group(1).strip()}"
    m2 = re.search(r"--- RESULT ---\n(.*?)(?:\nFull live transcript:|\Z)", text, re.DOTALL)
    if m2 and m2.group(1).strip():
        return f"📋 **Raport Subagent:**\n\n{m2.group(1).strip()}"
    return "Subagentul din fundal a terminat execuția. Dă-mi un semn dacă vrei detalii suplimentare!"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    t_start = time.time()
    data = await request.json()
    messages = data.get("messages", []) or []
    # Normalize multimodal/list content to text once, so every downstream .strip()/regex is safe
    for m in messages:
        if isinstance(m, dict) and not isinstance(m.get("content"), str):
            m["content"] = _as_text(m.get("content"))
    tools = data.get("tools", None)
    stream = data.get("stream", False)
    client_model = data.get("model", "")

    is_subagent = detect_is_subagent(messages)
    print(f"[DEBUG-INCOMING] is_subagent={is_subagent} | msgs={len(messages)} | tools={len(tools) if tools else 0}")

    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "") or ""
            break

    last_msg = messages[-1] if messages else {}
    is_tool_followup = (last_msg.get("role") == "tool")

    is_internal_system_event = any(marker in last_user_msg for marker in [
        "[ASYNC DELEGATION",
        "[INTERNAL NOTIFICATION",
        "A background fan-out unit you dispatched earlier",
        "A background subagent you dispatched earlier"
    ])

    routed_reply = None

    # --- GUARDRAIL B: INSTANT TURN RELEASE AFTER BACKGROUND SUBAGENT DISPATCH ---
    if not is_subagent and is_tool_followup:
        last_tool_content = (last_msg.get("content") or "").strip()
        if '"status": "dispatched"' in last_tool_content or '"status":"dispatched"' in last_tool_content:
            try:
                td = json.loads(last_tool_content)
                deleg_id = td.get("delegation_id", "subagent")
            except Exception:
                deleg_id = "subagent"
            routed_reply = (
                f"🚀 L-am trimis pe subagentul `{deleg_id}` în fundal să rezolve treaba!\n\n"
                f"Eu rămân activ aici la taclale — poți să-mi scrii orice între timp, iar cum termină băiatul în fundal îți livrez raportul complet!"
            )
            print(f"[FAST-DISPATCH-ACK] Subagent {deleg_id} dispatched! Releasing main turn in 0.01s.")

    # --- FAST AUTO-ROUTER (INTERCEPT QUICK COMMANDS & LAPTOP STEERING) ---
    if not routed_reply and not is_subagent and not is_tool_followup and not is_internal_system_event and last_user_msg:
        clean_prompt = last_user_msg.strip()
        # Strip Hermes gateway origin metadata header if present
        if "Do not guess a reply destination when these fields are insufficient." in clean_prompt:
            clean_prompt = clean_prompt.split("Do not guess a reply destination when these fields are insufficient.", 1)[-1].strip()

        # Case 0: /cancel /stop /opreste-te
        if re.search(r"^\s*/(cancel|stop)\b|\b(opreste(-te)?|anuleaza)\s+(tot|task|totul|laptop)\b", clean_prompt, re.I):
            print("[ROUTER] Cancel requested. Stopping background jobs...")
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    ["python3", "/opt/stacks/hermes/data/laptop_bridge.py", "cancel"],
                    capture_output=True, text=True, timeout=15
                )
                routed_reply = f"🛑 {proc.stdout.strip() or 'Am anulat sarcinile active de pe laptop!'}"
            except Exception as e:
                routed_reply = f"❌ Eroare la cancel: {e}"

        # Case 1: Side-channel / steering note (/btw <nota>, /nota <nota>)
        elif re.match(r"^\s*/(btw|nota|side)\b", clean_prompt, re.I):
            note = re.sub(r"^\s*/(btw|nota|side)\s*", "", clean_prompt, flags=re.I).strip()
            print(f"[ROUTER] Adding /btw note: {note[:60]}...")
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    ["python3", "/opt/stacks/hermes/data/laptop_bridge.py", "btw", note],
                    capture_output=True, text=True, timeout=15
                )
                routed_reply = f"⚡ [BTW / Notă Înregistrată]: Am injectat-o direct în contextul activ de pe laptop:\n> *{note}*"
            except Exception as e:
                routed_reply = f"❌ Eroare la trimitere /btw: {e}"

        # Case 2: Git Diff / Patch from Telegram
        elif "diff --git " in clean_prompt or ("--- a/" in clean_prompt and "+++ b/" in clean_prompt):
            print("[ROUTER] Detected incoming git diff. Dispatching to laptop_bridge patch...")
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    ["python3", "/opt/stacks/hermes/data/laptop_bridge.py", "patch", clean_prompt],
                    capture_output=True, text=True, timeout=120
                )
                routed_reply = proc.stdout.strip() or proc.stderr.strip()
            except Exception as e:
                routed_reply = f"❌ Eroare la aplicare patch pe laptop: {e}"

        # Case 3: Laptop Status Check (/status or questions about laptop status)
        elif re.search(r"^\s*/status\b|\b(status\s+laptop|laptop\s+status|ce\s+face\s+laptop)\b", clean_prompt, re.I):
            print("[ROUTER] Checking laptop status...")
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    ["python3", "/opt/stacks/hermes/data/laptop_bridge.py", "status"],
                    capture_output=True, text=True, timeout=20
                )
                routed_reply = proc.stdout.strip() or proc.stderr.strip()
            except Exception as e:
                routed_reply = f"❌ Eroare la status laptop: {e}"

        # Case 4: Antigravity Direct Addressing / Question / Task
        elif re.search(r"\b(antigravity|anti-gravity|antigrav|pe\s+laptop)\b", re.sub(r"antigravity-vibe-engine", "", clean_prompt, flags=re.I), re.I):
            print(f"[ROUTER] Routing prompt to Antigravity on laptop: {clean_prompt[:60]}...")
            is_heavy = bool(re.search(r"\b(fa|repara|fix|construieste|implementeaza|modifica|compileaza|scrie|creeaza|ruleaza|start)\b", clean_prompt, re.I))
            cmd_args = ["python3", "/opt/stacks/hermes/data/laptop_bridge.py", "run"]
            if is_heavy:
                cmd_args.append("--async")
            cmd_args.append(clean_prompt)
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    cmd_args,
                    capture_output=True, text=True, timeout=60
                )
                out = proc.stdout.strip()
                if out:
                    routed_reply = f"⚡ Răspuns de la Laptop Bridge:\n\n{out}"
                else:
                    routed_reply = f"⚠️ Laptop Bridge nu a întors text:\n{proc.stderr.strip()}"
            except Exception as e:
                routed_reply = f"❌ Eroare la comunicare cu laptop: {e}"

    if routed_reply:
        chunk_id = f"chatcmpl-{int(time.time())}"
        print(f"[ROUTER-DISPATCH] Success! Returned {len(routed_reply)} chars in {round(time.time()-t_start, 2)}s.")
        if stream:
            async def fast_stream():
                yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': routed_reply}}]})}\n\n"
                yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(fast_stream(), media_type="text/event-stream")
        else:
            return JSONResponse({
                "id": chunk_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "antigravity-vibe-engine",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": routed_reply},
                    "finish_reason": "stop"
                }]
            })

    prompt = build_cached_prompt(messages, tools=tools)
    chosen_model, initial_timeout = select_model(prompt, client_requested_model=client_model)

    def postprocess_output(full_text: str) -> tuple[str, str, list]:
        """Extracts reasoning FIRST, then tool calls, and applies Main-Chat Background Delegation Guardrails."""
        if not full_text.strip():
            if is_internal_system_event and "[ASYNC DELEGATION" in last_user_msg:
                return "", extract_async_delegation_fallback(last_user_msg), []
            return "", "Spune-mi exact ce vrei să verificăm și trimit imediat un subagent în fundal!", []

        reasoning, text_no_think = extract_reasoning(full_text)
        tool_calls, clean_text = extract_tool_calls(text_no_think)

        # If this is an [ASYNC DELEGATION COMPLETE] callback, deliver the report directly without spawning new tools
        if not is_subagent and is_internal_system_event and "[ASYNC DELEGATION" in last_user_msg and "status=completed" in last_user_msg:
            tool_calls = []
            if not clean_text.strip():
                clean_text = extract_async_delegation_fallback(last_user_msg)

        # --- GUARDRAIL S: SUBAGENT HARD ITERATION LIMIT (PREVENT 500-MESSAGE LOOPS) ---
        if is_subagent and len(messages) >= 32 and tool_calls:
            print(f"[SUBAGENT-GUARDRAIL] Subagent exceeded iteration limit ({len(messages)} messages). Suppressing tool calls to force completion!")
            tool_calls = []
            if not clean_text.strip():
                last_tool_res = ""
                for m in reversed(messages):
                    if m.get("role") == "tool":
                        last_tool_res = (m.get("content") or "")[:600]
                        break
                clean_text = f"Am atins limita maximă de siguranță a pașilor pentru această sarcină. Raport parțial bazat pe ultimele verificări:\n\n{last_tool_res}\n\nInvestigația a fost încheiată în siguranță."

        # --- GUARDRAIL A: AUTO-UPGRADE INLINE TOOL CALLS ON MAIN CHAT TO BACKGROUND DELEGATE_TASK ---
        if not is_subagent and not is_tool_followup and not is_internal_system_event and tool_calls:
            has_delegate = any(tc.get("function", {}).get("name") == "delegate_task" for tc in tool_calls)
            if not has_delegate:
                clean_user_goal = last_user_msg.strip()
                if "Do not guess a reply destination when these fields are insufficient." in clean_user_goal:
                    clean_user_goal = clean_user_goal.split("Do not guess a reply destination when these fields are insufficient.", 1)[-1].strip()

                clean_lower = clean_user_goal.lower()

                # Filter 1: Ignore internal Hermes skill/library auto-updates (never spawn subagents for them!)
                is_internal_skill = any(marker in clean_lower for marker in [
                    "update the skill library",
                    "review the conversation above",
                    "evaluate your performance",
                    "skill library",
                    "meta-evaluation"
                ])

                # Filter 2: Stop / cancel agents request -> do NOT spawn a new subagent to stop subagents!
                is_stop_agents = bool(re.search(
                    r"\b(opre[sș]te|stop|anuleaz[aă]|kill)\b.*\b(agen[tț]|subagen[tț]|task|totul|to[tț]i|sclav)\b",
                    clean_lower,
                    re.I
                ))

                # Filter 3: Status queries about active agents -> query list, don't spawn a new subagent!
                is_status_query = bool(re.search(
                    r"\b(ce face|ce a f[aă]cut|c[aâ]t mai are|a terminat|mai are|lucreaz[aă]|status\s+agent|sclavul)\b",
                    clean_lower,
                    re.I
                ))

                if is_internal_skill:
                    print("[GUARDRAIL-SKILL] Suppressing background delegation for internal Hermes skill update.")
                    tool_calls = []
                    if not clean_text:
                        clean_text = "Internal review complete."
                elif is_stop_agents:
                    print("[GUARDRAIL-STOP] User requested agent stop. Converting to delegate_task(action='stop')!")
                    tool_calls = [{
                        "id": f"call_{int(time.time() * 1000)}_0",
                        "type": "function",
                        "function": {
                            "name": "delegate_task",
                            "arguments": json.dumps({"action": "stop"}, ensure_ascii=False)
                        }
                    }]
                elif is_status_query:
                    print("[GUARDRAIL-STATUS] User asked agent status. Converting to delegate_task(action='list')!")
                    tool_calls = [{
                        "id": f"call_{int(time.time() * 1000)}_0",
                        "type": "function",
                        "function": {
                            "name": "delegate_task",
                            "arguments": json.dumps({"action": "list"}, ensure_ascii=False)
                        }
                    }]
                else:
                    # Legitimate heavy task request -> auto-upgrade inline tools to delegate_task
                    inline_heavy = [
                        tc for tc in tool_calls
                        if tc.get("function", {}).get("name") in ("terminal", "read_file", "write_file", "patch", "search_files", "execute_code", "web_search", "web_extract")
                        and "laptop_bridge.py" not in (tc.get("function", {}).get("arguments") or "")
                    ]
                    if inline_heavy:
                        hints = []
                        for tc in inline_heavy:
                            fn = tc.get("function", {})
                            hints.append(f"{fn.get('name')}: {fn.get('arguments')}")
                        deleg_payload = {
                            "tasks": [{
                                "goal": f"Rezolvă complet cerința lui Florin și întoarce un raport detaliat în română: {clean_user_goal}",
                                "context": (
                                    "Infrastructură: "
                                    "1) Proxmox Host / NAS (192.168.0.18 - Intel N150, senzori lm-sensors, dynamic-fancontrol, ZFS/HDD, VM 100): ssh -o BatchMode=yes root@192.168.0.18 '<cmd>' sau python3 /opt/data/proxmox_helper.py. "
                                    "2) Server Servicii (192.168.0.196 - LXC 102, containere Docker: radarr, sonarr, prowlarr, jellyfin, jellyseerr, dockge): comenzi docker direct în container sau ssh -o BatchMode=yes root@192.168.0.196 '<cmd>'. "
                                    f"Pași inițiali sugerați: {' | '.join(hints)}"
                                )
                            }]
                        }
                        print(f"[GUARDRAIL-DELEGATE] Auto-upgraded {len(inline_heavy)} inline tool call(s) on Main Chat to background delegate_task!")
                        tool_calls = [{
                            "id": f"call_{int(time.time() * 1000)}_0",
                            "type": "function",
                            "function": {
                                "name": "delegate_task",
                                "arguments": json.dumps(deleg_payload, ensure_ascii=False)
                            }
                        }]

        return reasoning, clean_text, tool_calls

    if stream:
        async def event_generator():
            chunk_id = f"chatcmpl-{int(time.time())}"
            task = asyncio.create_task(run_agy_prompt(prompt, chosen_model, timeout_str=initial_timeout))

            try:
                while not task.done():
                    await asyncio.sleep(2)
                    if not task.done():
                        yield f": keep-alive ping {int(time.time())}\n\n"

                full_text, success = await task
                effective_model = chosen_model

                if (not success or not full_text.strip()) and chosen_model != DEFAULT_MODEL:
                    print(f"[FALLBACK] Model {chosen_model} failed. Retrying with {DEFAULT_MODEL}...")
                    fallback_task = asyncio.create_task(run_agy_prompt(prompt, DEFAULT_MODEL, timeout_str="2m"))
                    try:
                        while not fallback_task.done():
                            await asyncio.sleep(2)
                            if not fallback_task.done():
                                yield f": keep-alive ping {int(time.time())}\n\n"
                        full_text, success = await fallback_task
                        effective_model = f"{chosen_model}->FALLBACK({DEFAULT_MODEL})"
                    finally:
                        if not fallback_task.done():
                            fallback_task.cancel()

                reasoning, clean_text, tool_calls = postprocess_output(full_text)

                t_elapsed = round(time.time() - t_start, 2)
                print(f"[COMPLETION-STREAM] subagent={is_subagent} | Model: {effective_model} | Time: {t_elapsed}s | Tool Calls: {len(tool_calls)} | Text len: {len(clean_text)}")

                if reasoning:
                    yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': f'<think>{reasoning}</think>\n'}}]})}\n\n"

                if clean_text:
                    yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': clean_text}}]})}\n\n"

                if tool_calls:
                    for tc in tool_calls:
                        yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'tool_calls': [tc]}}]})}\n\n"
                    yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]})}\n\n"
                else:
                    yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"

                yield "data: [DONE]\n\n"
            finally:
                if not task.done():
                    task.cancel()

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    else:
        full_text, success = await run_agy_prompt(prompt, chosen_model, timeout_str=initial_timeout)
        effective_model = chosen_model

        if (not success or not full_text.strip()) and chosen_model != DEFAULT_MODEL:
            print(f"[FALLBACK] Model {chosen_model} failed. Retrying with {DEFAULT_MODEL}...")
            full_text, success = await run_agy_prompt(prompt, DEFAULT_MODEL, timeout_str="2m")
            effective_model = f"{chosen_model}->FALLBACK({DEFAULT_MODEL})"

        reasoning, clean_text, tool_calls = postprocess_output(full_text)

        final_content = f"<think>{reasoning}</think>\n{clean_text}".strip() if reasoning else clean_text
        if not final_content and tool_calls:
            final_content = None

        msg_obj = {"role": "assistant"}
        msg_obj["content"] = final_content if final_content else ""

        if tool_calls:
            msg_obj["tool_calls"] = tool_calls

        t_elapsed = round(time.time() - t_start, 2)
        print(f"[COMPLETION-SYNC] subagent={is_subagent} | Model: {effective_model} | Time: {t_elapsed}s | Tool Calls: {len(tool_calls)} | Text len: {len(clean_text)}")

        return JSONResponse({
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": msg_obj,
                "finish_reason": "tool_calls" if tool_calls else "stop"
            }]
        })

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
