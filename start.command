#!/bin/bash
# Pablo (Cleverbrands Ad Generator) - lokaler Start (Static + CORS-Proxy zu Higgsfield).
# Doppelklick startet den Server und oeffnet die App im Browser.
# Server stoppen: dieses Terminal-Fenster schliessen oder Ctrl+C.

cd "$(dirname "$0")"

PORT=8000
URL="http://localhost:${PORT}/ad-generator.html"

if lsof -i :${PORT} -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${PORT} ist schon belegt. Oeffne nur den Browser..."
  open "${URL}"
  echo ""
  echo "Falls die App nicht funktioniert: anderes Terminal mit der App schliessen und nochmal versuchen."
  echo "Druecke Enter zum Schliessen."
  read
  exit 0
fi

echo "==================================="
echo " Pablo startet"
echo "==================================="
echo ""
echo " URL: ${URL}"
echo " Proxy: /api/* -> https://mcp.higgsfield.ai/*"
echo ""
echo " Server stoppen: dieses Fenster schliessen oder Ctrl+C"
echo "==================================="
echo ""

(sleep 1 && open "${URL}") &

if command -v python3 >/dev/null 2>&1; then
  python3 proxy.py ${PORT}
else
  echo "FEHLER: python3 nicht gefunden. macOS sollte python3 vorinstalliert haben."
  read
  exit 1
fi
