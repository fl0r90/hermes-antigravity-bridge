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

app = FastAPI(title="Hermes Antigravity Bridge Proxy", version="1.1.0")

AGY_BIN = os.environ.get("AGY_BIN", shutil.which("agy") or "/usr/local/bin/agy")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "Gemini 3.6 Flash (High)")
PRO_MODEL = os.environ.get("PRO_MODEL", "Gemini 3.1 Pro (High)")

# Fast mock endpoints for instant connectivity & capability probes
@app.get("/v1/models")
@app.get("/api/v1/models")
@app.get("/models")
async def list_models():
    return {
        "object": "list",
        "data": [{
            "id": "antigravity-vibe-engine",
            "object": "model",
            "created": 1700000000,
            "owned_by": "custom"
        }]
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
    return {"version": "1.1.0", "status": "running"}

@app.get("/props")
@app.get("/v1/props")
@app.post("/api/show")
async def mock_ok():
    return {"status": "ok", "version": "1.1.0"}

ALLOWED_TOOL_NAMES = {
    "terminal", "memory", "session_search", "web_search", 
    "read_file", "write_file", "patch_file", "dir_contents", 
    "view_file", "mempalace_helper"
}

STATIC_PREFIX = os.environ.get("STATIC_SYSTEM_PREFIX", """You are Hermes Agent, a sharp, witty Romanian SysAdmin & DevOps assistant.
Parlează românește direct, amuzant și fără limbaj corporatrist. Ești genial pe tehnică (Docker, Linux, Proxmox, Media Stack).
Tools available: [{"name":"terminal","description":"Run shell commands in container","parameters":{"type":"object","properties":{"command":{"type":"string"}}}},{"name":"memory","description":"Manage permanent memory","parameters":{"type":"object","properties":{"action":{"type":"string"},"text":{"type":"string"}}}},{"name":"mempalace_helper","description":"Search or save to MemPalace","parameters":{"type":"object","properties":{"command":{"type":"string"}}}}]
When analyzing, you can include your thinking in <think>...</think> tags at the very start.
To call a tool: <tool_call>{"name":"tool_name","arguments":{"key":"val"}}</tool_call>
Else reply directly.""")

def build_cached_prompt(messages, max_history_messages=10):
    prompt_parts = [STATIC_PREFIX]

    sys_msgs = [m for m in messages if m.get("role") == "system"]
    non_sys = [m for m in messages if m.get("role") != "system"]
    
    for sm in sys_msgs:
        s_content = sm.get("content", "").strip()
        if s_content and s_content not in STATIC_PREFIX:
            prompt_parts.append(f"[system]:\n{s_content}")
            
    recent_chat = non_sys[-max_history_messages:] if len(non_sys) > max_history_messages else non_sys
    
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

def select_model(prompt: str) -> str:
    heavy_keywords = ("refactor", "complex architecture", "deep analysis", "write full script", "analiza arhitectura")
    p_lower = prompt.lower()
    if any(k in p_lower for k in heavy_keywords):
        return PRO_MODEL
    return DEFAULT_MODEL

def extract_tool_calls(text):
    tool_calls = []
    matches = list(re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL))
    for i, m in enumerate(matches):
        raw_json = m.group(1).strip()
        try:
            call_obj = json.loads(raw_json)
            name = call_obj.get("name", "")
            args = call_obj.get("arguments", {})
            args_str = args if isinstance(args, str) else json.dumps(args)
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
    return tool_calls

async def run_agy_prompt(prompt: str, model_name: str, timeout_str: str = "10m") -> tuple[str, bool]:
    """Runs the AGY CLI with given model and timeout, returns (response_text, is_success)."""
    cmd = [
        AGY_BIN,
        "--model", model_name,
        "--print-timeout", timeout_str,
        "--disable-slash-commands",
        "-p", prompt,
        "--output-format", "json",
        "--dangerously-skip-permissions"
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        raw_output = stdout.decode("utf-8", errors="replace").strip()
        err_output = stderr.decode("utf-8", errors="replace").strip()
        
        if not raw_output:
            with open("/tmp/proxy_debug.log", "a") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] EMPTY STDOUT (Model {model_name}). STDERR: {err_output}\n")
            return "", False
            
        try:
            res_json = json.loads(raw_output)
            status = res_json.get("status", "")
            resp_text = res_json.get("response", "").strip()
            
            if status == "SUCCESS" and resp_text:
                return resp_text, True
            elif status == "ERROR":
                err_msg = res_json.get("error", "unknown error")
                with open("/tmp/proxy_debug.log", "a") as f:
                    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] AGY ERROR (Model {model_name}): {err_msg} | RAW: {raw_output}\n")
                return resp_text, False
            else:
                return resp_text, bool(resp_text)
        except Exception:
            return raw_output, bool(raw_output)
    except Exception as e:
        with open("/tmp/proxy_debug.log", "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] SUBPROCESS EXCEPTION (Model {model_name}): {str(e)}\n")
        return "", False

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    t_start = time.time()
    data = await request.json()
    messages = data.get("messages", [])
    stream = data.get("stream", False)
    
    prompt = build_cached_prompt(messages)
    chosen_model = select_model(prompt)
    
    # 1. First attempt with chosen model
    full_text, success = await run_agy_prompt(prompt, chosen_model, timeout_str="10m")
    effective_model = chosen_model
    
    # 2. Fallback to Flash if Pro failed or returned empty
    if (not success or not full_text.strip()) and chosen_model != DEFAULT_MODEL:
        print(f"[FALLBACK] Model {chosen_model} failed or timed out. Retrying with {DEFAULT_MODEL}...")
        full_text, success = await run_agy_prompt(prompt, DEFAULT_MODEL, timeout_str="8m")
        effective_model = f"{chosen_model}->FALLBACK({DEFAULT_MODEL})"
        
    # 3. Emergency fallback if still empty (ensures stream never closes abruptly with 0 bytes)
    if not full_text.strip():
        full_text = "Boss, m-am sincopat o secundă pe conexiune, dar sunt în picioare. Reîncearcă comanda sau dă-i un ping scurt!"
        print(f"[EMERGENCY-RESPONSE] Sent keep-alive fallback response.")
        
    tool_calls = extract_tool_calls(full_text)
    t_elapsed = round(time.time() - t_start, 2)
    print(f"[COMPLETION] Model: {effective_model} | Time: {t_elapsed}s | Tool Calls: {len(tool_calls)} | Text len: {len(full_text)}")
    
    if stream:
        async def event_generator():
            chunk_id = f"chatcmpl-{int(time.time())}"
            
            # Stream the text content chunk if present
            if full_text:
                chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": full_text
                        }
                    }]
                }
                yield f"data: {json.dumps(chunk)}\n\n"

            if tool_calls:
                for tc in tool_calls:
                    chunk = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "tool_calls": [tc]
                            }
                        }]
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                stop_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "tool_calls"
                    }]
                }
                yield f"data: {json.dumps(stop_chunk)}\n\n"
            else:
                stop_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(stop_chunk)}\n\n"
                
            yield "data: [DONE]\n\n"
            
        return StreamingResponse(event_generator(), media_type="text/event-stream")
    else:
        msg_obj = {
            "role": "assistant",
            "content": full_text
        }
        if tool_calls:
            msg_obj["tool_calls"] = tool_calls
            
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
