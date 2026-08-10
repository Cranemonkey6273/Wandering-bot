"""Safe, interface-only localization assets for the Wandering Bot web UI.

The browser helper deliberately translates only exact, owner-reviewed interface
phrases.  It never sends content to an external translation service and skips
all code/file editing surfaces so DayZ class names and file data remain exact.
"""

from __future__ import annotations

import json


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
        "Open App": "Abrir app", "Contact support": "Contactar con soporte", "Home": "Inicio", "Feeds": "Feeds",
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
        "Open App": "Otwórz aplikację", "Contact support": "Skontaktuj się z pomocą", "Home": "Strona główna",
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

  function translatedText(original, language) {
    if (language === 'en') return original;
    const leading = original.match(/^\s*/)?.[0] || '';
    const trailing = original.match(/\s*$/)?.[0] || '';
    const key = original.slice(leading.length, original.length - trailing.length).replace(/\s+/g, ' ').trim();
    if (!key || isTechnicalText(key)) return original;
    const result = translations[language]?.[key];
    return result ? `${leading}${result}${trailing}` : original;
  }

  function localizeTextNode(node, language) {
    const parent = node.parentElement;
    if (!parent || !translatableElement(parent)) return;
    if (!originals.has(node)) originals.set(node, node.nodeValue || '');
    const original = originals.get(node);
    const result = translatedText(original, language);
    if (node.nodeValue !== result) node.nodeValue = result;
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
      if (node.nodeType === Node.TEXT_NODE) localizeTextNode(node, language);
      else localizeAttributes(node, language);
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
