import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, font

class HelpWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Pomoc i Instrukcja")
        self.geometry("700x750")
        default_font = font.nametofont("TkDefaultFont")
        base_font_family = default_font.actual()["family"]
        txt = scrolledtext.ScrolledText(self, wrap=tk.WORD, padx=15, pady=15, font=(base_font_family, 10))
        txt.pack(fill=tk.BOTH, expand=True)

        # Konfiguracja tagów formatowania tekstu
        txt.tag_config('h1', font=(base_font_family, 13, 'bold'), spacing1=20, spacing3=10, foreground="#222222")
        txt.tag_config('h2', font=(base_font_family, 11, 'bold'), spacing1=10, spacing3=5)
        txt.tag_config('bold', font=(base_font_family, 10, 'bold'))
        txt.tag_config('normal', spacing3=2)
        txt.tag_config('italic', font=(base_font_family, 10, 'italic'))

        content = [
            ("JAK TO DZIAŁA?\n", 'h1'),
            ("Aplikacja wykonuje cykliczne zrzuty zdefiniowanego obszaru ekranu, przetwarza je przez OCR (rozpoznawanie tekstu) i porównuje z załadowanym plikiem napisów. Gdy znajdzie dopasowanie, odtwarza przypisany plik audio.\n",
             'normal'),

            ("PARAMETRY OCR\n", 'h1'),

            ("1. Skala OCR (0.1 - 1.0)\n", 'h2'),
            ("Określa, jak bardzo obraz jest skalowany przed odczytem. OCR (Tesseract) działa najlepiej, gdy litery mają określoną wysokość w pikselach.\n",
             'normal'),
            ("• Przykład: ", 'bold'),
            ("Dla ekranu 4K (3840x2160) ustaw 0.3 - 0.4. Dla FullHD (1920x1080) ustaw 0.9 - 1.0.\n", 'normal'),

            ("2. Czułość pustego obrazu (Empty Threshold)\n", 'h2'),
            ("Zapobiega uruchamianiu OCR na pustych/czarnych klatkach, sprawdzając zróżnicowanie kolorów.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("Ustawienie 0.15 ignoruje czarne ekrany ładowania. Ustawienie 0.0 wyłącza tę funkcję.\n",
             'normal'),

            ("3. Próg gęstości pikseli (Density Threshold)\n", 'h2'),
            ("Filtruje obrazy zawierające szum (np. deszcz, ziarno), które mają za mało 'czarnych pikseli' (tekstu), aby warto było je czytać.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("Domyślnie 0.015. Zwiększ (np. do 0.03), jeśli OCR próbuje czytać tło gry jako tekst.\n", 'normal'),

            ("4. Częstotliwość skanowania\n", 'h2'),
            ("Czas w sekundach między kolejnymi zrzutami ekranu.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("0.5s to standard. Jeśli gra ma bardzo szybkie dialogi, zmniejsz do 0.3s.\n",
             'normal'),

            ("5. Czułość jasności\n", 'h2'),
            ("Próg jasności napisów do wykrycia.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("Ustaw 255 jeżeli napisy w grze są białe. Zmniejsz proporcjonalnie do jasności napisów. Szare: 160-220 itd.\n",
             'normal'),

            ("6. Próg podobieństwa\n", 'h2'),
            ("Wykryta różnica pomiędzy zrobionymi zrzutami do uruchomienia OCR.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("5-cio % próg oznacza, że aktualny zrzut musi się różnić min o 5% od wcześniejszego, aby uruchomić OCR.\n",
             'normal'),
            ("Znacząco wpływa na wydajność aplikacji.\n", 'normal'),

            ("7. Podbicie kontrastu\n", 'h2'),
            ("Kontrast dla zrzutu jest o podaną wartość.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("0 oznacza brak zmian. -1 zmniejszenie kontrastu a mocne zwiększenie kontrastu.\n Ustawienie to jest wywoływane przez wykryciem napisów (pkt 5).\n",
             'normal'),

            ("8. DEBUG\n", 'h2'),
            ("Pokazuje obszar na którym zostały wykryte napisy.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("Przydaje się do poprawnego ustawienia kontrastu oraz czułości jasności. To ustawienie nie jest zapamiętywane i po restarcie aplikacji jest zerowane.\n",
             'normal'),

            ("USTAWIENIA DIALOGÓW\n", 'h1'),

            ("1. Tryb dopasowania\n", 'h2'),
            ("• Full Lines: ", 'bold'),
            ("Wymaga, aby OCR rozpoznał całą linię.\n", 'normal'),
            ("• Partial Lines: ", 'bold'),
            ("Wystarczy, że rozpoznany tekst zaczyna się w linii napisów. Przydatne, gdy gra pokazuje napisy w częściach.\n",
             'normal'),

            ("2. Progi Dopasowania\n", 'h2'),
            ("• Min score (Krótkie): Minimalny procent zgodności tekstu z OCR względem linii w pliku dla linii krótszych niż 6 znaków.\n", 'normal'),
            ("• Krótkie/Długie: ", 'bold'),
            ("Min score (Długie) wymagają niższej precyzji (np. 70%), długie zdania wybaczają więcej błędów OCR.\n", 'normal'),

            ("3. Maksymalna różnica długości\n", 'h2'),
            ("Maksymalna dopuszczalna różnica długości między tekstem OCR a dopasowywaną linią. Wartość 0.25 oznacza tolerancję 25%.\n", 'normal'),

            ("4. Min długość dla Partial Mode\n", 'h2'),
            ("Jeśli tekst jest dłuższy niż X znaków (domyślnie 25), system jednorazowo wyłączy tryb 'Partial Lines'.\n", 'normal'),

            ("4. Ignoruj krótsze niż\n", 'h2'),
            ("Ignoruje odczytany text ORC krótszy niż X znaków. Pomaga w eliminowaniu szumu OCR.\n", 'normal'),

            ("AUDIO (KOLEJKOWANIE)\n", 'h1'),

            ("1. Przyspieszanie\n", 'h2'),
            ("Gdy lektor nie nadąża czytać i w kolejce zbierają się nagrania, system automatycznie zwiększa prędkość odtwarzania kolejnych plików (np. o 20% lub 30%), aby zredukować opóźnienie (lag).\n", 'normal'),

            ("FILTRACJA\n", 'h1'),

            ("1. Regex \n", 'h2'),
            ("Pozwala usuwać imiona postaci z początku linii, aby OCR porównywał tylko dialog.\n", 'normal'),

            ("2. Usuwaj imiona (smart) \n", 'h2'),
            ("Aplikacja sama próbuje znaleźć i usunąć imię z dialogu.\n", 'normal'),

            ("3. Zapisz logi do pliku \n", 'h2'),
            ("Zapisuje logi do pliku w miejscu gdzie aplikacja się znajduje.\n", 'normal'),
        ]

        for item in content:
            if len(item) == 2:
                text, tag = item
                txt.insert(tk.END, text, tag)
            else:
                txt.insert(tk.END, item[0])  # Fallback

        txt.config(state=tk.DISABLED)
