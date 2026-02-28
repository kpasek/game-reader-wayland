import tkinter as tk
from tkinter import scrolledtext, font
from app.ctk_widgets import CTkToplevel


class HelpWindow(CTkToplevel):
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

        from app.matcher import MATCH_MODE_FULL, MATCH_MODE_STARTS, MATCH_MODE_PARTIAL
        content = [
            ("JAK TO DZIAŁA?\n", 'h1'),
            ("Aplikacja wykonuje cykliczne zrzuty zdefiniowanego obszaru ekranu, przetwarza je przez OCR (rozpoznawanie tekstu) i porównuje z załadowanym plikiem napisów. Gdy znajdzie dopasowanie, odtwarza przypisany plik audio.\n",
             'normal'),

            ("UWAGA DLA WAYLAND\n", 'h1'),
            ("Na systemach korzystających z Wayland aplikacja domyślnie wykonuje zrzuty tylko z wybranego okna (aplikacji), a nie z całego ekranu. Dotyczy to również testowania ustawień oraz narzędzia wyboru koloru z ekranu.\n", 'normal'),
            ("Jeżeli przed naciśnięciem 'Start' nie wybrano okna, zostaniesz poproszony o wskazanie okna, z którego mają być robione zrzuty — wybierz aplikację, której zawartość ma być monitorowana.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("Aby przetestować ustawienia lub pobrać kolor z innego okna, najpierw wybierz je w panelu wyboru okna, a dopiero potem uruchom monitorowanie.\n", 'normal'),

            ("PARAMETRY OCR\n", 'h1'),


            ("2. Częstotliwość skanowania\n", 'h2'),
            ("Czas w sekundach między kolejnymi zrzutami ekranu.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("0.5s to standard. Jeśli gra ma bardzo szybkie dialogi, zmniejsz do 0.3s.\n",
             'normal'),

            ("3. Czułość jasności\n", 'h2'),
            ("Próg jasności napisów do wykrycia.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("Ustaw 255 jeżeli napisy w grze są białe. Zmniejsz proporcjonalnie do jasności napisów. Szare: 160-220 itd.\n",
             'normal'),

            ("4. Próg podobieństwa\n", 'h2'),
            ("Wykryta różnica pomiędzy zrobionymi zrzutami do uruchomienia OCR.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("5-cio % próg oznacza, że aktualny zrzut musi się różnić min o 5% od wcześniejszego, aby uruchomić OCR.\n",
             'normal'),
            ("Znacząco wpływa na wydajność aplikacji.\n", 'normal'),

            ("5. Podbicie kontrastu\n", 'h2'),
            ("Kontrast dla zrzutu jest o podaną wartość.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("0 oznacza brak zmian. -1 zmniejszenie kontrastu a mocne zwiększenie kontrastu.\n Ustawienie to jest wywoływane przez wykryciem napisów (pkt 5).\n",
             'normal'),

            ("6. Tolerancja koloru napisów\n", 'h2'),
            ("Próg tolerancji koloru przy przy usuwaniu tła.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("1 oznacza Brak tolerancji. Czyli tylko wybrany kolor nie zostanie usunięty.\n Ustawienie około 10 oznacza delikatną tolerancję i pomaga nie wycinać napisów wraz z tłem.\n",
             'normal'),

            ("7. Pogrubienie napisów\n", 'h2'),
            ("Ilość pixeli które zostaną dodane do napisów.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("0 oznacza że napisy nie zostaną pogrubione. Przy niższych rozdzielczościach może być wymagane pogrubienie.\n",
             'normal'),

            ("8. Powiększenie (Magnification)\n", 'h2'),
            ("Wartość określająca powiększenie obrazu przed przekazaniem do OCR. Wyświetlana w procentach.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("100% to rozmiar oryginalny. Jeśli napisy są małe (np. na Steam Decku lub w wysokich rozdzielczościach), zwiększenie do 150-200% znacząco poprawia skuteczność rozpoznawania.\n",
             'normal'),

            ("9. DEBUG\n", 'h2'),
            ("Pokazuje obszar na którym zostały wykryte napisy.\n", 'normal'),
            ("• Przykład: ", 'bold'),
            ("Przydaje się do poprawnego ustawienia kontrastu oraz czułości jasności. To ustawienie nie jest zapamiętywane i po restarcie aplikacji jest zerowane.\n",
             'normal'),

            ("USTAWIENIA DIALOGÓW\n", 'h1'),

            ("1. Tryb dopasowania\n", 'h2'),
            (f"• {MATCH_MODE_FULL}: ", 'bold'),
            ("Wymaga, aby OCR rozpoznał całą linię.\n", 'normal'),
            (f"• {MATCH_MODE_STARTS}: ", 'bold'),
            ("Wystarczy, że rozpoznany tekst zaczyna się w linii napisów. Przydatne, gdy gra pokazuje napisy w częściach.\n",
             'normal'),
            (f"• {MATCH_MODE_PARTIAL}: ", 'bold'),
            ("Wystarczy, że rozpoznany tekst zaczyna się lub zawiera w linii napisów. Przydatne, gdy gra pokazuje napisy w częściach.\n",
             'normal'),

            ("2. Progi Dopasowania\n", 'h2'),
            ("• Min score (Krótkie): Minimalny procent zgodności tekstu z OCR względem linii w pliku dla linii krótszych niż 6 znaków.\n", 'normal'),
            ("• Krótkie/Długie: ", 'bold'),
            ("Min score (Długie) wymagają niższej precyzji (np. 70%), długie zdania wybaczają więcej błędów OCR.\n", 'normal'),

            ("3. Maksymalna różnica długości\n", 'h2'),
            ("Maksymalna dopuszczalna różnica długości między tekstem OCR a dopasowywaną linią. Wartość 0.25 oznacza tolerancję 25%.\n", 'normal'),

            ("4. Min długość dla Partial Mode i Starts With\n", 'h2'),
            ("Jeśli tekst jest dłuższy niż X znaków (domyślnie 25), system jednorazowo wyłączy tryb 'Partial' lub 'Starts With'.\n", 'normal'),

            ("4. Ignoruj krótsze niż\n", 'h2'),
            ("Ignoruje odczytany text ORC krótszy niż X znaków. Pomaga w eliminowaniu szumu OCR.\n", 'normal'),

            ("ZARZĄDZANIE OBSZARAMI I OPTYMALIZACJA\n", 'h1'),

            ("1. Konfiguracja Per-Obszar\n", 'h2'),
            ("Wszystkie parametry obrazu (powiększenie, jasność, kontrast, tolerancja) są teraz przypisane oddzielnie do każdego zdefiniowanego obszaru. Pozwala to na jednoczesne czytanie napisów o różnej charakterystyce z różnych części ekranu.\n", 'normal'),

            ("2. Kreator Optymalizacji\n", 'h2'),
            ("W oknie 'Zarządzaj Obszarami' w menu kontekstowym listy obszarów (Prawy Przycisk Myszy -> Kreator Optymalizacji) dostępny jest kreator. Należy dodać zrzuty ekranu z widocznym tekstem, a system automatycznie dobierze parametry OCR oraz dopasuje ramkę z marginesem 2%.\n", 'normal'),
            
            ("3. Zmiana nazwy\n", 'h2'),
            ("Możesz zmienić nazwę obszaru dwukrotnie klikając na niego na liście.\n", 'normal'),

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

        txt.configure(state=tk.DISABLED)
