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

app = FastAPI(title="Hermes Antigravity Bridge Proxy", version="1.0.0")

AGY_BIN = os.environ.get("AGY_BIN", shutil.which("agy") or "/usr/local/bin/agy")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "Gemini 3.7 Flash (Low)")
PRO_MODEL = os.environ.get("PRO_MODEL", "Gemini 3.1 Pro (Low)")

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
@app.get("/api/tags")
@app.get("/props")
@app.get("/v1/props")
@app.post("/api/show")
async def mock_ok():
    return {"status": "ok", "version": "1.0.0"}

ALLOWED_TOOL_NAMES = {
    "terminal", "memory", "session_search", "web_search", 
    "read_file", "write_file", "patch_file", "dir_contents", 
    "view_file", "mempalace_helper"
}

STATIC_PREFIX = os.environ.get("STATIC_SYSTEM_PREFIX", """You are Hermes Agent, a sharp, witty Romanian SysAdmin & DevOps assistant.
Parlează românește direct, amuzant și fără limbaj corporatrist. Ești genial pe tehnică (Docker, Linux, Proxmox, Media Stack).
Tools available: [{"name":"terminal","description":"Run shell commands in container","parameters":{"type":"object","properties":{"command":{"type":"string"}}}},{"name":"memory","description":"Manage permanent memory","parameters":{"type":"object","properties":{"action":{"type":"string"},"text":{"type":"string"}}}},{"name":"mempalace_helper","description":"Search or save to MemPalace","parameters":{"type":"object","properties":{"command":{"type":"string"}}}}]
To call a tool: <tool_call>{"name":"tool_name","arguments":{"key":"val"}}</tool_call>
Else reply directly.""")

def build_cached_prompt(messages, max_history_messages=8):
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
        content = m.get("content", "")
        
        if role == "tool":
            tool_name = m.get("name", "tool")
            if len(content) > 1500:
                content = content[:1000] + f"\n...[Truncated {len(content)-1000} chars]..."
            prompt_parts.append(f"[Tool Response for {tool_name}]:\n{content}")
        elif role == "assistant" and "tool_calls" in m:
            t_calls = m.get("tool_calls", [])
            calls_str = "\n".join([f"<tool_call>{json.dumps({name: tc.get(function, {}).get(name, ), arguments: json.loads(tc.get(function, {}).get(arguments, {}))})}</tool_call>" for tc in t_calls])
            prompt_parts.append(f"[assistant]:\n{content}\n{calls_str}")
        else:
            prompt_parts.append(f"[{role}]:\n{content}")
            
    return "\n\n".join(prompt_parts)

def select_model(prompt: str) -> str:
    heavy_keywords = ("refactor", "complex architecture", "deep analysis", "write full script", "analiza completa")
    p_lower = prompt.lower()
    if any(k in p_lower for k in heavy_keywords) or len(prompt) > 30000:
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

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    t_start = time.time()
    data = await request.json()
    messages = data.get("messages", [])
    stream = data.get("stream", False)
    
    prompt = build_cached_prompt(messages)
    chosen_model = select_model(prompt)
    
    if stream:
        async def event_generator():
            chunk_id = f"chatcmpl-{int(time.time())}"
            process = await asyncio.create_subprocess_exec(
                AGY_BIN, "--model", chosen_model, "--disable-slash-commands", "-p", prompt, "--output-format", "stream-json", "--dangerously-skip-permissions",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            full_accumulated = []
            has_emitted_first = False
            
            async for line in process.stdout:
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue
                try:
                    ev = json.loads(line_str)
                    ev_type = ev.get("event")
                    
                    # Handle live thinking / reasoning tokens
                    if ev_type == "step_update" and "step_update" in ev:
                        update = ev["step_update"]
                        step_t = update.get("step_type")
                        
                        # Stream thoughts if present
                        if "thinking_delta" in update and update["thinking_delta"]:
                            t_delta = update["thinking_delta"]
                            chunk = {
                                "id": chunk_id,
                                "object": "chat.completion.chunk",
                                "choices": [{
                                    "index": 0,
                                    "delta": {
                                        "role": "assistant",
                                        "reasoning_content": t_delta
                                    }
                                }]
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                            
                        # Stream text content delta
                        if "text_delta" in update and update["text_delta"]:
                            txt_delta = update["text_delta"]
                            full_accumulated.append(txt_delta)
                            chunk = {
                                "id": chunk_id,
                                "object": "chat.completion.chunk",
                                "choices": [{
                                    "index": 0,
                                    "delta": {
                                        "role": "assistant",
                                        "content": txt_delta
                                    }
                                }]
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                except Exception:
                    pass
                    
            await process.wait()
            entire_text = "".join(full_accumulated)
            tool_calls = extract_tool_calls(entire_text)
            
            if tool_calls:
                for tc in tool_calls:
                    chunk = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "choices": [{
                            "index": 0,
                            "delta": {
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
        process = await asyncio.create_subprocess_exec(
            AGY_BIN, "--model", chosen_model, "--disable-slash-commands", "-p", prompt, "--output-format", "json", "--dangerously-skip-permissions",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        raw_output = stdout.decode("utf-8").strip()
        full_text = ""
        try:
            res_json = json.loads(raw_output)
            full_text = res_json.get("response", "").strip()
        except Exception:
            full_text = raw_output
            
        tool_calls = extract_tool_calls(full_text)
        msg_obj = {
            "role": "assistant",
            "content": full_text if not tool_calls else None
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
