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
import decision

app = Flask(__name__, template_folder='templates')


def _describe(items):
    """« 3 transaction(s) Amazon » ou « 3 transaction(s) (2 Amazon, 1 Bouygues) »."""
    counts = {}
    for item in items:
        source = item.get("source", "Amazon")
        counts[source] = counts.get(source, 0) + 1
    if len(counts) <= 1:
        return f"{len(items)} transaction(s) {next(iter(counts), 'Amazon')}"
    return f"{len(items)} transaction(s) (" + ", ".join(f"{n} {s}" for s, n in counts.items()) + ")"


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
        self.month = None
        # Décision en attente de réponse (spec 001/002), ligne « Amazon » de
        # chaque société, et ligne de chaque source : {société: {source: texte}}.
        self.decision = None
        self.amazon = {}
        self.sources = {}
        self.stdin_lock = threading.Lock()
    
    def start(self, auto_mode=False, month=None):
        """Démarre le script dans un thread séparé"""
        self.running = True
        self.auto_mode = auto_mode
        self.month = month
        with self.statuses_lock:
            self.statuses = {}
            self.decision = None
            self.amazon = {}
            self.sources = {}
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
                [venv_python, "-u", script_path, "--noGui"]
                + (["--month", self.month] if self.month else []),
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
                    structured = self._consume(line.rstrip())
                    if self.auto_mode and not structured:
                        self._handle_auto_response(line)
                else:
                    time.sleep(0.05)

            # Le processus est terminé : on vide ce qui reste dans le tuyau.
            if self.process.stdout:
                for line in self.process.stdout:
                    self._consume(line.rstrip())
            with self.statuses_lock:
                self.decision = None

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
        """Aiguille une ligne : statut, décision, ligne d'une source (Amazon, Free, Bouygues) ou log classique.
        Renvoie True pour une ligne structurée (le mode auto n'y répond pas)."""
        for prefix, attr in ((decision.DECISION_PREFIX, "decision"), (decision.AMAZON_PREFIX, "amazon")):
            if line.startswith(prefix):
                try:
                    payload = json.loads(line[len(prefix):])
                except ValueError:
                    self.logs.put(line)
                    return False
                with self.statuses_lock:
                    if attr == "decision":
                        self.decision = payload
                        self.logs.put(f"⏸ En attente de ta décision pour {_describe(payload.get('items', []))}")
                    else:
                        society, source = payload.get("society", ""), payload.get("source", "Amazon")
                        self.sources.setdefault(society, {})[source] = payload.get("text", "")
                        if source == "Amazon":
                            self.amazon[society] = payload.get("text", "")
                return True
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
            return True
        else:
            self.logs.put(line)
            return False

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

    def get_decision(self):
        with self.statuses_lock:
            return self.decision

    def get_sources(self):
        with self.statuses_lock:
            return {society: dict(lines) for society, lines in self.sources.items()}

    def get_amazon(self):
        with self.statuses_lock:
            return dict(self.amazon)

    def answer_decision(self, decision_id, answers):
        """Renvoie au script les choix de la carte de décision Amazon."""
        with self.statuses_lock:
            if not self.decision or self.decision.get("id") != decision_id:
                return False
            self.decision = None
        self._write(decision.answer_line(decision_id, answers))
        return True

    def _write(self, text):
        if self.process and self.running:
            with self.stdin_lock:
                self.process.stdin.write(text + "\n")
                self.process.stdin.flush()
    
    def _handle_auto_response(self, line):
        """Répond automatiquement aux questions du script"""
        self._write("")
    
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
        self._write(answer)
    
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
    month = data.get('month')
    if month is not None and not (isinstance(month, str) and len(month) == 7 and month[4] == '_'
                                  and month[:4].isdigit() and month[5:].isdigit()):
        return jsonify({'status': 'refused', 'error': 'Mois invalide, format attendu AAAA_MM'}), 400
    if manager.running:
        return jsonify({'status': 'refused', 'error': 'Un traitement est déjà en cours'}), 409
    manager.start(auto_mode=data.get('auto', False), month=month)
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


@app.route('/api/decision', methods=['POST'])
def api_decision():
    """Réponse à la carte « Décision Amazon » (spec 001)."""
    data = request.json or {}
    pending = manager.get_decision()
    if not pending or pending.get('id') != data.get('id'):
        return jsonify({'status': 'refused', 'error': 'Aucune décision en attente'}), 409
    answers = data.get('answers') or {}
    missing = [item for item in pending.get('items', [])
               if answers.get(item['id']) not in item.get('choices', [])]
    if missing:
        return jsonify({'status': 'refused', 'missing': [item['id'] for item in missing]}), 400
    manager.answer_decision(pending['id'], answers)
    return jsonify({'status': 'answered'})


@app.route('/api/logs', methods=['GET'])
def api_logs():
    """Retourne les logs accumulés et l'état du script"""
    return jsonify({
        'logs': manager.get_logs(),
        'running': manager.running,
        'statuses': manager.get_statuses(),
        'decision': manager.get_decision(),
        'amazon': manager.get_amazon(),
        'sources': manager.get_sources(),
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
