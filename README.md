---
type: project
status: aktiv
tags: [pablo, static-ads, higgsfield, web-app, immunifanten]
created: 2026-05-22
updated: 2026-05-28
---

# Pablo — Cleverbrands Ad Generator

Single-HTML-Web-App zum Erzeugen der kompletten E-Commerce-Bildwelt via Higgsfield. Drei Bildtypen, gleiche Pipeline:

- **Werbeanzeigen** — Static Ads aus Produktbild(ern) + Wettbewerber-Referenzen (Layout-Transfer).
- **Onlineshop** — Produktseiten-Bilder über vier Vorlagen: Hero/Banner, Lifestyle/In-Use, Benefit-/Feature-Grafik, Clean Product & Detail. Format wird pro Vorlage automatisch gesetzt. Referenzen sind hier optional und wirken als reine Stil-Inspiration (Licht, Stimmung, Bildlook), kein Layout-Transfer wie bei Ads.
- **Amazon Listing** — der komplette Listing-Bilder-Stack. Geplant, wird als Nächstes gebaut.

Geteilt über alle Typen: Brand Kits für mehrere Marken, Reference Library mit Tags, automatisches Speichern in IndexedDB plus Download, iteratives Refinement pro Bild via Feedback-Loop.

> Pablo ist der interne Name des Tools — gewählt wie ein Mitarbeiter. "Pablo, mach mir vier Varianten" ist die Idee.

## Starten

`start.command` doppelklicken. Der lokale Proxy startet auf `http://localhost:8000` und öffnet die App im Browser. Wichtig: nicht die HTML direkt anklicken — der Higgsfield-OAuth-Login funktioniert nur über `http://localhost`, nicht über `file://`.

## Erst-Setup

1. App öffnet sich auf `http://localhost:8000/ad-generator.html`.
2. In **Settings** → **Higgsfield-Konto** auf **„Mit Higgsfield anmelden"** klicken. Du wirst zu higgsfield.ai weitergeleitet, loggst dich mit deinem Web-Abo-Account ein und kommst zurück auf localhost.
3. **Anthropic API Key** eintragen (für Discuss-Chat, kommt in Phase 1.5 — kann leer bleiben).
4. Defaults sind voreingestellt: Modell `gpt_image_2`, Format `1:1`, Qualität `medium`.

OAuth-Token und Settings liegen in `localStorage` deines Browsers, lokal auf diesem Mac. Generierungen werden auf dein bestehendes Higgsfield-Abo gebucht — keine API-Keys, keine zusätzlichen Kosten.

## Workflow

1. **Brand Kit** anlegen: Marke, **mehrere Produktbilder** (z.B. Verpackung + tatsächliches Produkt), Logo, Farben, Maskottchen, Tonalität, Do's/Don'ts, Beispiel-Texte.
2. **Reference Library** füllen: Wettbewerber-Ads als Inspiration. Pro Referenz Tags, Notizen und **abstrahiertes Prinzip** (kritisch — leere Felder → generischer Prompt). Bulk-Drop für mehrere Bilder.
3. **Generate**: Brand Kit + **mehrere Produktbilder per Multi-Select** + Referenzen wählen, Format und Modell setzen, Generate klicken. Pro Referenz eine Variante, oder konsolidiert. "Zusätzliche Anweisungen" werden an den Auto-Prompt angehängt.
4. **Output**: Bilder erscheinen in der Gallery, werden in IndexedDB gespeichert und als PNG ins Download-Verzeichnis abgelegt. Pro Karte gibt's einen **↺ Verbessern**-Button für Feedback-Refinement.
5. **Refinement**: Feedback-Text eintippen → der Output + Brand-Anker werden als Image-Inputs zurück an Higgsfield geschickt mit dem Feedback als Prompt. Neue Karte erscheint, alte bleibt vergleichbar daneben.

## Was Pablo noch NICHT kann

- Amazon-Listing-Generierung (Bildtypen sind im UI als Platzhalter sichtbar, Prompt-Logik fehlt — nächster Schritt)
- Discuss-Chat mit Claude (Phase 1.5)
- History-Tab mit Filter und Re-Generate aus alten Läufen (Phase 1.5 — DB ist schon da, UI fehlt)
- Refinement aus dem History-Tab (aktuell nur aus "Aktueller Lauf")
- Team-Hosting mit Auth (Phase 2)
- Meta Ad Library Auto-Scraping (Phase 2)
- Auto-Prinzip via Claude Vision für Referenzen mit leerem `extractedPrinciple` (geplant)
- Konfigurierbares Polling-Timeout in den Settings (aktuell hartkodiert 15 Min)

## Modell-Notizen

Stand 2026-05-23 — getestet mit Immunifanten-Verpackung als Produktbild:

- **`gpt_image_2`** → **Bester Default für Produkt-Ads.** Preserved Verpackung, Label-Typografie und Maskottchen sauber. Starke Image-to-Image-Treue.
- **`nano_banana`** → Solide Alternative, etwas schwächer bei Detail-Treue. Brauchbar wenn gpt_image_2 mal nicht passt.
- **`soul_2`** → **Nicht für Produkte.** Modell ist auf Personen, Portraits, UGC, Fashion trainiert. Ignoriert oder transformiert Verpackungs-Details.
- **`nano_banana_pro`** → Noch nicht ausführlich getestet, laut Higgsfield "top quality, 4K, text/diagrams".
- **`marketing_studio_image`** → Noch nicht aufgesetzt. Higgsfields offizieller Pfad für DTC-Ads, braucht aber ein **Brand Kit** (Logo, Hero-Bilder, Farben, Tonalität). Kann automatisch von Brand-Website gescraped werden via `show_marketing_studio(action='fetch')`.

## Technischer Hinweis: MCP-Architektur

Die App spricht **nicht** mehr die alte REST-API von `platform.higgsfield.ai` an, sondern den **MCP-Server** auf `mcp.higgsfield.ai/mcp` via JSON-RPC. Das hat zwei Vorteile: Login geht über OAuth statt API-Key, und Generierungen werden auf das normale Web-Abo gebucht statt separat über Cloud-Credits.

`proxy.py` proxied `/api/*` zu `mcp.higgsfield.ai/*`, damit Browser-CORS nicht blockt. Die wichtigsten Tool-Calls sind in `hfUploadImage()` (→ `media_upload` + PUT + `media_confirm`), `hfGenerate()` (→ `generate_image`), `hfPollJob()` (→ `job_status`). Falls eine Modell-ID mit "Model not found" fehlschlägt: per `models_explore` in der Browser-Console die aktuell gültige ID prüfen.

## Datenexport

Settings → "Export als JSON" sichert Brand Kits, References und History. Für Phase-2-Migration relevant. Bilder werden als Base64 im JSON eingebettet, daher Datei wird groß.

## Verwandte Notizen

- [[Static Ad Test]] — initialer Workflow-Test mit den drei Varianten v1/v2
- [[feedback-immunifanten-ads-with-children]] — Kinder dürfen im Bild sein
- [[feedback-references-as-style-inspiration]] — Layout-Transfer mit Brand-Swap (am 2026-05-26 präzisiert)

## Stand

Stand 2026-05-28: Sidebar-Nomenklatur final — "Ads / Onlineshop / Amazon Listing". Subheading "Cleverbrands Image Tool". Referenzen jetzt auch im Onlineshop verfügbar, dort aber semantisch anders als bei Ads: reine Stil-Inspiration (Licht, Stimmung, Bildlook) statt Layout-Transfer — der Prompt sagt dem Modell explizit, Produkt/Logos/Text/Layout der Referenz nicht zu kopieren. `proxy.py` auf `ThreadingMixIn` umgestellt, weil der single-threaded `TCPServer` bei einem einzigen hängenden Upstream-Call alle weiteren Requests blockierte (auch Login-POSTs). **Aktivierung:** beim nächsten Mal `start.command` neu starten. Higgsfield-Login schlägt aktuell mit "Email or password is incorrect" fehl, auch beim Direkt-Login auf higgsfield.ai — Account-Problem, nicht Pablo-Problem (Details und Untersuchungs-Reihenfolge im [[05 Daily Notes/2026-05-28]]). End-to-End-Generierung für den Onlineshop steht weiterhin aus, weil dafür eine eingeloggte Higgsfield-Session nötig ist.

Stand 2026-05-27: Pablo deckt drei Bildtypen ab. Neben Ads gibt es einen eigenen **Onlineshop**-Bereich (vier Vorlagen, Format pro Vorlage automatisch, eigener Prompt-Builder `buildShopPrompt`) und einen **Amazon-Listing**-Bereich als sichtbarer Platzhalter mit geplanten Bildtypen. Navigation als drei separate Sidebar-Einträge, Pipeline (Upload → generate → poll → Download → Verbessern) bleibt geteilt. Onlineshop-UI und Alpine-Rendering getestet.

Stand 2026-05-26: Generate-Loop mit Layout-Transfer-Prompt funktioniert, Multi-Produkt-Auswahl (Dose + Inhalt) drin, Feedback-Refinement pro Karte drin, Polling resilient gegen 502er, Defaults auf gpt_image_2 / 1:1 / high / 4k.

Bekannte offene Punkte:
- Bilder landen weiterhin in `~/Downloads`, nicht im `output/` (File System Access API noch nicht eingebaut)
- Quality- und Resolution-Dropdowns sind reine UI ohne Wirkung auf den Generate-Call
- `sendImages`-Toggle tut nichts
- Token-Refresh-Pfad existiert nicht (Logout/Login wenn Token abläuft)
- Stop-Button setzt nur Flag, bricht laufende Polls nicht ab
