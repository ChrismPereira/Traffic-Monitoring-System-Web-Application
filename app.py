from flask import Flask, render_template, request, redirect, send_file, jsonify, send_from_directory
import os
from yolopipe import process_video, cancel_processing
import threading

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
progress = {'value': 0, 'active': True}
result_ready = {'status': False}


@app.route('/')
def index():
    global progress, result_ready
    progress = {'value': 0, 'active': False}
    result_ready['status'] = False
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    global progress, result_ready, processing_thread
    file = request.files['video']
    if file:
        # Reset everything
        progress = {'value': 0, 'active': True}
        result_ready['status'] = False

        filename = os.path.join(app.config['UPLOAD_FOLDER'], 'input.mp4')
        output_path = os.path.join('static/processed', 'output.mp4')  # processed folder

        # ✅ DELETE old output file if it exists
        if os.path.exists(output_path):
            os.remove(output_path)

        file.save(filename)

        def update(p):
            global progress
            if progress['active']:
                progress['value'] = p

        def run_processing():
            process_video(filename, output_path, update, lambda: progress['active'])
            if progress['active']:
                result_ready['status'] = True
            progress['active'] = False

        processing_thread = threading.Thread(target=run_processing)
        processing_thread.start()

        return render_template('index.html', message="Processing started...")


@app.route('/cancel', methods=['POST'])
def cancel():
    global progress
    progress['active'] = False
    cancel_processing()

    # ✅ Delete any partially processed video
    output_path = os.path.join('static/processed', 'output.mp4')
    if os.path.exists(output_path):
        os.remove(output_path)

    return jsonify({'status': 'cancelled'})


@app.route('/result')
def result():
    filename = request.args.get('filename', 'output.mp4')
    log_data = {}
    if os.path.exists('static/processed/log.json'):
        import json
        with open('static/processed/log.json', 'r') as f:
            log_data = json.load(f)
    return render_template('result.html', filename=filename, log=log_data)


@app.route('/progress')
def get_progress():
    global progress, result_ready
    return jsonify({'progress': progress['value'], 'done': result_ready['status']})


@app.route('/processed/<filename>')
def processed_file(filename):
    return send_from_directory('static/processed', filename)


@app.route('/download-csv')
def download_csv():
    log_csv = 'static/processed/log.csv'
    if os.path.exists(log_csv):
        return send_file(log_csv, as_attachment=True)
    else:
        return "CSV log not found", 404


if __name__ == '__main__':
    app.run(debug=True)
