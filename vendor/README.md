# Vendor

Katalog przeznaczony na zewnętrzne zależności wymagane do zbudowania i działania aplikacji (szczególnie w środowisku Steam Deck).

## Tesseract-OCR dla Steam Deck (SteamOS)
Na Steam Deck system jest w trybie read-only, przez co paczki instalowane przez \`pacman\` często znikają po aktualizacji systemu, albo ingerencja wiąże się ze złamaniem gwarancji.
Rozwiązaniem jest zapakowanie aplikacji \`tesseract\` wraz z jej bibliotekami i językami w "przenośny" format.

### Budowanie (Linux)
Aby zbudować przenośną paczkę:
\`\`\`bash
./vendor/build_tesseract.sh
\`\`\`
*(Wymaga działającego silnika kontenerów \`podman\` lub wpisania ręcznie \`docker\` wewnątrz skryptu).*

Po poprawnym wykonaniu skryptu, powstanie folder \`vendor/tesseract_deck\` oraz archiwum \`vendor/tesseract_deck.tar.xz\`.
W aplikacji ścieżka do wykonywalnego binary powinna wskazywać na skrypt opakowujący, np.: \`vendor/tesseract_deck/tesseract\`.
