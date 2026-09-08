# Cykl skanu i opóźnienie o jeden cykl

## Kolejność wykonania

Silnik wykonuje wszystkie bloki schematu w JEDNYM, ustalonym porządku
na skan — nie w kolejności, w jakiej zostały narysowane, tylko w
porządku wynikającym z tego, KTO od KOGO zależy (kolejność
topologiczna): najpierw bloki źródłowe (wejścia fizyczne, znaczniki,
stałe), potem wszystko, co od nich zależy, w takiej kolejności, że gdy
blok jest liczony, wszystkie bloki podające mu dane na wejścia zostały
już policzone w TYM SAMYM skanie.

## Skąd bierze się z⁻¹

Dwa miejsca w tym programie celowo łamią powyższą zasadę "wejście już
policzone w tym skanie":

1. **Pętla sprzężenia zwrotnego przez blok stanowy** (przerzutnik SR/RS,
   timer, licznik, histereza analogowa...) — z definicji nie da się
   policzyć w kolejności topologicznej, bo blok zależy pośrednio od
   samego siebie. Rozwiązanie: blok stanowy w takiej pętli oddaje na
   wyjściu wartość ZE SWOJEGO WŁASNEGO STANU sprzed obliczenia, nie
   wynik obliczony na bieżąco — czyli wartość "z poprzedniego skanu".
2. **Znaczniki** (bity/rejestry wewnętrzne, M./MR./MW.) — zapis jest
   buforowany i zatwierdzany dopiero PO obliczeniu wszystkich bloków w
   danym skanie (patrz [Etykiety, znaczniki i bity
   urządzenia](help:concept_labels)). Blok czytający znacznik zapisany
   przez inny blok w TYM SAMYM skanie zawsze widzi wartość SPRZED tego
   zapisu.

W obu przypadkach mówi się o "opóźnieniu o jeden cykl skanu" albo,
językiem klasycznej automatyki, **z⁻¹** — wartość, którą coś widzi,
odpowiada stanowi sprzed jednego pełnego obiegu silnika, nie stanowi
"na żywo".

## Jak to czytać na schemacie

Nie ma dziś osobnego symbolu z⁻¹ na schemacie — opóźnienie wynika
wyłącznie z UŻYCIA bloku stanowego albo znacznika w danym miejscu, nie
z jakiegoś oddzielnego elementu. Jeśli logika zależy od tego, żeby dwie
wartości były widziane w TYM SAMYM skanie, unikaj przepuszczania jednej
z nich przez znacznik albo przez blok stanowy w pętli sprzężenia
zwrotnego.
