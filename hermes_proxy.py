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
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "Gemini 3.8 Flash (Low)")
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

def build_cached_prompt(messages, tools=None, max_history_messages=10):
    prompt_parts = []
    
    # Dynamic tools injection if tools provided by Hermes
    custom_tools_desc = ""
    if tools and isinstance(tools, list):
        filtered_tools = []
        for t in tools:
            fn = t.get("function", {})
            t_name = fn.get("name", "")
            # Skip heavy cloud tools if any, keep local and useful tools
            if any(bad in t_name.lower() for bad in ("feishu", "wechat", "lark", "dingtalk")):
                continue
            filtered_tools.append({
                "name": t_name,
                "description": fn.get("description", "")[:120],
                "parameters": fn.get("parameters", {})
            })
        if filtered_tools:
            custom_tools_desc = f"\nActive Tools available: {json.dumps(filtered_tools)}"

    base_prefix = STATIC_PREFIX + custom_tools_desc
    prompt_parts.append(base_prefix)

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

def select_model(prompt: str, client_requested_model: str = "") -> tuple[str, str]:
    """Returns (model_name, timeout_str). Allows client override or smart keyword routing."""
    req = (client_requested_model or "").lower()
    if "pro" in req:
        return PRO_MODEL, "15m"
    if "flash" in req:
        return DEFAULT_MODEL, "3m"
        
    heavy_keywords = ("refactor", "complex architecture", "deep analysis", "write full script", "analiza arhitectura")
    p_lower = prompt.lower()
    if any(k in p_lower for k in heavy_keywords):
        return PRO_MODEL, "15m"
    return DEFAULT_MODEL, "3m"

def extract_tool_calls(text: str) -> tuple[list, str]:
    """Extracts tool calls and returns (tool_calls, cleaned_text_without_xml)."""
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
            
    # Clean tool calls from the user-facing content to prevent session corruption
    cleaned_text = re.sub(r"<tool_call>\s*.*?\s*</tool_call>", "", text, flags=re.DOTALL).strip()
    return tool_calls, cleaned_text

def extract_reasoning(text: str) -> tuple[str, str]:
    """Separates <think>...</think> from main content."""
    reasoning = ""
    m = re.search(r"<think>\s*(.*?)\s*</think>", text, re.DOTALL)
    if m:
        reasoning = m.group(1).strip()
        text = re.sub(r"<think>\s*.*?\s*</think>", "", text, flags=re.DOTALL).strip()
    return reasoning, text

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
    tools = data.get("tools", None)
    stream = data.get("stream", False)
    client_model = data.get("model", "")
    
    prompt = build_cached_prompt(messages, tools=tools)
    chosen_model, initial_timeout = select_model(prompt, client_requested_model=client_model)
    
    if stream:
        async def event_generator():
            chunk_id = f"chatcmpl-{int(time.time())}"
            task = asyncio.create_task(run_agy_prompt(prompt, chosen_model, timeout_str=initial_timeout))
            
            # Keep-alive loop: while the model is thinking / working (even 10+ minutes),
            # send SSE comment pings every 12 seconds so Telegram/browsers don't drop the connection
            while not task.done():
                await asyncio.sleep(12)
                if not task.done():
                    yield f": keep-alive ping {int(time.time())}\n\n"
                    
            full_text, success = await task
            effective_model = chosen_model
            
            # Fallback to Flash if Pro failed or returned empty
            if (not success or not full_text.strip()) and chosen_model != DEFAULT_MODEL:
                print(f"[FALLBACK] Model {chosen_model} failed. Retrying with {DEFAULT_MODEL}...")
                fallback_task = asyncio.create_task(run_agy_prompt(prompt, DEFAULT_MODEL, timeout_str="5m"))
                while not fallback_task.done():
                    await asyncio.sleep(12)
                    if not fallback_task.done():
                        yield f": keep-alive ping {int(time.time())}\n\n"
                full_text, success = await fallback_task
                effective_model = f"{chosen_model}->FALLBACK({DEFAULT_MODEL})"
                
            if not full_text.strip():
                full_text = "Boss, a durat ceva dar sunt pe baricade. Mai dă o dată comanda sau un ping scurt!"
                
            tool_calls, clean_text = extract_tool_calls(full_text)
            reasoning, clean_text = extract_reasoning(clean_text)
            
            t_elapsed = round(time.time() - t_start, 2)
            print(f"[COMPLETION-STREAM] Model: {effective_model} | Time: {t_elapsed}s | Tool Calls: {len(tool_calls)} | Text len: {len(clean_text)}")
            
            # If reasoning exists, we can yield it
            if reasoning:
                yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': f'<think>{reasoning}</think>\n'}}]})}\n\n"
                
            # Yield user-facing cleaned text
            if clean_text:
                yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': clean_text}}]})}\n\n"
                
            # Yield tool calls if any
            if tool_calls:
                for tc in tool_calls:
                    yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'tool_calls': [tc]}}]})}\n\n"
                yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]})}\n\n"
            else:
                yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                
            yield "data: [DONE]\n\n"
            
        return StreamingResponse(event_generator(), media_type="text/event-stream")
        
    else:
        # Non-streaming request
        full_text, success = await run_agy_prompt(prompt, chosen_model, timeout_str=initial_timeout)
        effective_model = chosen_model
        
        if (not success or not full_text.strip()) and chosen_model != DEFAULT_MODEL:
            print(f"[FALLBACK] Model {chosen_model} failed. Retrying with {DEFAULT_MODEL}...")
            full_text, success = await run_agy_prompt(prompt, DEFAULT_MODEL, timeout_str="5m")
            effective_model = f"{chosen_model}->FALLBACK({DEFAULT_MODEL})"
            
        if not full_text.strip():
            full_text = "Boss, m-am sincopat o secundă pe conexiune, dar sunt în picioare. Reîncearcă comanda sau dă-i un ping scurt!"
            
        tool_calls, clean_text = extract_tool_calls(full_text)
        reasoning, clean_text = extract_reasoning(clean_text)
        
        # If there is clean text, attach it, else keep minimal explanation
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
