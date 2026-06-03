/*
 * launcher.c — exécutable natif du bundle QontoUpdate.app
 *
 * Pourquoi un binaire compilé plutôt qu'un script shell ?
 * macOS (TCC) rattache les accès fichiers au « responsible process ».
 * Avec un script, le process réellement lancé est /bin/bash et
 * l'autorisation « Accès complet au disque » accordée au bundle n'est
 * jamais reconnue. Un binaire Mach-O signé dans le bundle donne une
 * identité de code stable ; Python est lancé comme processus ENFANT et
 * hérite de cette autorisation.
 *
 * Compilation :
 *   clang -O2 -o QontoUpdate.app/Contents/MacOS/QontoUpdate launcher.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <sys/wait.h>

#define PROJECT_DIR "/Users/adrien/Documents/workspace/qonto"
#define VENV_PYTHON PROJECT_DIR "/qontoenv/bin/python3"
#define SCRIPT      PROJECT_DIR "/gui_launcher.py"
#define PYVENV_CFG  PROJECT_DIR "/qontoenv/pyvenv.cfg"

static pid_t child = 0;

/* « Quitter » depuis le Dock -> on transmet l'arrêt au serveur Python. */
static void on_term(int sig) {
    (void)sig;
    if (child > 0) kill(child, SIGTERM);
    _exit(0);
}

/* Accès au projet refusé : on guide vers les Réglages Système. */
static void show_permission_alert(void) {
    system("osascript -e 'display alert \"Qonto Update — Autorisation requise\" "
           "message \"macOS bloque l’accès au dossier du projet (Documents / Downloads).\n\n"
           "Dans les Réglages qui s’ouvrent :\n"
           "1. Bouton + et ajoutez QontoUpdate.app\n"
           "2. Activez l’interrupteur en face\n"
           "3. Relancez l’application.\n\n"
           "Étape unique.\" buttons {\"Ouvrir les Réglages\"} default button 1' >/dev/null 2>&1");
    system("open 'x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles'");
}

int main(void) {
    /* Pré-vol : le dossier projet est-il lisible (autorisation accordée) ? */
    FILE *cfg = fopen(PYVENV_CFG, "r");
    if (!cfg) {
        show_permission_alert();
        return 1;
    }
    fclose(cfg);

    signal(SIGTERM, on_term);
    signal(SIGINT, on_term);

    child = fork();
    if (child < 0) {
        return 1;
    }
    if (child == 0) {
        /* Enfant : journalise et lance le serveur Flask. */
        const char *home = getenv("HOME");
        char log_path[1024];
        snprintf(log_path, sizeof(log_path), "%s/Library/Logs/QontoUpdate.log",
                 home ? home : "/tmp");
        freopen(log_path, "a", stdout);
        freopen(log_path, "a", stderr);
        if (chdir(PROJECT_DIR) != 0) _exit(126);
        char *args[] = { (char *)VENV_PYTHON, (char *)SCRIPT, NULL };
        execv(VENV_PYTHON, args);
        _exit(127); /* atteint seulement si execv échoue */
    }

    /* Parent : reste vivant (identité de l'app) tant que le serveur tourne. */
    int status;
    waitpid(child, &status, 0);
    return 0;
}
