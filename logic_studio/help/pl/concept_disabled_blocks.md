# Bloki wyłączone i wymuszenia

## Co oznacza wyłączony blok

Blok można wyłączyć (z menu zaznaczenia albo skrótem, jeśli
przypisany) — wyłączony blok jest pomijany przy walidacji projektu, tak
jakby chwilowo nie istniał logicznie, choć wciąż widoczny na schemacie.
Przydatne przy tymczasowym wyłączaniu fragmentu logiki bez usuwania go
i bez zrywania przewodów, które trzeba by potem odtwarzać ręcznie.

Wyłączony blok jest oznaczany na kanwie WYRAŹNIE (inny wygląd niż blok
aktywny) — celowo rzucająco się w oczy, żeby nikt nie przeoczył, że
część logiki na schemacie jest nieaktywna.

## Co robi flaga w eksporcie

Stan wyłączenia jest częścią eksportowanego runtime'u — EPW-OS wie, że
dany blok ma być pominięty, dokładnie tak samo jak w edytorze i
symulacji. Wyłączenie bloku w Logic Studio nie jest więc czysto
kosmetyczną operacją na schemacie — ma realny wpływ na to, co
ostatecznie działa na obiekcie.

## Wymuszenia (Force)

Podczas symulacji wejścia/wyjścia fizyczne (DI/DO) i wewnętrzne bity
mogą mieć wymuszoną wartość (FORCE TRUE/FORCE FALSE) niezależnie od
tego, co faktycznie podaje symulowany sprzęt albo obliczona logika —
ustawiane w panelu właściwości zaznaczonego bloku podczas symulacji.
Wymuszenie jest stanem WYŁĄCZNIE runtime'owym: nigdy nie jest zapisywane
w pliku projektu ani w eksportowanym runtime, więc wymuszenie ustawione
podczas testów na stanowisku nie może przypadkiem "pojechać" razem z
projektem na obiekt i wymusić czegoś na prawdziwym sprzęcie.
