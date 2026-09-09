<!-- TODO: translate to English (feat/help-system §3.4) -->

# Etykiety, znaczniki i bity urządzenia

Trzy różne sposoby, żeby wartość policzona w jednym miejscu schematu
trafiła w inne, bez rysowania jednego, długiego przewodu przez cały
schemat. Łatwo je pomylić — poniżej reguła wyboru i to, co je realnie
różni.

| Sposób | Co to jest | Opóźnienie o cykl skanu |
|---|---|---|
| **Bit urządzenia** (DI/DO/AI/AO) | Fizyczny sygnał na konkretnym module ELA/ADA | Nie dotyczy — czytane/pisane bezpośrednio z/do sprzętu |
| **Znacznik** (bit/rejestr wewnętrzny, M./MR./MW.) | Pamięć wewnętrzna projektu, niezwiązana z żadnym fizycznym terminalem | **Tak, może wystąpić** |
| **Etykieta przewodu** | Tekstowa nazwa nadana wolnemu końcowi przewodu | Docelowo: nie — patrz zastrzeżenie niżej |

## Znacznik: dlaczego może dać opóźnienie o cykl

Zapis do znacznika (blok "Wyjście bitowe (wewn.)"/"Wyjście rejestru
(wewn.)") nie trafia do pamięci od razu — silnik buforuje wszystkie
zapisy z danego skanu i zatwierdza je dopiero PO obliczeniu wszystkich
bloków w tym skanie. Jeśli więc blok A zapisuje znacznik, a blok B go w
tym samym skanie odczytuje, blok B zobaczy wartość SPRZED zapisu bloku
A — dopiero w NASTĘPNYM skanie zobaczy nową wartość. To jest właśnie
opóźnienie z⁻¹, opisane osobno w [Cykl skanu i opóźnienie o jeden
cykl](help:concept_scan_cycle). Kolejność bloków na schemacie (czy A
jest "przed", czy "za" B) nie ma tu znaczenia — liczy się wyłącznie to,
że zapis i odczyt są rozdzielone przez granicę skanu.

## Etykieta przewodu: stan obecny

Przewód może dziś mieć jeden koniec **wolny** (niepodłączony do żadnego
pinu) i nosić tekstową etykietę — to zapobiega ostrzeżeniu kompilatora
"Niedokończony przewód" i dokumentuje, do czego ten koniec miał
prowadzić. **Scalanie dwóch przewodów o tej samej etykiecie w jeden
węzeł sieci (żeby etykieta faktycznie PRZENOSIŁA sygnał, bez rysowania
przewodu) jest planowaną, jeszcze niezaimplementowaną częścią tego
mechanizmu** — dziś etykieta jest metadaną dokumentacyjną, nie
działającym sposobem przenoszenia sygnału. Dopóki to nie powstanie,
jedynym DZIAŁAJĄCYM sposobem przeniesienia sygnału bez rysowania
przewodu przez cały schemat jest znacznik (patrz [Jak przenieść sygnał
w inne miejsce schematu](help:guide_move_signal)).

## Reguła wyboru

- Sygnał fizyczny (prawdziwy wejście/wyjście na module) → bit
  urządzenia, zawsze.
- Sygnał pomocniczy, potrzebny w kilku miejscach schematu, gdzie
  opóźnienie o jeden cykl jest akceptowalne (a zwykle jest — dotyczy to
  tylko relacji między dwoma konkretnymi blokami w tym samym skanie) →
  znacznik.
- Zaślepka na przewodzie, który dopiero zamierzasz podłączyć → wolny
  koniec bez etykiety (patrz [Zaślepka wejścia, wolny koniec przewodu,
  etykieta](help:concept_stubs) — to TRZECIA, osobna rzecz, mimo że
  wygląda podobnie).
