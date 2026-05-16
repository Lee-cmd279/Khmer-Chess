# Hugging Face Space — runs ouk_train.py as a background process
# Upload this as app.py to your HuggingFace Space (SDK: Gradio)
import subprocess, threading, gradio as gr, os, time

log_lines = []

def run_training():
    proc = subprocess.Popen(
        ['python', 'ouk_train.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    for line in proc.stdout:
        log_lines.append(line.strip())
        if len(log_lines) > 200:
            log_lines.pop(0)

# Start training in background immediately
thread = threading.Thread(target=run_training, daemon=True)
thread.start()

def get_log():
    return '\n'.join(log_lines[-50:]) if log_lines else 'Training starting...'

with gr.Blocks(title='Ouk Chess Trainer') as demo:
    gr.Markdown('# អុកចត្រង្គ AI Trainer\nRunning continuously in background.')
    log = gr.Textbox(label='Training Log', lines=20, every=5)
    log.attach_load_event(get_log, None)

demo.launch()
