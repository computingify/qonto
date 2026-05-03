#!/usr/bin/env python3
"""
GUI Launcher pour getTransactionAttachments.py
Serveur Flask avec interface web moderne pour lancer des scripts avec interactivité
"""

from flask import Flask, render_template, jsonify, request
import subprocess
import os
import threading
from datetime import datetime
from queue import Queue, Empty
import webbrowser
import time

app = Flask(__name__, template_folder='templates')


class ScriptManager:
    """Gère le cycle de vie d'un processus Python avec communication interactive"""
    
    def __init__(self):
        self.process = None
        self.running = False
        self.auto_mode = False
        self.logs = Queue()
    
    def start(self, auto_mode=False):
        """Démarre le script dans un thread séparé"""
        self.running = True
        self.auto_mode = auto_mode
        self.logs.put("▶ Script démarré...")
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
    
    def _run(self):
        """Exécute le script dans le venv et capture la sortie"""
        try:
            venv_python = os.path.join(os.path.dirname(__file__), "qontoenv", "bin", "python3")
            script_path = os.path.join(os.path.dirname(__file__), "getTransactionAttachments.py")
            
            self.process = subprocess.Popen(
                [venv_python, script_path, "--noGui"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=os.path.dirname(__file__)
            )
    
            while self.running and self.process.poll() is None:
                line = self.process.stdout.readline()
                if line:
                    self.logs.put(line.rstrip())
                    if self.auto_mode:
                        self._handle_auto_response(line)
                else:
                    time.sleep(0.05)
            
            self.running = False
            self.logs.put("✓ Script terminé")
        except Exception as e:
            self.logs.put(f"✗ Erreur: {str(e)}")
            self.running = False
    
    def _handle_auto_response(self, line):
        """Répond automatiquement aux questions du script"""
        self.process.stdin.write("\n")
        self.process.stdin.flush()
        self.logs.put("[AUTO] → default value")
    
    def stop(self):
        """Arrête le processus"""
        self.running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
    
    def send_answer(self, answer):
        """Envoie une réponse au stdin du processus"""
        if self.process and self.running:
            self.process.stdin.write(answer + "\n")
            self.process.stdin.flush()
    
    def get_logs(self):
        """Récupère tous les logs en attente"""
        logs = []
        try:
            while True:
                logs.append(self.logs.get_nowait())
        except Empty:
            pass
        return logs


manager = ScriptManager()


@app.route('/')
def index():
    """Sert la page d'accueil"""
    return render_template('index.html')


@app.route('/api/start', methods=['POST'])
def api_start():
    """Lance le script avec ou sans mode automatique"""
    data = request.json or {}
    manager.start(auto_mode=data.get('auto', False))
    return jsonify({'status': 'started'})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Arrête le script en cours"""
    manager.stop()
    return jsonify({'status': 'stopped'})


@app.route('/api/answer', methods=['POST'])
def api_answer():
    """Envoie une réponse au script"""
    data = request.json or {}
    manager.send_answer(data.get('answer', ''))
    return jsonify({'status': 'answered'})


@app.route('/api/logs', methods=['GET'])
def api_logs():
    """Retourne les logs accumulés et l'état du script"""
    return jsonify({
        'logs': manager.get_logs(),
        'running': manager.running
    })


if __name__ == '__main__':
    # Ouvre le navigateur automatiquement après 1 seconde
    threading.Timer(1, lambda: webbrowser.open('http://localhost:8000')).start()
    app.run(host='127.0.0.1', port=8000, debug=False)
