import gradio as gr
import subprocess
import threading
import queue
import time
import os
import sys
import signal
from pathlib import Path

# Global process and state
proc = None
stdout_queue: "queue.Queue[str]" = queue.Queue()
status_lock = threading.Lock()
agent_status = "Initializing"  # Initializing | Active | InActive


def _reader_thread(stream, q: "queue.Queue[str]"):
    global agent_status
    for raw in iter(stream.readline, b""):
        try:
            line = raw.decode("utf-8", errors="replace").rstrip("\n\r")
        except Exception:
            line = raw.decode(errors="replace").rstrip("\n\r")
        # Update status on READY marker
        if "READY" in line:
            with status_lock:
                agent_status = "Active"
        q.put(line)
    # Stream closed -> process likely ended
    with status_lock:
        agent_status = "InActive"


def start_agent_process():
    global proc, agent_status
    if proc and proc.poll() is None:
        return
    with status_lock:
        agent_status = "Initializing"
    root = Path(os.getcwd())
    py = sys.executable
    main_path = str(root / "main.py")
    # Spawn unbuffered so we can read stdout in real-time
    proc = subprocess.Popen(
        [py, "-u", main_path],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    t = threading.Thread(target=_reader_thread, args=(proc.stdout, stdout_queue), daemon=True)
    t.start()


def stop_agent_process(timeout: float = 3.0):
    global proc, agent_status
    if not proc:
        return
    if proc.poll() is None:
        try:
            if os.name == "nt":
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
                    proc.terminate()
            else:
                proc.terminate()
            start = time.time()
            while proc.poll() is None and (time.time() - start) < timeout:
                time.sleep(0.1)
            if proc.poll() is None:
                proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    proc = None
    with status_lock:
        agent_status = "Inactive"


# Kick off the agent on module import
start_agent_process()


def get_status() -> str:
    with status_lock:
        s = agent_status
    return s


def send_message(message, history):
    # history is a list of dicts with {role, content}
    if not message or not message.strip():
        return history, ""

    history = history + [{"role": "user", "content": message}]

    # Only allow interaction when Active
    if get_status() != "Active":
        updated = history + [{"role": "assistant", "content": "Agent not ready. Status: " + get_status()}]
        return updated, ""

    # Write message to agent stdin
    try:
        if proc and proc.stdin:
            proc.stdin.write((message + "\n").encode("utf-8"))
            proc.stdin.flush()
        else:
            updated = history + [{"role": "assistant", "content": "Agent process not available"}]
            return updated, ""
    except Exception as e:
        updated = history + [{"role": "assistant", "content": f"Failed to send to agent: {e}"}]
        return updated, ""

    # Wait for the assistant line: it prints as "Assist: <response>"
    response = None
    start = time.time()
    timeout_s = 120.0
    buffer_lines = []
    collecting_block = False
    block_lines = []
    while time.time() - start < timeout_s:
        try:
            line = stdout_queue.get(timeout=0.25)
        except queue.Empty:
            # Keep looping until timeout
            continue
        # Capture readiness transitions printed after startup
        if "READY" in line:
            with status_lock:
                agent_status = "Active"
            continue
        # New robust block protocol
        if line.strip() == "ASSIST_BEGIN":
            collecting_block = True
            block_lines = []
            continue
        if collecting_block:
            if line.strip() == "ASSIST_END":
                response = "\n".join(block_lines).strip()
                break
            else:
                block_lines.append(line)
            continue
        # Legacy single-line fallback
        if line.startswith("Assist:"):
            response = line.partition(":")[2].strip()
            # Do not break immediately; try to gather following lines quickly
            # in case the response included newlines printed subsequently.
            # We'll allow a short grace period to collect extra lines.
            grace_start = time.time()
            extra = []
            while time.time() - grace_start < 0.75:
                try:
                    nxt = stdout_queue.get(timeout=0.1)
                    if nxt.strip() and not nxt.startswith("You:") and not nxt.strip().endswith("READY"):
                        extra.append(nxt)
                except queue.Empty:
                    break
            if extra:
                response = (response + "\n" + "\n".join(extra)).strip()
            break
        # Optionally accumulate other lines; useful for debugging
        buffer_lines.append(line)

    if response is None:
        # If we couldn't parse an Assist line, provide a fallback
        fallback = "\n".join(buffer_lines[-5:]) if buffer_lines else "No response captured."
        updated = history + [{"role": "assistant", "content": f"(No Assist line)\n{fallback}"}]
        return updated, ""

    updated = history + [{"role": "assistant", "content": response}]
    return updated, ""


CSS = """
.status-pill { display:inline-block; padding:4px 10px; border-radius:9999px; font-weight:600; font-size:0.9rem; color:#fff; }
.status-pill.active { background:#16a34a; }
.status-pill.initializing { background:#f59e0b; }
.status-pill.inactive { background:#6b7280; }
.spinner { width:10px; height:10px; border:2px solid #fff; border-right-color:transparent; border-radius:50%; display:inline-block; margin-right:8px; animation:spin 0.8s linear infinite; vertical-align:middle; }
@keyframes spin { to { transform: rotate(360deg); } }
"""


def _status_pill_html() -> str:
    s = get_status()
    cls = s.lower()
    if s == "Initializing":
        return f'<span class="status-pill {cls}"><span class="spinner"></span>{s}</span>'
    return f'<span class="status-pill {cls}">{s}</span>'


with gr.Blocks(title="OCI GenAI Bot", css=CSS) as demo:
    gr.Markdown("# OCI GenAI Bot")

    with gr.Row():
        status_label = gr.HTML(_status_pill_html())
        refresh = gr.Button("Refresh Status", variant="secondary")
        restart = gr.Button("Restart Agent", variant="secondary")

    chat = gr.Chatbot(type="messages", height=480)
    msg = gr.Textbox(
        label="Message",
        placeholder="Type your query and press Enter...",
    )
    clear = gr.Button("Clear")

    def _update_status():
        return _status_pill_html()

    refresh.click(_update_status, outputs=status_label)

    def _restart():
        stop_agent_process()
        start_agent_process()
        # Return updated status pill immediately
        return _status_pill_html()

    restart.click(_restart, outputs=status_label)

    def _submit(m, h):
        # On submit, also refresh status display afterward
        new_hist, _ = send_message(m, h)
        return new_hist, "", _status_pill_html()

    msg.submit(_submit, inputs=[msg, chat], outputs=[chat, msg, status_label])
    clear.click(lambda: ([], ""), outputs=[chat, msg])

    # Initial status on load
    demo.load(_update_status, outputs=status_label)

if __name__ == "__main__":
    # Default to port 7860
    demo.queue().launch(server_name="0.0.0.0", server_port=7860)
