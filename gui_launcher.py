#!/usr/bin/env python3
"""
GUI Launcher pour getTransactionAttachments.py
Serveur Flask avec interface web moderne pour lancer des scripts avec interactivité
"""

from flask import Flask, render_template, jsonify, request
import subprocess
import os
import json
import threading
from datetime import datetime
from queue import Queue, Empty
import webbrowser
import time
import status

app = Flask(__name__, template_folder='templates')


class ScriptManager:
    """Gère le cycle de vie d'un processus Python avec communication interactive"""
    
    def __init__(self):
        self.process = None
        self.running = False
        self.auto_mode = False
        self.logs = Queue()
        # État de chaque société : {'level': ..., 'messages': [...]}
        self.statuses = {}
        self.statuses_lock = threading.Lock()
    
    def start(self, auto_mode=False):
        """Démarre le script dans un thread séparé"""
        self.running = True
        self.auto_mode = auto_mode
        with self.statuses_lock:
            self.statuses = {}
        self.logs.put("▶ Script démarré...")
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
    
    def _run(self):
        """Exécute le script dans le venv et capture la sortie"""
        try:
            venv_python = os.path.join(os.path.dirname(__file__), "qontoenv", "bin", "python3")
            script_path = os.path.join(os.path.dirname(__file__), "getTransactionAttachments.py")
            
            env = dict(os.environ, PYTHONUNBUFFERED="1")
            self.process = subprocess.Popen(
                # -u : sortie non tamponnée, sinon les logs et les statuts
                # arrivent par blocs de plusieurs kilo-octets.
                [venv_python, "-u", script_path, "--noGui"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=os.path.dirname(__file__),
                env=env
            )
    
            while self.running and self.process.poll() is None:
                line = self.process.stdout.readline()
                if line:
                    self._consume(line.rstrip())
                    if self.auto_mode:
                        self._handle_auto_response(line)
                else:
                    time.sleep(0.05)

            # Le processus est terminé : on vide ce qui reste dans le tuyau.
            if self.process.stdout:
                for line in self.process.stdout:
                    self._consume(line.rstrip())

            returncode = self.process.poll()
            self.running = False
            if returncode:
                self._fail_unfinished(f"Le script s'est arrêté (code {returncode})")
                self.logs.put(f"✗ Script terminé en erreur (code {returncode})")
            else:
                self._fail_unfinished("Traitement interrompu avant la fin")
                self.logs.put("✓ Script terminé")
        except Exception as e:
            self.logs.put(f"✗ Erreur: {str(e)}")
            self._fail_unfinished(f"Erreur du lanceur : {e}")
            self.running = False

    def _consume(self, line):
        """Aiguille une ligne : statut structuré ou log classique"""
        if line.startswith(status.STATUS_PREFIX):
            try:
                payload = json.loads(line[len(status.STATUS_PREFIX):])
            except ValueError:
                self.logs.put(line)
                return
            with self.statuses_lock:
                self.statuses[payload.get("society", "")] = {
                    "level": payload.get("level", status.Level.PENDING),
                    "messages": payload.get("messages", []),
                }
        else:
            self.logs.put(line)

    def _fail_unfinished(self, reason):
        """Une société encore « en cours » à l'arrêt du script est en échec."""
        with self.statuses_lock:
            for society, state in self.statuses.items():
                if state.get("level") in (status.Level.RUNNING, status.Level.PENDING):
                    state["level"] = status.Level.ERROR
                    state["messages"] = (state.get("messages") or []) + [reason]

    def get_statuses(self):
        with self.statuses_lock:
            return {k: dict(v) for k, v in self.statuses.items()}
    
    def _handle_auto_response(self, line):
        """Répond automatiquement aux questions du script"""
        self.process.stdin.write("\n")
        self.process.stdin.flush()
    
    def stop(self):
        """Arrête le processus"""
        was_running = self.running
        self.running = False
        if was_running:
            self._fail_unfinished("Arrêt demandé par l'utilisateur")
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


# --- Arrêt automatique quand la page web est fermée ---
# La page envoie un « battement de cœur » régulier. Sans battement pendant
# HEARTBEAT_TIMEOUT secondes (onglet fermé, navigateur quitté ou en veille),
# le serveur s'arrête tout seul : l'application se ferme et libère le port.
HEARTBEAT_TIMEOUT = 120  # secondes (tolère le throttling des onglets en arrière-plan)
_last_heartbeat = [time.time()]


def _shutdown_watchdog():
    while True:
        time.sleep(5)
        if time.time() - _last_heartbeat[0] > HEARTBEAT_TIMEOUT:
            os._exit(0)


threading.Thread(target=_shutdown_watchdog, daemon=True).start()


@app.route('/')
def index():
    """Sert la page d'accueil"""
    _last_heartbeat[0] = time.time()
    return render_template('index.html')


@app.route('/api/heartbeat', methods=['POST'])
def api_heartbeat():
    """Reçu périodiquement tant que la page est ouverte."""
    _last_heartbeat[0] = time.time()
    return jsonify({'status': 'alive'})


@app.route('/api/quit', methods=['POST'])
def api_quit():
    """Fermeture de l'onglet : on arrête le script puis l'application."""
    manager.stop()
    threading.Timer(0.2, lambda: os._exit(0)).start()
    return jsonify({'status': 'quitting'})


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
        'running': manager.running,
        'statuses': manager.get_statuses()
    })


if __name__ == '__main__':
    # Ouvre le navigateur automatiquement après 1 seconde
    threading.Timer(1, lambda: webbrowser.open('http://localhost:8000')).start()
    try:
        app.run(host='127.0.0.1', port=8000, debug=False, threaded=True)
    except OSError:
        # Le port est déjà occupé : une instance tourne encore.
        # On ne démarre pas en double, on affiche simplement l'interface existante.
        webbrowser.open('http://localhost:8000')
