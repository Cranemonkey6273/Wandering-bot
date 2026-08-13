"""Safe, interface-only localization assets for the Wandering Bot web UI.

The browser helper deliberately translates only exact, owner-reviewed interface
phrases.  It never sends content to an external translation service and skips
all code/file editing surfaces so DayZ class names and file data remain exact.
"""

from __future__ import annotations

import json
from pathlib import Path


SUPPORTED_UI_LANGUAGES = {
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "pl": "Polski",
}


UI_TRANSLATIONS = {
    "de": {
        "Interface language": "Oberflächensprache",
        "Interface only. DayZ technical content remains unchanged.": "Nur Benutzeroberfläche. Technische DayZ-Inhalte bleiben unverändert.",
        "Existing users log in": "Bestehende Benutzer anmelden",
        "AI Agent": "KI-Agent",
        "Add Wandering Bot": "Wandering Bot hinzufügen",
        "Read the setup guide": "Einrichtungsanleitung lesen",
        "Browse DayZ crafting": "DayZ-Herstellung durchsuchen",
        "Open existing dashboard": "Vorhandenes Dashboard öffnen",
        "Join support Discord": "Support-Discord beitreten",
        "Email support": "E-Mail-Support",
        "Onboarding": "Einrichtung",
        "Basic access after setup": "Basiszugriff nach der Einrichtung",
        "Invite the bot": "Bot einladen",
        "Check the connection": "Verbindung prüfen",
        "Open the dashboard": "Dashboard öffnen",
        "Bring players in": "Spieler einladen",
        "Free bot access includes": "Kostenloser Bot-Zugang enthält",
        "New server checklist": "Checkliste für neue Server",
        "Everything to prepare before setup": "Alles für die Einrichtung vorbereiten",
        "Discord permissions": "Discord-Berechtigungen",
        "Nitrado service ID and API token": "Nitrado-Service-ID und API-Token",
        "FTP access for that same server": "FTP-Zugang für denselben Server",
        "Platform, map, and ADM logs": "Plattform, Karte und ADM-Protokolle",
        "Run the first checks": "Erste Prüfungen durchführen",
        "Keep it safe": "Sicher bleiben",
        "One server profile at a time": "Ein Serverprofil nach dem anderen",
        "View the complete setup guide": "Vollständige Anleitung ansehen",
        "Download the setup guide": "Einrichtungsanleitung herunterladen",
        "Wandering Bot is now live on Google Play": "Wandering Bot ist jetzt bei Google Play verfügbar",
        "Install the Android app for mobile DayZ server control, feeds, guides and dashboard access.": "Installiere die Android-App für mobile DayZ-Serversteuerung, Feeds, Anleitungen und Dashboard-Zugriff.",
        "Get it on Google Play": "Bei Google Play herunterladen",
        "Android app live": "Android-App verfügbar",
        "Activate, monitor and control your server from your phone": "Server vom Handy aktivieren, überwachen und steuern",
        "Server control on touch": "Serversteuerung per Touch",
        "DayZ files and gameplay": "DayZ-Dateien und Gameplay",
        "Protected mobile access": "Geschützter mobiler Zugriff",
        "Included with Ultimate": "In Ultimate enthalten",
        "DayZ server control for Discord": "DayZ-Serversteuerung für Discord",
        "Connect your server from the app": "Server über die App verbinden",
        "Add Wandering Bot to Discord": "Wandering Bot zu Discord hinzufügen",
        "Browse free Crafting & Survival library": "Kostenlose Herstellungs- und Überlebensbibliothek durchsuchen",
        "First-time setup": "Ersteinrichtung",
        "Add the bot": "Bot hinzufügen",
        "Prepare your private details": "Private Daten vorbereiten",
        "Run setup in Discord": "Einrichtung in Discord ausführen",
        "Return here to sign in": "Zum Anmelden hierher zurückkehren",
        "Server login": "Server-Anmeldung",
        "Dashboard ID": "Dashboard-ID",
        "Password": "Passwort",
        "Open App": "App öffnen",
        "Forgotten password?": "Passwort vergessen?",
        "A Discord administrator can run": "Ein Discord-Administrator kann",
        ". For security, an existing password cannot be displayed again.": ". Aus Sicherheitsgründen kann ein vorhandenes Passwort nicht erneut angezeigt werden.",
        "Contact support": "Support kontaktieren",
        "Quick actions": "Schnellaktionen",
        "Server list": "Serverliste",
        "Vanilla file library": "Vanilla-Dateibibliothek",
        "Billing plans": "Tarife",
        "Edit access": "Zugriff bearbeiten",
        "Common Tasks": "Häufige Aufgaben",
        "Create Event": "Event erstellen",
        "Edit Zones": "Zonen bearbeiten",
        "Shop / Money": "Shop / Geld",
        "Restart Server": "Server neu starten",
        "Home": "Start",
        "Feeds": "Feeds",
        "Events": "Events",
        "Economy": "Wirtschaft",
        "Control": "Steuerung",
        "Guides": "Anleitungen",
        "Crafting": "Herstellung",
        "Live server feeds": "Live-Server-Feeds",
        "Activity stream": "Aktivitätsstream",
        "Airdrops and live events": "Airdrops und Live-Events",
        "Create an airdrop": "Airdrop erstellen",
        "Event name": "Eventname",
        "Map location": "Kartenposition",
        "Choose a location": "Position wählen",
        "Loot preset": "Loot-Voreinstellung",
        "Runs": "Durchläufe",
        "Next restart only": "Nur beim nächsten Neustart",
        "Every restart": "Bei jedem Neustart",
        "Infected guards": "Infizierte Wachen",
        "Guard count": "Anzahl Wachen",
        "Loot amount": "Loot-Menge",
        "Create and upload airdrop": "Airdrop erstellen und hochladen",
        "Configured events": "Konfigurierte Events",
        "Shop and economy": "Shop und Wirtschaft",
        "Find an item": "Gegenstand suchen",
        "Search item or category": "Gegenstand oder Kategorie suchen",
        "Price": "Preis",
        "Daily limit": "Tageslimit",
        "Category": "Kategorie",
        "Available": "Verfügbar",
        "Save item": "Gegenstand speichern",
        "Current state": "Aktueller Zustand",
        "Restart schedule": "Neustartplan",
        "Schedule": "Zeitplan",
        "Every hours": "Alle Stunden",
        "Start hour local": "Lokale Startstunde",
        "Timezone": "Zeitzone",
        "Warning minutes": "Warnminuten",
        "Save restart schedule": "Neustartplan speichern",
        "Base damage": "Basisschaden",
        "Container damage": "Containerschaden",
        "Save damage state": "Schadensstatus speichern",
        "Restart selected server": "Ausgewählten Server neu starten",
        "Feedback and app rating": "Feedback und App-Bewertung",
        "Rating": "Bewertung",
        "Review": "Rezension",
        "Send dashboard review": "Dashboard-Rezension senden",
        "Rate on Google Play": "Bei Google Play bewerten",
        "Support Discord": "Support-Discord",
        "Overview": "Übersicht", "Admin": "Admin", "Owner": "Besitzer", "Servers": "Server",
        "Server Access": "Serverzugriff", "Vanilla Files & Updates": "Vanilla-Dateien & Updates",
        "Start Here": "Hier starten", "Upgrade": "Upgrade", "Admin Center": "Admin-Center",
        "Airdrops & Events": "Airdrops & Events", "Zones & Radar": "Zonen & Radar",
        "XML & Loadouts": "XML & Loadouts", "Preset Files": "Voreinstellungsdateien",
        "Shop & Economy": "Shop & Wirtschaft", "Leaderboards": "Bestenlisten",
        "Live Feeds": "Live-Feeds", "Player Audit": "Spielerprüfung", "Reviews": "Rezensionen",
        "Help & Guides": "Hilfe & Anleitungen", "AI Sandbox": "KI-Sandbox",
        "Plans & Billing": "Tarife & Abrechnung", "Owner Home": "Besitzer-Startseite",
        "Switch Login": "Anmeldung wechseln", "Logout": "Abmelden", "Online": "Online",
        "Active Server": "Aktiver Server", "Switch Server": "Server wechseln",
        "Save": "Speichern", "Cancel": "Abbrechen", "Delete": "Löschen", "Edit": "Bearbeiten",
        "Retry": "Erneut versuchen", "Pause": "Pausieren", "Search": "Suchen", "Filter": "Filtern",
        "Show": "Anzeigen", "Hide": "Ausblenden", "Open": "Öffnen", "Close": "Schließen",
        "Download": "Herunterladen", "Upload": "Hochladen", "Add": "Hinzufügen", "Remove": "Entfernen",
        "Back": "Zurück", "Next": "Weiter", "Continue": "Fortfahren", "Submit": "Absenden",
        "Refresh": "Aktualisieren", "Copy": "Kopieren", "Create": "Erstellen", "Update": "Aktualisieren",
        "Enable": "Aktivieren", "Disable": "Deaktivieren", "On": "An", "Off": "Aus", "Yes": "Ja", "No": "Nein",
    },
    "fr": {
        "Interface language": "Langue de l’interface",
        "Interface only. DayZ technical content remains unchanged.": "Interface uniquement. Le contenu technique DayZ reste inchangé.",
        "Existing users log in": "Connexion des utilisateurs",
        "AI Agent": "Agent IA", "Add Wandering Bot": "Ajouter Wandering Bot",
        "Read the setup guide": "Lire le guide d’installation", "Browse DayZ crafting": "Parcourir l’artisanat DayZ",
        "Open existing dashboard": "Ouvrir le tableau de bord", "Join support Discord": "Rejoindre le Discord d’assistance",
        "Email support": "Assistance par e-mail", "Onboarding": "Configuration", "Invite the bot": "Inviter le bot",
        "Check the connection": "Vérifier la connexion", "Open the dashboard": "Ouvrir le tableau de bord",
        "Wandering Bot is now live on Google Play": "Wandering Bot est maintenant disponible sur Google Play",
        "Install the Android app for mobile DayZ server control, feeds, guides and dashboard access.": "Installez l’application Android pour contrôler votre serveur DayZ, consulter les flux, les guides et le tableau de bord.",
        "Get it on Google Play": "Disponible sur Google Play", "Android app live": "Application Android disponible",
        "Activate, monitor and control your server from your phone": "Activez, surveillez et contrôlez votre serveur depuis votre téléphone",
        "Server control on touch": "Contrôle tactile du serveur", "DayZ files and gameplay": "Fichiers DayZ et gameplay",
        "Protected mobile access": "Accès mobile protégé", "Included with Ultimate": "Inclus avec Ultimate",
        "DayZ server control for Discord": "Contrôle de serveur DayZ pour Discord",
        "Connect your server from the app": "Connectez votre serveur depuis l’application",
        "Add Wandering Bot to Discord": "Ajouter Wandering Bot à Discord",
        "Browse free Crafting & Survival library": "Parcourir la bibliothèque gratuite d’artisanat et de survie",
        "First-time setup": "Première configuration", "Server login": "Connexion au serveur",
        "Dashboard ID": "Identifiant du tableau de bord", "Password": "Mot de passe", "Open App": "Ouvrir l’application",
        "Forgotten password?": "Mot de passe oublié ?",
        "A Discord administrator can run": "Un administrateur Discord peut exécuter",
        ". For security, an existing password cannot be displayed again.": ". Pour des raisons de sécurité, un mot de passe existant ne peut pas être affiché de nouveau.",
        "Contact support": "Contacter l’assistance", "Home": "Accueil", "Feeds": "Flux", "Events": "Événements",
        "Economy": "Économie", "Control": "Contrôle", "Guides": "Guides", "Crafting": "Artisanat",
        "Quick actions": "Actions rapides", "Server list": "Liste des serveurs", "Create Event": "Créer un événement",
        "Edit Zones": "Modifier les zones", "Restart Server": "Redémarrer le serveur",
        "Overview": "Vue d’ensemble", "Server Access": "Accès serveur", "Start Here": "Commencer ici",
        "Upgrade": "Mettre à niveau", "Admin Center": "Centre d’administration", "Zones & Radar": "Zones et radar",
        "Preset Files": "Fichiers prédéfinis", "Shop & Economy": "Boutique et économie",
        "Leaderboards": "Classements", "Live Feeds": "Flux en direct", "Player Audit": "Audit des joueurs",
        "Reviews": "Avis", "Help & Guides": "Aide et guides", "Plans & Billing": "Offres et facturation",
        "Switch Login": "Changer de connexion", "Logout": "Déconnexion", "Active Server": "Serveur actif",
        "Switch Server": "Changer de serveur", "Save": "Enregistrer", "Cancel": "Annuler", "Delete": "Supprimer",
        "Edit": "Modifier", "Retry": "Réessayer", "Search": "Rechercher", "Filter": "Filtrer", "Open": "Ouvrir",
        "Close": "Fermer", "Download": "Télécharger", "Upload": "Téléverser", "Add": "Ajouter", "Remove": "Retirer",
        "Back": "Retour", "Next": "Suivant", "Continue": "Continuer", "Submit": "Envoyer", "Refresh": "Actualiser",
        "Copy": "Copier", "Create": "Créer", "Update": "Mettre à jour", "Enable": "Activer", "Disable": "Désactiver",
        "On": "Activé", "Off": "Désactivé", "Yes": "Oui", "No": "Non",
    },
    "es": {
        "Interface language": "Idioma de la interfaz",
        "Interface only. DayZ technical content remains unchanged.": "Solo la interfaz. El contenido técnico de DayZ no cambia.",
        "Existing users log in": "Acceso de usuarios", "AI Agent": "Agente de IA",
        "Add Wandering Bot": "Añadir Wandering Bot", "Read the setup guide": "Leer la guía de configuración",
        "Browse DayZ crafting": "Explorar fabricación de DayZ", "Open existing dashboard": "Abrir panel existente",
        "Join support Discord": "Unirse al Discord de soporte", "Email support": "Soporte por correo",
        "Onboarding": "Configuración", "Invite the bot": "Invitar al bot", "Check the connection": "Comprobar la conexión",
        "Open the dashboard": "Abrir el panel",
        "Wandering Bot is now live on Google Play": "Wandering Bot ya está disponible en Google Play",
        "Install the Android app for mobile DayZ server control, feeds, guides and dashboard access.": "Instala la app de Android para controlar tu servidor DayZ, ver feeds, guías y acceder al panel.",
        "Get it on Google Play": "Descargar en Google Play", "Android app live": "App de Android disponible",
        "Activate, monitor and control your server from your phone": "Activa, supervisa y controla tu servidor desde el teléfono",
        "Server control on touch": "Control táctil del servidor", "DayZ files and gameplay": "Archivos DayZ y jugabilidad",
        "Protected mobile access": "Acceso móvil protegido", "Included with Ultimate": "Incluido con Ultimate",
        "DayZ server control for Discord": "Control de servidor DayZ para Discord",
        "Connect your server from the app": "Conecta tu servidor desde la app",
        "Add Wandering Bot to Discord": "Añadir Wandering Bot a Discord", "First-time setup": "Configuración inicial",
        "Server login": "Acceso al servidor", "Dashboard ID": "ID del panel", "Password": "Contraseña",
        "Open App": "Abrir app", "Forgotten password?": "¿Has olvidado la contraseña?",
        "A Discord administrator can run": "Un administrador de Discord puede ejecutar",
        ". For security, an existing password cannot be displayed again.": ". Por seguridad, no se puede volver a mostrar una contraseña existente.",
        "Contact support": "Contactar con soporte", "Home": "Inicio", "Feeds": "Feeds",
        "Events": "Eventos", "Economy": "Economía", "Control": "Control", "Guides": "Guías", "Crafting": "Fabricación",
        "Quick actions": "Acciones rápidas", "Server list": "Lista de servidores", "Create Event": "Crear evento",
        "Edit Zones": "Editar zonas", "Restart Server": "Reiniciar servidor", "Overview": "Resumen",
        "Server Access": "Acceso al servidor", "Start Here": "Empieza aquí", "Upgrade": "Mejorar plan",
        "Admin Center": "Centro de administración", "Zones & Radar": "Zonas y radar",
        "Preset Files": "Archivos predefinidos", "Shop & Economy": "Tienda y economía",
        "Leaderboards": "Clasificaciones", "Live Feeds": "Feeds en directo", "Player Audit": "Auditoría de jugadores",
        "Reviews": "Reseñas", "Help & Guides": "Ayuda y guías", "Plans & Billing": "Planes y facturación",
        "Switch Login": "Cambiar acceso", "Logout": "Cerrar sesión", "Active Server": "Servidor activo",
        "Switch Server": "Cambiar servidor", "Save": "Guardar", "Cancel": "Cancelar", "Delete": "Eliminar",
        "Edit": "Editar", "Retry": "Reintentar", "Search": "Buscar", "Filter": "Filtrar", "Open": "Abrir",
        "Close": "Cerrar", "Download": "Descargar", "Upload": "Subir", "Add": "Añadir", "Remove": "Quitar",
        "Back": "Atrás", "Next": "Siguiente", "Continue": "Continuar", "Submit": "Enviar", "Refresh": "Actualizar",
        "Copy": "Copiar", "Create": "Crear", "Update": "Actualizar", "Enable": "Activar", "Disable": "Desactivar",
        "On": "Activado", "Off": "Desactivado", "Yes": "Sí", "No": "No",
    },
    "pl": {
        "Interface language": "Język interfejsu",
        "Interface only. DayZ technical content remains unchanged.": "Tylko interfejs. Techniczna zawartość DayZ pozostaje bez zmian.",
        "Existing users log in": "Logowanie użytkowników", "AI Agent": "Agent AI",
        "Add Wandering Bot": "Dodaj Wandering Bot", "Read the setup guide": "Przeczytaj instrukcję konfiguracji",
        "Browse DayZ crafting": "Przeglądaj rzemiosło DayZ", "Open existing dashboard": "Otwórz istniejący panel",
        "Join support Discord": "Dołącz do Discorda pomocy", "Email support": "Pomoc e-mail",
        "Onboarding": "Konfiguracja", "Invite the bot": "Zaproś bota", "Check the connection": "Sprawdź połączenie",
        "Open the dashboard": "Otwórz panel",
        "Wandering Bot is now live on Google Play": "Wandering Bot jest już dostępny w Google Play",
        "Install the Android app for mobile DayZ server control, feeds, guides and dashboard access.": "Zainstaluj aplikację Android do mobilnego sterowania serwerem DayZ, podglądu kanałów, poradników i panelu.",
        "Get it on Google Play": "Pobierz z Google Play", "Android app live": "Aplikacja Android dostępna",
        "Activate, monitor and control your server from your phone": "Aktywuj, monitoruj i kontroluj serwer z telefonu",
        "Server control on touch": "Dotykowe sterowanie serwerem", "DayZ files and gameplay": "Pliki DayZ i rozgrywka",
        "Protected mobile access": "Chroniony dostęp mobilny", "Included with Ultimate": "W pakiecie Ultimate",
        "DayZ server control for Discord": "Sterowanie serwerem DayZ dla Discorda",
        "Connect your server from the app": "Połącz serwer z poziomu aplikacji",
        "Add Wandering Bot to Discord": "Dodaj Wandering Bot do Discorda", "First-time setup": "Pierwsza konfiguracja",
        "Server login": "Logowanie do serwera", "Dashboard ID": "ID panelu", "Password": "Hasło",
        "Open App": "Otwórz aplikację", "Forgotten password?": "Nie pamiętasz hasła?",
        "A Discord administrator can run": "Administrator Discorda może uruchomić",
        ". For security, an existing password cannot be displayed again.": ". Ze względów bezpieczeństwa istniejącego hasła nie można ponownie wyświetlić.",
        "Contact support": "Skontaktuj się z pomocą", "Home": "Strona główna",
        "Feeds": "Kanały", "Events": "Wydarzenia", "Economy": "Ekonomia", "Control": "Sterowanie",
        "Guides": "Poradniki", "Crafting": "Rzemiosło", "Quick actions": "Szybkie działania",
        "Server list": "Lista serwerów", "Create Event": "Utwórz wydarzenie", "Edit Zones": "Edytuj strefy",
        "Restart Server": "Uruchom serwer ponownie", "Overview": "Przegląd", "Server Access": "Dostęp do serwera",
        "Start Here": "Zacznij tutaj", "Upgrade": "Ulepsz plan", "Admin Center": "Centrum administracyjne",
        "Zones & Radar": "Strefy i radar", "Preset Files": "Pliki ustawień", "Shop & Economy": "Sklep i ekonomia",
        "Leaderboards": "Rankingi", "Live Feeds": "Kanały na żywo", "Player Audit": "Audyt graczy",
        "Reviews": "Opinie", "Help & Guides": "Pomoc i poradniki", "Plans & Billing": "Plany i rozliczenia",
        "Switch Login": "Zmień logowanie", "Logout": "Wyloguj", "Active Server": "Aktywny serwer",
        "Switch Server": "Zmień serwer", "Save": "Zapisz", "Cancel": "Anuluj", "Delete": "Usuń",
        "Edit": "Edytuj", "Retry": "Spróbuj ponownie", "Search": "Szukaj", "Filter": "Filtruj", "Open": "Otwórz",
        "Close": "Zamknij", "Download": "Pobierz", "Upload": "Prześlij", "Add": "Dodaj", "Remove": "Usuń",
        "Back": "Wstecz", "Next": "Dalej", "Continue": "Kontynuuj", "Submit": "Wyślij", "Refresh": "Odśwież",
        "Copy": "Kopiuj", "Create": "Utwórz", "Update": "Aktualizuj", "Enable": "Włącz", "Disable": "Wyłącz",
        "On": "Włączone", "Off": "Wyłączone", "Yes": "Tak", "No": "Nie",
    },
}


# High-visibility app and onboarding copy must be complete in every supported
# non-English language.  Keeping this as a small reviewed overlay makes it much
# harder for a newly added mobile tool to appear half-translated while leaving
# DayZ filenames, classnames and editor content untouched.
CORE_APP_UI_TRANSLATIONS = {
    "de": {
        "Add Wandering Bot to your Discord before signing in. The bot will create a private dashboard login after an administrator completes setup.": "Füge Wandering Bot vor der Anmeldung zu deinem Discord hinzu. Der Bot erstellt einen privaten Dashboard-Zugang, nachdem ein Administrator die Einrichtung abgeschlossen hat.",
        "Read the full setup guide": "Vollständige Einrichtungsanleitung lesen",
        "Understand DayZ server files": "DayZ-Serverdateien verstehen",
        "Get started": "Loslegen",
        "Command centre": "Kommandozentrale",
        "A focused mobile overview. Full desktop-only builders stay out of the app.": "Eine übersichtliche mobile Ansicht. Umfangreiche Werkzeuge nur für den Desktop bleiben außerhalb der App.",
        "Mobile tools": "Mobile Werkzeuge",
        "Server feeds": "Server-Feeds",
        "Airdrop builder": "Airdrop-Builder",
        "Shop control": "Shop-Steuerung",
        "Server control": "Serversteuerung",
        "DayZ field guide": "DayZ-Handbuch",
        "Crafting library": "Herstellungsbibliothek",
        "DayZ files explained": "DayZ-Dateien erklärt",
        "DayZ AI agent": "DayZ-KI-Agent",
        "Ask questions, repair errors and prepare validated DayZ file drafts in separate conversations.": "Stelle Fragen, behebe Fehler und erstelle geprüfte DayZ-Dateientwürfe in getrennten Unterhaltungen.",
        "Tour": "Rundgang",
        "Log out": "Abmelden",
        "Choose the correct server": "Den richtigen Server auswählen",
        "Watch feeds and events": "Feeds und Events beobachten",
        "Control with confirmation": "Steuerung mit Bestätigung",
        "Use Guides before file changes": "Vor Dateiänderungen die Anleitungen nutzen",
    },
    "fr": {
        "Add Wandering Bot to your Discord before signing in. The bot will create a private dashboard login after an administrator completes setup.": "Ajoutez Wandering Bot à votre Discord avant de vous connecter. Le bot créera un accès privé au tableau de bord après la configuration par un administrateur.",
        "Read the full setup guide": "Lire le guide d’installation complet",
        "Understand DayZ server files": "Comprendre les fichiers serveur DayZ",
        "Get started": "Commencer",
        "Command centre": "Centre de commande",
        "A focused mobile overview. Full desktop-only builders stay out of the app.": "Une vue mobile claire. Les outils complets réservés à l’ordinateur restent hors de l’application.",
        "Mobile tools": "Outils mobiles",
        "Server feeds": "Flux du serveur",
        "Airdrop builder": "Créateur de largages",
        "Shop control": "Gestion de la boutique",
        "Server control": "Contrôle du serveur",
        "DayZ field guide": "Guide pratique DayZ",
        "Crafting library": "Bibliothèque d’artisanat",
        "DayZ files explained": "Fichiers DayZ expliqués",
        "DayZ AI agent": "Agent IA DayZ",
        "Ask questions, repair errors and prepare validated DayZ file drafts in separate conversations.": "Posez des questions, corrigez les erreurs et préparez des fichiers DayZ validés dans des conversations séparées.",
        "Tour": "Visite",
        "Log out": "Se déconnecter",
        "Choose the correct server": "Choisir le bon serveur",
        "Watch feeds and events": "Surveiller les flux et événements",
        "Control with confirmation": "Contrôler avec confirmation",
        "Use Guides before file changes": "Consulter les guides avant de modifier les fichiers",
    },
    "es": {
        "Add Wandering Bot to your Discord before signing in. The bot will create a private dashboard login after an administrator completes setup.": "Añade Wandering Bot a tu Discord antes de iniciar sesión. El bot creará un acceso privado al panel cuando un administrador termine la configuración.",
        "Read the full setup guide": "Leer la guía de configuración completa",
        "Understand DayZ server files": "Entender los archivos del servidor DayZ",
        "Get started": "Empezar",
        "Command centre": "Centro de control",
        "A focused mobile overview. Full desktop-only builders stay out of the app.": "Una vista móvil clara. Las herramientas completas para ordenador se mantienen fuera de la aplicación.",
        "Mobile tools": "Herramientas móviles",
        "Server feeds": "Canales del servidor",
        "Airdrop builder": "Creador de airdrops",
        "Shop control": "Control de la tienda",
        "Server control": "Control del servidor",
        "DayZ field guide": "Guía práctica de DayZ",
        "Crafting library": "Biblioteca de fabricación",
        "DayZ files explained": "Archivos de DayZ explicados",
        "DayZ AI agent": "Agente de IA de DayZ",
        "Ask questions, repair errors and prepare validated DayZ file drafts in separate conversations.": "Haz preguntas, corrige errores y prepara borradores validados de archivos DayZ en conversaciones separadas.",
        "Tour": "Recorrido",
        "Log out": "Cerrar sesión",
        "Choose the correct server": "Elegir el servidor correcto",
        "Watch feeds and events": "Ver canales y eventos",
        "Control with confirmation": "Controlar con confirmación",
        "Use Guides before file changes": "Usar las guías antes de cambiar archivos",
    },
    "pl": {
        "Add Wandering Bot to your Discord before signing in. The bot will create a private dashboard login after an administrator completes setup.": "Dodaj Wandering Bot do swojego Discorda przed zalogowaniem. Bot utworzy prywatny dostęp do panelu po zakończeniu konfiguracji przez administratora.",
        "Read the full setup guide": "Przeczytaj pełną instrukcję konfiguracji",
        "Understand DayZ server files": "Poznaj pliki serwera DayZ",
        "Get started": "Rozpocznij",
        "Command centre": "Centrum dowodzenia",
        "A focused mobile overview. Full desktop-only builders stay out of the app.": "Przejrzysty widok mobilny. Rozbudowane narzędzia komputerowe pozostają poza aplikacją.",
        "Mobile tools": "Narzędzia mobilne",
        "Server feeds": "Kanały serwera",
        "Airdrop builder": "Kreator zrzutów",
        "Shop control": "Sterowanie sklepem",
        "Server control": "Sterowanie serwerem",
        "DayZ field guide": "Przewodnik DayZ",
        "Crafting library": "Biblioteka rzemiosła",
        "DayZ files explained": "Objaśnienia plików DayZ",
        "DayZ AI agent": "Agent AI DayZ",
        "Ask questions, repair errors and prepare validated DayZ file drafts in separate conversations.": "Zadawaj pytania, naprawiaj błędy i przygotowuj zweryfikowane pliki DayZ w osobnych rozmowach.",
        "Tour": "Prezentacja",
        "Log out": "Wyloguj",
        "Choose the correct server": "Wybierz właściwy serwer",
        "Watch feeds and events": "Obserwuj kanały i wydarzenia",
        "Control with confirmation": "Steruj z potwierdzeniem",
        "Use Guides before file changes": "Przed zmianami plików skorzystaj z poradników",
    },
}

for _language, _phrases in CORE_APP_UI_TRANSLATIONS.items():
    UI_TRANSLATIONS[_language].update(_phrases)


# The public homepage is the first experience for most customers.  Keep its
# high-visibility marketing, setup and support copy complete in every supported
# language.  File names, slash commands and DayZ class names are intentionally
# absent: the browser localizer protects those technical fragments.
PUBLIC_HOME_UI_TRANSLATIONS = {
    "de": {
        "Overview": "Übersicht",
        "Android App": "Android-App",
        "Kill Feed": "Killfeed",
        "Discord Bot": "Discord-Bot",
        "Nitrado Tools": "Nitrado-Werkzeuge",
        "Trader Economy": "Händlerwirtschaft",
        "Raid Alerts": "Raid-Warnungen",
        "Dashboard": "Dashboard",
        "Airdrops": "Airdrops",
        "Console Killfeed": "Konsolen-Killfeed",
        "DayZ server control": "DayZ-Serversteuerung",
        "Add Wandering Bot to your DayZ server": "Wandering Bot zu deinem DayZ-Server hinzufügen",
        "Install the Wandering Bot Android app or add the bot to Discord, connect Nitrado, and unlock mobile server control plus a guided dashboard for ADM feeds, live maps, events, restarts, XML tools, economy, bans, zones, and server setup.": "Installiere die Wandering-Bot-Android-App oder füge den Bot zu Discord hinzu, verbinde Nitrado und erhalte mobile Serversteuerung sowie ein geführtes Dashboard für ADM-Feeds, Live-Karten, Events, Neustarts, XML-Werkzeuge, Wirtschaft, Sperren, Zonen und Servereinrichtung.",
        "Owner support is built in": "Besitzer-Support ist integriert",
        "Need help after adding the bot? Open a ticket straight from your Discord.": "Brauchst du nach dem Hinzufügen des Bots Hilfe? Öffne direkt aus deinem Discord ein Ticket.",
        "Any server administrator can use": "Jeder Serveradministrator kann",
        ". It sends your issue directly to the Wandering Bot owner and keeps the reply in your server’s support ticket.": ". Dadurch wird dein Anliegen direkt an den Besitzer von Wandering Bot gesendet und die Antwort bleibt im Support-Ticket deines Servers.",
        "DayZ Android app": "DayZ-Android-App",
        "Install Wandering Bot from Google Play for mobile DayZ server control, live feeds, guides, events, economy and dashboard access.": "Installiere Wandering Bot aus Google Play für mobile DayZ-Serversteuerung, Live-Feeds, Anleitungen, Events, Wirtschaft und Dashboard-Zugriff.",
        "DayZ kill feed and ADM feeds": "DayZ-Killfeed und ADM-Feeds",
        "Track kills, deaths, longshots, online players, restart alerts, and audit feeds from your server logs.": "Verfolge Kills, Tode, Weitschüsse, Online-Spieler, Neustartwarnungen und Prüf-Feeds aus deinen Serverprotokollen.",
        "Airdrops, animals and hordes": "Airdrops, Tiere und Horden",
        "Queue airdrops, animal drops, zombie hordes, gas zones, crash scenes, convoy-style events, and live event uploads from the dashboard.": "Plane Airdrops, Tier-Drops, Zombiehorden, Gaszonen, Absturzstellen, Konvoi-Events und Live-Event-Uploads im Dashboard.",
        "Server dashboard": "Server-Dashboard",
        "Create temporary or permanent admin logins for trusted staff, then choose which live events, XML tools, schedules, shops, economy, zones, and moderation tools they can use.": "Erstelle temporäre oder dauerhafte Admin-Zugänge für vertrauenswürdige Mitarbeiter und bestimme, welche Live-Events, XML-Werkzeuge, Zeitpläne, Shops, Wirtschafts-, Zonen- und Moderationswerkzeuge sie nutzen dürfen.",
        "Restarts and vehicle resets": "Neustarts und Fahrzeug-Resets",
        "Schedule server restarts, raid weekend reminders, base damage windows, container damage windows, and vehicle reset workflows from one control area.": "Plane Serverneustarts, Raid-Wochenend-Erinnerungen, Zeitfenster für Basis- und Containerschaden sowie Fahrzeug-Resets in einem Bereich.",
        "Nitrado and Discord automation": "Nitrado- und Discord-Automatisierung",
        "Connect Nitrado, organise Discord channels, manage ban feeds, link gamertags, and keep staff actions visible.": "Verbinde Nitrado, organisiere Discord-Kanäle, verwalte Sperr-Feeds, verknüpfe Gamertags und halte Teamaktionen nachvollziehbar.",
        "Automatic Discord translation": "Automatische Discord-Übersetzung",
        "Give international communities readable conversations with original messages and translations posted in the same channel or routed to a dedicated translation channel.": "Gib internationalen Communities verständliche Unterhaltungen, indem Originalnachrichten und Übersetzungen im selben Kanal oder in einem eigenen Übersetzungskanal erscheinen.",
        "What it covers": "Enthaltene Bereiche",
        "DayZ PC, PlayStation and Xbox killfeed, Discord server tools, Nitrado dashboard, live events, shop economy, and admin control.": "DayZ-Killfeed für PC, PlayStation und Xbox, Discord-Serverwerkzeuge, Nitrado-Dashboard, Live-Events, Shop-Wirtschaft und Admin-Steuerung.",
        "Choose your Discord server, approve the requested permissions, then let the bot create or repair its channel layout.": "Wähle deinen Discord-Server, bestätige die angeforderten Berechtigungen und lass den Bot anschließend seine Kanalstruktur erstellen oder reparieren.",
        "Run": "Ausführen",
        "Enter platform, map, Nitrado token, service ID, FTP username, and FTP password. These are used for your server only.": "Gib Plattform, Karte, Nitrado-Token, Service-ID, FTP-Benutzername und FTP-Passwort ein. Diese Daten werden nur für deinen Server verwendet.",
        "Use": "Verwende",
        ", then": ", danach",
        "once your ADM log is available so feeds can begin tracking players.": "sobald dein ADM-Protokoll verfügbar ist, damit die Feeds mit der Spielererfassung beginnen können.",
        "Enable dashboard login for trusted admins, then manage live events, XML tools, shop, economy, zones, and moderation from the web panel.": "Aktiviere den Dashboard-Zugang für vertrauenswürdige Admins und verwalte anschließend Live-Events, XML-Werkzeuge, Shop, Wirtschaft, Zonen und Moderation im Webpanel.",
        "Players can use": "Spieler können",
        ". Staff can review links, run events, and keep the server tools organised from Discord or the dashboard.": ". Mitarbeiter können Verknüpfungen prüfen, Events ausführen und die Serverwerkzeuge über Discord oder das Dashboard organisieren.",
        "guidance, ADM connection checks, core Discord player and server feeds, leaderboards, Discord channel setup, and server rules. The dashboard plans below add the web control tools.": "Anleitung, ADM-Verbindungsprüfungen, grundlegende Discord-Spieler- und Server-Feeds, Bestenlisten, Discord-Kanaleinrichtung und Serverregeln. Die folgenden Dashboard-Tarife ergänzen die Web-Steuerungswerkzeuge.",
        "You do not need a dashboard login to use this guide. Gather the right details first, then run the private Discord setup without putting any credentials in public chat.": "Für diese Anleitung brauchst du keinen Dashboard-Zugang. Sammle zuerst die richtigen Daten und führe dann die private Discord-Einrichtung durch, ohne Zugangsdaten in einen öffentlichen Chat zu schreiben.",
        "Step 1": "Schritt 1", "Step 2": "Schritt 2", "Step 3": "Schritt 3", "Step 4": "Schritt 4", "Step 5": "Schritt 5",
        "Be the server owner or an administrator. After inviting the bot, place its Discord role above every role it needs to manage.": "Du musst Serverbesitzer oder Administrator sein. Setze die Discord-Rolle des Bots nach dem Einladen über alle Rollen, die er verwalten soll.",
        "Open the correct DayZ service in Nitrado. Copy its service ID and create or copy an API token from the account/API settings. Keep the token private.": "Öffne den richtigen DayZ-Dienst in Nitrado. Kopiere seine Service-ID und erstelle oder kopiere in den Konto-/API-Einstellungen ein API-Token. Halte das Token geheim.",
        "Use the FTP/file-access details for the selected DayZ service: host, username, and password. Never post these in Discord.": "Verwende die FTP-/Dateizugangsdaten des ausgewählten DayZ-Dienstes: Host, Benutzername und Passwort. Veröffentliche sie niemals in Discord.",
        "Know whether the server is PC, Xbox, or PlayStation and choose the right map. ADM logs must be available before feeds can start.": "Prüfe, ob der Server auf PC, Xbox oder PlayStation läuft, und wähle die richtige Karte. ADM-Protokolle müssen verfügbar sein, bevor Feeds starten können.",
        ", and finally": "und schließlich",
        "once to confirm the first feed scan.": "einmal aus, um den ersten Feed-Scan zu bestätigen.",
        "Keep each Cherno, Livonia, Sakhal, or customer server on its own profile with its own credentials and feed routes.": "Behalte jeden Cherno-, Livonia-, Sakhal- oder Kundenserver in einem eigenen Profil mit eigenen Zugangsdaten und Feed-Routen.",
        "Android app live on Google Play — iPhone coming soon": "Android-App jetzt bei Google Play – iPhone folgt bald",
        "The Wandering Bot Android app is live on Google Play now, with the iPhone version coming soon. Use the same permission-checked controls on a touch screen: activate server tools, check live feeds and status, run authorised actions, and prepare DayZ file or gameplay changes away from your desktop.": "Die Wandering-Bot-Android-App ist jetzt bei Google Play verfügbar; die iPhone-Version folgt bald. Nutze dieselben berechtigungsgeprüften Funktionen per Touchscreen: Serverwerkzeuge aktivieren, Live-Feeds und Status prüfen, autorisierte Aktionen ausführen und DayZ-Datei- oder Gameplay-Änderungen auch ohne Desktop vorbereiten.",
        "Use your phone to check feeds and server status, manage supported dashboard controls, and keep your DayZ community moving without needing a desktop.": "Prüfe Feeds und Serverstatus auf deinem Handy, verwalte unterstützte Dashboard-Funktionen und betreue deine DayZ-Community ohne Desktop.",
        "Prepare and review XML or JSON file changes, adjust supported gameplay settings, and keep every live upload behind the same clear review and approval step.": "Bereite XML- oder JSON-Dateiänderungen vor und prüfe sie, passe unterstützte Gameplay-Einstellungen an und halte jeden Live-Upload hinter demselben klaren Prüf- und Bestätigungsschritt.",
        "The Android and iPhone app uses the same permission-checked backend as the dashboard, so credentials, billing, file uploads, restarts and staff roles stay protected.": "Die Android- und iPhone-App nutzt dasselbe berechtigungsgeprüfte Backend wie das Dashboard, damit Zugangsdaten, Abrechnung, Datei-Uploads, Neustarts und Teamrollen geschützt bleiben.",
        "The Android app is live now and uses the same account access as Wandering Bot. The iPhone companion is coming soon for owners and trusted staff who want supported server tools, gameplay settings and DayZ file work from their phone.": "Die Android-App ist jetzt verfügbar und nutzt denselben Kontozugang wie Wandering Bot. Die iPhone-App folgt bald für Besitzer und vertrauenswürdige Mitarbeiter, die Serverwerkzeuge, Gameplay-Einstellungen und DayZ-Dateiarbeiten vom Handy aus nutzen möchten.",
    },
    "fr": {
        "Overview": "Aperçu", "Android App": "Application Android", "Kill Feed": "Flux des éliminations", "Discord Bot": "Bot Discord", "Nitrado Tools": "Outils Nitrado", "Trader Economy": "Économie de commerce", "Raid Alerts": "Alertes de raid", "Dashboard": "Tableau de bord", "Airdrops": "Largages", "Console Killfeed": "Flux console",
        "DayZ server control": "Contrôle de serveur DayZ", "Add Wandering Bot to your DayZ server": "Ajoutez Wandering Bot à votre serveur DayZ",
        "Install the Wandering Bot Android app or add the bot to Discord, connect Nitrado, and unlock mobile server control plus a guided dashboard for ADM feeds, live maps, events, restarts, XML tools, economy, bans, zones, and server setup.": "Installez l’application Android Wandering Bot ou ajoutez le bot à Discord, connectez Nitrado et profitez du contrôle mobile du serveur ainsi que d’un tableau de bord guidé pour les flux ADM, les cartes en direct, les événements, les redémarrages, les outils XML, l’économie, les bannissements, les zones et la configuration du serveur.",
        "Owner support is built in": "L’assistance du propriétaire est intégrée", "Need help after adding the bot? Open a ticket straight from your Discord.": "Besoin d’aide après avoir ajouté le bot ? Ouvrez un ticket directement depuis votre Discord.", "Any server administrator can use": "Tout administrateur du serveur peut utiliser", ". It sends your issue directly to the Wandering Bot owner and keeps the reply in your server’s support ticket.": ". Votre demande est envoyée directement au propriétaire de Wandering Bot et la réponse reste dans le ticket d’assistance de votre serveur.",
        "DayZ Android app": "Application Android DayZ", "Install Wandering Bot from Google Play for mobile DayZ server control, live feeds, guides, events, economy and dashboard access.": "Installez Wandering Bot depuis Google Play pour contrôler votre serveur DayZ sur mobile et accéder aux flux, guides, événements, à l’économie et au tableau de bord.",
        "DayZ kill feed and ADM feeds": "Flux d’éliminations DayZ et flux ADM", "Track kills, deaths, longshots, online players, restart alerts, and audit feeds from your server logs.": "Suivez les éliminations, les morts, les tirs longue distance, les joueurs en ligne, les alertes de redémarrage et les flux d’audit depuis les journaux du serveur.",
        "Airdrops, animals and hordes": "Largages, animaux et hordes", "Queue airdrops, animal drops, zombie hordes, gas zones, crash scenes, convoy-style events, and live event uploads from the dashboard.": "Programmez des largages, apparitions d’animaux, hordes de zombies, zones de gaz, scènes de crash, événements de convoi et envois d’événements depuis le tableau de bord.",
        "Server dashboard": "Tableau de bord du serveur", "Create temporary or permanent admin logins for trusted staff, then choose which live events, XML tools, schedules, shops, economy, zones, and moderation tools they can use.": "Créez des accès administrateur temporaires ou permanents pour le personnel de confiance, puis choisissez les événements, outils XML, horaires, boutiques, outils d’économie, zones et fonctions de modération qu’il peut utiliser.",
        "Restarts and vehicle resets": "Redémarrages et réinitialisations des véhicules", "Schedule server restarts, raid weekend reminders, base damage windows, container damage windows, and vehicle reset workflows from one control area.": "Planifiez les redémarrages, rappels de week-end de raid, périodes de dégâts des bases et conteneurs et réinitialisations des véhicules depuis un seul espace.",
        "Nitrado and Discord automation": "Automatisation Nitrado et Discord", "Connect Nitrado, organise Discord channels, manage ban feeds, link gamertags, and keep staff actions visible.": "Connectez Nitrado, organisez les canaux Discord, gérez les flux de bannissement, liez les gamertags et gardez les actions du personnel visibles.",
        "Automatic Discord translation": "Traduction Discord automatique", "Give international communities readable conversations with original messages and translations posted in the same channel or routed to a dedicated translation channel.": "Offrez aux communautés internationales des conversations lisibles avec les messages d’origine et leurs traductions dans le même canal ou dans un canal dédié.",
        "What it covers": "Ce qui est inclus", "DayZ PC, PlayStation and Xbox killfeed, Discord server tools, Nitrado dashboard, live events, shop economy, and admin control.": "Flux DayZ pour PC, PlayStation et Xbox, outils Discord, tableau de bord Nitrado, événements en direct, économie de boutique et contrôle administratif.",
        "Choose your Discord server, approve the requested permissions, then let the bot create or repair its channel layout.": "Choisissez votre serveur Discord, approuvez les autorisations demandées, puis laissez le bot créer ou réparer l’organisation de ses canaux.",
        "Run": "Exécuter", "Enter platform, map, Nitrado token, service ID, FTP username, and FTP password. These are used for your server only.": "Saisissez la plateforme, la carte, le jeton Nitrado, l’identifiant de service, le nom d’utilisateur FTP et le mot de passe FTP. Ces données servent uniquement à votre serveur.", "Use": "Utilisez", ", then": ", puis", "once your ADM log is available so feeds can begin tracking players.": "une fois le journal ADM disponible afin que les flux puissent commencer à suivre les joueurs.",
        "Enable dashboard login for trusted admins, then manage live events, XML tools, shop, economy, zones, and moderation from the web panel.": "Activez l’accès au tableau de bord pour les administrateurs de confiance, puis gérez les événements, outils XML, la boutique, l’économie, les zones et la modération depuis le panneau web.", "Players can use": "Les joueurs peuvent utiliser", ". Staff can review links, run events, and keep the server tools organised from Discord or the dashboard.": ". Le personnel peut vérifier les liaisons, lancer des événements et organiser les outils du serveur depuis Discord ou le tableau de bord.",
        "guidance, ADM connection checks, core Discord player and server feeds, leaderboards, Discord channel setup, and server rules. The dashboard plans below add the web control tools.": "guidage, vérifications de connexion ADM, principaux flux Discord des joueurs et du serveur, classements, configuration des canaux Discord et règles du serveur. Les offres ci-dessous ajoutent les outils de contrôle web.",
    },
    "es": {
        "Overview": "Resumen", "Android App": "App Android", "Kill Feed": "Feed de bajas", "Discord Bot": "Bot de Discord", "Nitrado Tools": "Herramientas de Nitrado", "Trader Economy": "Economía comercial", "Raid Alerts": "Alertas de incursión", "Dashboard": "Panel", "Airdrops": "Airdrops", "Console Killfeed": "Killfeed de consola",
        "DayZ server control": "Control de servidor DayZ", "Add Wandering Bot to your DayZ server": "Añade Wandering Bot a tu servidor DayZ",
        "Install the Wandering Bot Android app or add the bot to Discord, connect Nitrado, and unlock mobile server control plus a guided dashboard for ADM feeds, live maps, events, restarts, XML tools, economy, bans, zones, and server setup.": "Instala la app Android de Wandering Bot o añade el bot a Discord, conecta Nitrado y obtén control móvil del servidor y un panel guiado para feeds ADM, mapas en directo, eventos, reinicios, herramientas XML, economía, vetos, zonas y configuración del servidor.",
        "Owner support is built in": "El soporte del propietario está integrado", "Need help after adding the bot? Open a ticket straight from your Discord.": "¿Necesitas ayuda después de añadir el bot? Abre un ticket directamente desde tu Discord.", "Any server administrator can use": "Cualquier administrador del servidor puede usar", ". It sends your issue directly to the Wandering Bot owner and keeps the reply in your server’s support ticket.": ". Envía tu problema directamente al propietario de Wandering Bot y conserva la respuesta en el ticket de soporte de tu servidor.",
        "DayZ Android app": "App Android de DayZ", "Install Wandering Bot from Google Play for mobile DayZ server control, live feeds, guides, events, economy and dashboard access.": "Instala Wandering Bot desde Google Play para controlar el servidor DayZ desde el móvil y acceder a feeds, guías, eventos, economía y panel.",
        "DayZ kill feed and ADM feeds": "Killfeed de DayZ y feeds ADM", "Track kills, deaths, longshots, online players, restart alerts, and audit feeds from your server logs.": "Sigue bajas, muertes, disparos lejanos, jugadores conectados, alertas de reinicio y feeds de auditoría desde los registros del servidor.",
        "Airdrops, animals and hordes": "Airdrops, animales y hordas", "Queue airdrops, animal drops, zombie hordes, gas zones, crash scenes, convoy-style events, and live event uploads from the dashboard.": "Programa airdrops, apariciones de animales, hordas de zombis, zonas de gas, escenas de accidente, eventos tipo convoy y cargas de eventos desde el panel.",
        "Server dashboard": "Panel del servidor", "Create temporary or permanent admin logins for trusted staff, then choose which live events, XML tools, schedules, shops, economy, zones, and moderation tools they can use.": "Crea accesos de administrador temporales o permanentes para personal de confianza y elige qué eventos, herramientas XML, horarios, tiendas, economía, zonas y herramientas de moderación pueden usar.",
        "Restarts and vehicle resets": "Reinicios y restablecimientos de vehículos", "Schedule server restarts, raid weekend reminders, base damage windows, container damage windows, and vehicle reset workflows from one control area.": "Programa reinicios, recordatorios de fin de semana de incursión, periodos de daño de bases y contenedores y restablecimientos de vehículos desde una sola zona.",
        "Nitrado and Discord automation": "Automatización de Nitrado y Discord", "Connect Nitrado, organise Discord channels, manage ban feeds, link gamertags, and keep staff actions visible.": "Conecta Nitrado, organiza canales de Discord, gestiona feeds de vetos, vincula gamertags y mantén visibles las acciones del personal.",
        "Automatic Discord translation": "Traducción automática de Discord", "Give international communities readable conversations with original messages and translations posted in the same channel or routed to a dedicated translation channel.": "Ofrece conversaciones legibles a comunidades internacionales con mensajes originales y traducciones en el mismo canal o en uno dedicado.",
        "What it covers": "Qué incluye", "DayZ PC, PlayStation and Xbox killfeed, Discord server tools, Nitrado dashboard, live events, shop economy, and admin control.": "Killfeed de DayZ para PC, PlayStation y Xbox, herramientas de Discord, panel de Nitrado, eventos en directo, economía de tienda y control administrativo.",
        "Choose your Discord server, approve the requested permissions, then let the bot create or repair its channel layout.": "Elige tu servidor de Discord, aprueba los permisos solicitados y deja que el bot cree o repare la organización de sus canales.",
        "Run": "Ejecuta", "Enter platform, map, Nitrado token, service ID, FTP username, and FTP password. These are used for your server only.": "Introduce plataforma, mapa, token de Nitrado, ID de servicio, usuario FTP y contraseña FTP. Estos datos se usan solo para tu servidor.", "Use": "Usa", ", then": ", después", "once your ADM log is available so feeds can begin tracking players.": "cuando el registro ADM esté disponible para que los feeds empiecen a seguir a los jugadores.",
        "Enable dashboard login for trusted admins, then manage live events, XML tools, shop, economy, zones, and moderation from the web panel.": "Activa el acceso al panel para administradores de confianza y gestiona eventos, herramientas XML, tienda, economía, zonas y moderación desde el panel web.", "Players can use": "Los jugadores pueden usar", ". Staff can review links, run events, and keep the server tools organised from Discord or the dashboard.": ". El personal puede revisar vínculos, ejecutar eventos y organizar las herramientas del servidor desde Discord o el panel.",
        "guidance, ADM connection checks, core Discord player and server feeds, leaderboards, Discord channel setup, and server rules. The dashboard plans below add the web control tools.": "guía, comprobaciones de conexión ADM, feeds principales de jugadores y servidor en Discord, clasificaciones, configuración de canales y reglas del servidor. Los planes inferiores añaden las herramientas de control web.",
    },
    "pl": {
        "Overview": "Przegląd", "Android App": "Aplikacja Android", "Kill Feed": "Kanał zabójstw", "Discord Bot": "Bot Discord", "Nitrado Tools": "Narzędzia Nitrado", "Trader Economy": "Ekonomia handlowa", "Raid Alerts": "Alerty rajdów", "Dashboard": "Panel", "Airdrops": "Zrzuty", "Console Killfeed": "Killfeed konsolowy",
        "DayZ server control": "Sterowanie serwerem DayZ", "Add Wandering Bot to your DayZ server": "Dodaj Wandering Bot do swojego serwera DayZ",
        "Install the Wandering Bot Android app or add the bot to Discord, connect Nitrado, and unlock mobile server control plus a guided dashboard for ADM feeds, live maps, events, restarts, XML tools, economy, bans, zones, and server setup.": "Zainstaluj aplikację Wandering Bot na Androidzie lub dodaj bota do Discorda, połącz Nitrado i korzystaj z mobilnego sterowania serwerem oraz panelu prowadzącego przez kanały ADM, mapy na żywo, wydarzenia, restarty, narzędzia XML, ekonomię, bany, strefy i konfigurację serwera.",
        "Owner support is built in": "Pomoc właściciela jest wbudowana", "Need help after adding the bot? Open a ticket straight from your Discord.": "Potrzebujesz pomocy po dodaniu bota? Otwórz zgłoszenie bezpośrednio z Discorda.", "Any server administrator can use": "Każdy administrator serwera może użyć", ". It sends your issue directly to the Wandering Bot owner and keeps the reply in your server’s support ticket.": ". Problem zostanie wysłany bezpośrednio do właściciela Wandering Bot, a odpowiedź pozostanie w zgłoszeniu pomocy twojego serwera.",
        "DayZ Android app": "Aplikacja DayZ na Androida", "Install Wandering Bot from Google Play for mobile DayZ server control, live feeds, guides, events, economy and dashboard access.": "Zainstaluj Wandering Bot z Google Play, aby sterować serwerem DayZ z telefonu oraz korzystać z kanałów, poradników, wydarzeń, ekonomii i panelu.",
        "DayZ kill feed and ADM feeds": "Killfeed DayZ i kanały ADM", "Track kills, deaths, longshots, online players, restart alerts, and audit feeds from your server logs.": "Śledź zabójstwa, zgony, dalekie strzały, graczy online, alerty restartów i kanały audytu z dzienników serwera.",
        "Airdrops, animals and hordes": "Zrzuty, zwierzęta i hordy", "Queue airdrops, animal drops, zombie hordes, gas zones, crash scenes, convoy-style events, and live event uploads from the dashboard.": "Planuj zrzuty, pojawianie się zwierząt, hordy zombie, strefy gazowe, miejsca katastrof, wydarzenia konwojowe i wysyłanie wydarzeń z panelu.",
        "Server dashboard": "Panel serwera", "Create temporary or permanent admin logins for trusted staff, then choose which live events, XML tools, schedules, shops, economy, zones, and moderation tools they can use.": "Twórz tymczasowe lub stałe loginy administratorów dla zaufanej obsługi i wybieraj wydarzenia, narzędzia XML, harmonogramy, sklepy, ekonomię, strefy i narzędzia moderacji, których mogą używać.",
        "Restarts and vehicle resets": "Restarty i resetowanie pojazdów", "Schedule server restarts, raid weekend reminders, base damage windows, container damage windows, and vehicle reset workflows from one control area.": "Planuj restarty, przypomnienia o weekendach rajdowych, okna uszkodzeń baz i kontenerów oraz resetowanie pojazdów w jednym miejscu.",
        "Nitrado and Discord automation": "Automatyzacja Nitrado i Discorda", "Connect Nitrado, organise Discord channels, manage ban feeds, link gamertags, and keep staff actions visible.": "Połącz Nitrado, uporządkuj kanały Discorda, zarządzaj kanałami banów, łącz gamertagi i zachowaj widoczność działań obsługi.",
        "Automatic Discord translation": "Automatyczne tłumaczenie Discorda", "Give international communities readable conversations with original messages and translations posted in the same channel or routed to a dedicated translation channel.": "Zapewnij międzynarodowym społecznościom czytelne rozmowy z oryginalnymi wiadomościami i tłumaczeniami w tym samym lub osobnym kanale.",
        "What it covers": "Co obejmuje", "DayZ PC, PlayStation and Xbox killfeed, Discord server tools, Nitrado dashboard, live events, shop economy, and admin control.": "Killfeed DayZ na PC, PlayStation i Xbox, narzędzia Discorda, panel Nitrado, wydarzenia na żywo, ekonomia sklepu i sterowanie administratora.",
        "Choose your Discord server, approve the requested permissions, then let the bot create or repair its channel layout.": "Wybierz serwer Discord, zatwierdź wymagane uprawnienia, a następnie pozwól botowi utworzyć lub naprawić układ kanałów.",
        "Run": "Uruchom", "Enter platform, map, Nitrado token, service ID, FTP username, and FTP password. These are used for your server only.": "Wprowadź platformę, mapę, token Nitrado, identyfikator usługi, nazwę użytkownika FTP i hasło FTP. Dane są używane tylko dla twojego serwera.", "Use": "Użyj", ", then": ", następnie", "once your ADM log is available so feeds can begin tracking players.": "gdy dziennik ADM będzie dostępny, aby kanały mogły rozpocząć śledzenie graczy.",
        "Enable dashboard login for trusted admins, then manage live events, XML tools, shop, economy, zones, and moderation from the web panel.": "Włącz logowanie do panelu dla zaufanych administratorów, a następnie zarządzaj wydarzeniami, narzędziami XML, sklepem, ekonomią, strefami i moderacją w panelu WWW.", "Players can use": "Gracze mogą użyć", ". Staff can review links, run events, and keep the server tools organised from Discord or the dashboard.": ". Obsługa może sprawdzać połączenia, uruchamiać wydarzenia i porządkować narzędzia serwera z Discorda lub panelu.",
        "guidance, ADM connection checks, core Discord player and server feeds, leaderboards, Discord channel setup, and server rules. The dashboard plans below add the web control tools.": "wskazówki, kontrolę połączenia ADM, podstawowe kanały graczy i serwera na Discordzie, rankingi, konfigurację kanałów i zasady serwera. Poniższe plany panelu dodają internetowe narzędzia sterowania.",
    },
}

for _language, _phrases in PUBLIC_HOME_UI_TRANSLATIONS.items():
    UI_TRANSLATIONS[_language].update(_phrases)


# Additional reviewed marketing copy lives in data so the main localization
# module stays readable as public pages grow.  Loading is local and optional;
# a missing file never makes the dashboard unavailable.
_PUBLIC_TRANSLATION_DATA = Path(__file__).with_name("data") / "public_ui_translations.json"
try:
    _public_translation_payload = json.loads(_PUBLIC_TRANSLATION_DATA.read_text(encoding="utf-8"))
except (OSError, ValueError, TypeError):
    _public_translation_payload = {}
for _language in ("de", "fr", "es", "pl"):
    _phrases = _public_translation_payload.get(_language)
    if isinstance(_phrases, dict):
        UI_TRANSLATIONS[_language].update(
            {
                str(_english): str(_translated)
                for _english, _translated in _phrases.items()
                if str(_english).strip() and str(_translated).strip()
            }
        )


# Reviewed copy used by authenticated dashboard and AI Sandbox screens.  Keep
# this separate from public marketing copy so missing signed-in translations
# cannot be hidden by an otherwise complete homepage dictionary.
_DASHBOARD_TRANSLATION_DATA = Path(__file__).with_name("data") / "dashboard_ui_translations.json"
try:
    _dashboard_translation_payload = json.loads(_DASHBOARD_TRANSLATION_DATA.read_text(encoding="utf-8"))
except (OSError, ValueError, TypeError):
    _dashboard_translation_payload = {}
for _language in ("de", "fr", "es", "pl"):
    _phrases = _dashboard_translation_payload.get(_language)
    if isinstance(_phrases, dict):
        UI_TRANSLATIONS[_language].update(
            {
                str(_english): str(_translated)
                for _english, _translated in _phrases.items()
                if str(_english).strip() and str(_translated).strip()
            }
        )


UI_LOCALIZATION_CSS = r"""
.ui-language-control{display:inline-flex;align-items:center;gap:.42rem;padding:.36rem .5rem;border:1px solid rgba(53,212,194,.34);border-radius:10px;background:rgba(4,15,14,.9);color:#d9efeb;font:600 12px/1.2 system-ui,sans-serif;box-shadow:0 8px 22px rgba(0,0,0,.22)}
.ui-language-control label{white-space:nowrap;color:#a9c5c0}.ui-language-control select{max-width:132px;border:1px solid rgba(255,155,48,.55);border-radius:7px;background:#071311;color:#f5faf9;padding:.36rem .55rem;font:inherit;cursor:pointer}
.ui-language-control--floating{position:fixed;right:14px;top:72px;z-index:2147482000}.theme-picker .ui-language-control,.top-actions .ui-language-control,.header-actions .ui-language-control{margin-left:.35rem}
.google-play-launch{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:14px;margin:14px auto;padding:14px 16px;max-width:1180px;border:1px solid rgba(255,153,43,.58);border-left:4px solid #ff9829;border-radius:14px;background:linear-gradient(105deg,rgba(21,67,40,.96),rgba(4,25,23,.97));color:#effcf5;box-shadow:0 15px 35px rgba(0,0,0,.26)}
.google-play-launch__badge{display:inline-flex;align-items:center;justify-content:center;min-width:70px;padding:8px 10px;border-radius:999px;background:#28a745;color:#fff;font:800 11px/1 system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase}.google-play-launch__copy{display:grid;gap:3px}.google-play-launch__copy strong{font:800 clamp(15px,2vw,20px)/1.2 system-ui,sans-serif;color:#fff}.google-play-launch__copy span{font:500 13px/1.45 system-ui,sans-serif;color:#bfe2d4}.google-play-launch__button{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:0 15px;border:1px solid rgba(255,177,85,.8);border-radius:10px;background:#ff9829;color:#15100a!important;text-decoration:none!important;font:800 13px/1.1 system-ui,sans-serif;white-space:nowrap}.google-play-launch__button:hover{background:#ffb35c;transform:translateY(-1px)}
@media(max-width:720px){.google-play-launch{grid-template-columns:auto 1fr;margin:10px 12px}.google-play-launch__button{grid-column:1/-1;width:100%}.ui-language-control--floating{top:64px;right:8px}.ui-language-control label{display:none}}
.shell>.google-play-launch,.app-shell>.google-play-launch,main>.google-play-launch{width:100%}.shell>.google-play-launch{grid-column:1/-1;margin:0}.app-shell>.google-play-launch{margin:.1rem 0 .8rem}
"""


_UI_LOCALIZATION_JS_TEMPLATE = r"""
(() => {
  'use strict';
  const languages = __LANGUAGES__;
  const translations = __TRANSLATIONS__;
  const storageKey = 'wanderingUiLanguage';
  const skipSelector = '[data-no-translate],[translate="no"],code,pre,textarea,kbd,samp,script,style,noscript,[contenteditable="true"],.guide-code,.code-block,.file-editor,.xml-editor,.json-editor,.monaco-editor,.ace_editor';
  const originals = new WeakMap();
  const attributeOriginals = new WeakMap();

  function safeLanguage(value) {
    const code = String(value || '').trim().toLowerCase().split(/[-_]/)[0];
    return Object.prototype.hasOwnProperty.call(languages, code) ? code : 'en';
  }

  function requestedLanguage() {
    const query = new URLSearchParams(window.location.search).get('lang');
    if (query && Object.prototype.hasOwnProperty.call(languages, safeLanguage(query))) return safeLanguage(query);
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) return safeLanguage(saved);
    } catch (_) {}
    return safeLanguage(navigator.language || 'en');
  }

  function isTechnicalText(value) {
    const text = String(value || '').trim();
    if (!text) return false;
    return /<\/?[A-Za-z][^>]*>|^[\[{].*[\]}]$|\b(?:cfg\w+|types\.xml|events\.xml|mapgrouppos\.xml|mapgroupproto\.xml|cfggameplay\.json)\b|(?:^|\s)[A-Z][A-Za-z0-9]+_[A-Za-z0-9_]+|\b[XYZ]:\s*-?\d/i.test(text);
  }

  function translatableElement(element) {
    return element instanceof Element && !element.closest(skipSelector) && !element.closest('[data-ui-localizer]');
  }

  function normalizePhrase(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function directTextNodes(element) {
    return Array.from(element.childNodes).filter((node) => node.nodeType === Node.TEXT_NODE);
  }

  function directTextOriginal(node) {
    if (!originals.has(node)) originals.set(node, node.nodeValue || '');
    return originals.get(node);
  }

  function translatedText(original, language) {
    if (language === 'en') return original;
    const leading = original.match(/^\s*/)?.[0] || '';
    const trailing = original.match(/\s*$/)?.[0] || '';
    const key = original.slice(leading.length, original.length - trailing.length).replace(/\s+/g, ' ').trim();
    if (!key) return original;
    const result = translations[language]?.[key];
    if (result) return `${leading}${result}${trailing}`;
    if (isTechnicalText(key)) return original;
    return original;
  }

  function localizeTextNode(node, language) {
    const parent = node.parentElement;
    if (!parent || !translatableElement(parent)) return;
    if (!originals.has(node)) originals.set(node, node.nodeValue || '');
    const original = originals.get(node);
    const result = translatedText(original, language);
    if (node.nodeValue !== result) node.nodeValue = result;
  }

  function localizeElementPhrase(element, language) {
    if (!(element instanceof Element) || !translatableElement(element)) return false;
    if (element.matches('select,option,input,button,textarea')) return false;
    if (element.querySelector('div,p,section,article,aside,header,footer,nav,ul,ol,table,form')) return false;
    const nodes = directTextNodes(element);
    if (!nodes.length) return false;
    const originalPhrase = normalizePhrase(Array.from(element.childNodes).map((node) => {
      if (node.nodeType === Node.TEXT_NODE) return directTextOriginal(node);
      if (node instanceof Element && node.matches('code,kbd,samp')) return node.textContent || '';
      return '';
    }).join(' '));
    if (!originalPhrase) return false;
    const translated = language === 'en' ? originalPhrase : translations[language]?.[originalPhrase];
    if (!translated) return false;
    const target = nodes[0];
    const leading = directTextOriginal(target).match(/^\s*/)?.[0] || '';
    const trailing = directTextOriginal(nodes[nodes.length - 1]).match(/\s*$/)?.[0] || '';
    target.nodeValue = `${leading}${translated}${trailing}`;
    for (const node of nodes.slice(1)) node.nodeValue = '';
    return true;
  }

  function ensureInlineSpacing(element) {
    if (!(element instanceof Element) || !translatableElement(element)) return;
    const children = Array.from(element.childNodes);
    for (let index = 1; index < children.length; index += 1) {
      const previous = children[index - 1];
      const current = children[index];
      if (!(previous instanceof Element) || current.nodeType !== Node.TEXT_NODE) continue;
      if (!previous.matches('strong,b,code,kbd,samp')) continue;
      const value = current.nodeValue || '';
      if (value && !/^\s|^[,.;:!?)]/.test(value)) current.nodeValue = ` ${value}`;
    }
  }

  function localizeAttributes(element, language) {
    if (!translatableElement(element)) return;
    let saved = attributeOriginals.get(element);
    if (!saved) { saved = {}; attributeOriginals.set(element, saved); }
    for (const name of ['placeholder', 'title', 'aria-label']) {
      if (!element.hasAttribute(name)) continue;
      if (!(name in saved)) saved[name] = element.getAttribute(name) || '';
      const original = saved[name];
      const result = translatedText(original, language);
      if (element.getAttribute(name) !== result) element.setAttribute(name, result);
    }
  }

  function localizeRoot(root, language) {
    if (root.nodeType === Node.TEXT_NODE) return localizeTextNode(root, language);
    if (!(root instanceof Element) && root !== document) return;
    if (root instanceof Element) localizeAttributes(root, language);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (node.nodeType === Node.TEXT_NODE) {
        if (!(node.parentElement && localizeElementPhrase(node.parentElement, language))) localizeTextNode(node, language);
      } else {
        localizeAttributes(node, language);
        localizeElementPhrase(node, language);
        ensureInlineSpacing(node);
      }
    }
  }

  function setLanguage(value) {
    const language = safeLanguage(value);
    try { localStorage.setItem(storageKey, language); } catch (_) {}
    document.cookie = `wandering_ui_language=${encodeURIComponent(language)}; Path=/; Max-Age=31536000; SameSite=Lax`;
    document.documentElement.lang = language;
    const selector = document.getElementById('wandering-ui-language');
    if (selector && selector.value !== language) selector.value = language;
    localizeRoot(document.body, language);
    window.dispatchEvent(new CustomEvent('wandering:language-changed', {detail: {language}}));
  }

  function mountSelector(language) {
    if (document.getElementById('wandering-ui-language')) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'ui-language-control';
    wrapper.dataset.uiLocalizer = 'true';
    wrapper.title = 'Interface only. DayZ technical content remains unchanged.';
    const label = document.createElement('label');
    label.htmlFor = 'wandering-ui-language';
    label.textContent = 'Language';
    const select = document.createElement('select');
    select.id = 'wandering-ui-language';
    select.setAttribute('aria-label', 'Interface language');
    for (const [code, name] of Object.entries(languages)) {
      const option = document.createElement('option');
      option.value = code; option.textContent = name; select.appendChild(option);
    }
    select.value = language;
    select.addEventListener('change', () => setLanguage(select.value));
    wrapper.append(label, select);
    const host = document.querySelector('.theme-picker') || document.querySelector('.top-actions') || document.querySelector('.header-actions') || document.querySelector('.app-header') || document.querySelector('.topbar');
    if (host) host.appendChild(wrapper);
    else { wrapper.classList.add('ui-language-control--floating'); document.body.appendChild(wrapper); }
  }

  const language = requestedLanguage();
  function start() {
    mountSelector(language);
    setLanguage(language);
    let queued = false;
    const observer = new MutationObserver((mutations) => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;
        const active = safeLanguage(document.getElementById('wandering-ui-language')?.value || language);
        for (const mutation of mutations) for (const node of mutation.addedNodes) localizeRoot(node, active);
      });
    });
    observer.observe(document.body, {childList: true, subtree: true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
"""


def ui_localization_javascript() -> str:
    return (
        _UI_LOCALIZATION_JS_TEMPLATE
        .replace("__LANGUAGES__", json.dumps(SUPPORTED_UI_LANGUAGES, ensure_ascii=False))
        .replace("__TRANSLATIONS__", json.dumps(UI_TRANSLATIONS, ensure_ascii=False))
    )
