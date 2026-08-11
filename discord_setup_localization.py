"""Owner-reviewed, interface-only localization for the Discord /setup wizard."""

SETUP_SUPPORTED_LANGUAGES = {"en", "de", "fr", "es", "pl"}


SETUP_TEXT = {
    "en": {
        "platform_xbox_desc": "DayZXB mission files",
        "platform_playstation_desc": "DayZPS mission files",
        "platform_pc_desc": "DayZPC/MP missions; optional BattlEye RCon",
        "mode_pve_label": "PVE only", "mode_pve_desc": "No player-versus-player play",
        "mode_hybrid_label": "Hybrid", "mode_hybrid_desc": "PVP and PVE features",
        "mode_pvp_label": "PVP only", "mode_pvp_desc": "Player-versus-player focused",
        "channel_essentials_label": "Essentials (recommended)", "channel_essentials_desc": "A small starter set; add more later",
        "channel_live_label": "Live feeds", "channel_live_desc": "Killfeed and live server activity",
        "channel_community_label": "Community", "channel_community_desc": "Welcome, links, clips and community",
        "channel_staff_label": "Staff", "channel_staff_desc": "Private staff and audit routes",
        "channel_economy_label": "Economy", "channel_economy_desc": "Shop, purchases and rentals",
        "channel_factions_label": "Factions", "channel_factions_desc": "Faction chat, tickets and staff",
        "channel_pve_label": "PVE", "channel_pve_desc": "Quests, hunting and expeditions",
        "channel_full_label": "Full", "channel_full_desc": "Every channel included by the plan",
        "channel_custom_label": "Custom list", "channel_custom_desc": "Enter exact channel keys in Advanced",
        "choose_platform": "Choose Xbox, PlayStation or PC", "choose_map": "Choose the DayZ map",
        "choose_mode": "Choose PVE, PVP or Hybrid", "choose_channels": "Choose the starter channel pack",
        "platform_saved": "Platform saved. Now choose the map and server style.", "selection_updated": "Selection updated.",
        "credentials_title": "Connect Nitrado and FTP", "token_label": "Nitrado API token",
        "token_placeholder": "Paste the token from Nitrado API access", "service_label": "Nitrado service ID",
        "service_placeholder": "Numbers only, from the service page", "nitrado_user_label": "Nitrado account/FTP user",
        "nitrado_user_placeholder": "Example: ni12248929_2", "ftp_user_label": "FTP login username",
        "ftp_user_placeholder": "The FTP username shown by Nitrado", "ftp_password_label": "FTP password",
        "ftp_password_placeholder": "The FTP password shown by Nitrado", "already_saved": "Already supplied - blank keeps it",
        "credentials_saved": "Credentials captured privately. Values are hidden from the review.",
        "advanced_title": "Advanced and PC options", "ftp_host_label": "Optional FTP host or IP",
        "ftp_host_placeholder": "Blank uses Nitrado discovery / keeps saved host", "rcon_host_label": "PC only: BattlEye RCon host",
        "rcon_host_placeholder": "Blank keeps RCon unchanged/disabled", "rcon_port_label": "PC only: BattlEye RCon port",
        "rcon_port_placeholder": "Port from BEServer_x64.cfg", "rcon_password_label": "PC only: BattlEye RCon password",
        "rcon_password_placeholder": "Blank keeps the saved password", "custom_channels_label": "Custom channel keys (Custom list only)",
        "custom_channels_placeholder": "killfeed, online, radar", "advanced_saved": "Advanced choices captured. RCon is used only when PC is selected.",
        "wrong_user": "This private setup belongs to the administrator who opened it.",
        "wrong_server": "Open `/setup` inside the server you want to configure.", "previous_step": "Previous step restored.",
        "review_notice": "Review these choices. Confirm applies them; Back changes them.",
        "step_1": "First, choose where this DayZ server runs: Xbox, PlayStation or PC.",
        "step_2": "Now choose the map and whether the server is PVE, PVP or Hybrid.",
        "step_3": "Choose a small channel pack. You can enable more feeds later from the dashboard.",
        "step_4": "Open the private credentials pop-up, then review the finished setup.",
        "cancel": "Cancel", "back": "Back", "continue": "Continue", "credentials_button": "Enter Nitrado and FTP",
        "advanced_pc": "PC RCon / Advanced", "advanced_console": "Advanced FTP host", "review_button": "Review setup",
        "ready": "Ready", "still_needed": "Still needed: {items}", "optional": "Optional / not configured",
        "review_title": "WANDERING BOT SETUP REVIEW", "step_title": "WANDERING BOT SETUP - STEP {step} OF 4",
        "private_description": "Private guided setup for **{guild}**.\nNothing changes until the final Confirm button is pressed.",
        "server": "SERVER", "connection": "CONNECTION", "discord_channels": "DISCORD CHANNELS",
        "platform": "Platform", "map": "Map", "style": "Style", "pack": "Pack", "warning": "Warning",
        "will_enable": "Will enable **{count}** included channel routes.",
        "more_feeds": "More feeds can be enabled later from Dashboard -> Feed Routing.",
        "progress": "PROGRESS", "progress_platform": "Platform", "progress_server": "Map and style",
        "progress_channels": "Channels", "progress_connection": "Connection", "selected_platform": "SELECTED PLATFORM",
        "selected_server": "SELECTED SERVER", "channel_pack": "CHANNEL PACK", "credentials": "CREDENTIALS",
        "what_to_do": "WHAT TO DO", "private_footer": "Only you can see and control this setup - times out after 15 minutes",
        "cancelled_title": "SETUP CANCELLED", "cancelled_desc": "Nothing was changed. Run `/setup` whenever you are ready.",
        "change_notice": "Change any choice, then press Review again.", "confirm": "Confirm setup",
        "complete_title": "SETUP COMPLETE", "complete_desc": "Wandering Bot is connected. Only the selected channel pack was enabled.\n\nUse the dashboard Feed Routing page whenever you want to add or remove feeds.",
        "guild_only": "Run `/setup` inside the Discord server you want to connect.",
        "admin_only": "Only the Discord server owner or an administrator can run setup.",
    },
    "de": {
        "platform_xbox_desc": "DayZXB-Missionsdateien", "platform_playstation_desc": "DayZPS-Missionsdateien", "platform_pc_desc": "DayZPC/MP-Missionen; optional BattlEye RCon",
        "mode_pve_label": "Nur PVE", "mode_pve_desc": "Kein Spieler-gegen-Spieler", "mode_hybrid_label": "Hybrid", "mode_hybrid_desc": "PVP- und PVE-Funktionen", "mode_pvp_label": "Nur PVP", "mode_pvp_desc": "Auf Spieler-gegen-Spieler ausgerichtet",
        "channel_essentials_label": "Grundausstattung (empfohlen)", "channel_essentials_desc": "Kleines Startpaket; später erweiterbar", "channel_live_label": "Live-Feeds", "channel_live_desc": "Killfeed und Live-Serveraktivität", "channel_community_label": "Community", "channel_community_desc": "Willkommen, Links, Clips und Community", "channel_staff_label": "Team", "channel_staff_desc": "Private Team- und Prüfkanäle", "channel_economy_label": "Wirtschaft", "channel_economy_desc": "Shop, Käufe und Vermietungen", "channel_factions_label": "Fraktionen", "channel_factions_desc": "Fraktionschat, Tickets und Team", "channel_pve_label": "PVE", "channel_pve_desc": "Quests, Jagd und Expeditionen", "channel_full_label": "Vollständig", "channel_full_desc": "Alle im Tarif enthaltenen Kanäle", "channel_custom_label": "Benutzerdefiniert", "channel_custom_desc": "Exakte Kanalschlüssel unter Erweitert eingeben",
        "choose_platform": "Xbox, PlayStation oder PC wählen", "choose_map": "DayZ-Karte wählen", "choose_mode": "PVE, PVP oder Hybrid wählen", "choose_channels": "Start-Kanalpaket wählen", "platform_saved": "Plattform gespeichert. Wähle jetzt Karte und Serverstil.", "selection_updated": "Auswahl aktualisiert.",
        "credentials_title": "Nitrado und FTP verbinden", "token_label": "Nitrado-API-Token", "token_placeholder": "Token aus dem Nitrado-API-Zugang einfügen", "service_label": "Nitrado-Service-ID", "service_placeholder": "Nur Zahlen von der Serviceseite", "nitrado_user_label": "Nitrado-Konto/FTP-Benutzer", "nitrado_user_placeholder": "Beispiel: ni12248929_2", "ftp_user_label": "FTP-Benutzername", "ftp_user_placeholder": "Von Nitrado angezeigter FTP-Benutzer", "ftp_password_label": "FTP-Passwort", "ftp_password_placeholder": "Von Nitrado angezeigtes FTP-Passwort", "already_saved": "Bereits gespeichert - leer lassen zum Beibehalten", "credentials_saved": "Zugangsdaten wurden privat erfasst und in der Prüfung ausgeblendet.",
        "advanced_title": "Erweiterte und PC-Optionen", "ftp_host_label": "Optionaler FTP-Host oder IP", "ftp_host_placeholder": "Leer nutzt Nitrado-Erkennung / behält gespeicherten Host", "rcon_host_label": "Nur PC: BattlEye-RCon-Host", "rcon_host_placeholder": "Leer lässt RCon unverändert/deaktiviert", "rcon_port_label": "Nur PC: BattlEye-RCon-Port", "rcon_port_placeholder": "Port aus BEServer_x64.cfg", "rcon_password_label": "Nur PC: BattlEye-RCon-Passwort", "rcon_password_placeholder": "Leer behält das gespeicherte Passwort", "custom_channels_label": "Eigene Kanalschlüssel (nur benutzerdefiniert)", "custom_channels_placeholder": "killfeed, online, radar", "advanced_saved": "Erweiterte Auswahl gespeichert. RCon wird nur bei PC verwendet.",
        "wrong_user": "Diese private Einrichtung gehört dem Administrator, der sie geöffnet hat.", "wrong_server": "Öffne `/setup` in dem Server, den du konfigurieren möchtest.", "previous_step": "Vorheriger Schritt wiederhergestellt.", "review_notice": "Prüfe die Auswahl. Bestätigen übernimmt sie; Zurück ändert sie.",
        "step_1": "Wähle zuerst, wo der DayZ-Server läuft: Xbox, PlayStation oder PC.", "step_2": "Wähle Karte und PVE, PVP oder Hybrid.", "step_3": "Wähle ein kleines Kanalpaket. Weitere Feeds können später im Dashboard aktiviert werden.", "step_4": "Öffne das private Zugangsdaten-Fenster und prüfe danach die Einrichtung.",
        "cancel": "Abbrechen", "back": "Zurück", "continue": "Weiter", "credentials_button": "Nitrado und FTP eingeben", "advanced_pc": "PC RCon / Erweitert", "advanced_console": "Erweiterter FTP-Host", "review_button": "Einrichtung prüfen", "ready": "Bereit", "still_needed": "Noch erforderlich: {items}", "optional": "Optional / nicht eingerichtet",
        "review_title": "WANDERING BOT – EINRICHTUNG PRÜFEN", "step_title": "WANDERING BOT – SCHRITT {step} VON 4", "private_description": "Private geführte Einrichtung für **{guild}**.\nBis zur endgültigen Bestätigung wird nichts geändert.", "server": "SERVER", "connection": "VERBINDUNG", "discord_channels": "DISCORD-KANÄLE", "platform": "Plattform", "map": "Karte", "style": "Stil", "pack": "Paket", "warning": "Warnung", "will_enable": "Aktiviert **{count}** enthaltene Kanalrouten.", "more_feeds": "Weitere Feeds können später unter Dashboard -> Feed Routing aktiviert werden.", "progress": "FORTSCHRITT", "progress_platform": "Plattform", "progress_server": "Karte und Stil", "progress_channels": "Kanäle", "progress_connection": "Verbindung", "selected_platform": "GEWÄHLTE PLATTFORM", "selected_server": "GEWÄHLTER SERVER", "channel_pack": "KANALPAKET", "credentials": "ZUGANGSDATEN", "what_to_do": "NÄCHSTER SCHRITT", "private_footer": "Nur du kannst diese Einrichtung sehen und bedienen – Zeitlimit 15 Minuten", "cancelled_title": "EINRICHTUNG ABGEBROCHEN", "cancelled_desc": "Es wurde nichts geändert. Starte `/setup`, wenn du bereit bist.", "change_notice": "Ändere die Auswahl und drücke erneut auf Prüfen.", "confirm": "Einrichtung bestätigen", "complete_title": "EINRICHTUNG ABGESCHLOSSEN", "complete_desc": "Wandering Bot ist verbunden. Nur das gewählte Kanalpaket wurde aktiviert.\n\nFeeds können jederzeit unter Feed Routing im Dashboard geändert werden.", "guild_only": "Führe `/setup` in dem Discord-Server aus, den du verbinden möchtest.", "admin_only": "Nur der Serverbesitzer oder ein Administrator kann die Einrichtung starten.",
    },
    "fr": {
        "platform_xbox_desc": "Fichiers de mission DayZXB", "platform_playstation_desc": "Fichiers de mission DayZPS", "platform_pc_desc": "Missions DayZPC/MP ; BattlEye RCon facultatif", "mode_pve_label": "PVE uniquement", "mode_pve_desc": "Aucun combat entre joueurs", "mode_hybrid_label": "Hybride", "mode_hybrid_desc": "Fonctions PVP et PVE", "mode_pvp_label": "PVP uniquement", "mode_pvp_desc": "Axé sur le combat entre joueurs",
        "channel_essentials_label": "Essentiels (recommandé)", "channel_essentials_desc": "Petit ensemble de départ ; extensible ensuite", "channel_live_label": "Flux en direct", "channel_live_desc": "Killfeed et activité du serveur", "channel_community_label": "Communauté", "channel_community_desc": "Accueil, liens, clips et communauté", "channel_staff_label": "Équipe", "channel_staff_desc": "Canaux privés d’équipe et d’audit", "channel_economy_label": "Économie", "channel_economy_desc": "Boutique, achats et locations", "channel_factions_label": "Factions", "channel_factions_desc": "Chat, tickets et équipe des factions", "channel_pve_label": "PVE", "channel_pve_desc": "Quêtes, chasse et expéditions", "channel_full_label": "Complet", "channel_full_desc": "Tous les canaux inclus dans l’offre", "channel_custom_label": "Liste personnalisée", "channel_custom_desc": "Saisir les clés exactes dans Avancé",
        "choose_platform": "Choisissez Xbox, PlayStation ou PC", "choose_map": "Choisissez la carte DayZ", "choose_mode": "Choisissez PVE, PVP ou Hybride", "choose_channels": "Choisissez les canaux de départ", "platform_saved": "Plateforme enregistrée. Choisissez maintenant la carte et le style.", "selection_updated": "Sélection mise à jour.", "credentials_title": "Connecter Nitrado et FTP", "token_label": "Jeton API Nitrado", "token_placeholder": "Collez le jeton d’accès API Nitrado", "service_label": "ID du service Nitrado", "service_placeholder": "Chiffres uniquement, depuis la page du service", "nitrado_user_label": "Compte Nitrado/utilisateur FTP", "nitrado_user_placeholder": "Exemple : ni12248929_2", "ftp_user_label": "Nom d’utilisateur FTP", "ftp_user_placeholder": "Utilisateur FTP affiché par Nitrado", "ftp_password_label": "Mot de passe FTP", "ftp_password_placeholder": "Mot de passe FTP affiché par Nitrado", "already_saved": "Déjà enregistré – laissez vide pour conserver", "credentials_saved": "Identifiants saisis en privé et masqués dans la vérification.",
        "advanced_title": "Options avancées et PC", "ftp_host_label": "Hôte ou IP FTP facultatif", "ftp_host_placeholder": "Vide : détection Nitrado / conserve l’hôte", "rcon_host_label": "PC uniquement : hôte BattlEye RCon", "rcon_host_placeholder": "Vide : RCon inchangé/désactivé", "rcon_port_label": "PC uniquement : port BattlEye RCon", "rcon_port_placeholder": "Port de BEServer_x64.cfg", "rcon_password_label": "PC uniquement : mot de passe RCon", "rcon_password_placeholder": "Vide : conserve le mot de passe", "custom_channels_label": "Clés de canaux personnalisées", "custom_channels_placeholder": "killfeed, online, radar", "advanced_saved": "Options avancées enregistrées. RCon n’est utilisé que sur PC.",
        "wrong_user": "Cette configuration privée appartient à l’administrateur qui l’a ouverte.", "wrong_server": "Ouvrez `/setup` dans le serveur à configurer.", "previous_step": "Étape précédente restaurée.", "review_notice": "Vérifiez les choix. Confirmer les applique ; Retour permet de les modifier.", "step_1": "Choisissez d’abord la plateforme : Xbox, PlayStation ou PC.", "step_2": "Choisissez la carte et le mode PVE, PVP ou Hybride.", "step_3": "Choisissez quelques canaux. D’autres flux peuvent être activés plus tard.", "step_4": "Ouvrez la fenêtre privée des identifiants, puis vérifiez la configuration.", "cancel": "Annuler", "back": "Retour", "continue": "Continuer", "credentials_button": "Saisir Nitrado et FTP", "advanced_pc": "PC RCon / Avancé", "advanced_console": "Hôte FTP avancé", "review_button": "Vérifier", "ready": "Prêt", "still_needed": "Encore requis : {items}", "optional": "Facultatif / non configuré", "review_title": "VÉRIFICATION DE LA CONFIGURATION", "step_title": "CONFIGURATION WANDERING BOT – ÉTAPE {step} SUR 4", "private_description": "Configuration guidée privée pour **{guild}**.\nRien ne change avant la confirmation finale.", "server": "SERVEUR", "connection": "CONNEXION", "discord_channels": "CANAUX DISCORD", "platform": "Plateforme", "map": "Carte", "style": "Style", "pack": "Ensemble", "warning": "Avertissement", "will_enable": "Active **{count}** canaux inclus.", "more_feeds": "D’autres flux peuvent être activés dans Dashboard -> Feed Routing.", "progress": "PROGRESSION", "progress_platform": "Plateforme", "progress_server": "Carte et style", "progress_channels": "Canaux", "progress_connection": "Connexion", "selected_platform": "PLATEFORME CHOISIE", "selected_server": "SERVEUR CHOISI", "channel_pack": "ENSEMBLE DE CANAUX", "credentials": "IDENTIFIANTS", "what_to_do": "À FAIRE", "private_footer": "Visible et contrôlable uniquement par vous – expiration après 15 minutes", "cancelled_title": "CONFIGURATION ANNULÉE", "cancelled_desc": "Rien n’a été modifié. Relancez `/setup` quand vous êtes prêt.", "change_notice": "Modifiez les choix puis appuyez à nouveau sur Vérifier.", "confirm": "Confirmer", "complete_title": "CONFIGURATION TERMINÉE", "complete_desc": "Wandering Bot est connecté. Seuls les canaux choisis ont été activés.\n\nModifiez les flux depuis Feed Routing dans le tableau de bord.", "guild_only": "Exécutez `/setup` dans le serveur Discord à connecter.", "admin_only": "Seul le propriétaire ou un administrateur peut lancer la configuration.",
    },
    "es": {
        "platform_xbox_desc": "Archivos de misión DayZXB", "platform_playstation_desc": "Archivos de misión DayZPS", "platform_pc_desc": "Misiones DayZPC/MP; BattlEye RCon opcional", "mode_pve_label": "Solo PVE", "mode_pve_desc": "Sin combate entre jugadores", "mode_hybrid_label": "Híbrido", "mode_hybrid_desc": "Funciones PVP y PVE", "mode_pvp_label": "Solo PVP", "mode_pvp_desc": "Centrado en combate entre jugadores",
        "channel_essentials_label": "Esenciales (recomendado)", "channel_essentials_desc": "Conjunto inicial pequeño; amplíalo después", "channel_live_label": "Feeds en directo", "channel_live_desc": "Killfeed y actividad del servidor", "channel_community_label": "Comunidad", "channel_community_desc": "Bienvenida, enlaces, clips y comunidad", "channel_staff_label": "Equipo", "channel_staff_desc": "Canales privados de equipo y auditoría", "channel_economy_label": "Economía", "channel_economy_desc": "Tienda, compras y alquileres", "channel_factions_label": "Facciones", "channel_factions_desc": "Chat, tickets y equipo de facciones", "channel_pve_label": "PVE", "channel_pve_desc": "Misiones, caza y expediciones", "channel_full_label": "Completo", "channel_full_desc": "Todos los canales incluidos en el plan", "channel_custom_label": "Lista personalizada", "channel_custom_desc": "Introduce las claves exactas en Avanzado",
        "choose_platform": "Elige Xbox, PlayStation o PC", "choose_map": "Elige el mapa de DayZ", "choose_mode": "Elige PVE, PVP o Híbrido", "choose_channels": "Elige los canales iniciales", "platform_saved": "Plataforma guardada. Ahora elige mapa y estilo.", "selection_updated": "Selección actualizada.", "credentials_title": "Conectar Nitrado y FTP", "token_label": "Token API de Nitrado", "token_placeholder": "Pega el token de acceso API de Nitrado", "service_label": "ID de servicio de Nitrado", "service_placeholder": "Solo números de la página del servicio", "nitrado_user_label": "Cuenta Nitrado/usuario FTP", "nitrado_user_placeholder": "Ejemplo: ni12248929_2", "ftp_user_label": "Usuario FTP", "ftp_user_placeholder": "Usuario FTP mostrado por Nitrado", "ftp_password_label": "Contraseña FTP", "ftp_password_placeholder": "Contraseña FTP mostrada por Nitrado", "already_saved": "Ya guardado; déjalo vacío para conservarlo", "credentials_saved": "Credenciales capturadas en privado y ocultas en la revisión.",
        "advanced_title": "Opciones avanzadas y de PC", "ftp_host_label": "Host o IP FTP opcional", "ftp_host_placeholder": "Vacío: detección Nitrado / conserva el host", "rcon_host_label": "Solo PC: host BattlEye RCon", "rcon_host_placeholder": "Vacío: RCon sin cambios/desactivado", "rcon_port_label": "Solo PC: puerto BattlEye RCon", "rcon_port_placeholder": "Puerto de BEServer_x64.cfg", "rcon_password_label": "Solo PC: contraseña RCon", "rcon_password_placeholder": "Vacío: conserva la contraseña", "custom_channels_label": "Claves de canales personalizadas", "custom_channels_placeholder": "killfeed, online, radar", "advanced_saved": "Opciones avanzadas guardadas. RCon solo se usa al elegir PC.",
        "wrong_user": "Esta configuración privada pertenece al administrador que la abrió.", "wrong_server": "Abre `/setup` en el servidor que quieras configurar.", "previous_step": "Paso anterior restaurado.", "review_notice": "Revisa las opciones. Confirmar las aplica; Atrás permite cambiarlas.", "step_1": "Primero elige la plataforma: Xbox, PlayStation o PC.", "step_2": "Elige mapa y modo PVE, PVP o Híbrido.", "step_3": "Elige pocos canales. Podrás activar más feeds desde el panel.", "step_4": "Abre la ventana privada de credenciales y revisa la configuración.", "cancel": "Cancelar", "back": "Atrás", "continue": "Continuar", "credentials_button": "Introducir Nitrado y FTP", "advanced_pc": "PC RCon / Avanzado", "advanced_console": "Host FTP avanzado", "review_button": "Revisar", "ready": "Listo", "still_needed": "Aún necesario: {items}", "optional": "Opcional / no configurado", "review_title": "REVISIÓN DE CONFIGURACIÓN", "step_title": "CONFIGURACIÓN WANDERING BOT – PASO {step} DE 4", "private_description": "Configuración guiada privada para **{guild}**.\nNada cambia hasta pulsar Confirmar.", "server": "SERVIDOR", "connection": "CONEXIÓN", "discord_channels": "CANALES DE DISCORD", "platform": "Plataforma", "map": "Mapa", "style": "Estilo", "pack": "Paquete", "warning": "Aviso", "will_enable": "Activará **{count}** rutas de canal incluidas.", "more_feeds": "Puedes activar más feeds desde Dashboard -> Feed Routing.", "progress": "PROGRESO", "progress_platform": "Plataforma", "progress_server": "Mapa y estilo", "progress_channels": "Canales", "progress_connection": "Conexión", "selected_platform": "PLATAFORMA ELEGIDA", "selected_server": "SERVIDOR ELEGIDO", "channel_pack": "PAQUETE DE CANALES", "credentials": "CREDENCIALES", "what_to_do": "QUÉ HACER", "private_footer": "Solo tú puedes ver y controlar esto; caduca en 15 minutos", "cancelled_title": "CONFIGURACIÓN CANCELADA", "cancelled_desc": "No se cambió nada. Ejecuta `/setup` cuando estés listo.", "change_notice": "Cambia las opciones y vuelve a pulsar Revisar.", "confirm": "Confirmar configuración", "complete_title": "CONFIGURACIÓN COMPLETA", "complete_desc": "Wandering Bot está conectado. Solo se activó el paquete elegido.\n\nCambia los feeds en Feed Routing del panel.", "guild_only": "Ejecuta `/setup` en el servidor de Discord que quieras conectar.", "admin_only": "Solo el propietario o un administrador puede iniciar la configuración.",
    },
    "pl": {
        "platform_xbox_desc": "Pliki misji DayZXB", "platform_playstation_desc": "Pliki misji DayZPS", "platform_pc_desc": "Misje DayZPC/MP; opcjonalny BattlEye RCon", "mode_pve_label": "Tylko PVE", "mode_pve_desc": "Bez walki między graczami", "mode_hybrid_label": "Hybrydowy", "mode_hybrid_desc": "Funkcje PVP i PVE", "mode_pvp_label": "Tylko PVP", "mode_pvp_desc": "Nastawiony na walkę graczy",
        "channel_essentials_label": "Podstawowe (zalecane)", "channel_essentials_desc": "Mały zestaw startowy; rozbuduj później", "channel_live_label": "Kanały na żywo", "channel_live_desc": "Killfeed i aktywność serwera", "channel_community_label": "Społeczność", "channel_community_desc": "Powitanie, linki, klipy i społeczność", "channel_staff_label": "Administracja", "channel_staff_desc": "Prywatne kanały obsługi i audytu", "channel_economy_label": "Ekonomia", "channel_economy_desc": "Sklep, zakupy i wynajem", "channel_factions_label": "Frakcje", "channel_factions_desc": "Czat, zgłoszenia i obsługa frakcji", "channel_pve_label": "PVE", "channel_pve_desc": "Zadania, polowania i wyprawy", "channel_full_label": "Pełny", "channel_full_desc": "Wszystkie kanały zawarte w planie", "channel_custom_label": "Lista własna", "channel_custom_desc": "Wpisz dokładne klucze w Zaawansowanych",
        "choose_platform": "Wybierz Xbox, PlayStation lub PC", "choose_map": "Wybierz mapę DayZ", "choose_mode": "Wybierz PVE, PVP lub tryb hybrydowy", "choose_channels": "Wybierz początkowe kanały", "platform_saved": "Platforma zapisana. Teraz wybierz mapę i styl.", "selection_updated": "Wybór zaktualizowany.", "credentials_title": "Połącz Nitrado i FTP", "token_label": "Token API Nitrado", "token_placeholder": "Wklej token dostępu API Nitrado", "service_label": "ID usługi Nitrado", "service_placeholder": "Tylko cyfry ze strony usługi", "nitrado_user_label": "Konto Nitrado/użytkownik FTP", "nitrado_user_placeholder": "Przykład: ni12248929_2", "ftp_user_label": "Nazwa użytkownika FTP", "ftp_user_placeholder": "Użytkownik FTP pokazany przez Nitrado", "ftp_password_label": "Hasło FTP", "ftp_password_placeholder": "Hasło FTP pokazane przez Nitrado", "already_saved": "Już zapisano — pozostaw puste, aby zachować", "credentials_saved": "Dane zapisano prywatnie i ukryto w podsumowaniu.",
        "advanced_title": "Opcje zaawansowane i PC", "ftp_host_label": "Opcjonalny host lub IP FTP", "ftp_host_placeholder": "Puste: wykrywanie Nitrado / zachowuje host", "rcon_host_label": "Tylko PC: host BattlEye RCon", "rcon_host_placeholder": "Puste: RCon bez zmian/wyłączony", "rcon_port_label": "Tylko PC: port BattlEye RCon", "rcon_port_placeholder": "Port z BEServer_x64.cfg", "rcon_password_label": "Tylko PC: hasło RCon", "rcon_password_placeholder": "Puste: zachowuje zapisane hasło", "custom_channels_label": "Własne klucze kanałów", "custom_channels_placeholder": "killfeed, online, radar", "advanced_saved": "Opcje zaawansowane zapisane. RCon działa tylko dla PC.",
        "wrong_user": "Ta prywatna konfiguracja należy do administratora, który ją otworzył.", "wrong_server": "Otwórz `/setup` na serwerze, który chcesz skonfigurować.", "previous_step": "Przywrócono poprzedni krok.", "review_notice": "Sprawdź wybór. Potwierdź, aby zastosować; Wstecz, aby zmienić.", "step_1": "Najpierw wybierz platformę: Xbox, PlayStation lub PC.", "step_2": "Wybierz mapę oraz PVE, PVP lub tryb hybrydowy.", "step_3": "Wybierz mały pakiet kanałów. Więcej włączysz później w panelu.", "step_4": "Otwórz prywatne okno danych logowania, a potem sprawdź konfigurację.", "cancel": "Anuluj", "back": "Wstecz", "continue": "Dalej", "credentials_button": "Wpisz Nitrado i FTP", "advanced_pc": "PC RCon / Zaawansowane", "advanced_console": "Zaawansowany host FTP", "review_button": "Sprawdź konfigurację", "ready": "Gotowe", "still_needed": "Nadal wymagane: {items}", "optional": "Opcjonalne / nieskonfigurowane", "review_title": "SPRAWDZENIE KONFIGURACJI", "step_title": "KONFIGURACJA WANDERING BOT – KROK {step} Z 4", "private_description": "Prywatna konfiguracja dla **{guild}**.\nNic nie zmieni się przed ostatecznym potwierdzeniem.", "server": "SERWER", "connection": "POŁĄCZENIE", "discord_channels": "KANAŁY DISCORD", "platform": "Platforma", "map": "Mapa", "style": "Styl", "pack": "Pakiet", "warning": "Ostrzeżenie", "will_enable": "Włączy **{count}** zawartych tras kanałów.", "more_feeds": "Więcej kanałów można włączyć w Dashboard -> Feed Routing.", "progress": "POSTĘP", "progress_platform": "Platforma", "progress_server": "Mapa i styl", "progress_channels": "Kanały", "progress_connection": "Połączenie", "selected_platform": "WYBRANA PLATFORMA", "selected_server": "WYBRANY SERWER", "channel_pack": "PAKIET KANAŁÓW", "credentials": "DANE LOGOWANIA", "what_to_do": "CO ZROBIĆ", "private_footer": "Tylko Ty widzisz i kontrolujesz tę konfigurację — wygasa po 15 minutach", "cancelled_title": "KONFIGURACJA ANULOWANA", "cancelled_desc": "Nic nie zmieniono. Uruchom `/setup`, gdy będziesz gotowy.", "change_notice": "Zmień wybór i ponownie kliknij Sprawdź.", "confirm": "Potwierdź konfigurację", "complete_title": "KONFIGURACJA GOTOWA", "complete_desc": "Wandering Bot jest połączony. Włączono tylko wybrany pakiet kanałów.\n\nKanały zmienisz w Feed Routing w panelu.", "guild_only": "Uruchom `/setup` na serwerze Discord, który chcesz połączyć.", "admin_only": "Tylko właściciel serwera lub administrator może rozpocząć konfigurację.",
    },
}


SETUP_RUNTIME_TEXT = {
    "en": {
        "invalid_ftp_host": "That FTP host does not look valid. Use only the host/IP shown by Nitrado, not a full URL or file path.",
        "invalid_channel_selection": "The channel selection is not valid. Check the chosen pack or the exact custom channel keys.",
        "channels_outside_plan": "These channels are not included in this subscription's automatic Discord pack: {channels}. Use Dashboard -> Feed Routing for an available feed, or upgrade the plan.",
        "missing_setup": "This server has no saved setup for: {items}. Open the private credentials step in `/setup` and enter the Nitrado/API/FTP details.",
        "invalid_nitrado_token": "The Nitrado API token is not valid. Copy the complete token from Nitrado API access and try again.",
        "invalid_service_id": "The Nitrado service ID must contain numbers only.",
        "invalid_credential": "The value for {field} is not valid. Check it against the value shown by Nitrado and try again.",
        "rcon_pc_only": "BattlEye RCon is only used for PC servers. Select PC before saving RCon details.",
        "rcon_all_required": "PC BattlEye RCon needs all three values: rcon_host, rcon_port and rcon_password. Leave all three blank to keep RCon disabled.",
        "invalid_rcon_host": "The BattlEye RCon host is not valid. Enter only the host name or IP address.",
        "invalid_rcon_port": "rcon_port must be a number between 1 and 65535.",
        "invalid_rcon_password": "The BattlEye RCon password is not valid. Copy it exactly from BEServer_x64.cfg.",
        "connected": "Wandering Bot is fully connected and operational. Server mode: `{mode}`.",
        "dashboard_new": "Dashboard URL: {url}\nDashboard ID: `{dashboard_id}`\nDashboard password: `{password}`\n\nSave this password now. It will not be shown again. Use `/dashboardcredentials reset:true` if you need a new one.",
        "dashboard_existing": "Dashboard URL: {url}\nDashboard ID: `{dashboard_id}`\nPassword already exists and was not changed. Use `/dashboardcredentials reset:true` if you need a new one.",
        "routes": "routes",
    },
    "de": {
        "invalid_ftp_host": "Dieser FTP-Host ist ungültig. Verwende nur den von Nitrado angezeigten Host oder die IP, keine vollständige URL oder einen Dateipfad.",
        "invalid_channel_selection": "Die Kanalauswahl ist ungültig. Prüfe das Paket oder die genauen benutzerdefinierten Kanalschlüssel.",
        "channels_outside_plan": "Diese Kanäle sind nicht im automatischen Discord-Paket dieses Tarifs enthalten: {channels}. Nutze Dashboard -> Feed Routing für verfügbare Feeds oder wechsle den Tarif.",
        "missing_setup": "Für diesen Server fehlen gespeicherte Einrichtungsdaten: {items}. Öffne in `/setup` den privaten Zugangsdaten-Schritt und trage Nitrado/API/FTP ein.",
        "invalid_nitrado_token": "Der Nitrado-API-Token ist ungültig. Kopiere den vollständigen Token aus dem Nitrado-API-Zugang.",
        "invalid_service_id": "Die Nitrado-Service-ID darf nur Zahlen enthalten.",
        "invalid_credential": "Der Wert für {field} ist ungültig. Vergleiche ihn mit dem bei Nitrado angezeigten Wert.",
        "rcon_pc_only": "BattlEye RCon wird nur für PC-Server verwendet. Wähle PC, bevor du RCon-Daten speicherst.",
        "rcon_all_required": "PC BattlEye RCon benötigt alle drei Werte: rcon_host, rcon_port und rcon_password. Lasse alle drei leer, um RCon deaktiviert zu lassen.",
        "invalid_rcon_host": "Der BattlEye-RCon-Host ist ungültig. Gib nur Hostname oder IP-Adresse ein.",
        "invalid_rcon_port": "rcon_port muss eine Zahl zwischen 1 und 65535 sein.",
        "invalid_rcon_password": "Das BattlEye-RCon-Passwort ist ungültig. Kopiere es exakt aus BEServer_x64.cfg.",
        "connected": "Wandering Bot ist vollständig verbunden und betriebsbereit. Servermodus: `{mode}`.",
        "dashboard_new": "Dashboard-URL: {url}\nDashboard-ID: `{dashboard_id}`\nDashboard-Passwort: `{password}`\n\nSpeichere dieses Passwort jetzt. Es wird nicht erneut angezeigt. Mit `/dashboardcredentials reset:true` kannst du ein neues erzeugen.",
        "dashboard_existing": "Dashboard-URL: {url}\nDashboard-ID: `{dashboard_id}`\nDas bestehende Passwort wurde nicht geändert. Mit `/dashboardcredentials reset:true` kannst du ein neues erzeugen.",
        "routes": "Routen",
    },
    "fr": {
        "invalid_ftp_host": "Cet hôte FTP n'est pas valide. Utilisez uniquement l'hôte ou l'IP affiché par Nitrado, sans URL complète ni chemin de fichier.",
        "invalid_channel_selection": "La sélection de canaux n'est pas valide. Vérifiez l'ensemble choisi ou les clés personnalisées exactes.",
        "channels_outside_plan": "Ces canaux ne sont pas inclus dans l'ensemble Discord automatique de cette offre : {channels}. Utilisez Dashboard -> Feed Routing ou changez d'offre.",
        "missing_setup": "Aucune configuration n'est enregistrée pour : {items}. Ouvrez l'étape privée des identifiants dans `/setup` et renseignez Nitrado/API/FTP.",
        "invalid_nitrado_token": "Le jeton API Nitrado n'est pas valide. Copiez le jeton complet depuis l'accès API Nitrado.",
        "invalid_service_id": "L'ID du service Nitrado doit contenir uniquement des chiffres.",
        "invalid_credential": "La valeur de {field} n'est pas valide. Comparez-la à celle affichée par Nitrado.",
        "rcon_pc_only": "BattlEye RCon est réservé aux serveurs PC. Sélectionnez PC avant d'enregistrer RCon.",
        "rcon_all_required": "BattlEye RCon sur PC exige rcon_host, rcon_port et rcon_password. Laissez les trois vides pour désactiver RCon.",
        "invalid_rcon_host": "L'hôte BattlEye RCon n'est pas valide. Saisissez uniquement le nom d'hôte ou l'adresse IP.",
        "invalid_rcon_port": "rcon_port doit être un nombre compris entre 1 et 65535.",
        "invalid_rcon_password": "Le mot de passe BattlEye RCon n'est pas valide. Copiez-le exactement depuis BEServer_x64.cfg.",
        "connected": "Wandering Bot est entièrement connecté et opérationnel. Mode du serveur : `{mode}`.",
        "dashboard_new": "URL du tableau de bord : {url}\nID : `{dashboard_id}`\nMot de passe : `{password}`\n\nEnregistrez ce mot de passe maintenant. Il ne sera plus affiché. Utilisez `/dashboardcredentials reset:true` pour en créer un autre.",
        "dashboard_existing": "URL du tableau de bord : {url}\nID : `{dashboard_id}`\nLe mot de passe existant n'a pas été modifié. Utilisez `/dashboardcredentials reset:true` pour en créer un autre.",
        "routes": "routes",
    },
    "es": {
        "invalid_ftp_host": "Ese host FTP no es válido. Usa solo el host o la IP que muestra Nitrado, no una URL completa ni una ruta de archivo.",
        "invalid_channel_selection": "La selección de canales no es válida. Revisa el paquete o las claves personalizadas exactas.",
        "channels_outside_plan": "Estos canales no están incluidos en el paquete automático de Discord de este plan: {channels}. Usa Dashboard -> Feed Routing o mejora el plan.",
        "missing_setup": "Este servidor no tiene configuración guardada para: {items}. Abre el paso privado de credenciales en `/setup` e introduce Nitrado/API/FTP.",
        "invalid_nitrado_token": "El token API de Nitrado no es válido. Copia el token completo desde el acceso API de Nitrado.",
        "invalid_service_id": "El ID de servicio de Nitrado debe contener solo números.",
        "invalid_credential": "El valor de {field} no es válido. Compáralo con el que muestra Nitrado.",
        "rcon_pc_only": "BattlEye RCon solo se usa en servidores de PC. Elige PC antes de guardar RCon.",
        "rcon_all_required": "BattlEye RCon en PC necesita rcon_host, rcon_port y rcon_password. Deja los tres vacíos para desactivarlo.",
        "invalid_rcon_host": "El host de BattlEye RCon no es válido. Introduce solo el host o la dirección IP.",
        "invalid_rcon_port": "rcon_port debe ser un número entre 1 y 65535.",
        "invalid_rcon_password": "La contraseña de BattlEye RCon no es válida. Cópiala exactamente desde BEServer_x64.cfg.",
        "connected": "Wandering Bot está totalmente conectado y operativo. Modo del servidor: `{mode}`.",
        "dashboard_new": "URL del panel: {url}\nID del panel: `{dashboard_id}`\nContraseña: `{password}`\n\nGuarda esta contraseña ahora. No volverá a mostrarse. Usa `/dashboardcredentials reset:true` para crear otra.",
        "dashboard_existing": "URL del panel: {url}\nID del panel: `{dashboard_id}`\nLa contraseña existente no se modificó. Usa `/dashboardcredentials reset:true` para crear otra.",
        "routes": "rutas",
    },
    "pl": {
        "invalid_ftp_host": "Ten host FTP jest nieprawidłowy. Użyj tylko hosta lub IP pokazanego przez Nitrado, bez pełnego adresu URL ani ścieżki pliku.",
        "invalid_channel_selection": "Wybór kanałów jest nieprawidłowy. Sprawdź pakiet lub dokładne własne klucze kanałów.",
        "channels_outside_plan": "Te kanały nie należą do automatycznego pakietu Discord tego planu: {channels}. Użyj Dashboard -> Feed Routing albo zmień plan.",
        "missing_setup": "Na tym serwerze brakuje zapisanej konfiguracji dla: {items}. Otwórz prywatny krok danych logowania w `/setup` i wpisz Nitrado/API/FTP.",
        "invalid_nitrado_token": "Token API Nitrado jest nieprawidłowy. Skopiuj pełny token z dostępu API Nitrado.",
        "invalid_service_id": "ID usługi Nitrado może zawierać tylko cyfry.",
        "invalid_credential": "Wartość pola {field} jest nieprawidłowa. Porównaj ją z wartością pokazaną przez Nitrado.",
        "rcon_pc_only": "BattlEye RCon działa tylko na serwerach PC. Wybierz PC przed zapisaniem danych RCon.",
        "rcon_all_required": "BattlEye RCon na PC wymaga rcon_host, rcon_port i rcon_password. Zostaw wszystkie trzy puste, aby wyłączyć RCon.",
        "invalid_rcon_host": "Host BattlEye RCon jest nieprawidłowy. Wpisz tylko nazwę hosta lub adres IP.",
        "invalid_rcon_port": "rcon_port musi być liczbą od 1 do 65535.",
        "invalid_rcon_password": "Hasło BattlEye RCon jest nieprawidłowe. Skopiuj je dokładnie z BEServer_x64.cfg.",
        "connected": "Wandering Bot jest w pełni połączony i działa. Tryb serwera: `{mode}`.",
        "dashboard_new": "Adres panelu: {url}\nID panelu: `{dashboard_id}`\nHasło panelu: `{password}`\n\nZapisz to hasło teraz. Nie zostanie pokazane ponownie. Użyj `/dashboardcredentials reset:true`, aby utworzyć nowe.",
        "dashboard_existing": "Adres panelu: {url}\nID panelu: `{dashboard_id}`\nIstniejące hasło nie zostało zmienione. Użyj `/dashboardcredentials reset:true`, aby utworzyć nowe.",
        "routes": "tras",
    },
}

for _language, _phrases in SETUP_RUNTIME_TEXT.items():
    SETUP_TEXT[_language].update(_phrases)


def setup_language_code(locale_value):
    raw = str(locale_value or "en").strip().lower().replace("_", "-")
    primary = raw.split("-", 1)[0]
    return primary if primary in SETUP_SUPPORTED_LANGUAGES else "en"


def setup_interaction_language(interaction):
    locale_value = getattr(interaction, "locale", None) or getattr(interaction, "guild_locale", None) or "en"
    return setup_language_code(locale_value)


def setup_text(language, key, **values):
    language = setup_language_code(language)
    template = SETUP_TEXT.get(language, {}).get(key) or SETUP_TEXT["en"].get(key) or key
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return template


def setup_choice_text(language, prefix, value, fallback_label, fallback_description):
    label = setup_text(language, f"{prefix}_{value}_label")
    description = setup_text(language, f"{prefix}_{value}_desc")
    if label == f"{prefix}_{value}_label":
        label = fallback_label
    if description == f"{prefix}_{value}_desc":
        description = fallback_description
    return label, description
