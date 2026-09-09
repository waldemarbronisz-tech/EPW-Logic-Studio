<!-- TODO: translate to English (feat/help-system §3.4) -->

# Jak utworzyć makro i użyć go w kilku polach

1. **Zaznacz fragment schematu**, który chcesz zamknąć w makro.
2. **Utwórz makro z zaznaczenia** (menu kontekstowe zaznaczenia) i podaj
   nazwę. Piny graniczne powstają automatycznie z przewodów przecinających
   granicę zaznaczenia — patrz [Makrobloki i parametry](help:concept_macros)
   dla pełnego wyjaśnienia, skąd się biorą.
3. **Wstaw kolejne instancje** tego samego makra z biblioteki bloków (w
   sekcji makr) w innych polach schematu — każda instancja jest
   niezależną kopią wizualną tej samej definicji.
4. **Powiąż właściwość z parametrem**, jeśli różne pola mają mieć różne
   wartości (np. inny czas opóźnienia) — bez tego wszystkie instancje
   dzielą jedną wartość zapisaną w definicji.
5. **Edytuj definicję**, żeby zmienić logikę wewnątrz makra dla
   WSZYSTKICH jego instancji naraz — wejdź w edycję makra (podwójne
   kliknięcie na instancję albo z drzewa nawigacji) i wprowadź zmianę
   raz.
6. **Wyeksportuj/zaimportuj makro** jako plik `.epwmacro`, jeśli chcesz
   użyć go w innym projekcie.

Zobacz też pełne wyjaśnienie pojęć w [Makrobloki i
parametry](help:concept_macros).
