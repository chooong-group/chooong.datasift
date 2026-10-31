# AGENTS.md — Arbeitsregeln für Python-Packages

Gilt für jedes Python-Package-Repository. Die jeweils aktuelle Repository-Konfiguration (`pyproject.toml`, `tox.ini`, `Makefile`, CI-Workflows) bestimmt Stack, Befehle und Ordner; keine Pfade oder Befehle aus einem anderen Repo übernehmen. Repositoryspezifische Besonderheiten gehören in die Fachdokumentation des Repos, nicht in abweichende AGENTS-Regelwerke. Explizite Aufträge und verbindliche Architekturentscheidungen gelten zusätzlich, sofern sie nicht Sicherheit oder Datenintegrität verletzen.

Leitbild ist der faule Senior-Entwickler („Ponytail"-Prinzip, nach `DietrichGebert/ponytail`): Faul heißt effizient, nicht nachlässig. Der beste Code ist der Code, der nie geschrieben wurde. Das Prinzip steckt in Abschnitt 1 (Lösungsleiter, Root Cause), Abschnitt 2 (Faulheit mit Maß) und Abschnitt 4 (minimaler Nachweis). Es gilt nie gegen Architektur-, Sicherheits-, Test- und Dokumentationsregeln dieses Dokuments; bei einem Konflikt haben diese Vorrang.

## 1. Arbeitsbeginn und Scope

1. Vor jeder Änderung erfassen: Repository, aktueller Branch, `git rev-parse HEAD`, `git status --short`, Basis-SHA, offene PRs sowie `git diff --name-only <basis>...HEAD`. Offene oder fremde Änderungen nicht überschreiben. Offene PRs desselben Themenbereichs vor der Planung vollständig prüfen.
2. Zuerst die geltenden Architekturentscheidungen, den öffentlichen Contract (Public API, CLI, Config, Wire-/Dateiformate), die direkten Consumer sowie alle betroffenen Dateien, Tests, Workflows und Migrationen vollständig lesen. Eine Codesuche ist kein Dateireview. Fehlender Zugriff = `UNVERIFIED` samt Grund.
3. Ein Auftrag, ein Feature-Branch, ein Repository, ein PR. Keine Cross-Repo-Codeänderungen, keine Folgeaufträge ohne Erlaubnis. Einen bestehenden auftragsbezogenen Branch weiterverwenden. Nie direkt auf `main` arbeiten.
4. Änderungen minimal und vollständig auf den Auftrag begrenzen. Keine beiläufigen Refactorings, zusätzlichen Frameworks oder erfundenen Infrastrukturkomponenten. Den Dateiumfang nach tatsächlich gefundenen Abhängigkeiten präzisieren und dokumentieren.
5. Den gesamten ausführbaren Auftrag selbstständig erledigen. Nur bei echten, ungeklärten Architektur-, Sicherheits- oder Contract-Widersprüchen nachfragen; nicht raten und nichts partiell als fertig ausgeben.
6. Tests werden erst ausgeführt und neue geschrieben, wenn alles funktional fertig ist!
7. Datenbank zugriff erfolgt immer über die DATABASE_URL aus der .env lokal. wir brauchen kein tmp host!
8. Rudd Rules werden nicht in der pyproject.toml geändert!
9. **Lösungsleiter:** Nach dem Verstehen des Problems (Punkt 2) und vor jedem Code beim ersten tragenden Schritt stehen bleiben:
   1. Muss das überhaupt gebaut werden? (YAGNI)
   2. Gibt es das schon in diesem Codebase? Vorhandenen Helper, Util oder vorhandenes Pattern wiederverwenden, nicht neu schreiben.
   3. Deckt die Standardbibliothek es ab? Dann diese nutzen.
   4. Deckt eine native Plattform- oder Framework-Funktion es ab (Pydantic, Dataclasses, Datenbank-Constraints)? Dann diese nutzen.
   5. Löst eine bereits installierte Abhängigkeit es? Dann diese nutzen.
   6. Geht es in einer Zeile? Dann eine Zeile.
   7. Erst dann: den minimalen Code schreiben, der funktioniert.

   Die Leiter ersetzt das Verstehen nicht: Auftrag und berührten Code lesen, den realen Ablauf Ende-zu-Ende nachvollziehen, erst dann steigen. Keine Stufe darf Auftrag, Architekturschnitt (Abschnitt 2), Sicherheit oder Datenintegrität verletzen.
10. **Bugfix = Root Cause, nicht Symptom:** Eine Meldung nennt ein Symptom. Alle Aufrufer der zu ändernden Funktion im Repo suchen (direkte Consumer im Abdeckungsprotokoll erfassen, nicht ändern) und die gemeinsame Funktion einmal an der Ursache korrigieren. Ein Guard dort ist ein kleinerer Diff als je einer pro Aufrufer; nur den im Ticket genannten Pfad zu patchen lässt einen Geschwister-Aufrufer defekt. Der Negativfall bekommt einen Test (Abschnitt 4).

## 2. Architektur und Contracts

- **Hexagonale Architektur:** Domain und Application bleiben unabhängig von konkreten Transport-, Datenbank-, Netzwerk- und I/O-Implementierungen. Fachliche Bibliotheken und Standardbibliothekstypen sind zulässig. Die Fachlogik spricht mit der Außenwelt über Ports (`Protocol` oder ABC), die ausschließlich an tatsächlichen Austauschgrenzen verwendet werden, nicht für jeden Funktionsaufruf. Adapter (Datenbank, HTTP, CLI, Dateien, externe APIs) implementieren diese Ports und hängen von der Fachlogik ab, nie umgekehrt. Abhängigkeiten werden von außen injiziert, die Verdrahtung geschieht an einer einzigen Stelle (Composition Root). Neuer und geänderter Code folgt diesem Schnitt; eine bestehende abweichende Struktur wird nicht beiläufig umgebaut, sondern nur auf ausdrücklichen Auftrag.
- **KISS:** Die einfachste Lösung, die Auftrag und Invarianten erfüllt. Keine spekulative Allgemeinheit, keine künstlichen Wrapper oder Abstraktionen ohne zweite reale Implementierung oder Austauschgrenze. Keine Hilfsfunktionen oder Utility-Module für Aufgaben, die Pydantic oder Dataclasses bereits leisten, insbesondere nicht für Validierung, Parsing oder Serialisierung.
- **Faulheit mit Maß (Ponytail):** Innerhalb von Auftrag und Architekturschnitt gilt:
  - Keine Abstraktionen, die nicht ausdrücklich beauftragt sind; Ports nur an echten Austauschgrenzen (siehe Hexagonale Architektur).
  - Keine neue Abhängigkeit, wenn sie vermeidbar ist; kein Boilerplate, das niemand verlangt hat.
  - Löschen vor Hinzufügen, langweilig vor clever, so wenige Dateien wie der Architekturschnitt zulässt.
  - Der kürzeste funktionierende Diff gewinnt, aber erst nach dem Verstehen des Problems. Die kleinste Änderung am falschen Ort ist kein fauler Fix, sondern ein zweiter Bug.
  - Komplexe Aufträge hinterfragen („Braucht es X, oder reicht Y?"). Der Einwand und die einfachere Alternative werden im Plan oder Abschlussbericht vermerkt; eine Rückfrage an den Nutzer erfolgt nur unter den Bedingungen aus Abschnitt 1, Punkt 5.
  - Bei zwei gleich großen Standardbibliotheks-Varianten die randfallkorrekte wählen: weniger Code, nicht der fragilere Algorithmus.
  - Bewusste Vereinfachungen, die eine reale Ecke mit bekannter Grenze abschneiden (globales Lock, O(n²)-Scan, naive Heuristik), mit einem `ponytail:`-Kommentar markieren, der die Grenze und den Upgrade-Pfad nennt. Der Kommentar ersetzt keine Dokumentation von Contract-relevanten Einschränkungen.
- **Nie faul bei:** Verstehen des Problems (eine kleine Änderung ohne Verständnis ist Faulheit im Effizienz-Kostüm), Eingabevalidierung an Vertrauensgrenzen, Fehlerbehandlung gegen Datenverlust, Sicherheit (Abschnitt 3), Barrierefreiheit, Kalibrierung realer Systeme (Uhren driften, Sensoren und Geräte weichen von der Spezifikation ab), allem ausdrücklich Beauftragten sowie den Nachweisen aus Abschnitt 4. Fauler Code ohne seinen Check ist unfertig.
- **Modellierung:** Komplexe, strukturierte Eingaben an Systemgrenzen (API, CLI, Dateien, Messages, Config) werden mit Pydantic-Modellen validiert und geparst; Pydantic wird nur ergänzt, wenn ein Package solche Eingaben tatsächlich hat. Interne Wertobjekte und Datentransfer nutzen `dataclass` (bevorzugt `frozen=True`, `slots=True`). Funktionen und Methoden erhalten zusammengehörige Daten als ein typisiertes Objekt statt als lange Parameterlisten oder lose Dicts.
- **Klassen und Funktionen:** Zustandsbehaftete Services, Use Cases, Adapter und Repositories werden als Klassen mit klarer Verantwortung und injizierten Abhängigkeiten umgesetzt. Reine, zustandslose Berechnungen dürfen unabhängig von ihrer Größe als typisierte Funktionen implementiert werden; eine Klasse nur um der Klasse willen ist unzulässig.
- **Konfiguration:** Besitzt ein Package Laufzeitkonfiguration, kommt sie ausschließlich über Pydantic Settings (`pydantic-settings`): typisiert, validiert, ohne verstreutes `os.environ`/`os.getenv` im Code, Secrets als `SecretStr`. Settings werden einmal an der Composition Root gelesen und als Objekt übergeben, nicht global importiert. Ein reines Berechnungs-Package ohne Laufzeitkonfiguration erhält keine künstliche Settings-Klasse.
- Die öffentliche API wird durch ausdrücklich dokumentierte Importpfade, Exportnamen, CLI-Befehle und versionierte Config-/Wire-Verträge festgelegt. `__all__` unterstützt die Exportpflege, ersetzt aber keine Contract-Deklaration. Interne Module (`_`-Präfix, `_internal`) sind keine zugesicherte API. Consumer greifen nicht auf interne Klassen, Datenbanken oder Dateiformate zu.
- Vertragsänderungen zuerst am kanonischen Modell vornehmen; daraus generierte Schemas/Manifeste aus derselben Quelle regenerieren. Dokumentieren: API-/Config-/Wire-Semantik, Versionierung, Umgang mit unbekannten Feldern, negative Fälle, Kompatibilitätsstrategie und betroffene direkte Consumer. Keine stillen Vertragsänderungen.
- Breaking Changes sind nur bei ausdrücklich vereinbarter Neuentwicklung oder explizitem Auftrag zulässig und als solche zu dokumentieren. Bei Greenfield-Aufträgen keine Legacy-/Migrationspflicht erfinden.
- Fehlende Informationen bleiben `unknown` und werden niemals stillschweigend als `0`, `false`, `free`, `verified`, `active` oder `connected` interpretiert. Sicherheits-, Berechtigungs-, Kosten- und Ausführungsentscheidungen sind bei unzureichender Information fail-closed. Optionale Darstellungsdaten dürfen unbekannt bleiben.
- Geld, Mengen und Zeiten korrekt modellieren: `Decimal` und explizite Währung statt `float`, UTC und explizite Kalenderfenster, keine naiven `datetime`-Objekte.
- Typisierung: Öffentliche Signaturen vollständig annotieren, `py.typed` bereitstellen, Typfehler nicht per `# type: ignore` ohne Begründung unterdrücken. Python-Mindestversion und Abhängigkeitsgrenzen in `pyproject.toml` pflegen. Neue Laufzeitabhängigkeiten nur bei nachgewiesenem Bedarf ergänzen und mit begründeten, kompatiblen Versionsgrenzen deklarieren. Entwicklungs- und Release-Builds über die tatsächlich vorhandenen Lock- und Build-Mechanismen reproduzierbar halten.

## 3. Sicherheit und Datenintegrität

- Authentifizierung, Autorisierung, Tenant-/Owner-Isolation an jeder mutierenden oder secret-lesenden Grenze erzwingen; UI-Sperren allein sind keine Security.
- Keine echten Secrets, Tokens, Connection-Strings, Credential-Werte oder personenbezogenen Daten in Git, Logs, Fehlermeldungen, URL-Ausgaben, Reprs oder Tests. Eindeutig synthetische Test-Credentials sind zulässig. Secrets verschlüsselt und kontogebunden speichern; Klartext nur für nachweislich autorisierte Ausführung.
- Transaktionsgrenzen und konkurrierende Updates definieren. Idempotency-Key mit Payload-Bindung, Replay, Timeout, Crash, Rate-Limit, Teilfehler, doppelte Events und Recovery explizit berücksichtigen. Unklare externe Ausführung nicht als garantiert erfolgreich oder garantiert fehlgeschlagen verbuchen.
- Eingaben aus untrusted Quellen validieren (Pfade, Archive, Deserialisierung, Subprozess-Argumente, SQL, Templates). Kein `eval`/`exec`/`pickle` auf externen Daten, kein `shell=True` mit unvalidierten Eingaben.
- Bei Greenfield-Aufträgen ausschließlich Fresh-Schema, Constraints und neue Testdaten prüfen; historische Upgrades, Downgrades und Altbestand sind dann keine Abnahmekriterien. Ohne explizite Freigabe niemals bestehende Entwicklungs- oder Produktivdaten verändern oder löschen.
- Bestehende lokale Dienste, Container und Server nur diagnostizieren; nicht starten, stoppen, löschen, resetten oder einen zweiten Stack erstellen. Integrationstests nur in belegbar isolierten Datenbanken/Ressourcen.

## 4. Belegbare Tests

- Für jede fachliche Änderung zuerst Invariante, echten Produktionspfad, beobachtbare Wirkung und Negativgegenfall festlegen. Tests müssen diese Wirkung assertieren, nicht nur Mocks oder Aufrufe bestätigen.
- **Minimaler Nachweis (Ponytail):** Das ist die Untergrenze, keine Obergrenze. Rein technische Einzeiler ohne fachliche Wirkung brauchen keinen Test. Jede nicht-triviale Logik hinterlässt mindestens einen ausführbaren Check, der fehlschlägt, sobald die Logik bricht (kleinste Form: ein assert-basierter Selbsttest oder eine kleine Testdatei). Dafür kein zusätzliches Test-Framework und keine Fixtures ohne Bedarf; das bereits im Repo genutzte Test-Setup wiederverwenden. Fachliche Änderungen erfüllen darüber hinaus die übrigen Regeln dieses Abschnitts vollständig.
- Bestehende Tests auf Relevanz prüfen. Keine `assert True`, bloßen Existenztests, sinnlosen Snapshots, Mock-bestätigt-Mock-Tests oder künstlichen E2E-Harnesses. Kein unnötiges doppeltes CI-Gate.
- Passende Unit-, Contract-, Fresh-Schema- und lokale Integrationsnachweise gegen echte isolierte lokale Komponenten. Externe APIs (Broker, Zahlung, Marktdaten, Drittdienste) ausschließlich durch strikte Fakes, Fixtures oder offizielle Contract-Schemas ersetzen. Keine Live-API-Calls verlangen oder ausführen.
- Negativfälle nach fachlicher Relevanz testen: Berechtigung, Tenant-Leak, 4xx/5xx, Timeout, 429, Teilantwort, Replay, Race, Rundung, Secret-Redaction. Kein mechanisches Testen jeder theoretischen Variante.
- Projektdefinierte Lint-, Format-, Typcheck-, Build- und Testbefehle aus dem aktuellen Repo ermitteln und ausführen; vor dem PR zusätzlich `git diff --check`. Nicht ausgeführte Prüfungen oder fehlende lokale Umgebung = `UNVERIFIED`, niemals als Erfolg behaupten. CI-Läufe nicht manuell starten, pollen oder abwarten; der Nutzer prüft CI nach PR-Erstellung.
- `[x] GESCHLOSSEN` ausschließlich nach Belegen für Implementation, Fehlerpfade, Datenintegrität, Idempotenz/Replay, relevante automatische Tests und lokal mögliche Integration. Grüne CI allein genügt nicht. `DEFERRED` ist ausschließlich zulässig, wenn die Funktion nachweislich standardmäßig deaktiviert ist, andere Funktionen nicht beeinträchtigt und nirgends als fertig dargestellt wird. Alle drei Bedingungen sind einzeln zu belegen.

## 5. Git, Release und Dokumentation

- Änderungen gezielt stagen (`git add <pfad>`); sinnvolle Commits mit `feat|fix|test|docs|chore|refactor: ...`. Kein `git add -A`, Force-Push, `--no-verify`, History-Rewrite oder PR-Selbstmerge.
- Vor dem PR den vollständigen Diff prüfen, einschließlich ungewollter Löschungen sowie aller betroffenen Contracts, Tests, Configs, Migrationen und CI-Workflows. Genau einen PR erstellen und danach stoppen. Merge, Tag und Release nur auf expliziten Nutzerauftrag.
- Versionssprünge nur bei explizitem Auftrag. Versionierung, deklarierte Breaking Changes und das gebaute Release-Artefakt gesondert belegen. Bei Package-Releases den gebauten Kernpfad mit dem exakten Kandidaten-Wheel (und sdist) lokal in frischer Umgebung nachweisen sowie direkte Consumer-Änderungen und nötige separate Integrationsaufträge dokumentieren. Ein neues Release ist nicht gleichbedeutend mit einer integrierten Consumer-Funktion; Consumer-Integration nie als erledigt melden, wenn sie nicht beauftragt und nachgewiesen ist. Bei vorhandenen unterstützten direkten Consumern ist mindestens ein tatsächlicher Import-/Config-/Wire-Pfad gegen das exakt gebaute Release-Artefakt zu prüfen. Cross-Repo-Codeänderungen sind dabei verboten. Bei ausdrücklich vereinbarten Greenfield-Breaking-Changes dürfen noch nicht umgestellte Consumer als inkompatibel dokumentiert und separat beauftragt werden; ihre Integration gilt nicht als abgeschlossen.
- **CHANGELOG.md** wird in jedem PR geprüft und bei jeder nutzer- oder consumerrelevanten Änderung aktualisiert. Änderungen stehen unter `Unreleased`, gruppiert nach `Added`, `Changed`, `Fixed`, `Removed`, `Security`. Breaking Changes, Contract-Änderungen und Migrationshinweise werden ausdrücklich gekennzeichnet. Die Release-Version wird nur im ausdrücklichen Releaseauftrag gesetzt. Rein interne Änderungen ohne Auswirkungen auf Nutzer oder Consumer erhalten keinen Changelog-Eintrag. Bleibt die Datei unverändert, wird dies im Abdeckungsprotokoll dokumentiert (`CHANGELOG.md GEPRÜFT, unverändert`).
- **README.md** wird in jedem PR geprüft und bei jeder Änderung an Einstieg, Installation, Benutzung, Voraussetzungen, Konfiguration, Architektur oder öffentlichem Contract aktualisiert. Bleibt sie unverändert, steht im Abdeckungsprotokoll `README.md GEPRÜFT, unverändert`. Sie ist ein kompakter menschlicher Einstieg, in etwa zwei Minuten lesbar, und enthält:
  1. Name und Zweck in ein bis drei Sätzen, einschließlich Abgrenzung (was das Package nicht tut).
  2. Status und Voraussetzungen: unterstützte Python-Versionen, Laufzeitabhängigkeiten mit externen Diensten oder Systempaketen, Reifegrad (z. B. Greenfield, Breaking Changes erlaubt).
  3. Installation mit dem tatsächlich gültigen Befehl für den Distributionsnamen.
  4. Quickstart: ein kurzes, lauffähiges und verifiziertes Beispiel mit dem öffentlichen Importpfad und, falls vorhanden, dem CLI-Befehl. Kein Beispiel mit Namen, die es nicht gibt.
  5. Öffentliche API und Konfiguration: eine kurze Übersicht der zugesicherten Importpfade, CLI-Befehle und Config-Schlüssel mit Verweis auf die Fachdokumentation. Keine duplizierten Contract-Tabellen.
  6. Architektur: wenige Sätze oder ein kleines Diagramm zu Schichten, Verantwortlichkeiten und Abgrenzung zu Consumern.
  7. Entwicklung: Setup der Umgebung sowie die tatsächlichen Lint-, Typcheck-, Test- und Build-Befehle des Repos.
  8. Verweise auf `CHANGELOG.md`, weitere Dokumentation und Lizenz.
  Keine Werbung, Emoji-Spam, AI-Floskeln, Testprotokolle, Roadmaps als Funktionszusage oder Inhalte, die schon in der Fachdokumentation stehen.
- Dokumentation beschreibt keine zukünftige Funktion als bereits implementiert; archivierte Entscheidungen nicht als aktuellen Stand ausgeben.

## 6. Abschlussformat

1. **Prüfstand:** Repo, Branch, Basis-SHA, HEAD, PR, Zeitpunkt, exakter Diff.
2. **Urteil:** `FREIGABE`, `BLOCKIERT` oder `NICHT ENTSCHEIDBAR`, mit einem Satz Grund.
3. **Befunde:** ID, Priorität, `[x] GESCHLOSSEN` / `[ ] OFFEN` / `UNVERIFIED`, Datei:Zeile beziehungsweise Test-/Befehlsbeleg, Auswirkung, Korrektur.
4. **Abdeckungsprotokoll** für alle betroffenen Dateien, Configs, Tests, Workflows und Consumer mit `GEPRÜFT` bzw. `NICHT GEPRÜFT` + Grund.
5. **Ausgeführte Befehle** mit Ausgabe und Exit-Code; CI und nicht mögliche lokale Tests als `UNVERIFIED`.
6. **TODOs:** Für jeden offenen oder unverifizierten Befund ein einzeln abnehmbares TODO mit Basis-SHA, präzisem Soll, Dateien, Schritten, Negativ-/Replay-Tests, Verifikationsbefehlen, Kriterien, Abhängigkeiten und Consumer-Auswirkung. Keine Sammel-TODOs. Eine Eigenmeldung des Agenten schließt kein TODO; ein unabhängiges Re-Review ist erforderlich.
7. Kein Gesamtfreigabeversprechen bei fehlender Datei-/Consumer-Abdeckung oder bei Lücken in Contract, Datenkorrektheit, Reliability oder Tests.


## 7. Verbindliche Entwicklungsrichtlinien

**Du arbeitest als Senior Software Engineer – nicht als Junior. Dein Code muss diesem Anspruch entsprechen.**

1. **Keine statischen Mappings oder hartcodierten Zuordnungen.** Provider, Worker, Kategorien, Fähigkeiten und API-Operationen müssen dynamisch aus ihren autoritativen Contracts bzw. Registrierungen aufgelöst werden.

2. **Keine Magic Strings in der Geschäftslogik.** Konstrukte wie `if day == "monday"` oder `if provider == "eodhd"` sind nicht akzeptabel. Verwende typisierte Modelle, Enums, stabile IDs und validierte Contracts.

3. **Single Source of Truth.** Keine doppelt gepflegten Operationslisten, HTTP-Mappings, JSON-Tabellen oder Konstantensammlungen. Änderungen am Contract dürfen keine manuellen Anpassungen an mehreren Stellen erfordern.

4. **Keine Scheinabstraktionen.** Keine unnötigen Wrapper, künstlichen Services, redundanten Adapter oder Boilerplate. Jede Abstraktion muss einen konkreten technischen Zweck erfüllen.

5. **Keine Fehler kaschieren.** Kein `type: ignore`, `Any`, stiller Fallback oder pauschales Exception-Handling, um fehlerhafte Architektur oder inkompatible Schnittstellen zu verstecken.

6. **Dynamisch bedeutet nicht unkontrolliert.** Alle externen Werte werden an der Systemgrenze typisiert und validiert. Unbekannte Provider, Kategorien, Methoden oder Contracts müssen kontrolliert abgewiesen werden (Fail-Closed).

7. **Keine Schwurbel-Tests.** Teste reale Geschäftsabläufe, Fehlerpfade, Concurrency, Idempotenz und Datenkorrektheit. Interne Logik nicht wegmocken. Playwright muss die tatsächliche Integration nachweisen.

8. **Bestehenden Code kritisch hinterfragen.** Schlechte Architektur nicht einfach erweitern. Ursachen beheben, redundanten Code entfernen und bestehende öffentliche Contracts respektieren.

**Grundregel:** Fachlich veränderliche Zuordnungen gehören in typisierte, dynamisch geladene Contracts oder Registrierungen – nicht als hartcodierte Entscheidungen in den Sourcecode.

**Für jede Änderung:** Betroffene Dateien vollständig prüfen, die Ursache beheben und das Ergebnis mit `Datei:Zeile` sowie aussagekräftigen Tests nachweisen.

**Qualitätsmaßstab: wartbar, typsicher, dynamisch, nachvollziehbar und zuverlässig. Keine Quick-Fixes.**
