from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from agent import ask_agent
from tools import resize_vm
from threading import Thread
import html

app = FastAPI()

resize_status = "No resize job started yet."


def run_resize_job(vm_name, resource_group, target_size):
    global resize_status

    resize_status = f"Resize job running for {vm_name} to {target_size}. Please wait..."

    result = resize_vm.invoke({
        "vm_name": vm_name,
        "resource_group": resource_group,
        "target_size": target_size,
        "approval": "yes"
    })

    resize_status = result


def page(chat_log="", resize_output="", pending_vm="", pending_rg="", pending_size=""):
    chat_log = html.escape(chat_log)
    resize_output = html.escape(resize_output)
    pending_vm = html.escape(pending_vm)
    pending_rg = html.escape(pending_rg)
    pending_size = html.escape(pending_size)

    return f"""
<html>
<head>
    <title>Azure VM Cost Optimization Agent</title>
    <style>
        body {{ font-family: Arial; margin: 40px; background: #111; color: #eee; }}
        textarea, input {{ width: 100%; padding: 8px; margin: 6px 0; background: #222; color: #eee; border: 1px solid #555; }}
        button {{ padding: 10px 18px; margin: 8px 4px 8px 0; cursor: pointer; }}
        .box {{ border: 1px solid #555; padding: 20px; margin-bottom: 25px; }}
        pre {{ white-space: pre-wrap; background: #222; padding: 15px; border: 1px solid #555; }}
    </style>
</head>
<body>
    <h2>Azure VM Cost Optimization Agent</h2>
    <p>Find idle Azure VMs and resize only after human approval.</p>

    <div class="box">
        <h3>Chat Agent</h3>
        <form method="post" action="chat">
            <textarea name="chat_log" rows="10" readonly>{chat_log}</textarea>
            <input name="message" placeholder="Example: Find idle VMs">
            <button type="submit">Send</button>
        </form>
    </div>

    <div class="box">
        <h3>Resize Approval Panel</h3>

        <form method="post" action="preview">
            <label>VM Name</label>
            <input name="vm_name" value="vm-runbook">

            <label>Resource Group</label>
            <input name="resource_group" value="rg-infra-lab">

            <label>Target Size</label>
            <input name="target_size" value="Standard_D2lds_v5">

            <button type="submit">Preview Resize</button>
        </form>

        <form method="post" action="approve">
            <input type="hidden" name="vm_name" value="{pending_vm}">
            <input type="hidden" name="resource_group" value="{pending_rg}">
            <input type="hidden" name="target_size" value="{pending_size}">
            <button type="submit">Approve Resize</button>
        </form>

        <form method="get" action="status">
            <button type="submit">Check Resize Status</button>
        </form>

        <form method="get" action="./">
            <button type="submit">Cancel / Refresh</button>
        </form>

        <h4>Resize Output</h4>
        <pre>{resize_output}</pre>
    </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    return page()


@app.post("/chat", response_class=HTMLResponse)
def chat(message: str = Form(""), chat_log: str = Form("")):
    blocked_words = ["yes", "approve", "approved", "confirm", "proceed"]

    if message.lower().strip() in blocked_words:
        response = "Blocked: approval is not accepted in chat. Use the Approve Resize button."
    else:
        try:
            response = ask_agent(message)
        except Exception as e:
            response = f"Error: {str(e)}"

    new_log = chat_log + f"\nYou: {message}\nAgent: {response}\n"
    return page(chat_log=new_log)


@app.post("/preview", response_class=HTMLResponse)
def preview(
    vm_name: str = Form(...),
    resource_group: str = Form(...),
    target_size: str = Form(...)
):
    result = resize_vm.invoke({
        "vm_name": vm_name,
        "resource_group": resource_group,
        "target_size": target_size,
        "approval": "no"
    })

    return page(
        resize_output=result,
        pending_vm=vm_name,
        pending_rg=resource_group,
        pending_size=target_size
    )


@app.post("/approve", response_class=HTMLResponse)
def approve(
    vm_name: str = Form(""),
    resource_group: str = Form(""),
    target_size: str = Form("")
):
    if not vm_name or not resource_group or not target_size:
        return page(resize_output="No pending resize found. Click Preview Resize first.")

    Thread(
        target=run_resize_job,
        args=(vm_name, resource_group, target_size),
        daemon=True
    ).start()

    return page(
        resize_output=f"Resize job started for {vm_name} to {target_size}. Click 'Check Resize Status' after 2-5 minutes."
    )


@app.get("/status", response_class=HTMLResponse)
def status():
    return page(resize_output=resize_status)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
