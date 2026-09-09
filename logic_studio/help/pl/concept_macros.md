# Makrobloki i parametry

Makroblok pozwala zamknąć fragment schematu w jeden, wielokrotnie
używalny blok — przydatne dla powtarzalnych układów (np. "sekwencja
startowa silnika"), które inaczej trzeba by kopiować i wklejać osobno w
każdym miejscu.

## Jak zamknąć fragment w makro

Zaznacz bloki, które mają wejść w skład makra, i użyj polecenia
utworzenia makra z zaznaczenia (menu kontekstowe zaznaczenia). Powstaje
nowa definicja makra oraz jego pierwsza instancja w miejscu starego
zaznaczenia.

## Skąd biorą się piny graniczne

**To jest najczęstsze nieporozumienie**: piny na brzegu makrobloku NIE
są czymś, co trzeba ręcznie dodać. Powstają automatycznie z każdego
przewodu, który w momencie tworzenia makra PRZECINAŁ granicę
zaznaczenia — jeden koniec wewnątrz zaznaczonych bloków, drugi na
zewnątrz. Każdy taki przewód staje się jednym pinem granicznym makra, z
kierunkiem wynikającym z tego, w którą stronę sygnał płynął. Jeśli po
utworzeniu makra okaże się, że brakuje pinu (bo np. zapomniałeś podłączyć
coś przed zaznaczeniem) albo jest zbędny — piny graniczne można edytować
później, bez konieczności tworzenia makra od nowa.

## Jak powiązać nastawę z parametrem

Parametr makra pozwala, żeby każda INSTANCJA tego samego makra miała
własną wartość jakiejś właściwości (np. czas opóźnienia inny dla
każdego pola), zamiast jednej wspólnej dla wszystkich kopii. Właściwość
bloku WEWNĄTRZ definicji makra wiąże się z parametrem makra — od tej
pory każda instancja pyta o swoją własną wartość tego parametru, zamiast
dziedziczyć wartość zapisaną w definicji.

Zobacz też: [Jak utworzyć makro i użyć go w kilku
polach](help:guide_macros).
