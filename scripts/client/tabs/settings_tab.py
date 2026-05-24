"""Settings tab with lazy-loaded sub-tabs."""

from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from scripts.client.api_client import ForecastApiClient
from scripts.client.tabs.accounts_tab import AccountsTab
from scripts.client.tabs.bybit_settings_sub_tab import _BybitSettingsSubTab
from scripts.client.tabs.keys_sub_tab import _KeysSubTab
from scripts.client.tabs.prompts_tab import PromptsTab
from scripts.client.tabs.providers_tab import ProvidersTab


class SettingsTab(QWidget):
    """Providers, Prompts, Accounts, Keys and Bybit Settings — one sub-tab loaded at a time."""

    def __init__(self, api: ForecastApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self._loaded_subtabs: set[int] = set()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.sub_tabs = QTabWidget()
        self.providers_tab = ProvidersTab(self.api)
        self.sub_tabs.addTab(self.providers_tab, "🔑 Providers")

        self.prompts_tab = PromptsTab(self.api)
        self.sub_tabs.addTab(self.prompts_tab, "📝 Prompts")

        self.accounts_tab = AccountsTab(self.api)
        self.sub_tabs.addTab(self.accounts_tab, "🏦 Accounts")

        self.keys_tab = _KeysSubTab(self.api)
        self.sub_tabs.addTab(self.keys_tab, "🔐 Keys")

        self.bybit_settings_tab = _BybitSettingsSubTab(self.api)
        self.sub_tabs.addTab(self.bybit_settings_tab, "⚙️ Bybit Settings")

        self.sub_tabs.currentChanged.connect(self._load_sub_tab)
        layout.addWidget(self.sub_tabs)

    def _subtab_loader(self, index: int):
        if index == 0:
            return self.providers_tab.load
        if index == 1:
            return self.prompts_tab.load
        if index == 2:
            return self.accounts_tab.load
        if index == 3:
            return self.keys_tab.load
        if index == 4:
            return self.bybit_settings_tab.load
        return None

    def _load_sub_tab(self, index: int) -> None:
        if index < 0 or index in self._loaded_subtabs:
            return
        loader = self._subtab_loader(index)
        if loader is None:
            return
        self._loaded_subtabs.add(index)
        loader()

    def load(self):
        self._load_sub_tab(self.sub_tabs.currentIndex())

    def set_auto_refresh_enabled(self, enabled: bool) -> None:
        pass


ConfigTab = SettingsTab
