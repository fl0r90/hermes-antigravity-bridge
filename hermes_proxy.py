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

app = FastAPI(title="Hermes Antigravity Bridge Proxy", version="1.3.0")

AGY_BIN = os.environ.get("AGY_BIN", shutil.which("agy") or "/usr/local/bin/agy")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "Gemini 3.8 Flash (Low)")
PRO_MODEL = os.environ.get("PRO_MODEL", "Gemini 4 Argon (Medium)")

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
                "owned_by": "custom"
            },
            {
                "id": "gemini-3.8-flash",
                "object": "model",
                "created": 1700000000,
                "owned_by": "custom"
            },
            {
                "id": "gemini-4-argon",
                "object": "model",
                "created": 1700000000,
                "owned_by": "custom"
            }
        ]
    }

@app.get("/v1/models/{model_name:path}")
async def get_model(model_name: str):
    return {
        "id": model_name,
        "object": "model",
        "created": 1700000000,
        "owned_by": "custom"
    }

@app.get("/version")
@app.get("/api/version")
async def version():
    return {"version": "1.3.0", "status": "running"}

@app.get("/props")
@app.get("/v1/props")
@app.post("/api/show")
async def mock_ok():
    return {"status": "ok", "version": "1.3.0"}

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

ALLOWED_TOOL_NAMES = {
    "terminal", "memory", "session_search", "web_search", 
    "read_file", "write_file", "patch_file", "dir_contents", 
    "view_file", "mempalace_helper", "laptop_bridge",
    "delegate_task"
}

SUBAGENT_SYSTEM_PREFIX = os.environ.get("SUBAGENT_SYSTEM_PREFIX", """You are a focused, autonomous subagent executing a delegated task inside the container.
Execute the available tools directly and systematically to achieve your goal.
Do not output meta-commentary, conversational filler, disclaimers, or placeholder tags.
Emit real tool calls in the exact format:
<tool_call>{"name":"tool_name","arguments":{"key":"value"}}</tool_call>
When the task is complete, provide your final summary and conclusion directly in plain text without any tool calls.""")

STATIC_PREFIX = os.environ.get("STATIC_SYSTEM_PREFIX", """You are Hermes Agent, a sharp, witty Romanian SysAdmin & DevOps assistant.
Parlează românește direct, amuzant și fără limbaj corporatrist. Ești genial pe tehnică (Docker, Linux, Proxmox, Media Stack).

CRITICAL RUNTIME DIRECTIVE:
DO NOT EVER CALL ANY INTERNAL OR NATIVE CLI TOOLS (such as run_command, read_file, grep_search, write_to_file, etc.). You DO NOT have permission to run tools locally.
You are acting STRICTLY as a fast LLM generator producing text completions for the external Hermes Agent container.
If a command or tool needs to be executed, you MUST ONLY emit standard text tags for the external container to run:
<tool_call>{"name":"tool_name","arguments":{"key":"value"}}</tool_call>
Never emit placeholder examples or dummy calls like <command_to_run>. Only emit real, concrete tool calls when needed.
Never execute tools yourself on the host. Always reply directly in text or real tool_call tags.

REGULĂ DE AUR: DELEGARE PRIN SUBAGENȚI ÎN FUNDAL (NU BLOCA TELEGRAM-UL!):
- Când Florin îți cere o investigație, verificare de sistem, analiză de loguri sau o sarcină compusă pe server (ex: "verifică proxmox", "vezi de ce nu merge X", "caută în diskuri", "fa un script"):
  NU rula comenzi secvențiale în chat-ul principal ca să nu ții Telegram-ul blocat în 'busy'!
  SPAWNEAZĂ UN SUBAGENT ÎN FUNDAL apelând unealta delegate_task:
  <tool_call>{"name":"delegate_task","arguments":{"tasks":[{"goal":"<obiectiv detaliat și complet>","context":"<căi de fișiere, comenzi utile, ex: python3 /opt/data/proxmox_helper.py>"}]}}</tool_call>
  Și răspunde-i lui Florin printr-un mesaj scurt (1 frază) că ai pus un subagent la treabă în fundal și că chat-ul rămâne complet liber pentru conversație.
- CÂND FLORIN ÎNTREABĂ DE STATUS SAU CE FACE AGENTUL ("ce face?", "cât mai are?", "status agent", "ce lucrează?"):
  Verifică starea subagenților activi apelând:
  <tool_call>{"name":"delegate_task","arguments":{"action":"list"}}</tool_call>
  Și raportează-i direct ce face subagentul și starea lui.
- CÂND FLORIN VREA SĂ TRANSMITĂ O NOTĂ/INSTRUCȚIUNE SUBAGENTULUI DIN MERS:
  <tool_call>{"name":"delegate_task","arguments":{"action":"steer","subagent_id":"<id_agent>","message":"<instructiune>"}}</tool_call>
- CÂND FLORIN VREA SĂ OPREASCĂ SUBAGENTUL:
  <tool_call>{"name":"delegate_task","arguments":{"action":"stop","subagent_id":"<id_agent>"}}</tool_call>

ROL & COLABORARE STRICTĂ CU ANTIGRAVITY (LAPTOP DEV):
- Tu ești Hermes (SysAdmin Homelab & Orchestrator mobil pe Telegram).
- Pe laptopul fizic al lui Florin rulează Antigravity, Senior Core Developer (responsabil de codul DocAI V2, investigații, forensic engine).
- REGULĂ CAPITALĂ PENTRU COMUNICAREA CU ANTIGRAVITY:
  Dacă Florin îți spune „spune-i lui Antigravity...”, „transmite-i lui Antigravity...”, „întreabă-l pe Antigravity...”, „ce zice Antigravity”, sau orice mesaj adresat lui Antigravity ori legat de cod DocAI:
  EȘTI OBLIGAT SĂ EXECUȚI IMEDIAT:
  <tool_call>{"name":"terminal","arguments":{"command":"python3 /opt/data/laptop_bridge.py run --async \"<mesajul lui Florin>\""}}</tool_call>
  Sub nicio formă NU răspunde tu în locul lui Antigravity și NU minți că i-ai transmis mesajul dacă nu ai rulat comanda de mai sus!
- ALTE COMENZI RAPIDE (prin terminal):
  * Status Proxmox nod & resurse / VM-uri: python3 /opt/data/proxmox_helper.py
  * Status laptop/git/taskuri: python3 /opt/data/laptop_bridge.py status
  * Anulare sarcini active laptop: python3 /opt/data/laptop_bridge.py cancel
  * Notă rapidă de steering (/btw): python3 /opt/data/laptop_bridge.py btw "<nota>"
  * Aplică git diff pe laptop: python3 /opt/data/laptop_bridge.py patch "<git_diff_content>"
- Memorie comună în MemPalace: folosește python3 /opt/data/mempalace_helper.py search <termen> pentru a vedea ce a lucrat Antigravity.

Tools available: [{"name":"terminal","description":"Run shell commands in container","parameters":{"type":"object","properties":{"command":{"type":"string"}}}},{"name":"delegate_task","description":"Spawn or monitor background subagents in container. Actions: spawn (default), list, steer, stop","parameters":{"type":"object","properties":{"tasks":{"type":"array","items":{"type":"object","properties":{"goal":{"type":"string"},"context":{"type":"string"}}}},"action":{"type":"string","enum":["spawn","list","steer","stop"]},"subagent_id":{"type":"string"},"message":{"type":"string"}}}},{"name":"mempalace_helper","description":"Search or save to MemPalace","parameters":{"type":"object","properties":{"command":{"type":"string"}}}}]
When analyzing, you can include your thinking in <think>...</think> tags at the very start.
To call a tool: <tool_call>{"name":"tool_name","arguments":{"key":"val"}}</tool_call>
Else reply directly.""")

def build_cached_prompt(messages, tools=None, max_history_messages=40):
    prompt_parts = []
    
    sys_msgs = [m for m in messages if m.get("role") == "system"]
    non_sys = [m for m in messages if m.get("role") != "system"]

    is_subagent = any(
        "subagent" in (m.get("content") or "").lower() or "delegated task" in (m.get("content") or "").lower()
        for m in sys_msgs
    )
    
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
    else:
        base_prefix = STATIC_PREFIX + custom_tools_desc
    prompt_parts.append(base_prefix)
    
    for sm in sys_msgs:
        s_content = sm.get("content", "").strip()
        if s_content and s_content not in STATIC_PREFIX and s_content not in SUBAGENT_SYSTEM_PREFIX:
            prompt_parts.append(f"[system]:\n{s_content}")
            
    if len(non_sys) > max_history_messages:
        # Preserve root user task goal (first non-system message) + recent tail
        recent_chat = [non_sys[0]] + non_sys[-(max_history_messages - 1):]
    else:
        recent_chat = non_sys
    
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
    
    for m in recent_chat:
        role = m.get("role", "user")
        content = m.get("content", "") or ""
        
        if role == "tool":
            tool_name = m.get("name", "tool")
            if len(content) > 1500:
                content = content[:800] + f"\n...[Truncated {len(content)-1300} chars]...\n" + content[-500:]
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
                calls_list.append("<tool_call>" + json.dumps(call_dict) + "</tool_call>")
            calls_str = "\n".join(calls_list)
            prompt_parts.append(f"[assistant]:\n{content}\n{calls_str}")
        else:
            prompt_parts.append(f"[{role}]:\n{content}")
            
    return "\n\n".join(prompt_parts)

def select_model(prompt: str, client_requested_model: str = "") -> tuple[str, str]:
    return DEFAULT_MODEL, "3m"

def extract_tool_calls(text: str) -> tuple[list, str]:
    tool_calls = []
    seen = set()
    matches = list(re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL))
    for i, m in enumerate(matches):
        raw_json = m.group(1).strip()
        try:
            call_obj = json.loads(raw_json)
            name = call_obj.get("name", "")
            args = call_obj.get("arguments", {})
            args_str = args if isinstance(args, str) else json.dumps(args)
            key = (name, args_str)
            if key in seen:
                continue
            seen.add(key)
            tool_calls.append({
                "id": f"call_{int(time.time())}_{i}",
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

def extract_reasoning(text: str) -> tuple[str, str]:
    reasoning = ""
    m = re.search(r"<think>\s*(.*?)\s*</think>", text, re.DOTALL)
    if m:
        reasoning = m.group(1).strip()
        text = re.sub(r"<think>\s*.*?\s*</think>", "", text, flags=re.DOTALL).strip()
    return reasoning, text

async def run_agy_prompt(prompt: str, model_name: str, timeout_str: str = "3m") -> tuple[str, bool]:
    cmd = [
        AGY_BIN,
        "--model", model_name,
        "--print-timeout", timeout_str,
        "--disable-slash-commands",
        "-p", prompt,
        "--output-format", "stream-json",
        "--dangerously-skip-permissions"
    ]
    os.makedirs("/tmp/agy_scratch", exist_ok=True)
    
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/tmp/agy_scratch"
        )
        
        full_response = ""
        success = False
        loop_timeout = 120.0
        start_wait = time.time()
        
        while time.time() - start_wait < loop_timeout:
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=12.0)
            except asyncio.TimeoutError:
                if process.returncode is not None:
                    break
                continue
                
            if not line:
                break
                
            line_str = line.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue
                
            try:
                data = json.loads(line_str)
                ev = data.get("event")
                if ev == "result":
                    res = data.get("result", {})
                    status = res.get("status", "")
                    if status == "SUCCESS":
                        full_response = res.get("response", "").strip()
                        success = bool(full_response)
                    break
            except Exception:
                pass
                
        return full_response, success
    except Exception:
        return "", False
    finally:
        if process:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    t_start = time.time()
    data = await request.json()
    messages = data.get("messages", [])
    tools = data.get("tools", None)
    print(f"[DEBUG-INCOMING] Keys: {list(data.keys())} | Tools in request: {len(tools) if tools else 0}")
    stream = data.get("stream", False)
    client_model = data.get("model", "")

    # --- FAST AUTO-ROUTER (INTERCEPT QUICK COMMANDS & LAPTOP STEERING) ---
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "") or ""
            break
            
    is_tool_followup = any(m.get("role") == "tool" for m in messages[-2:]) if messages else False
    
    routed_reply = None
    if not is_tool_followup and last_user_msg:
        clean_prompt = last_user_msg.strip()
        
        # Check if message is an internal Hermes gateway/system event or delegation result
        is_internal_system_event = any(marker in clean_prompt for marker in [
            "[ASYNC DELEGATION",
            "[INTERNAL NOTIFICATION",
            "A background fan-out unit you dispatched earlier",
            "delegate_task",
            "delegation_id",
            "sa-0-"
        ])
        
        if is_internal_system_event:
            # Let internal system notifications pass through to LLM reasoning!
            routed_reply = None

        # Case 0: /cancel /stop /opreste-te
        elif re.search(r"^\s*/(cancel|stop)\b|\b(opreste(-te)?|anuleaza)\s+(tot|task|totul|laptop)\b", clean_prompt, re.I):
            print(f"[ROUTER] Cancel requested. Stopping background jobs...")
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
                routed_reply = f"⚡ [BTW / Nota Inregistrata]: Am injectat-o direct in contextul activ de pe laptop:\n> *{note}*"
            except Exception as e:
                routed_reply = f"❌ Eroare la trimitere /btw: {e}"

        # Case 2: Git Diff / Patch from Telegram
        elif "diff --git " in clean_prompt or ("--- a/" in clean_prompt and "+++ b/" in clean_prompt):
            print(f"[ROUTER] Detected incoming git diff. Dispatching to laptop_bridge patch...")
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
            print(f"[ROUTER] Checking laptop status...")
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    ["python3", "/opt/stacks/hermes/data/laptop_bridge.py", "status"],
                    capture_output=True, text=True, timeout=20
                )
                routed_reply = proc.stdout.strip() or proc.stderr.strip()
            except Exception as e:
                routed_reply = f"❌ Eroare la status laptop: {e}"
                
        # Case 4: Antigravity Direct Addressing / Question / Task (strip model name to avoid false trigger)
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
                    routed_reply = f"⚡ Raspuns de la Laptop Bridge:\n\n{out}"
                else:
                    routed_reply = f"⚠️ Laptop Bridge nu a intors text:\n{proc.stderr.strip()}"
            except Exception as e:
                routed_reply = f"❌ Eroare la comunicare cu laptop: {e}"
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
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": routed_reply},
                        "finish_reason": "stop"
                    }
                ]
            })
    
    prompt = build_cached_prompt(messages, tools=tools)
    chosen_model, initial_timeout = select_model(prompt, client_requested_model=client_model)
    
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
                    fallback_task = asyncio.create_task(run_agy_prompt(prompt, DEFAULT_MODEL, timeout_str="3m"))
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
                    
                if not full_text.strip():
                    full_text = "Boss, m-am sincopat o secunda pe conexiune, dar sunt in picioare. Reincearca comanda sau da-i un ping scurt!"
                    
                tool_calls, clean_text = extract_tool_calls(full_text)
                reasoning, clean_text = extract_reasoning(clean_text)
                
                t_elapsed = round(time.time() - t_start, 2)
                print(f"[COMPLETION-STREAM] Model: {effective_model} | Time: {t_elapsed}s | Tool Calls: {len(tool_calls)} | Text len: {len(clean_text)}")
                
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
            full_text, success = await run_agy_prompt(prompt, DEFAULT_MODEL, timeout_str="3m")
            effective_model = f"{chosen_model}->FALLBACK({DEFAULT_MODEL})"
            
        if not full_text.strip():
            full_text = "Boss, m-am sincopat o secunda pe conexiune, dar sunt in picioare. Reincearca comanda sau da-i un ping scurt!"
            
        tool_calls, clean_text = extract_tool_calls(full_text)
        reasoning, clean_text = extract_reasoning(clean_text)
        
        final_content = f"<think>{reasoning}</think>\n{clean_text}".strip() if reasoning else clean_text
        if not final_content and tool_calls:
            final_content = None
            
        msg_obj = {"role": "assistant"}
        if final_content:
            msg_obj["content"] = final_content
        else:
            msg_obj["content"] = ""
            
        if tool_calls:
            msg_obj["tool_calls"] = tool_calls
            
        t_elapsed = round(time.time() - t_start, 2)
        print(f"[COMPLETION-SYNC] Model: {effective_model} | Time: {t_elapsed}s | Tool Calls: {len(tool_calls)} | Text len: {len(clean_text)}")
        
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
