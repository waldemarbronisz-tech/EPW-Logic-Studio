# Pierwszy schemat: wejście, bramka, wyjście

Najkrótsza droga do zobaczenia działającej logiki na ekranie.

1. **Dodaj wejście cyfrowe.** Znajdź [DI](help:block:input.di) w
   bibliotece bloków (kategoria "Wejścia / Wyjścia") i przeciągnij je na
   kanwę.
2. **Dodaj bramkę logiczną.** Przeciągnij np. [NOT](help:block:logic.not)
   z kategorii "Bramki logiczne" obok wejścia.
3. **Dodaj wyjście cyfrowe.** Przeciągnij [DO](help:block:output.do).
4. **Połącz je przewodami.** Kliknij i przeciągnij od pinu wyjściowego
   jednego bloku do pinu wejściowego drugiego: DI → NOT → DO.
5. **Ustaw adresy.** Zaznacz DI, w panelu właściwości ustaw jego
   `Address` (np. "ELA01.DI01"); analogicznie dla DO.
6. **Skompiluj** (F5) — sprawdź, że nie ma błędów.
7. **Uruchom symulację** i przełącz stan wejścia — zobacz, jak zmienia
   się wyjście. Szczegóły w [Jak uruchomić symulację i sprawdzić
   działanie logiki](help:guide_simulation).

Gdy nie wiesz, co robi jakiś blok po drodze — zaznacz go i naciśnij
**F1**.
