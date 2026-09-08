# Jakość sygnału analogowego

Blok [QUALITY](help:block:analog.quality) i wyjście `Quality` bloku
[AI](help:block:input.ai) nadzorują, czy pomiarowi analogowemu można w
ogóle ufać, zanim logika bezpieczeństwa zacznie na nim polegać.

## Do czego służy wyjście Quality

`Quality`/`Good` jest prawdziwe tylko wtedy, gdy odczyt jest LICZBĄ (nie
NaN/Inf), mieści się w zakresie pomiarowym, nie zmienia się szybciej niż
dopuszczalna szybkość zmiany i nie jest "zamrożony" (patrz Stuck niżej).
To wyjście jest oznaczone jako **istotne dla bezpieczeństwa** — logika
sterująca krytycznymi wyjściami powinna sprawdzać je, zanim zaufa
wartości pomiarowej, a nie tylko samej wartości.

## Dlaczego Stuck Tolerance MUSI być większa od zera na realnym torze pomiarowym

Detekcja "zamrożenia" sygnału (Stuck) polega na porównaniu dwóch
kolejnych odczytów. Przy domyślnym `Stuck Tolerance = 0.0` (dokładna
równość) sygnał z PRAWDZIWEGO przetwornika analogowo-cyfrowego
praktycznie nigdy nie zostanie uznany za zamrożony — szum ostatniego
bitu przetwornika sprawia, że dwie kolejne próbki niemal nigdy nie są
identyczne co do bitu, nawet gdy fizycznie mierzona wielkość się nie
zmienia. Efekt: detekcja zamrożenia realnie NIE DZIAŁA, dopóki `Stuck
Tolerance` nie zostanie ustawiona powyżej zera. Punkt startowy: około
0,1% zakresu pomiarowego — na tyle ciasno, żeby złapać prawdziwie
zamrożony sygnał, na tyle luźno, żeby normalny szum przetwornika nie
psuł detekcji co skan.

## Co robi Max Hold (ms)

Gdy `Quality` jest fałszywe, blok AI trzyma OSTATNIĄ dobrą wartość na
wyjściu `Value` (fail-safe: logika dalej działa na wiarygodnych, choć
nieco nieaktualnych danych, zamiast na śmieciach). Bez limitu czasowego
ta "ostatnia dobra wartość" mogłaby być trzymana godzinami albo dniami,
jeśli nic nie obserwuje `Quality`. `Max Hold (ms)` ogranicza to w
czasie — po jego przekroczeniu `Hold Expired` (też istotne dla
bezpieczeństwa) staje się prawdziwe, a `Value` przełącza się na wartość
wybraną we właściwości `Hold Timeout Value` (zero, ostatnia dobra
wartość, albo dolna granica zakresu). `Max Hold (ms) = 0` oznacza brak
limitu — zachowanie identyczne jak przed wprowadzeniem tej właściwości.
