"""
Session Chrome commune aux sites de justificatifs (spec 002, B2).

Google Chrome installé (channel « chrome »), piloté par Playwright, avec un
seul profil réservé à QontoUpdate : `browser-profile/`. Amazon, Free et
Bouygues y gardent chacun leur session d'une fois sur l'autre. L'ancien
`amazon-profile/` (spec 001) est renommé au premier lancement : la session
Amazon est conservée.

La session démarre sans fenêtre. Dès qu'un site demande une connexion, elle est
relancée avec une fenêtre visible et le reste jusqu'à la fin du traitement.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(HERE, "browser-profile")
LEGACY_PROFILE_DIR = os.path.join(HERE, "amazon-profile")


def migrate_profile(profile=PROFILE_DIR, legacy=LEGACY_PROFILE_DIR):
    """amazon-profile/ devient browser-profile/, une seule fois."""
    if os.path.isdir(legacy) and not os.path.exists(profile):
        os.rename(legacy, profile)


class ChromeSession:
    def __init__(self, profile=PROFILE_DIR):
        self.profile = profile
        self.headless = True
        self._playwright = None
        self._context = None
        self._pages = {}

    def _launch(self, headless):
        from playwright.sync_api import sync_playwright
        if self._playwright is None:
            migrate_profile(self.profile)
            self._playwright = sync_playwright().start()
        if self._context is not None:
            self._context.close()
        self._context = self._playwright.chromium.launch_persistent_context(
            self.profile, channel="chrome", headless=headless, accept_downloads=True)
        self._pages = {}
        self.headless = headless

    @property
    def context(self):
        if self._context is None:
            self._launch(self.headless)
        return self._context

    def page(self, key):
        """Un onglet par site, recréé si la session a été relancée."""
        page = self._pages.get(key)
        if page is None or page.is_closed():
            context = self.context
            free = [p for p in context.pages if p not in self._pages.values()]
            page = free[0] if free else context.new_page()
            self._pages[key] = page
        return page

    def show(self):
        """Relance avec une fenêtre visible (connexion demandée)."""
        if self.headless or self._context is None:
            self._launch(headless=False)

    def close(self):
        try:
            if self._context is not None:
                self._context.close()
            if self._playwright is not None:
                self._playwright.stop()
        finally:
            self._context = self._playwright = None
            self._pages = {}
            self.headless = True


SESSION = ChromeSession()


class SiteBrowser:
    """
    Un site dans la session commune. Une sous-classe donne `name` (affiché à
    l'utilisateur), `home_url`, `_logged_in()` et `_on_login_page()`.
    Si le site demande une connexion, la fenêtre s'affiche et on attend sans
    limite (A4 de la spec 001).
    """

    name = ""
    home_url = ""

    def __init__(self, notify=print, session=None):
        self.notify = notify
        self.session = session or SESSION
        self._page = None

    def _logged_in(self):
        raise NotImplementedError

    def _on_login_page(self):
        raise NotImplementedError

    def _goto_home(self):
        self._page = self.session.page(self.name)
        self._page.goto(self.home_url, wait_until="domcontentloaded")
        self._settle()

    def _settle(self):
        """Laisse le site rediriger vers sa page de connexion s'il le doit."""

    def _wait_login(self):
        """Hors des pages de connexion (identifiant, code SMS…), on revient à l'accueil du site."""
        while not self._logged_in():
            self._page.wait_for_timeout(2000)
            if not self._on_login_page() and not self._logged_in():
                try:
                    self._page.goto(self.home_url, wait_until="domcontentloaded")
                except Exception:
                    pass

    def open(self):
        self._goto_home()
        if self._logged_in():
            return
        self.session.show()
        self._goto_home()
        if self._logged_in():
            return
        self.notify(f"{self.name} : connecte-toi à {self.name} dans la fenêtre Chrome ouverte, l'application attend.")
        self._wait_login()
        self.notify(f"{self.name} : connexion détectée, reprise.")

    @property
    def context(self):
        return self.session.context

    def close(self):
        self.session.close()
        self._page = None
