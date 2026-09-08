<!-- TODO: translate to English (feat/help-system §3.4) -->

# Jak przenieść sygnał w inne miejsce schematu

Bez rysowania jednego, długiego przewodu przez cały schemat — patrz
najpierw [Etykiety, znaczniki i bity urządzenia](help:concept_labels)
dla pełnego porównania. Poniżej sposób, który **działa dzisiaj**:

## Przez znacznik (bit/rejestr wewnętrzny)

1. W miejscu, gdzie sygnał POWSTAJE, dodaj blok "Wyjście bitowe (wewn.)"
   (albo "Wyjście rejestru (wewn.)" dla wartości analogowej) i podłącz
   do niego przewód z wynikiem.
2. Kliknij właściwość `Bit` tego bloku i wybierz/utwórz nazwę
   wewnętrznego sygnału (np. "M_Gotowosc").
3. W miejscu, gdzie sygnał jest POTRZEBNY — nawet daleko na schemacie,
   albo w ogóle w innym polu ekranu — dodaj blok "Wejście bitowe
   (wewn.)" (albo "Wejście rejestru (wewn.)"), i w jego właściwości
   `Bit` wybierz TĘ SAMĄ nazwę.
4. Gotowe — obie kopie czytają/piszą ten sam wewnętrzny sygnał, bez
   żadnego przewodu między nimi na schemacie.

Pamiętaj o możliwym opóźnieniu o jeden cykl skanu między zapisem a
odczytem tego samego znacznika w tym samym skanie — patrz [Cykl skanu i
opóźnienie o jeden cykl](help:concept_scan_cycle).

## Etykiety przewodów — jeszcze nie w pełni

Wolny koniec przewodu z etykietą (patrz [Zaślepka wejścia, wolny koniec
przewodu, etykieta](help:concept_stubs)) dokumentuje dziś tylko, dokąd
przewód miał prowadzić — nie przenosi jeszcze sygnału. Gdy scalanie
etykiet w węzły sieci zostanie ukończone, ten poradnik zostanie
zaktualizowany o odpowiedni, krótszy sposób.
